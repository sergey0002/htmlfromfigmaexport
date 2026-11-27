"""Fault tests for the gated publication prototype, using synthetic trees only.

The real eligibility gate remains closed. Mocking plan here tests transaction
mechanics, not permission to publish or filesystem crash durability.
"""
import errno
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import publication
from test_publication_transaction import cd, fixture, report


@unittest.skipUnless(os.name == 'posix', 'publication prototype requires POSIX flock')
class PublicationFaultMatrixTests(unittest.TestCase):
    def setup_publication(self, root, existing=True):
        src, work, target, current = fixture(root, existing=existing)
        approved = {**current, 'apply_allowed': True}
        path, digest = report(work, approved)
        return src, work, target, approved, path, digest

    def test_apply_rename_errors_before_and_after_each_move(self):
        for existing, number, timing, error in (
            (True, 1, 'before', errno.EACCES), (True, 1, 'after', errno.EIO),
            (True, 2, 'before', errno.ENOSPC), (True, 2, 'after', errno.EIO),
            (False, 1, 'before', errno.ENOSPC), (False, 1, 'after', errno.EIO),
        ):
            with self.subTest(existing=existing, rename=number, timing=timing), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src, work, target, approved, path, digest = self.setup_publication(Path.cwd(), existing)
                original = os.rename
                count = 0
                def fail_rename(*args, **kwargs):
                    nonlocal count
                    count += 1
                    if count == number and timing == 'before':
                        raise OSError(error, 'injected before rename')
                    result = original(*args, **kwargs)
                    if count == number and timing == 'after':
                        raise OSError(error, 'injected after rename')
                    return result
                with patch('tools.publication.plan', return_value=approved), patch('os.rename', side_effect=fail_rename):
                    with self.assertRaises(publication.PublicationUncertain):
                        publication.apply(src, path, digest, True)
                run = next((work/'publications').iterdir())
                state = publication.inspect(src, run.name)
                if existing and number == 1 and timing == 'before':
                    self.assertEqual(state['target_state'], 'old')
                    self.assertFalse(state['backup_valid'])
                    with self.assertRaises(ValueError):
                        publication.restore(src, run.name, state['target_snapshot'], True)
                    self.assertEqual((target/'index.html').read_text(), 'old user data')
                else:
                    self.assertTrue(state['backup_valid'])
                    publication.restore(src, run.name, state['target_snapshot'] or 'absent', True)
                    if existing:
                        self.assertEqual((target/'index.html').read_text(), 'old user data')
                        self.assertEqual((run/'previous/old.css').read_text(), 'must preserve')
                    else:
                        self.assertFalse(target.exists())
                    if state['target_state'] == 'new':
                        self.assertIn('new version', (run/'recovery-preserved/index.html').read_text())
                    else:
                        self.assertIn('new version', (run/'next/index.html').read_text())

    def test_apply_directory_sync_failures_after_rename_preserve_both_versions(self):
        for move in (1, 2):
            for directory in ('target-parent', 'run'):
                for timing in ('before', 'after'):
                    with self.subTest(move=move, directory=directory, timing=timing), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                        src, work, target, approved, path, digest = self.setup_publication(Path.cwd())
                        original_rename = os.rename
                        original_sync = publication.md._sync_dir
                        count = 0
                        def observe_rename(*args, **kwargs):
                            nonlocal count
                            result = original_rename(*args, **kwargs)
                            count += 1
                            return result
                        def fail_sync(path):
                            path = Path(path)
                            selected = path == target.parent if directory == 'target-parent' else path.parent == work/'publications'
                            if count == move and selected and timing == 'before': raise OSError(errno.EIO, 'injected before directory fsync')
                            value = original_sync(path)
                            if count == move and selected and timing == 'after': raise OSError(errno.EIO, 'injected after directory fsync')
                            return value
                        with patch('tools.publication.plan', return_value=approved), patch('os.rename', side_effect=observe_rename), patch('tools.publication.md._sync_dir', side_effect=fail_sync):
                            with self.assertRaises(publication.PublicationUncertain): publication.apply(src, path, digest, True)
                        run = next((work/'publications').iterdir())
                        state = publication.inspect(src, run.name)
                        self.assertTrue(state['backup_valid'])
                        publication.restore(src, run.name, state['target_snapshot'] or 'absent', True)
                        self.assertEqual((target/'index.html').read_text(), 'old user data')
                        self.assertEqual((run/'previous/old.css').read_text(), 'must preserve')
                        candidate = run/('recovery-preserved' if state['target_state'] == 'new' else 'next')/'index.html'
                        self.assertIn('new version', candidate.read_text())

    def test_restore_rename_errors_before_and_after_each_move_can_resume(self):
        for number, timing in ((1, 'before'), (1, 'after'), (2, 'before'), (2, 'after')):
            with self.subTest(rename=number, timing=timing), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src, work, target, approved, path, digest = self.setup_publication(Path.cwd())
                with patch('tools.publication.plan', return_value=approved):
                    result = publication.apply(src, path, digest, True)
                run = work/'publications'/result['publication_id']
                state = publication.inspect(src, run.name)
                original = os.rename
                count = 0
                def fail_rename(*args, **kwargs):
                    nonlocal count
                    count += 1
                    if count == number and timing == 'before': raise OSError(errno.ENOSPC, 'injected before rename')
                    value = original(*args, **kwargs)
                    if count == number and timing == 'after': raise OSError(errno.EIO, 'injected after rename')
                    return value
                with patch('os.rename', side_effect=fail_rename):
                    with self.assertRaises(publication.PublicationUncertain):
                        publication.restore(src, run.name, state['target_snapshot'], True)
                state = publication.inspect(src, run.name)
                self.assertTrue(state['backup_valid'])
                self.assertIn(state['target_state'], ('new', 'old', 'absent'))
                publication.restore(src, run.name, state['target_snapshot'] or 'absent', True)
                self.assertEqual((target/'index.html').read_text(), 'old user data')
                self.assertEqual((run/'previous/old.css').read_text(), 'must preserve')
                self.assertIn('new version', (run/'recovery-preserved/index.html').read_text())
                final = publication.inspect(src, run.name)
                self.assertEqual(final['journal']['phase'], 'restored')
                self.assertEqual(publication.restore(src, run.name, final['target_snapshot'], True)['operation'], 'not_applied')

    def test_restore_journal_error_before_and_after_commit_can_resume(self):
        for phase in ('recovery_saved', 'restored'):
            for timing in ('before', 'after'):
                with self.subTest(phase=phase, timing=timing), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                    src, work, target, approved, path, digest = self.setup_publication(Path.cwd())
                    with patch('tools.publication.plan', return_value=approved):
                        result = publication.apply(src, path, digest, True)
                    run = work/'publications'/result['publication_id']
                    state = publication.inspect(src, run.name)
                    original = publication._journal
                    def fail_journal(directory, journal):
                        if journal['phase'] == phase and timing == 'before': raise OSError(errno.ENOSPC, 'injected before journal')
                        original(directory, journal)
                        if journal['phase'] == phase and timing == 'after': raise OSError(errno.EIO, 'injected after journal')
                    with patch('tools.publication._journal', side_effect=fail_journal):
                        with self.assertRaises(publication.PublicationUncertain):
                            publication.restore(src, run.name, state['target_snapshot'], True)
                    state = publication.inspect(src, run.name)
                    self.assertTrue(state['backup_valid'])
                    publication.restore(src, run.name, state['target_snapshot'] or 'absent', True)
                    self.assertEqual((target/'index.html').read_text(), 'old user data')
                    self.assertIn('new version', (run/'recovery-preserved/index.html').read_text())
                    self.assertEqual((run/'previous/old.css').read_text(), 'must preserve')

    def test_inspection_and_cli_disclose_metadata_limitations_and_restore_mode(self):
        import contextlib
        import io
        import json
        import stat
        from tools.cli import main
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src, work, target, approved, path, digest = self.setup_publication(Path.cwd())
            (target/'index.html').chmod(0o644)
            with patch('tools.publication.plan', return_value=approved):
                result = publication.apply(src, path, digest, True)
            run = work/'publications'/result['publication_id']
            state = publication.inspect(src, run.name)
            self.assertTrue(state['metadata_policy_recorded']); self.assertIn('ctime', state['limitations'][0])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['publication-inspect', '--source', str(src), '--id', run.name, '--json'])
            self.assertEqual(code, 2)
            self.assertIn('ACL', json.loads(output.getvalue())['warnings'][0])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['publication-inspect', '--source', str(src), '--id', run.name])
            self.assertEqual(code, 2); self.assertIn('Метаданные: цель=', output.getvalue())
            restored = publication.restore(src, run.name, state['target_snapshot'], True)
            self.assertTrue(restored['limitations'])
            self.assertEqual(stat.S_IMODE((run/'previous/index.html').stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE((target/'index.html').stat().st_mode), 0o644)

    def test_restore_rechecks_target_backup_journal_and_copy_after_preparation(self):
        for changed in ('target', 'backup', 'journal', 'restore-copy'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src, work, target, approved, path, digest = self.setup_publication(Path.cwd())
                with patch('tools.publication.plan', return_value=approved):
                    result = publication.apply(src, path, digest, True)
                run = work/'publications'/result['publication_id']
                state = publication.inspect(src, run.name)
                original = publication._copy_snapshot
                def copy_then_change(source, destination, snapshot):
                    original(source, destination, snapshot)
                    if changed == 'target': (target/'index.html').write_text('external edit')
                    elif changed == 'backup': (run/'previous/index.html').write_text('backup changed')
                    elif changed == 'journal':
                        journal = run/'journal.json'
                        journal.write_text(journal.read_text().replace('published_unverified', 'postcheck_started'))
                    else: (destination/'index.html').write_text('partial tampering')
                with patch('tools.publication._copy_snapshot', side_effect=copy_then_change):
                    with self.assertRaisesRegex(publication.PublicationUncertain, 'изменились|отличается'):
                        publication.restore(src, run.name, state['target_snapshot'], True)
                self.assertFalse((run/'recovery-preserved').exists())
                if changed == 'target': self.assertEqual((target/'index.html').read_text(), 'external edit')
                else: self.assertIn('new version', (target/'index.html').read_text())

    def test_sigkill_during_restore_preserves_versions_and_requires_lock_clear(self):
        repo = Path(__file__).resolve().parent.parent
        script = '''import os, sys
sys.path.insert(0, sys.argv[1])
from tools import publication
kind, point = sys.argv[5], sys.argv[6]
if kind == 'rename':
    original = os.rename
    calls = 0
    def kill_after(*args, **kwargs):
        global calls
        value = original(*args, **kwargs)
        calls += 1
        if calls == int(point): os.kill(os.getpid(), 9)
        return value
    os.rename = kill_after
else:
    original = publication._journal
    def kill_after(run, journal):
        original(run, journal)
        if journal['phase'] == point: os.kill(os.getpid(), 9)
    publication._journal = kill_after
publication.restore(sys.argv[2], sys.argv[3], sys.argv[4], True)
'''
        for kind, point in (('rename','1'), ('rename','2'), ('journal','recovery_saved'), ('journal','restored')):
            with self.subTest(kind=kind, point=point), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src, work, target, approved, path, digest = self.setup_publication(Path.cwd())
                with patch('tools.publication.plan', return_value=approved):
                    result = publication.apply(src, path, digest, True)
                run = work/'publications'/result['publication_id']
                state = publication.inspect(src, run.name)
                proc = subprocess.run([sys.executable, '-c', script, str(repo), str(src), run.name,
                                       state['target_snapshot'], kind, point], timeout=20, capture_output=True, text=True)
                self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stdout+'\n'+proc.stderr)
                state = publication.inspect(src, run.name)
                self.assertTrue(state['backup_valid'])
                self.assertTrue((work/'.queue.lock').exists())
                with self.assertRaises(OSError): publication.restore(src, run.name, state['target_snapshot'] or 'absent', True)
                publication.restore(src, run.name, state['target_snapshot'] or 'absent', True, clear_stale_lock=True)
                self.assertEqual((target/'index.html').read_text(), 'old user data')
                self.assertEqual((run/'previous/old.css').read_text(), 'must preserve')
                self.assertIn('new version', (run/'recovery-preserved/index.html').read_text())
                self.assertEqual(publication.inspect(src, run.name)['journal']['phase'], 'restored')
                self.assertFalse((work/'.queue.lock').exists())

    def test_sigkill_apply_checkpoints_preserve_data_and_require_explicit_recovery(self):
        repo = Path(__file__).resolve().parent.parent
        script = '''import json, os, sys
sys.path.insert(0, sys.argv[1])
from tools import publication
payload = json.loads(open(sys.argv[3]).read())['plan']
publication.plan = lambda *a, **kw: payload
kind, point = sys.argv[5], sys.argv[6]
if kind == 'rename':
    original = os.rename
    calls = 0
    def kill_after(*args, **kwargs):
        global calls
        value = original(*args, **kwargs)
        calls += 1
        if calls == int(point): os.kill(os.getpid(), 9)
        return value
    os.rename = kill_after
elif kind == 'copy':
    original = publication._copy_snapshot
    def kill_after(*args, **kwargs):
        original(*args, **kwargs)
        os.kill(os.getpid(), 9)
    publication._copy_snapshot = kill_after
else:
    original = publication._journal
    def kill_after(run, journal):
        original(run, journal)
        if journal['phase'] == point: os.kill(os.getpid(), 9)
    publication._journal = kill_after
publication.apply(sys.argv[2],sys.argv[3],sys.argv[4],True)
'''
        cases = [('journal',phase) for phase in ('preparing','prepared','installed','postcheck_started','published_unverified')]
        cases += [('copy','complete'),('rename','1')]
        for existing in (True,False):
            checkpoints = cases + ([('journal','backup_moved'),('rename','2')] if existing else [])
            for kind, point in checkpoints:
                with self.subTest(existing=existing, kind=kind, point=point), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                    src, work, target, approved, path, digest = self.setup_publication(Path.cwd(), existing)
                    proc = subprocess.run([sys.executable,'-c',script,str(repo),str(src),str(path),digest,kind,point],
                                          timeout=25,capture_output=True,text=True)
                    self.assertEqual(proc.returncode,-signal.SIGKILL,proc.stdout+'\n'+proc.stderr)
                    runs=list((work/'publications').iterdir()); self.assertEqual(len(runs),1)
                    run=runs[0]; state=publication.inspect(src,run.name)
                    self.assertTrue((work/'.queue.lock').exists())
                    self.assertIn('new version',(work/'deliveries/candidate/index.html').read_text())
                    if existing and not state['backup_valid']:
                        self.assertEqual(state['target_state'],'old')
                        self.assertEqual((target/'index.html').read_text(),'old user data')
                        with self.assertRaises(ValueError):
                            publication.restore(src,run.name,state['target_snapshot'],True,clear_stale_lock=True)
                        self.assertEqual((target/'old.css').read_text(),'must preserve')
                    else:
                        self.assertTrue(state['backup_valid'])
                        with self.assertRaises(OSError):
                            publication.restore(src,run.name,state['target_snapshot'] or 'absent',True)
                        publication.restore(src,run.name,state['target_snapshot'] or 'absent',True,clear_stale_lock=True)
                        if existing:
                            self.assertEqual((target/'index.html').read_text(),'old user data')
                            self.assertEqual((run/'previous/old.css').read_text(),'must preserve')
                        else: self.assertFalse(target.exists())
                        if state['target_state']=='new':
                            self.assertIn('new version',(run/'recovery-preserved/index.html').read_text())
                        elif (run/'next').exists():
                            self.assertIn('new version',(run/'next/index.html').read_text())
                    self.assertFalse((work/'.queue.lock').exists())

    def test_preparation_failures_are_unknown_and_block_blind_apply(self):
        import contextlib
        import io
        import json
        from tools.cli import main
        for point in ('mkdir','journal','copy'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src,work,target,approved,path,digest=self.setup_publication(Path.cwd()); original_mkdir=Path.mkdir
                def mkdir_then_fail(folder,*args,**kwargs):
                    result=original_mkdir(folder,*args,**kwargs)
                    if folder.parent==work/'publications': raise OSError(errno.EIO,'injected after mkdir')
                    return result
                def partial_journal(run,journal):
                    (run/'journal.json').write_text('{"partial":'); raise OSError(errno.ENOSPC,'injected journal')
                def partial_copy(source,destination,snapshot):
                    destination.mkdir(); (destination/'partial').write_text('partial data'); raise OSError(errno.ENOSPC,'injected copy')
                fault=(patch.object(Path,'mkdir',autospec=True,side_effect=mkdir_then_fail) if point=='mkdir' else
                       patch('tools.publication._journal',side_effect=partial_journal) if point=='journal' else
                       patch('tools.publication._copy_snapshot',side_effect=partial_copy))
                output=io.StringIO()
                with patch('tools.publication.plan',return_value=approved),fault,contextlib.redirect_stdout(output):
                    code=main(['publish-apply','--source',str(src),'--plan',str(path),'--sha256',digest,'--acknowledge-offline-writers','--json'])
                self.assertEqual(code,4); self.assertEqual(json.loads(output.getvalue())['operation'],'unknown')
                runs=list((work/'publications').iterdir()); self.assertEqual(len(runs),1)
                self.assertEqual((target/'index.html').read_text(),'old user data')
                self.assertFalse((runs[0]/'previous').exists())
                with patch('tools.publication.plan',return_value=approved):
                    with self.assertRaisesRegex(ValueError,'журнал|публикация'): publication.apply(src,path,digest,True)
                self.assertEqual(list((work/'publications').iterdir()),runs)

    def test_sigkill_before_first_journal_blocks_next_apply(self):
        repo=Path(__file__).resolve().parent.parent
        script='''import json, os, sys
sys.path.insert(0,sys.argv[1])
from tools import publication
payload=json.loads(open(sys.argv[3]).read())['plan']
publication.plan=lambda *a,**kw: payload
publication._journal=lambda *args: os.kill(os.getpid(),9)
publication.apply(sys.argv[2],sys.argv[3],sys.argv[4],True)
'''
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,approved,path,digest=self.setup_publication(Path.cwd())
            proc=subprocess.run([sys.executable,'-c',script,str(repo),str(src),str(path),digest],capture_output=True,timeout=25)
            self.assertEqual(proc.returncode,-signal.SIGKILL); runs=list((work/'publications').iterdir()); self.assertEqual(len(runs),1)
            self.assertFalse((runs[0]/'journal.json').exists()); self.assertTrue((work/'.queue.lock').exists())
            self.assertEqual((target/'index.html').read_text(),'old user data')
            with self.assertRaises((OSError,ValueError)):
                publication.restore(src,runs[0].name,approved['target_snapshot'],True,clear_stale_lock=True)
            self.assertFalse((work/'.queue.lock').exists())
            with patch('tools.publication.plan',return_value=approved):
                with self.assertRaisesRegex(ValueError,'журнал'): publication.apply(src,path,digest,True)
            self.assertEqual(list((work/'publications').iterdir()),runs)
            self.assertEqual((target/'index.html').read_text(),'old user data')

    def test_unverified_publication_blocks_next_apply_until_restored(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,approved,path,digest=self.setup_publication(Path.cwd())
            with patch('tools.publication.plan',return_value=approved): first=publication.apply(src,path,digest,True)
            run=work/'publications'/first['publication_id']; state=publication.inspect(src,run.name)
            current=publication.plan(src,approved['delivery_record'],target); next_plan={**current,'apply_allowed':True}; path,digest=report(work,next_plan)
            with patch('tools.publication.plan',return_value=next_plan):
                with self.assertRaisesRegex(ValueError,'не завершена'): publication.apply(src,path,digest,True)
            self.assertEqual(len(list((work/'publications').iterdir())),1)
            publication.restore(src,run.name,state['target_snapshot'],True)
            restored=publication.plan(src,approved['delivery_record'],target); next_plan={**restored,'apply_allowed':True}; path,digest=report(work,next_plan)
            with patch('tools.publication.plan',return_value=next_plan): second=publication.apply(src,path,digest,True)
            self.assertNotEqual(second['publication_id'],first['publication_id'])
            self.assertEqual((run/'previous/old.css').read_text(),'must preserve')

    def test_interrupted_restore_copy_is_retained_and_never_overwritten(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src, work, target, approved, path, digest = self.setup_publication(Path.cwd())
            with patch('tools.publication.plan', return_value=approved):
                result = publication.apply(src, path, digest, True)
            run = work/'publications'/result['publication_id']
            state = publication.inspect(src, run.name)
            def partial_copy(source, destination, snapshot):
                destination.mkdir()
                (destination/'partial').write_text('partial copy')
                raise OSError(errno.ENOSPC, 'injected during backup copy')
            with patch('tools.publication._copy_snapshot', side_effect=partial_copy):
                with self.assertRaises(publication.PublicationUncertain): publication.restore(src, run.name, state['target_snapshot'], True)
            partial=publication.inspect(src,run.name)
            self.assertIsNotNone(partial['restore_copy_snapshot']); self.assertFalse(partial['restore_copy_valid'])
            self.assertIn('new version', (target/'index.html').read_text())
            self.assertEqual((run/'previous/old.css').read_text(), 'must preserve')
            with self.assertRaisesRegex(ValueError, 'копия восстановления отличается'):
                publication.restore(src, run.name, state['target_snapshot'], True)
            self.assertEqual((run/'restore-copy/partial').read_text(), 'partial copy')
            self.assertIn('new version', (target/'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
