import contextlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.core import analyze, fingerprint
from tools.queue import discover, load, merge_discovery, save, check_manifest
from tools.lifecycle import record, stale_checks, publish

HTML='''<!doctype html><html lang="ru"><head><title>T</title><meta name="viewport" content="width=device-width"></head><body><!-- HEADER:START --><header><a href="{home}">Home</a></header><!-- HEADER:END --><main>Page</main><!-- FOOTER:START --><footer>Footer</footer><!-- FOOTER:END --></body></html>'''

@contextlib.contextmanager
def cwd(p):
    old=os.getcwd(); os.chdir(p)
    try: yield
    finally: os.chdir(old)


def source_fixture(root):
    source=root/'source'; source.mkdir(); (source/'package.json').write_text('{}'); (source/'package-lock.json').write_text('{}'); (source/'index.html').write_text('x')
    return source

@unittest.skipUnless(importlib.util.find_spec('tree_sitter'), 'tree-sitter not installed')
class DiscoverTests(unittest.TestCase):
    def test_tsx_discovers_router_branches_dynamic_array_and_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=source_fixture(Path(tmp)); (source/'src').mkdir()
            (source/'src/App.tsx').write_text('''const data=[{id:"one",title:"One"},{id:"two",title:"Two"}]; function go(x){location.hash=x}; function App(){if(page === "about")return <div/>; if(page === "program")return <div/>; return <>{data.map(item => <button onClick={()=>go(`program/${item.id}`)} />)}<button onClick={()=>go("about/missing")}/></>}''')
            pre,data=discover(source); routes={p['reference_route'] for p in data['pages']}
            self.assertIn('/#about',routes); self.assertIn('/#program/one',routes); self.assertIn('/#program/two',routes)
            self.assertNotIn('/#about/missing',routes); self.assertTrue(any(x['reference_route']=='/#about/missing' for x in data['unresolved_links']))
            self.assertTrue(all(p['confirmation']=='candidate' for p in data['pages']))

    def test_static_multipage_and_ambiguous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=source_fixture(Path(tmp)); (source/'nested').mkdir()
            (source/'index.html').write_text('<a href="nested/page.html">next</a>')
            (source/'nested/page.html').write_text('<a href="../index.html">home</a>')
            pre,data=discover(source); routes={p['reference_route'] for p in data['pages']}
            self.assertIn('/nested/page.html',routes)
            self.assertTrue(any(x['reference_route']=='/index.html' for x in data['unresolved_links']))

    def test_optimistic_lock_rejects_lost_update(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            source=source_fixture(Path(tmp)); pre,data=discover(source); path=source/'.work/manifest.json'; save(path,data,create=True)
            old=hashlib.sha256(path.read_bytes()).hexdigest(); changed=load(path); changed['pages'][0]['title']='new'; save(path,changed,expected_hash=old)
            with self.assertRaises(ValueError): save(path,data,expected_hash=old)
            self.assertEqual(load(path)['pages'][0]['title'],'new')

    def test_repeat_preserves_manual_decisions_and_invalidates_after_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=source_fixture(Path(tmp)); pre,old=discover(source)
            old['pages'][0]['confirmation']='confirmed'; old['pages'][0]['checks']['manual']='checked'; old['pages'][0]['work_status']='built'
            (source/'other.js').write_text('function x(){}')
            pre,new=discover(source); merged=merge_discovery(old,new)
            self.assertEqual(merged['pages'][0]['confirmation'],'confirmed'); self.assertEqual(merged['pages'][0]['checks']['manual'],'not_run')
            self.assertEqual(merged['pages'][0]['work_status'],'in_progress'); self.assertEqual(merged['discovery']['status'],'unconfirmed')

class TemplateTests(unittest.TestCase):
    def test_template_compares_nested_paths_and_does_not_ignore_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp); (site/'sub').mkdir(); (site/'template').mkdir()
            (site/'index.html').write_text(HTML.format(home='index.html'))
            (site/'sub/about.html').write_text(HTML.format(home='../index.html'))
            (site/'template/header.php').write_text('<header><a href="index.html">Home</a></header>'); (site/'template/footer.php').write_text('<footer>Footer</footer>')
            def page(i,out): return {'id':i,'title':i,'reference_route':'/'+out,'output':out,'confirmation':'confirmed','work_status':'pending','states':[], 'checks':{}}
            data={'schema_version':1,'source':{},'discovery':{'status':'confirmed','confirmation_reason':'test'},'pages':[page('home','index.html'),page('about','sub/about.html')],'unresolved_links':[]}
            result=check_manifest(site,data); self.assertEqual(result['issues'],[])
            (site/'sub/about.html').write_text(HTML.format(home='../index.html').replace('<header>', '<header class="active">'))
            result=check_manifest(site,data); self.assertTrue(any('header' in x for x in result['issues']))
            (site/'sub/about.html').write_text(HTML.format(home='../index.html').replace('Footer','Changed'))
            result=check_manifest(site,data); self.assertTrue(any('footer' in x for x in result['issues']))

class LifecycleTests(unittest.TestCase):
    def test_checked_and_publish_fail_closed_even_with_existing_data(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cwd(tmp):
            root=Path.cwd(); src=source_fixture(root); stage=src/'.work/staging/run'; stage.mkdir(parents=True)
            (stage/'index.html').write_text('candidate')
            (root/'vanilla').mkdir(); (root/'vanilla/user.txt').write_text('keep')
            for kind in ('static', 'browser', 'manual'):
                with self.assertRaisesRegex(ValueError, 'временно отключена'):
                    record(src,stage,None,kind,'checked',src/'.work/report.json')
            with self.assertRaisesRegex(ValueError, 'временно отключена'):
                publish(src,stage,replace=True)
            self.assertEqual((root/'vanilla/user.txt').read_text(),'keep')
            self.assertFalse((root/'vanilla/index.html').exists())

    def test_incomplete_evidence_can_be_recorded_and_becomes_stale(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cwd(tmp):
            root=Path.cwd(); src=source_fixture(root); stage=src/'.work/staging/run'; stage.mkdir(parents=True)
            (stage/'index.html').write_text('candidate'); report=src/'.work/report.json'; report.write_text('{}')
            pre,data=discover(src); save(src/'.work/manifest.json',data,create=True)
            page=data['pages'][0]['id']
            record(src,stage,page,'manual','review',report)
            self.assertEqual(stale_checks(load(src/'.work/manifest.json'),src)['pages'][0]['checks']['manual'],'review')
            (stage/'index.html').write_text('changed')
            self.assertEqual(stale_checks(load(src/'.work/manifest.json'),src)['pages'][0]['checks']['manual'],'stale')

@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS')=='1','browser not requested')
class BrowserWorkflowTests(unittest.TestCase):
    def test_batch_managed_site_and_evidence(self):
        import io
        from tools.cli import main
        from tools.lifecycle import serve_site
        with tempfile.TemporaryDirectory(dir='.') as tmp, cwd(tmp):
            root=Path.cwd(); src=source_fixture(root); stage=src/'.work/staging/run';stage.mkdir(parents=True)
            reference=root/'reference'; reference.mkdir()
            content=HTML.format(home='index.html'); (stage/'index.html').write_text(content); (reference/'index.html').write_text(content)
            sh=analyze(src)['fingerprint']; data={'schema_version':1,'source':{'root':'.','fingerprint':sh},'discovery':{'status':'confirmed','confirmation_reason':'reviewed'},'pages':[{'id':'home','title':'Home','reference_route':'/','output':'index.html','confirmation':'confirmed','work_status':'built','states':[],'checks':{'static':'not_run','browser':'not_run','manual':'not_run'}}],'unresolved_links':[]}
            save(src/'.work/manifest.json',data,create=True); buf=io.StringIO()
            with serve_site(reference) as base,contextlib.redirect_stdout(buf):
                code=main(['browser-audit-site','--source',str(src),'--site',str(stage),'--reference-url',base,'--json'])
            self.assertEqual(code,2,buf.getvalue()); r=json.loads(buf.getvalue()); self.assertEqual(r['candidate_binding'],'managed-static')
            report=Path(r['artifact_directory'])/'summary.json'
            with self.assertRaisesRegex(ValueError, 'временно отключена'):
                record(src,stage,'home','browser','checked',report)
            self.assertEqual(load(src/'.work/manifest.json')['pages'][0]['checks']['browser'],'not_run')
