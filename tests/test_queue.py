import copy
import functools
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from tools.core import analyze, fingerprint
from tools.queue import validate, save, load, render, check_manifest, local_route
from tools.screen_audit import audit_urls


def manifest():
    def page(i, route, out):
        return {'id':i,'title':i,'reference_route':route,'reference_aliases':[], 'output':out,'confirmation':'confirmed','work_status':'pending','states':[], 'checks':{'static':'not_run','browser':'not_run','manual':'not_run'}}
    return {'schema_version':1,'source':{'root':'.','fingerprint':'x'},'discovery':{'status':'confirmed','confirmation_reason':'test','unresolved':[]},'pages':[page('home','/','index.html'),page('about','/#about','about.html')],'unresolved_links':[]}


def html(content):
    return '<!doctype html><html lang="ru"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body><!-- HEADER:START --><header>Header</header><!-- HEADER:END -->'+content+'<!-- FOOTER:START --><footer>Footer</footer><!-- FOOTER:END --></body></html>'

class QueueTests(unittest.TestCase):
    def test_paths_and_collisions(self):
        for value in ['../x.html','/a.html','a/../b.html','a%2fb.html','foo.html?x','a\\b.html', 'NUL.html','name|bad.html']:
            d=manifest(); d['pages'][0]['output']=value
            with self.assertRaises(ValueError): validate(d)
        for value in ['//example.com', '/%2e%2e/x','/%252e%252e/x', '/\\evil', '/%00x']:
            self.assertFalse(local_route(value), value)
        d=manifest(); d['pages'][1]['output']='INDEX.html'
        with self.assertRaises(ValueError): validate(d)
        d=manifest(); d['pages'][1]['reference_route']='/'
        with self.assertRaises(ValueError): validate(d)

    def test_save_no_overwrite_and_fingerprint_excludes_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'package.json').write_text('{}'); (root/'index.html').write_text('x'); (root/'package-lock.json').write_text('{}')
            before=fingerprint(root); p=root/'.work'/'manifest.json'; save(p,manifest(),create=True)
            self.assertEqual(fingerprint(root),before); self.assertEqual(analyze(root)['status'],'INCOMPLETE')
            self.assertEqual(load(p),manifest()); self.assertEqual((p.parent/'PAGE-QUEUE.md').read_text(),render(manifest()))
            with self.assertRaises(ValueError): save(p,manifest(),create=True)
            self.assertEqual(load(p),manifest())

    def test_coverage_markers_and_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'index.html').write_text(html('<a href="about.html">link</a>'))
            result=check_manifest(root,manifest()); self.assertEqual(result['status'],'FAIL')
            self.assertEqual(result['coverage']['pages_missing'],['about.html'])
            self.assertTrue(any('HTML-ссылка' in x for x in result['issues']))
            (root/'about.html').write_text(html('<h1>about</h1>'))
            result=check_manifest(root,manifest()); self.assertEqual(result['status'],'INCOMPLETE'); self.assertEqual(result['coverage']['pages_present'],2)
            (root/'about.html').write_text(html('<h1>about</h1>').replace('<!-- HEADER:END -->',''))
            self.assertEqual(check_manifest(root,manifest())['status'],'FAIL')

    def test_static_pages_reject_php_short_tags_encoded_paths_and_form_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'about.html').write_text(html('<h1>about</h1>'))
            target=root/'index.html'
            cases=['<?php echo 1; ?>','<?= 1 ?>','<? echo 1; ?>','<?xml version="1.0"?>',
                   '<a href="handler%2ePHP?x=1">send</a>',
                   '<form action="send.phtml"><button>Send</button></form>',
                   '<form><button formaction="/execute.PHP8/extra">Send</button></form>',
                   '<img src="foo.php;extra=1" alt="">',
                   '<img srcset="pic.php 1x, photo.png 2x" alt="">',
                   '<svg><use xlink:href="icon.php#mark"></use></svg>']
            for content in cases:
                with self.subTest(content=content):
                    target.write_text(html(content)); result=check_manifest(root,manifest())
                    self.assertEqual(result['status'],'FAIL',result)
                    self.assertTrue(any('PHP' in issue for issue in result['issues']),result)
            target.write_text(html('<p>PHP documentation, not code</p>'))
            self.assertFalse(any('PHP' in issue for issue in check_manifest(root,manifest())['issues']))

    def test_unresolved_link_must_be_classified_before_confirmation(self):
        d=manifest(); d['unresolved_links']=[{'reference_route':'/#missing','reason':'not implemented'}]
        with self.assertRaises(ValueError): validate(d)
        d['unresolved_links'][0].update({'resolution':'missing','resolution_reason':'no page component'})
        validate(d)

    def test_unconfirmed_never_complete(self):
        d=manifest(); d['discovery']['status']='unconfirmed'; validate(d)
        d['discovery']['status']='confirmed'; d['pages'][0]['confirmation']='candidate'
        with self.assertRaises(ValueError): validate(d)

@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS') == '1', 'browser not requested')
class RouteBrowserTests(unittest.TestCase):
    def test_different_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'index.html').write_text(html('<h1>same</h1>')); (root/'about.html').write_text(html('<h1>same</h1>'))
            handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=tmp)
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'; out=root/'out';out.mkdir()
                r=audit_urls(base,base,out,reference_route='/#about',candidate_route='/about.html')
                self.assertEqual(r['status'],'INCOMPLETE',r);self.assertEqual(r['coverage']['states_checked'],3)
                self.assertEqual(r['candidate_route'],'/about.html')
            finally:
                server.shutdown(); server.server_close(); thread.join()

class BatchCLITests(unittest.TestCase):
    def test_batch_preserves_failure_and_uses_distinct_routes(self):
        import contextlib, io
        from unittest.mock import patch
        from tools.cli import main
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            root=Path(tmp); src=root/'source'; src.mkdir(); (src/'package.json').write_text('{}'); (src/'package-lock.json').write_text('{}'); (src/'index.html').write_text('source')
            site=root/'site'; site.mkdir(); (site/'index.html').write_text(html('x')); (site/'about.html').write_text(html('y'))
            d=manifest(); d['source']['fingerprint']=analyze(src)['fingerprint']; save(src/'.work'/'manifest.json',d,create=True)
            seen=[]
            def fake(*args):
                seen.append((args[11],args[12])); return {'status':'FAIL' if len(seen)==2 else 'INCOMPLETE','issues':[],'warnings':[]}
            buf=io.StringIO()
            with patch('tools.cli.run_audit',side_effect=fake),contextlib.redirect_stdout(buf):
                code=main(['browser-audit-site','--source',str(src),'--site',str(site),'--reference-url','http://127.0.0.1:8000','--candidate-url','http://127.0.0.1:8001','--json'])
            self.assertEqual(code,1); report=json.loads(buf.getvalue()); self.assertEqual(report['pages_planned'],2)
            self.assertEqual(seen,[('/','/index.html'),('/#about','/about.html')]); self.assertEqual(report['pages'][1]['result']['status'],'FAIL')

    def test_autostart_remains_blocked(self):
        from tools.audit_runner import run
        Path('.work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='.work') as tmp:
            result=run(Path('source'),Path('vanilla'),Path(tmp)/'out',[],trust_source=True)
            self.assertEqual(result['status'],'BLOCKED'); self.assertIn('ОС-изоляция',result['issues'][0])
