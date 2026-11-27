import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import queue_md as md, static_reference, run_store
from tools.cli import main


def setup(base):
    source=base/'source'; source.mkdir()
    html='<!doctype html><html lang="en"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body><h1>Static reference</h1></body></html>'
    (source/'index.html').write_text(html); (source/'.env').write_text('not copied')
    work=source/'.work'; work.mkdir(); site=work/'staging'/'candidate'; site.mkdir(parents=True); (site/'index.html').write_text(html)
    data=md.parse(md.template(source)); data['pages']=[dict(zip(md.TABLES['pages'],['home','Home','/','index.html','confirmed','true','built','reviewed','']))]
    for row in data['meta']:
        if row['key']=='discovery_status': row['value']='confirmed'
        if row['key']=='confirmation_reason': row['value']='reviewed'
    proposal=work/'proposal.md'; proposal.write_text(md.render(data)); md.commit(source,proposal,'absent','initial')
    selection=work/'selection.json'; selection.write_text(json.dumps(['index.html']))
    ref=static_reference.materialize(source,selection,work/'static-references'/'one')
    return source,work,site,ref


class StaticReferenceAuditTests(unittest.TestCase):
    def test_explicit_risk_acknowledgment_before_server_or_browser(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,work,site,ref=setup(Path(t).absolute())
            with patch('tools.lifecycle.serve_site') as server:
                with self.assertRaisesRegex(ValueError,'подтвердить риск'):
                    static_reference.audit(source,site,ref['record'],ref['sha256'],False)
                server.assert_not_called()
            with self.assertRaisesRegex(ValueError,'отдельными'):
                static_reference.audit(source,Path(ref['reference']),ref['record'],ref['sha256'],True)
            (source/'index.html').write_text('stale')
            with self.assertRaisesRegex(ValueError,'устарела'):
                static_reference.audit(source,site,ref['record'],ref['sha256'],True)

    def test_drift_or_binding_failure_after_audit_is_reported_unknown(self):
        for fault in ('drift','binding'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(dir='.') as t:
                source,work,site,ref=setup(Path(t).absolute()); folder=work/'audits-md'/'synthetic'; output=io.StringIO()
                def fake_audit(*args):
                    folder.mkdir(parents=True); (folder/'summary.json').write_text('partial diagnostic')
                    if fault=='drift': (Path(ref['reference'])/'index.html').write_text('changed during audit')
                    return {'operation':'applied','artifact_directory':str(folder),'warnings':[]}
                with patch('tools.audit_markdown.audit',side_effect=fake_audit), contextlib.redirect_stdout(output):
                    if fault=='binding':
                        with patch('tools.static_reference.md._write_new',side_effect=OSError('disk full')):
                            code=main(['browser-audit-static-md','--source',str(source),'--site',str(site),
                                       '--reference-record',ref['record'],'--reference-sha256',ref['sha256'],
                                       '--acknowledge-browser-code','--json'])
                    else:
                        code=main(['browser-audit-static-md','--source',str(source),'--site',str(site),
                                   '--reference-record',ref['record'],'--reference-sha256',ref['sha256'],
                                   '--acknowledge-browser-code','--json'])
                self.assertEqual(code,4); self.assertEqual(json.loads(output.getvalue())['operation'],'unknown')
                self.assertEqual((folder/'summary.json').read_text(),'partial diagnostic')
                self.assertFalse((folder/'static-reference-binding.json').exists())

    @unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS')=='1','browser not requested')
    def test_real_browser_static_copy_is_linked_but_unverified(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,work,site,ref=setup(Path(t).absolute())
            result=static_reference.audit(source,site,ref['record'],ref['sha256'],True)
            self.assertFalse(result['eligible']); self.assertEqual(result['coverage']['executed'],3)
            self.assertFalse(result['static_reference_binding']['isolated'])
            folder=Path(result['artifact_directory']); sha=hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest()
            sealed=run_store.seal(source,site,folder,sha)
            self.assertIsNotNone(sealed['record']['static_reference_binding'])
            self.assertFalse(sealed['record']['publication_eligible'])
            self.assertEqual(run_store.inspect(source,site,sealed['path'],sealed['sha256'])['freshness'],'current')
            (Path(ref['reference'])/'index.html').write_text('tampered')
            state=run_store.inspect(source,site,sealed['path'],sealed['sha256'])
            self.assertEqual(state['freshness'],'stale'); self.assertIn('artifacts',state['changed'])
            with self.assertRaisesRegex(ValueError,'устарела'): run_store.seal(source,site,folder,sha)

if __name__=='__main__': unittest.main()
