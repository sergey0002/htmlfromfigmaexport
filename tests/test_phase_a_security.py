import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from tools.cli import main
from tools.core import analyze, fingerprint
from tools.lifecycle import record, serve_site
from tools.queue import save


def setup(root):
    src = root / 'source'; src.mkdir()
    (src / 'package.json').write_text('{}'); (src / 'package-lock.json').write_text('{}')
    (src / 'index.html').write_text('source')
    stage = src / '.work' / 'staging' / 'run'; stage.mkdir(parents=True)
    (stage / 'index.html').write_text('candidate')
    evidence = src / '.work' / 'manual.txt'; evidence.write_text('review')
    data = {'schema_version': 1, 'source': {'fingerprint': analyze(src)['fingerprint']},
            'discovery': {'status': 'unconfirmed'}, 'unresolved_links': [],
            'pages': [{'id': 'home', 'title': 'Home', 'reference_route': '/', 'output': 'index.html',
                       'confirmation': 'confirmed', 'work_status': 'pending', 'states': [],
                       'checks': {'manual': 'not_run'}}]}
    save(src / '.work' / 'manifest.json', data, create=True)
    return src, stage, evidence


class RecordFailureTests(unittest.TestCase):
    def test_failure_after_first_replace_is_unknown_not_blocked(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src, site, ev = setup(Path(tmp).absolute()); m = src / '.work' / 'manifest.json'
            before, markdown = m.read_bytes(), (src / '.work' / 'PAGE-QUEUE.md').read_bytes()
            original = os.replace; calls = []
            def fail_second(a, b):
                calls.append((a, b))
                if len(calls) == 2: raise OSError('injected second replacement failure')
                return original(a, b)
            out = io.StringIO()
            with patch('tools.queue.os.replace', side_effect=fail_second), contextlib.redirect_stdout(out):
                code = main(['record-check','--source',str(src),'--site',str(site),'--page','home',
                             '--kind','manual','--status','review','--evidence',str(ev),'--json'])
            result = json.loads(out.getvalue())
            self.assertEqual(code, 4); self.assertEqual(result['operation'], 'unknown')
            self.assertNotEqual(before, m.read_bytes())
            self.assertEqual(markdown, (src / '.work' / 'PAGE-QUEUE.md').read_bytes())

    def test_direct_record_signals_uncertain_save(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src, site, ev = setup(Path(tmp).absolute())
            with patch('tools.lifecycle.save', side_effect=OSError('injected')):
                with self.assertRaisesRegex(OSError, 'неизвест'):
                    record(src, site, 'home', 'manual', 'review', ev)


    def test_faults_at_each_save_stage_never_report_not_applied(self):
        for operation, failure in (('replace', 1), ('replace', 2), ('fsync', 1), ('fsync', 2)):
            with self.subTest(operation=operation, failure=failure), tempfile.TemporaryDirectory(dir='.') as tmp:
                src, site, ev = setup(Path(tmp).absolute())
                manifest = src / '.work' / 'manifest.json'
                before = manifest.read_bytes()
                original = getattr(os, operation); calls = []
                def fail(*args):
                    calls.append(args)
                    if len(calls) == failure: raise OSError('injected')
                    return original(*args)
                out = io.StringIO()
                with patch('tools.queue.os.' + operation, side_effect=fail), contextlib.redirect_stdout(out):
                    code = main(['record-check', '--source', str(src), '--site', str(site), '--page', 'home',
                                 '--kind', 'manual', '--status', 'review', '--evidence', str(ev), '--json'])
                self.assertEqual(code, 4)
                self.assertEqual(json.loads(out.getvalue())['operation'], 'unknown')
                self.assertEqual(manifest.read_bytes() != before, failure == 2)

    def test_report_failure_after_record_preserves_successful_command_result(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src, site, ev = setup(Path(tmp).absolute())
            report = src / '.work' / 'report.json'; real = os.fsync; calls = []
            def fail_third(fd):
                calls.append(fd)
                if len(calls) == 3: raise OSError('injected report failure')
                return real(fd)
            out = io.StringIO()
            with patch('tools.cli.os.fsync', side_effect=fail_third), contextlib.redirect_stdout(out):
                code = main(['record-check', '--source', str(src), '--site', str(site), '--page', 'home',
                             '--kind', 'manual', '--status', 'review', '--evidence', str(ev),
                             '--report', str(report), '--json'])
            result = json.loads(out.getvalue())
            self.assertEqual(code, 4); self.assertEqual(result['operation'], 'unknown')
            self.assertEqual(result['command_result']['operation'], 'applied')
            self.assertEqual(json.loads((src/'.work/manifest.json').read_text())['pages'][0]['checks']['manual'], 'review')


class ManagedServerTests(unittest.TestCase):
    def test_refuses_site_with_work_or_secret_names(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            site=Path(tmp).absolute(); (site/'index.html').write_text('ok')
            (site/'.work').mkdir(); (site/'.work'/'private').write_text('synthetic')
            with self.assertRaises(ValueError):
                with serve_site(site/'.work'): pass
            with self.assertRaises(ValueError):
                with serve_site(site): pass
            (site/'.work'/'private').unlink(); (site/'.work').rmdir()
            (site/'.env.production').write_text('synthetic')
            with self.assertRaises(ValueError):
                with serve_site(site): pass

    def test_denies_new_hidden_paths_and_symlinks_during_serving(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            site=Path(tmp).absolute(); (site/'index.html').write_text('ok')
            with serve_site(site) as base:
                self.assertEqual(urlopen(base + '/', timeout=2).read(), b'ok')
                (site/'.work').mkdir(); (site/'.work'/'private').write_text('synthetic')
                for path in ('/.work/private','/%2ework/private','/.work%2fprivate'):
                    with self.assertRaises(HTTPError) as err: urlopen(base + path, timeout=2)
                    self.assertEqual(err.exception.code, 404)
                (site/'private').write_text('synthetic')
                with self.assertRaises(HTTPError) as err: urlopen(base + '/private', timeout=2)
                self.assertEqual(err.exception.code, 404)
                try: (site/'link').symlink_to(site/'private')
                except OSError: continue_test = False
                else: continue_test = True
                if continue_test:
                    with self.assertRaises(HTTPError) as err: urlopen(base + '/link', timeout=2)
                    self.assertEqual(err.exception.code, 404)


class LegacyFingerprintPrivacyTests(unittest.TestCase):
    def test_env_files_are_not_opened_or_silently_excluded(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src = Path(tmp)
            (src/'package.json').write_text('{}')
            (src/'index.html').write_text('source')
            env = src/'.env.production'
            env.write_text('SYNTHETIC_SECRET=do-not-read')
            real_open = Path.open
            def guarded(path, *args, **kwargs):
                if path == env: raise AssertionError('secret read')
                return real_open(path, *args, **kwargs)
            with patch('pathlib.Path.open', guarded):
                result = analyze(src)
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertNotIn('SYNTHETIC_SECRET', str(result))
                with self.assertRaises(ValueError): fingerprint(src)
            from tools.snapshot import take_snapshot
            snap = take_snapshot(src, 'source')
            self.assertIn('.env.production', [x['path'] for x in snap['excluded']])

    def test_fingerprint_keeps_legacy_identity_for_trees_without_env(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            import hashlib
            root = Path(tmp); (root/'a').write_bytes(b'one'); (root/'b').write_bytes(b'two')
            legacy = hashlib.sha256(b'a\0one\0b\0two\0').hexdigest()
            self.assertEqual(fingerprint(root), legacy)

    def test_legacy_refuses_nested_work_without_reading_files(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=Path(tmp); (src/'package.json').write_text('{}'); (src/'index.html').write_text('source')
            nested=src/'nested'/'.work'; nested.mkdir(parents=True); (nested/'sensitive.txt').write_text('secret')
            self.assertEqual(analyze(src)['status'],'BLOCKED')
            with self.assertRaises(ValueError): fingerprint(src)
            from tools.snapshot import take_snapshot
            self.assertIn('nested/.work',[x['path'] for x in take_snapshot(src,'source')['excluded']])

    def test_analyze_redacts_untrusted_source_values_unless_explicit(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=Path(tmp); (src/'index.html').write_text('source')
            (src/'package.json').write_text(json.dumps({'scripts':{'dev':'echo SYNTHETIC_SECRET'}, 'dependencies':{'vite':'https://token.example/SYNTHETIC_SECRET'}}))
            (src/'app.js').write_text('<img src="/SYNTHETIC_SECRET">')
            default=analyze(src)
            self.assertNotIn('SYNTHETIC_SECRET',json.dumps(default))
            self.assertEqual(default['missing_literal_assets_count'],1)
            self.assertIn('SYNTHETIC_SECRET',json.dumps(analyze(src,include_source_text=True)))
