import functools
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from tools.audit_runner import package_install, run, brief_report
from tools.screen_audit import load_scenarios, audit_urls, inline_font_css


class AuditSetupTests(unittest.TestCase):
    def test_overlay_does_not_crop_different_sizes(self):
        import io
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed')
        from tools.visual_diff import save_comparison
        first = Image.new('RGB', (10, 10), 'white')
        second = Image.new('RGB', (10, 15), 'white')
        second.putpixel((2, 3), (255, 0, 0))
        def png(image):
            out = io.BytesIO(); image.save(out, format='PNG'); return out.getvalue()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            result = save_comparison(png(first), png(second), folder, 'full', 12)
            self.assertEqual(result['reference_size'], [10, 10])
            self.assertEqual(result['candidate_size'], [10, 15])
            self.assertEqual(result['canvas_size'], [10, 15])
            self.assertEqual(result['missing_pixels'], 50)
            self.assertGreater(result['difference_ratio'], 0.33)
            self.assertEqual(Image.open(folder/'full-heatmap.png').getpixel((2, 12)), (255, 0, 255))
            self.assertEqual(Image.open(folder/'full-overlay.png').size, (10, 15))
            self.assertEqual(Image.open(folder/'full-overlay.png').getpixel((2, 3)), (255, 127, 127))
            strict = save_comparison(png(first), png(second), folder, 'strict', 255)
            self.assertEqual(strict['difference_ratio'], 50 / 150)
            huge = Image.new('RGB', (4000, 3001), 'white')
            with self.assertRaises(ValueError): save_comparison(png(huge), png(huge), folder, 'huge', 0)

    def test_locked_pnpm_and_unsafe_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/'package.json').write_text(json.dumps({'devDependencies':{'vite':'8'}, 'scripts':{'dev':'vite'}}))
            (p/'pnpm-lock.yaml').write_text('lockfileVersion: 9')
            (p/'.mise.toml').write_text('[tools]\n"npm:pnpm" = "10.34.3"\n')
            command = package_install(p)
            self.assertIn('--ignore-scripts', command); self.assertIn('--frozen-lockfile', command)
            (p/'package.json').write_text(json.dumps({'devDependencies':{'vite':'8'}, 'scripts':{'dev':'rm -rf /'}}))
            with self.assertRaises(ValueError): package_install(p)

    def test_scenarios_validation_and_viewports(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'s.json'
            valid = [{'name':'menu','viewports':[390,768], 'reference':[{'type':'click','selector':'#a'}], 'candidate':[{'type':'click','selector':'#b'}]}]
            p.write_text(json.dumps(valid)); self.assertEqual(load_scenarios(p), valid)
            for bad in [[{'name':'../escape','reference':[],'candidate':[]}], [{'name':'x','reference':[{'type':'press','key':'F5'}],'candidate':[]}], [{'name':'x','viewports':[320],'reference':[],'candidate':[]}]]:
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError): load_scenarios(p)

    def test_brief_prioritizes_fullpage_warning_and_limits(self):
        data = {'status': 'INCOMPLETE', 'warnings': [f'missing {i}' for i in range(12)] + ['Не удалось снять/сравнить длинную страницу']}
        brief = brief_report(data)
        self.assertEqual(len(brief['warnings']), 8)
        self.assertEqual(brief['warnings_total'], 13)
        self.assertIn('длинную страницу', brief['warnings'][0])

    def test_font_path_restrictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'css').mkdir(); (root/'fonts').mkdir()
            (root/'fonts'/'font.woff2').write_bytes(b'wOF2test')
            css=root/'css'/'font.css'; css.write_text("@font-face{font-family:X;src:url('../fonts/font.woff2')}")
            content, files=inline_font_css(css); self.assertIn('data:font/woff2;base64,',content); self.assertEqual(len(files),1)
            css.write_text("@font-face{src:url('https://example.com/file.woff2')}")
            with self.assertRaises(ValueError): inline_font_css(css)

    def test_run_without_trust_and_output_guard(self):
        Path('.work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='.work', prefix='audit-test-') as tmp:
            out=Path(tmp)/'new'
            result=run(Path('source'),Path('vanilla'),out,[],trust_source=False)
            self.assertEqual(result['status'],'BLOCKED'); self.assertTrue((out/'summary.json').is_file())
            result=run(Path('source'),Path('vanilla'),out,[],trust_source=False)
            self.assertEqual(result['status'],'BLOCKED')
            self.assertTrue((out/'summary.json').is_file())


@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS') == '1', 'browser not requested')
class ScreenBrowserTests(unittest.TestCase):
    def test_visual_difference_is_detected_on_lower_screens(self):
        Path('.work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='.work', prefix='pixel-test-') as tmp:
            root=Path(tmp); ref=root/'ref'; candidate=root/'candidate'; ref.mkdir(); candidate.mkdir()
            base='<!doctype html><html><body style="margin:0"><div style="height:2400px;background:COLOR"></div></body></html>'
            (ref/'index.html').write_text(base.replace('COLOR','white'))
            (candidate/'index.html').write_text(base.replace('2400px','2700px').replace('COLOR','linear-gradient(white 50%,red 50%)'))
            servers=[]; threads=[]
            try:
                for folder in (ref,candidate):
                    server=http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(folder)))
                    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();servers.append(server);threads.append(thread)
                urls=[f'http://127.0.0.1:{s.server_port}' for s in servers]
                output=root/'out';output.mkdir(); report=audit_urls(*urls,output,[])
                self.assertEqual(report['status'],'FAIL',report)
                mobile=report['viewports'][0]['states'][0]['screens']
                self.assertEqual(mobile[0]['status'],'OK')
                self.assertIn('any_difference_ratio', mobile[0])
                self.assertEqual(report['channel_tolerance'], 12)
                self.assertTrue(any(screen['status']=='FAIL' for screen in mobile[1:]))
                self.assertEqual(report['behavior'],'not_checked')
                state = report['viewports'][0]['states'][0]
                self.assertEqual(state['fullpage']['reference_size'], [390, 2400])
                self.assertEqual(state['fullpage']['candidate_size'], [390, 2700])
                self.assertEqual(state['fullpage']['missing_pixels'], 390 * 300)
                self.assertTrue(any(not screen['offsets_match'] for screen in mobile))
            finally:
                for server in servers: server.shutdown();server.server_close()
                for thread in threads: thread.join()

    def test_screens_and_behavior_and_missing_files(self):
        Path('.work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='.work', prefix='screen-test-') as tmp:
            root=Path(tmp); ref=root/'ref'; candidate=root/'candidate'; ref.mkdir();candidate.mkdir()
            html='''<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0} main{height:2400px;background:white}</style></head><body><button id="btn" aria-expanded="false" onclick="this.setAttribute('aria-expanded','true');this.textContent='Opened'">Open</button><input id="text"><input id="check" type="checkbox"><select id="select"><option value="a">A</option><option value="b">B</option></select><main><h1>Hello</h1><img src="missing.png" alt=""></main></body></html>'''
            for folder in (ref,candidate): (folder/'index.html').write_text(html)
            servers=[]; threads=[]
            try:
                for folder in (ref,candidate):
                    server=http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(folder)))
                    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();servers.append(server);threads.append(thread)
                urls=[f'http://127.0.0.1:{s.server_port}' for s in servers]
                actions = [{'type':'focus','selector':'#text'}, {'type':'fill','selector':'#text','value':'test'},
                           {'type':'check','selector':'#check','value':True}, {'type':'select','selector':'#select','value':'b'},
                           {'type':'click','selector':'#btn'}, {'type':'scroll','y':600}]
                scenario=[{'name':'opened','reference':actions, 'candidate':actions}]
                out=root/'out';out.mkdir(); report=audit_urls(*urls,out,scenario)
                self.assertEqual(report['status'],'INCOMPLETE',report)
                self.assertEqual(report['coverage']['states_checked'],6)
                self.assertGreater(report['coverage']['screens_compared'],6)
                self.assertTrue(any('missing.png' in x for x in report['warnings']))
                self.assertTrue(any(s['name']=='opened' for v in report['viewports'] for s in v['states']))
                self.assertTrue((out/'390x844'/'initial'/'002-diff.png').exists())
                self.assertTrue((out/'390x844'/'initial'/'full-overlay.png').exists())
                self.assertTrue((out/'390x844'/'initial'/'full-heatmap.png').exists())
                self.assertTrue((out/'390x844'/'opened'/'action-heatmap.png').exists())
                self.assertEqual(report['coverage']['action_screens_compared'], 3)
                self.assertEqual(report['viewports'][0]['states'][1]['action']['actual_y'], [600, 600])
                self.assertTrue(report['viewports'][0]['states'][1]['controls']['candidate'][2]['checked'])
                # A changed control behavior is reported even when an unrelated file is absent.
                (candidate/'index.html').write_text(html.replace("this.textContent='Opened'", "this.textContent='Wrong'"))
                out2=root/'different';out2.mkdir(); changed=audit_urls(*urls,out2,scenario)
                self.assertEqual(changed['status'],'FAIL',changed)
                self.assertTrue(any(s.get('mismatches') for v in changed['viewports'] for s in v['states']))
            finally:
                for server in servers: server.shutdown(); server.server_close()
                for thread in threads: thread.join()

if __name__ == '__main__': unittest.main()
