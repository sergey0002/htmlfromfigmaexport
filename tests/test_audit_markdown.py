import contextlib
import functools
import http.server
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import queue_md as md
from tools.audit_markdown import AuditUncertain, audit
from tools.cli import main


def setup(base):
    source=base/'source'; source.mkdir(); (source/'index.html').write_text('source')
    work=source/'.work'; work.mkdir(); site=work/'staging'/'site'; site.mkdir(parents=True)
    html='<!doctype html><html lang="en"><head><title>Test</title></head><body><main><h1>Home</h1></main></body></html>'
    (site/'index.html').write_text(html)
    data=md.parse(md.template(source))
    data['pages']=[dict(zip(md.TABLES['pages'],['home','Home','/','index.html','confirmed','true','built','reviewed','']))]
    data['states']=[dict(zip(md.TABLES['states'],['home','menu','true','390x844','']))]
    for row in data['meta']:
        if row['key']=='discovery_status': row['value']='confirmed'
        if row['key']=='confirmation_reason': row['value']='reviewed'
    proposal=work/'p.md'; proposal.write_text(md.render(data)); md.commit(source,proposal,'absent','review')
    return source,site,html


class MarkdownAuditTests(unittest.TestCase):
    def test_skipped_state_and_snapshot_changes_are_not_pass(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute())
            def fake(*args):
                return {'status':'INCOMPLETE','issues':[],'warnings':[], 'viewports':[{'width':390,'height':844,'states':[{'name':'initial','status':'OK'}]}]}
            with patch('tools.audit_markdown.run',side_effect=fake): result=audit(src,site,'http://127.0.0.1:8080')
            self.assertFalse(result['eligible']); self.assertEqual(result['operation'],'applied'); self.assertEqual(result['coverage']['planned'],4)
            self.assertEqual(result['coverage']['executed'],1)
            menu=next(x for x in result['coverage']['entries'] if x['state']=='menu')
            self.assertEqual(menu['outcome'],'unknown'); self.assertEqual(menu['execution'],'not_run')
            self.assertEqual(result['reference_provenance'],'external-unverified')
            def mutate(*args):
                (site/'index.html').write_text('changed')
                return fake(*args)
            with patch('tools.audit_markdown.run',side_effect=mutate):
                with self.assertRaisesRegex(AuditUncertain,'изменились'): audit(src,site,'http://127.0.0.1:8080')

    def test_child_failure_without_viewport_rows_is_not_hidden(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute())
            (site/'index.html').write_text('<!doctype html><html lang="en"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body><!-- HEADER:START --><header>h</header><!-- HEADER:END --><main>body</main><!-- FOOTER:START --><footer>f</footer><!-- FOOTER:END --></body></html>')
            fake={'status':'FAIL','issues':['Synthetic child failure'], 'warnings':[], 'viewports':[]}
            with patch('tools.audit_markdown.run',return_value=fake): result=audit(src,site,'http://127.0.0.1:8080')
            self.assertEqual(result['status'],'FAIL'); self.assertIn('Synthetic child failure',result['issues'])
            self.assertEqual(result['coverage']['executed'],0); self.assertEqual(result['operation'],'applied')
            self.assertEqual(json.loads((Path(result['artifact_directory'])/'summary.json').read_text())['status'],'FAIL')

    def test_known_failure_is_not_hidden_by_another_blocked_route(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute()); work=src/'.work'
            (site/'index.html').write_text('<!doctype html><html lang="en"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body><!-- HEADER:START --><header>h</header><!-- HEADER:END --><main>body</main><!-- FOOTER:START --><footer>f</footer><!-- FOOTER:END --></body></html>')
            queue=work/'PAGE-QUEUE.md'; raw=queue.read_bytes(); data=md.parse(raw.decode())
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='review_required'
            data['aliases']=[dict(zip(md.TABLES['aliases'],['home','/#home','alias','reviewed']))]
            proposal=work/'new.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,md.sha(raw),'review alias')
            responses=[{'status':'FAIL','issues':['known failure'],'warnings':[],'viewports':[]},
                       {'status':'BLOCKED','issues':['other route blocked'],'warnings':[],'viewports':[]}]
            with patch('tools.audit_markdown.run',side_effect=responses): result=audit(src,site,'http://127.0.0.1:8080')
            self.assertEqual(result['status'],'FAIL'); self.assertIn('known failure',result['issues'])
            self.assertIn('other route blocked',result['issues']); self.assertEqual(result['operation'],'applied')

    def test_blocked_state_overrides_misleading_child_summary(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute())
            (site/'index.html').write_text('<!doctype html><html lang="en"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body><!-- HEADER:START --><header>h</header><!-- HEADER:END --><main>body</main><!-- FOOTER:START --><footer>f</footer><!-- FOOTER:END --></body></html>')
            fake={'status':'INCOMPLETE','issues':[],'warnings':[],
                  'viewports':[{'width':390,'height':844,'states':[{'name':'initial','status':'BLOCKED','issue':'navigation failed'}]}]}
            with patch('tools.audit_markdown.run',return_value=fake): result=audit(src,site,'http://127.0.0.1:8080')
            self.assertEqual(result['status'],'BLOCKED'); self.assertEqual(result['coverage']['executed'],0)
            state=next(row for row in result['coverage']['entries'] if row['viewport']==[390,844] and row['state']=='initial')
            self.assertEqual(state['execution'],'blocked'); self.assertEqual(state['outcome'],'unknown')

    def test_unknown_duplicate_or_unplanned_states_fail_closed_as_uncertain(self):
        states=[[{'name':'initial','status':'MYSTERY'}],
                [{'name':'initial','status':'OK'},{'name':'initial','status':'OK'}],
                [{'name':'unplanned','status':'OK'}]]
        for reported in states:
            with self.subTest(reported=reported), tempfile.TemporaryDirectory(dir='.') as t:
                src,site,_=setup(Path(t).absolute())
                fake={'status':'INCOMPLETE','issues':[],'warnings':[],
                      'viewports':[{'width':390,'height':844,'states':reported}]}
                output=io.StringIO()
                with patch('tools.audit_markdown.run',return_value=fake),contextlib.redirect_stdout(output):
                    code=main(['browser-audit-md','--source',str(src),'--site',str(site),
                               '--reference-url','http://127.0.0.1:8080','--json'])
                result=json.loads(output.getvalue())
                self.assertEqual(code,4); self.assertEqual(result['operation'],'unknown')
                roots=list((src/'.work/audits-md').iterdir()); self.assertEqual(len(roots),1)
                self.assertFalse((roots[0]/'summary.json').exists())

    def test_summary_write_failure_is_unknown_and_partial_data_is_preserved(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute()); output=io.StringIO()
            fake={'status':'INCOMPLETE','issues':[],'warnings':[], 'viewports':[]}
            def partial(path,data):
                Path(path).write_bytes(data[:10]); raise OSError('synthetic disk full')
            with patch('tools.audit_markdown.run',return_value=fake),patch('tools.audit_markdown.md._write_new',side_effect=partial),contextlib.redirect_stdout(output):
                code=main(['browser-audit-md','--source',str(src),'--site',str(site),
                           '--reference-url','http://127.0.0.1:8080','--json'])
            self.assertEqual(code,4); self.assertEqual(json.loads(output.getvalue())['operation'],'unknown')
            roots=list((src/'.work/audits-md').iterdir()); self.assertEqual(len(roots),1)
            self.assertEqual(len((roots[0]/'summary.json').read_bytes()),10)

    def test_invalid_reference_is_rejected_before_creating_artifacts(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute()); output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=main(['browser-audit-md','--source',str(src),'--site',str(site),
                           '--reference-url','https://example.invalid/','--json'])
            self.assertEqual(code,3); self.assertEqual(json.loads(output.getvalue())['operation'],'not_applied')
            self.assertFalse((src/'.work/audits-md').exists())

    @unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS')=='1','browser not requested')
    def test_real_browser_returns_diagnostic_coverage(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            root=Path(t).absolute(); src,site,html=setup(root); ref=root/'reference'; ref.mkdir(); (ref/'index.html').write_text(html)
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ref)))
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try: result=audit(src,site,'http://127.0.0.1:'+str(server.server_port))
            finally: server.shutdown(); server.server_close(); thread.join()
            self.assertEqual(result['coverage']['planned'],4); self.assertEqual(result['coverage']['executed'],3)
            self.assertFalse(result['eligible']); self.assertTrue(all(e['outcome']!='pass' for e in result['coverage']['entries']))

if __name__=='__main__': unittest.main()
