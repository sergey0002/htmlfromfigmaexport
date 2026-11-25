import contextlib
import io
import functools
import http.server
import json
import os
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from tools.core import analyze, check_site, fingerprint
from tools.browser import compare, loopback_url
from tools.cli import main

SHELL = '<!doctype html><html lang="ru"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body>{}</body></html>'

class StaticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def write(self, path, content):
        dest = self.root / path; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(content, encoding='utf8')

    def test_figma_export_preflight(self):
        self.write('package.json', json.dumps({'scripts': {'dev': 'vite'}, 'dependencies': {'react': '^19'}, 'devDependencies': {'vite': '^8'}}))
        self.write('pnpm-lock.yaml', 'lockfileVersion: 9')
        self.write('index.html', '<div id="root"></div>')
        self.write('src/App.tsx', '<img src="/images/logo.svg" />')
        self.write('public/images/x.png', 'version https://git-lfs.github.com/spec/v1\noid sha256:xyz\n')
        result = analyze(self.root)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(len(result['warnings']), 2)
        self.assertEqual(result['locks'], ['pnpm-lock.yaml'])
        self.assertEqual(result['missing_literal_assets'], ['/images/logo.svg'])
        self.assertIn('public/images/x.png', result['lfs_pointers'])
        self.assertEqual(result['fingerprint'], fingerprint(self.root))
        self.write('public/images/logo.svg', '<svg/>')
        self.assertNotEqual(result['fingerprint'], fingerprint(self.root))

    def test_invalid_manifest_does_not_crash(self):
        self.write('package.json', '[]')
        self.assertEqual(analyze(self.root)['status'], 'BLOCKED')

    def test_multiple_manifests_are_ambiguous(self):
        self.write('one/package.json', '{}'); self.write('two/package.json', '{}')
        self.assertEqual(analyze(self.root)['status'], 'BLOCKED')

    def test_two_distinct_sites_and_regressions(self):
        self.write('index.html', SHELL.format('<h1 id="top">Alpha</h1><a href="other.html#x">Other</a><img src="pic.svg" alt="logo"><link rel="stylesheet" href="styles/a.css">'))
        self.write('other.html', SHELL.format('<main id="x"><h1>Other page</h1></main>'))
        self.write('pic.svg', '<svg/>'); self.write('styles/a.css', '@import "missing.css"; body { background: url(../pic.svg) }'); self.write('styles/missing.css', '')
        r = check_site(self.root); self.assertEqual(r['status'], 'INCOMPLETE'); self.assertEqual(len(r['pages']), 2)
        (self.root/'styles/missing.css').unlink()
        self.write('other.html', SHELL.format('<h1>Changed</h1>'))
        self.write('pic.svg', 'version https://git-lfs.github.com/spec/v1\n')
        r = check_site(self.root); self.assertEqual(r['status'], 'FAIL')
        self.assertTrue(any('missing.css' in x for x in r['warnings']))
        self.assertTrue(any('якорь' in x for x in r['issues']))
        self.assertTrue(any('LFS' in x for x in r['warnings']))
        self.write('index.html', SHELL.format('<h1>Beta</h1><img src="missing.jpg"><a href="%2e%2e/secret">x</a>'))
        r = check_site(self.root); self.assertTrue(any('отсутствует файл missing' in x for x in r['warnings']))
        self.assertTrue(any('вне сайта' in x for x in r['issues']))
        self.assertTrue(any('без alt' in x for x in r['issues']))

    def test_missing_files_are_only_warnings_and_printed_by_cli(self):
        self.write('index.html', SHELL.format('<h1>Hi</h1><img src="lost.png" alt=""><link rel="stylesheet" href="lost.css">'))
        result = check_site(self.root)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['issues'], [])
        self.assertEqual(len(result['warnings']), 2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['check', '--site', str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn('WARN:', out.getvalue())
        self.assertIn('lost.png', out.getvalue())

    def test_fallback_image_files_and_corrupt_svg_warn(self):
        self.write('index.html', SHELL.format('<span data-image-src="lost.png">fallback</span><img src="broken.svg" alt="">'))
        self.write('broken.svg', '<svg><![CDATA[unterminated')
        result = check_site(self.root)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['issues'], [])
        self.assertTrue(any('lost.png' in w for w in result['warnings']))
        self.assertTrue(any('повреждённый SVG' in w for w in result['warnings']))

    def test_blocked_without_site_and_no_false_pass(self):
        self.assertEqual(check_site(self.root)['status'], 'BLOCKED')
        self.assertFalse(loopback_url('http://example.com:80/'))
        self.assertFalse(loopback_url('http://127.0.0.1.evil:80/'))
        self.assertFalse(loopback_url('http://localhost:80@evil:80/'))
        self.assertTrue(loopback_url('http://127.0.0.1:8080/'))

@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS') == '1', 'browser not requested')
class BrowserTests(unittest.TestCase):
    def test_compare_detects_change_missing_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'a.html').write_text(SHELL.format('<h1>Same</h1>'), encoding='utf8')
            (root/'b.html').write_text(SHELL.format('<h1>Same</h1>'), encoding='utf8')
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                def run(): return compare(base+'/a.html', base+'/b.html', 390, 844, Path('.work/tests')/uuid.uuid4().hex)
                r = run(); self.assertEqual(r['status'], 'INCOMPLETE', r)
                html = SHELL.format("""<h1>Same</h1><button type="button" onclick="this.textContent='Opened'">Open</button>""")
                (root/'a.html').write_text(html, encoding='utf8'); (root/'b.html').write_text(html, encoding='utf8')
                action_result = compare(base+'/a.html', base+'/b.html', 390, 844, Path('.work/tests')/uuid.uuid4().hex, actions=[{'type':'click','selector':'button'}])
                self.assertEqual(action_result['status'], 'INCOMPLETE', action_result)
                self.assertIn('Opened', action_result['observed'][0]['text'])
                (root/'a.html').write_text(SHELL.format('<h1>Same</h1>'), encoding='utf8')
                (root/'b.html').write_text(SHELL.format('<h1>Different</h1><button>button</button><div style="height:2000px"></div>'), encoding='utf8')
                r = run(); self.assertEqual(r['status'], 'FAIL', r); self.assertTrue(r['mismatches'])
                missing_html = SHELL.format('<h1>Same</h1><img src="missing.png" alt="">')
                (root/'a.html').write_text(missing_html, encoding='utf8')
                (root/'b.html').write_text(missing_html, encoding='utf8')
                r = run(); self.assertEqual(r['status'], 'INCOMPLETE', r)
                self.assertTrue(any('missing.png' in w for w in r['warnings']))
                self.assertFalse(r['issues'])
                missing_page = compare(base+'/nonexistent.html', base+'/b.html', 390, 844, Path('.work/tests')/uuid.uuid4().hex)
                self.assertEqual(missing_page['status'], 'BLOCKED', missing_page)
            finally:
                server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__': unittest.main()
