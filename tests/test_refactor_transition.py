import contextlib
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.cli import main
from tools.core import analyze
from tools.queue import save
from tools.facts import scan_facts


@contextlib.contextmanager
def cd(path):
    previous = os.getcwd(); os.chdir(path)
    try: yield
    finally: os.chdir(previous)


def invoke(*args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main([*args, '--json'])
    return code, json.loads(output.getvalue())


def fixture(root):
    src=root/'source'; src.mkdir(); (src/'package.json').write_text('{}'); (src/'index.html').write_text('<a href="/icons/search.svg">search</a>')
    (src/'app.js').write_text('const icon = "/icons/search.svg";')
    data={'schema_version':1,'source':{'fingerprint':analyze(src)['fingerprint']},
          'discovery':{'status':'unconfirmed','unresolved':['review manually']},'unresolved_links':[],
          'pages':[{'id':'home','title':'Home','reference_route':'/','output':'index.html',
                    'confirmation':'candidate','work_status':'pending','states':[],
                    'checks':{'static':'checked','browser':'not_run','manual':'not_run'}}]}
    save(src/'.work/manifest.json',data,create=True)
    return src


class TransitionTests(unittest.TestCase):
    def test_fact_scan_and_discover_do_not_update_manifest(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); path=src/'.work/manifest.json'; before=path.read_bytes()
            facts=scan_facts(src, include_text=True); self.assertTrue(any(f.get('value')=='/icons/search.svg' for f in facts['facts']))
            code, result=invoke('discover','--source',str(src),'--limit','2')
            self.assertEqual(code,2); self.assertEqual(len(result['facts']),2); self.assertGreater(result['facts_total'],2)
            self.assertNotIn('pages',result); self.assertEqual(before,path.read_bytes())

    def test_fact_values_require_explicit_opt_in_and_filter(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); (src/'secrets.js').write_text('const token = "SYNTHETIC_SECRET";')
            code,result=invoke('discover','--source',str(src))
            self.assertEqual(code,2); self.assertNotIn('SYNTHETIC_SECRET',json.dumps(result))
            self.assertFalse(result['text_included'])
            code,result=invoke('discover','--source',str(src),'--include-source-text','--file','secrets.js')
            self.assertEqual(code,2); self.assertIn('SYNTHETIC_SECRET',json.dumps(result))
            self.assertTrue(all(x['file']=='secrets.js' for x in result['facts']))
            self.assertTrue(result['warnings'])

    def test_queue_read_only_computes_stale_without_writing(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); path=src/'.work/manifest.json'; md=src/'.work/PAGE-QUEUE.md'
            before=(path.read_bytes(),md.read_bytes())
            code,result=invoke('queue','--source',str(src))
            self.assertEqual(code,2); self.assertEqual(result['pages'][0]['checks']['static'],'stale')
            self.assertEqual((path.read_bytes(),md.read_bytes()),before)
            self.assertEqual(result['manifest_sha256'],hashlib.sha256(before[0]).hexdigest())

    def test_invalid_report_is_rejected_before_queue_mutation(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); path=src/'.work/manifest.json'; before=path.read_bytes()
            code,result=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--report',str(Path.cwd()/'bad.json'))
            self.assertEqual(code,3); self.assertEqual(result['operation'],'not_applied'); self.assertEqual(path.read_bytes(),before)
            self.assertFalse((Path.cwd()/'bad.json').exists())

    def test_existing_report_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); report=src/'.work/report.json'; report.write_text('keep')
            code,_=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--report',str(report))
            self.assertEqual(code,3); self.assertEqual(report.read_text(),'keep')
            self.assertEqual(json.loads((src/'.work/manifest.json').read_text())['pages'][0]['confirmation'],'candidate')

    def test_report_failure_after_mutation_reports_unknown_with_result(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); report=src/'.work/report.json'; real=os.fsync; calls=[]
            def fail_last(fd):
                calls.append(fd)
                if len(calls)==3: raise OSError('injected report error')
                return real(fd)
            with patch('tools.cli.os.fsync',side_effect=fail_last):
                code,result=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--report',str(report))
            self.assertEqual(code,4); self.assertEqual(result['operation'],'unknown')
            self.assertEqual(result['command_result']['status'],'INCOMPLETE')
            self.assertEqual(json.loads((src/'.work/manifest.json').read_text())['pages'][0]['confirmation'],'confirmed')

    def test_report_paths_cannot_create_service_files_or_overlap_command_paths(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); work=src/'.work'; before=(work/'manifest.json').read_bytes()
            forbidden=['.queue.lock','.queue-md-active','.queue-md-head.json','manifest.json','PAGE-QUEUE.md',
                       'queue-history/bad.json','migrations/bad.json','run-records/bad.json','reports',
                       'reports/.hidden/result.json','reports/../bad.json']
            for value in forbidden:
                with self.subTest(value=value):
                    path=work/value
                    code,result=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--report',str(path))
                    self.assertEqual(code,3); self.assertEqual(result['operation'],'not_applied')
                    self.assertEqual(result['report_operation'],'not_applied'); self.assertEqual((work/'manifest.json').read_bytes(),before)
                    if value not in ('manifest.json','PAGE-QUEUE.md'): self.assertFalse(path.exists())
            output=work/'proposal.json'
            code,result=invoke('queue-md','template','--source',str(src),'--output',str(output),'--report',str(output))
            self.assertEqual(code,3); self.assertEqual(result['report_operation'],'not_applied'); self.assertFalse(output.exists())
            path=work/'reports'/'nested'/'snapshot.json'
            code,result=invoke('snapshot','--root',str(work/'reports'),'--kind','delivery','--report',str(path))
            self.assertEqual(code,3); self.assertFalse(path.exists())

    def test_successful_report_has_separate_stdout_outcome(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); report=src/'.work/reports/run/report.json'
            code,result=invoke('queue','--source',str(src),'--report',str(report))
            self.assertEqual(code,2); self.assertEqual(result['operation'],'not_applied'); self.assertEqual(result['report_operation'],'applied')
            saved=json.loads(report.read_text()); self.assertEqual(saved['operation'],'not_applied')
            self.assertNotIn('report_operation',saved)

    def test_plain_output_shows_report_outcome(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); report=src/'.work/reports/plain.json'; output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=main(['queue','--source',str(src),'--report',str(report)])
            self.assertEqual(code,2); self.assertIn('report_operation=applied',output.getvalue())
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=main(['queue','--source',str(src),'--report',str(src/'.work/.queue.lock')])
            self.assertEqual(code,3); self.assertIn('report_operation=not_applied',output.getvalue())

    def test_reservation_fault_is_unknown_before_command_and_preserves_partial_files(self):
        for point in ('mkdir','open'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src=fixture(Path.cwd()); work=src/'.work'; before=(work/'manifest.json').read_bytes(); report=work/'reports'/'run'/'report.json'
                original_mkdir=Path.mkdir; original_open=os.open
                def fail_mkdir(path,*args,**kwargs):
                    value=original_mkdir(path,*args,**kwargs)
                    if path==report.parent: raise OSError('injected after mkdir')
                    return value
                def fail_open(path,*args,**kwargs):
                    fd=original_open(path,*args,**kwargs)
                    if Path(path)==report:
                        os.close(fd); raise OSError('injected after open')
                    return fd
                fault=patch.object(Path,'mkdir',autospec=True,side_effect=fail_mkdir) if point=='mkdir' else patch('tools.cli.os.open',side_effect=fail_open)
                with fault:
                    code,result=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--report',str(report))
                self.assertEqual(code,4); self.assertEqual(result['operation'],'not_applied'); self.assertEqual(result['report_operation'],'unknown')
                self.assertTrue(report.parent.exists()); self.assertEqual(report.exists(),point=='open')
                self.assertEqual((work/'manifest.json').read_bytes(),before)

    def test_report_directory_sync_failure_does_not_erase_command_result(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); report=src/'.work/reports/report.json'
            with patch('tools.cli.queue_md._sync_dir',side_effect=OSError('directory fsync failed')):
                code,result=invoke('queue','--source',str(src),'--report',str(report))
            self.assertEqual(code,4); self.assertEqual(result['report_operation'],'unknown')
            self.assertEqual(result['command_result']['operation'],'not_applied')
            self.assertNotIn('report_operation',json.loads(report.read_text()))

    def test_unexpected_command_error_still_finalizes_report(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); report=src/'.work/reports/error.json'
            with patch('tools.cli.analyze',side_effect=RuntimeError('injected unexpected failure')):
                code,result=invoke('analyze','--source',str(src),'--report',str(report))
            self.assertEqual(code,4); self.assertEqual(result['operation'],'unknown'); self.assertEqual(result['report_operation'],'applied')
            self.assertEqual(json.loads(report.read_text())['status'],'ERROR')

    def test_report_serialization_failure_preserves_command_status_and_closes_reservation(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); report=src/'.work/reports/error.json'
            with patch('tools.cli.analyze',return_value={'status':'INCOMPLETE','operation':'not_applied','bad':object()}):
                code,result=invoke('analyze','--source',str(src),'--report',str(report))
            self.assertEqual(code,4); self.assertEqual(result['report_operation'],'unknown')
            self.assertEqual(result['command_result'],{'status':'INCOMPLETE','operation':'not_applied'})
            self.assertTrue(report.exists()); self.assertEqual(report.read_bytes(),b'')

    @unittest.skipUnless(os.name=='posix','SIGKILL semantics require POSIX')
    def test_sigkill_report_reservation_and_post_command_are_not_safe_to_retry(self):
        repo=str(Path(__file__).resolve().parents[1])
        for point in ('reserve','write'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src=fixture(Path.cwd()); report=src/'.work/reports/report.json'; manifest=src/'.work/manifest.json'; before=manifest.read_bytes()
                script='''import os, sys
from pathlib import Path
from tools.cli import main
if sys.argv[3]=='reserve':
    original=os.open
    def stop(path,*args,**kwargs):
        fd=original(path,*args,**kwargs)
        if Path(path)==Path(sys.argv[2]): os.kill(os.getpid(),9)
        return fd
    os.open=stop
else:
    original=os.fsync
    count=0
    def stop(fd):
        global count
        count+=1
        if count==3: os.kill(os.getpid(),9)
        return original(fd)
    os.fsync=stop
main(['queue-update','--source',sys.argv[1],'--page','home','--confirm-page','--report',sys.argv[2],'--json'])
'''
                env={**os.environ,'PYTHONPATH':repo}
                proc=subprocess.run([sys.executable,'-c',script,str(src),str(report),point],env=env,capture_output=True)
                self.assertEqual(proc.returncode,-signal.SIGKILL); self.assertEqual(proc.stdout,b''); self.assertTrue(report.exists())
                if point=='reserve': self.assertEqual(manifest.read_bytes(),before); self.assertEqual(report.read_bytes(),b'')
                else: self.assertEqual(json.loads(manifest.read_text())['pages'][0]['confirmation'],'confirmed')
                code,result=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--report',str(report))
                self.assertEqual(code,3); self.assertEqual(result['report_operation'],'not_applied')

    @unittest.skipUnless(hasattr(os,'symlink'),'symlinks unavailable')
    def test_report_rejects_symlink_components_before_mutation(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); work=src/'.work'; outside=Path.cwd()/'outside'; outside.mkdir()
            (work/'reports').symlink_to(outside,target_is_directory=True)
            before=(work/'manifest.json').read_bytes()
            code,result=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--report',str(work/'reports/a.json'))
            self.assertEqual(code,3); self.assertEqual(result['report_operation'],'not_applied')
            self.assertEqual((work/'manifest.json').read_bytes(),before); self.assertEqual(list(outside.iterdir()),[])

    def test_unclassified_discovery_notes_block_confirmation(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src=fixture(Path.cwd()); before=(src/'.work/manifest.json').read_bytes()
            code,result=invoke('queue-update','--source',str(src),'--page','home','--confirm-page','--confirm-discovery','--reason','reviewed')
            self.assertEqual(code,3); self.assertIn('не классифицированы',result['issues'][0]); self.assertEqual((src/'.work/manifest.json').read_bytes(),before)
