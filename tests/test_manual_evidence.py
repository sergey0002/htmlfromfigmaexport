import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import queue_md as md, manual_evidence, readiness
from tools.cli import main
from tools.manual_evidence import create, inspect


def fixture(base):
    src=base/'source'; src.mkdir(); (src/'index.html').write_text('source')
    work=src/'.work'; work.mkdir(); site=work/'stage'/'run'; site.mkdir(parents=True)
    (site/'index.html').write_text('candidate')
    proposal=work/'p.md'; md.write_template(src,proposal); md.commit(src,proposal,'absent','initial')
    return src,site,work


class ManualEvidenceTests(unittest.TestCase):
    def test_attestation_is_not_eligibility_and_change_makes_it_stale(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src=Path(t).absolute()/'source'; src.mkdir(); (src/'index.html').write_text('source')
            work=src/'.work'; work.mkdir(); site=work/'stage'/'run'; site.mkdir(parents=True); (site/'index.html').write_text('candidate')
            proposal=work/'p.md'; md.write_template(src,proposal); md.commit(src,proposal,'absent','initial')
            output=work/'manual-attestations'/'one.json'
            result=create(src,site,output,'Reviewer','home, 390x844, initial','Viewed and tabbed','pass','No mobile device')
            self.assertFalse(result['attestation']['verified_identity']); self.assertFalse(result['attestation']['publication_eligible'])
            current=inspect(src,site,output,result['sha256']); self.assertEqual(current['freshness'],'current')
            (site/'index.html').write_text('different')
            self.assertEqual(inspect(src,site,output,result['sha256'])['freshness'],'stale')
            output.write_text('{}')
            with self.assertRaisesRegex(ValueError,'изменена'): inspect(src,site,output,result['sha256'])

    def test_claim_schema_rejects_forged_identity_and_other_invalid_fields(self):
        changes=[{'verified_identity':True},{'publication_eligible':True},{'reference_provenance':'trusted'},
                 {'outcome':'great'},{'version':True},{'scope':''},{'queue_sha256':'invalid'},{'extra':'unknown'}]
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,work=fixture(Path(t).absolute()); path=work/'manual-attestations'/'one.json'
            result=create(src,site,path,'actor','scope','actions','pass','limits')
            entry=result['attestation']
            for changed in changes:
                with self.subTest(changed=changed):
                    raw=json.dumps({**entry,**changed}).encode(); path.write_bytes(raw)
                    with self.assertRaisesRegex(ValueError,'формат'): inspect(src,site,path,hashlib.sha256(raw).hexdigest())

    def test_claim_queue_revision_stales_even_when_requirements_unchanged(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,work=fixture(Path(t).absolute()); path=work/'manual-attestations'/'one.json'
            result=create(src,site,path,'actor','scope','actions','pass','limits')
            queue=work/'PAGE-QUEUE.md'; original=queue.read_bytes()
            proposal=work/'new.md'; proposal.write_bytes(original+b'new agent note\n')
            md.commit(src,proposal,md.sha(original),'note')
            state=inspect(src,site,path,result['sha256'])
            self.assertEqual(state['freshness'],'stale'); self.assertEqual(state['changed'],['queue_sha256'])

    def test_current_manual_failure_is_visible_and_never_grants_trust(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,work=fixture(Path(t).absolute())
            path=work/'manual-attestations'/'fail.json'
            claim=create(src,site,path,'actor','scope','actions','fail','limits')
            state=readiness.evaluate(src,site,manual_record=path,manual_sha256=claim['sha256'])
            self.assertEqual(state['status'],'FAIL'); self.assertFalse(state['eligible'])
            self.assertFalse(state['manual']['verified_identity']); self.assertEqual(state['manual']['reported_outcome'],'fail')
            self.assertTrue(any('ручном заявлении указан fail' in text for text in state['blockers']))

    def test_cli_creation_and_partial_write_report_actual_operation(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,work=fixture(Path(t).absolute()); path=work/'manual-attestations'/'one.json'
            args=['manual-attest','--source',str(src),'--site',str(site),'--output',str(path),
                  '--actor','actor','--scope','scope','--actions','actions','--outcome','pass','--limitations','limits','--json']
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream): code=main(args)
            self.assertEqual(code,2); self.assertEqual(json.loads(stream.getvalue())['operation'],'applied')
            args[args.index(str(path))]=str(path.parent/'two.json')
            def partial(out, data):
                Path(out).write_bytes(data[:10]); raise OSError('synthetic disk full')
            stream=io.StringIO()
            with patch('tools.manual_evidence.md._write_new',side_effect=partial), contextlib.redirect_stdout(stream):
                code=main(args)
            result=json.loads(stream.getvalue())
            self.assertEqual(code,4); self.assertEqual(result['operation'],'unknown')
            self.assertTrue((path.parent/'two.json').exists()); self.assertTrue(path.exists())

    def test_changed_input_before_write_does_not_create_record_directory(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,work=fixture(Path(t).absolute()); path=work/'manual-attestations'/'one.json'
            original=manual_evidence.diagnostic; calls=0
            def changing(*args):
                nonlocal calls
                calls+=1
                if calls==2: (site/'index.html').write_text('changed during preparation')
                return original(*args)
            with patch('tools.manual_evidence.diagnostic',side_effect=changing):
                with self.assertRaisesRegex(ValueError,'изменились'):
                    create(src,site,path,'actor','scope','actions','pass','limits')
            self.assertFalse(path.parent.exists())

    def test_sync_failure_marks_record_uncertain_without_removing_it(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,work=fixture(Path(t).absolute()); path=work/'manual-attestations'/'one.json'
            with patch('tools.manual_evidence.md._sync_dir',side_effect=OSError('synthetic sync failure')):
                with self.assertRaises(manual_evidence.ManualRecordUncertain):
                    create(src,site,path,'actor','scope','actions','pass','limits')
            self.assertTrue(path.is_file())
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(inspect(src,site,path,digest)['freshness'],'current')
            self.assertFalse(inspect(src,site,path,digest)['publication_eligible'])

    def test_requires_scope_actions_and_limitations(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            base=Path(t).absolute()
            with self.assertRaises(ValueError): create(base,base,base/'x','actor','','actions','pass','none')

if __name__=='__main__': unittest.main()
