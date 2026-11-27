import contextlib
import functools
import hashlib
import http.server
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from tools import queue_md as md
from tools.audit_markdown import audit
from tools.coverage import diagnostic
from tools.delivery import materialize
from tools.manual_evidence import create, inspect
from tools.publication import plan
from tools.run_store import seal, inspect as inspect_run
from tools.readiness import evaluate


@contextlib.contextmanager
def cd(path):
    old=os.getcwd(); os.chdir(path)
    try: yield
    finally: os.chdir(old)


@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS')=='1','browser not requested')
class MultiPageV2Tests(unittest.TestCase):
    def test_two_independent_sites_and_shared_file_regression(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            root=Path.cwd(); src=root/'source'; src.mkdir(); (src/'index.html').write_text('synthetic source')
            work=src/'.work'; work.mkdir(); stage=work/'staging'/'site'; stage.mkdir(parents=True)
            (stage/'sub').mkdir(); (stage/'assets').mkdir(); (stage/'template').mkdir()
            header='<header><span>Site</span></header>'; footer='<footer>Footer</footer>'
            (stage/'template/header.php').write_text(header); (stage/'template/footer.php').write_text(footer)
            (stage/'assets/common.css').write_text('body{font-family:sans-serif;color:#111}')
            html=lambda title,css: f'''<!doctype html><html lang="en"><head><title>{title}</title><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="{css}"></head><body><!-- HEADER:START -->{header}<!-- HEADER:END --><main><h1>{title}</h1><button type="button" onclick="this.textContent='Opened'">Open</button></main><!-- FOOTER:START -->{footer}<!-- FOOTER:END --></body></html>'''
            (stage/'index.html').write_text(html('Home','assets/common.css'))
            (stage/'sub/other.html').write_text(html('Other','../assets/common.css'))
            reference=root/'reference'; shutil.copytree(stage,reference)
            data=md.parse(md.template(src))
            data['pages']=[dict(zip(md.TABLES['pages'],['home','Home','/','index.html','confirmed','true','built','reviewed',''])),
                           dict(zip(md.TABLES['pages'],['other','Other','/sub/other.html','sub/other.html','confirmed','true','built','reviewed','']))]
            data['aliases']=[dict(zip(md.TABLES['aliases'],['home','/#home','direct','reviewed']))]
            data['states']=[dict(zip(md.TABLES['states'],['home','menu','true','390x844','scenario.json']))]
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='confirmed'
                if row['key']=='confirmation_reason': row['value']='reviewed both pages'
            (work/'scenario.json').write_text(json.dumps([{'name':'menu','viewports':[390],
                'reference':[{'type':'click','selector':'button'}],'candidate':[{'type':'click','selector':'button'}],
                'assertions':{'reference':[{'type':'text','selector':'button','value':'Opened'}],
                              'candidate':[{'type':'text','selector':'button','value':'Opened'}]}}]))
            proposal=work/'p.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,'absent','inventory')
            selected=['index.html','sub/other.html','assets/common.css','template/header.php','template/footer.php']
            selection=work/'selection.json'; selection.write_text(json.dumps(selected))
            record=materialize(src,stage,selection,work/'deliveries'/'run'); delivery=work/'deliveries'/'run'
            static=diagnostic(src,delivery); self.assertEqual(static['coverage']['planned'],10)
            self.assertEqual(static['status'],'INCOMPLETE',static['issues'])
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(reference)))
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try: result=audit(src,delivery,'http://127.0.0.1:'+str(server.server_port))
            finally: server.shutdown();server.server_close();thread.join()
            self.assertEqual(result['coverage']['planned'],10); self.assertEqual(result['coverage']['executed'],10, result['issues'])
            self.assertFalse(result['eligible']); self.assertTrue(all(x['outcome']!='pass' for x in result['coverage']['entries']))
            state=next(s for v in result['runs'][0]['result']['viewports'] for s in v['states'] if s['name']=='menu')
            self.assertEqual(state['assertions_checked'],2); self.assertEqual(state['mismatches'],[])
            run_dir=Path(result['artifact_directory']); summary_hash=hashlib.sha256((run_dir/'summary.json').read_bytes()).hexdigest()
            sealed=seal(src,delivery,run_dir,summary_hash)
            self.assertEqual(inspect_run(src,delivery,sealed['path'],sealed['sha256'])['freshness'],'current')
            self.assertTrue(sealed['record']['browser_versions'])
            manual=create(src,delivery,work/'manual-attestations'/'review.json','tester','both pages','synthetic keyboard review','pass','synthetic only')
            self.assertEqual(inspect(src,delivery,manual['path'],manual['sha256'])['freshness'],'current')
            status=evaluate(src,delivery,sealed['path'],sealed['sha256'],manual['path'],manual['sha256'])
            self.assertFalse(status['eligible']); self.assertEqual(status['coverage']['required_unconfirmed'],10)
            plan_result=plan(src,record['record'],root/'vanilla',sealed['path'],sealed['sha256'],manual['path'],manual['sha256'])
            self.assertFalse(plan_result['apply_allowed']); self.assertEqual(plan_result['run']['freshness'],'current')
            (delivery/'assets/common.css').write_text('body{color:red}')
            self.assertEqual(inspect(src,delivery,manual['path'],manual['sha256'])['freshness'],'stale')
            self.assertEqual(inspect_run(src,delivery,sealed['path'],sealed['sha256'])['freshness'],'stale')
            with self.assertRaises(ValueError): plan(src,record['record'],root/'vanilla')
            self.assertFalse((root/'vanilla').exists())

if __name__=='__main__': unittest.main()
