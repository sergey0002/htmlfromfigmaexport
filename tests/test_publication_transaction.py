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

from tools import queue_md as md, publication
from tools.cli import main
from tools.delivery import materialize


@contextlib.contextmanager
def cd(path):
    old=os.getcwd(); os.chdir(path)
    try: yield
    finally: os.chdir(old)


def fixture(root, existing=True, invalid=False):
    src=root/'source'; src.mkdir(); (src/'index.html').write_text('source')
    work=src/'.work'; work.mkdir(); site=work/'staging'/'candidate'; site.mkdir(parents=True)
    (site/'index.html').write_text('<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Test</title></head><body><main><h1>new version</h1></main></body></html>')
    if invalid: (site/'index.html').write_text('<html>invalid fixture</html>')
    (site/'empty').mkdir()
    proposal=work/'p.md'; md.write_template(src,proposal); md.commit(src,proposal,'absent','initial')
    selection=work/'selection.json'; selection.write_text(json.dumps(['index.html','empty']))
    delivery=materialize(src,site,selection,work/'deliveries'/'candidate')
    target=root/'vanilla'
    if existing:
        target.mkdir(); (target/'index.html').write_text('old user data'); (target/'old.css').write_text('must preserve')
    plan=publication.plan(src,delivery['record'],target)
    return src,work,target,plan


def report(work, plan):
    path=work/'plan.json'; path.write_text(json.dumps({'plan':plan})); return path,hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(os.name=='posix','publication protocol requires POSIX flock')
class PublicationTransactionTests(unittest.TestCase):
    def test_public_gate_cannot_be_bypassed_by_forged_report(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); path,digest=report(work,current)
            with self.assertRaisesRegex(ValueError,'заблокирована'): publication.apply(src,path,digest,True)
            forged={**current,'apply_allowed':True}; path,digest=report(work,forged)
            with self.assertRaisesRegex(ValueError,'устарел'): publication.apply(src,path,digest,True)
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=main(['publish-apply','--source',str(src),'--plan',str(path),'--sha256',digest,'--acknowledge-offline-writers','--json'])
            self.assertEqual(code,3); self.assertEqual(json.loads(output.getvalue())['operation'],'not_applied')
            self.assertEqual((target/'index.html').read_text(),'old user data')
            self.assertFalse((work/'publications').exists())

    def test_success_then_restore_preserves_both_trees(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            # Mock ONLY the currently unavailable eligibility gate; tests of the
            # transaction machinery are not evidence that publication is safe.
            with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
            self.assertEqual(result['status'],'published_unverified'); self.assertIn('new version',(target/'index.html').read_text())
            state=publication.inspect(src,result['publication_id']); self.assertTrue(state['backup_valid']); self.assertEqual(state['target_state'],'new')
            output=io.StringIO()
            with contextlib.redirect_stdout(output): code=main(['publication-inspect','--source',str(src),'--id',result['publication_id']])
            self.assertEqual(code,2); self.assertIn('published_unverified',output.getvalue()); self.assertIn(state['target_snapshot'],output.getvalue())
            with self.assertRaises(ValueError): publication.restore(src,result['publication_id'],'0'*64,True)
            restored=publication.restore(src,result['publication_id'],state['target_snapshot'],True)
            self.assertEqual(restored['status'],'restored'); self.assertEqual((target/'index.html').read_text(),'old user data')
            run=work/'publications'/result['publication_id']
            self.assertEqual((run/'previous/old.css').read_text(),'must preserve')
            self.assertIn('new version',(run/'recovery-preserved/index.html').read_text())
            state=publication.inspect(src,result['publication_id']); self.assertEqual(state['journal']['phase'],'restored')
            self.assertEqual(publication.restore(src,result['publication_id'],state['target_snapshot'],True)['operation'],'not_applied')

    def test_failure_after_backup_is_unknown_and_restore_is_possible(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            original=os.rename; calls=[]
            def fail_second(*args):
                calls.append(args)
                if len(calls)==2: raise OSError('injected')
                return original(*args)
            with patch('tools.publication.plan',return_value=approved), patch('os.rename',side_effect=fail_second):
                with self.assertRaises(publication.PublicationUncertain): publication.apply(src,path,digest,True)
            run=next((work/'publications').iterdir()); state=publication.inspect(src,run.name)
            self.assertEqual(state['target_state'],'absent'); self.assertTrue(state['backup_valid'])
            self.assertEqual(publication.restore(src,run.name,'absent',True)['status'],'restored')
            self.assertEqual((target/'index.html').read_text(),'old user data')

    def test_restore_original_absence_preserves_new_version(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd(),existing=False); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
            state=publication.inspect(src,result['publication_id'])
            self.assertIsNone(state['journal']['old_snapshot'])
            publication.restore(src,result['publication_id'],state['target_snapshot'],True)
            self.assertFalse(target.exists())
            self.assertIn('new version',(work/'publications'/result['publication_id']/'recovery-preserved/index.html').read_text())

    def test_corrupt_backup_and_unrecognized_target_are_never_replaced(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
            run=work/'publications'/result['publication_id']; (run/'previous/index.html').write_text('tampered backup')
            state=publication.inspect(src,result['publication_id']); self.assertFalse(state['backup_valid'])
            with self.assertRaisesRegex(ValueError,'backup'): publication.restore(src,run.name,state['target_snapshot'],True)
            self.assertIn('new version',(target/'index.html').read_text())
            (target/'index.html').write_text('user edit')
            state=publication.inspect(src,run.name); self.assertEqual(state['target_state'],'unknown')
            with self.assertRaises(ValueError): publication.restore(src,run.name,state['target_snapshot'],True)
            self.assertEqual((target/'index.html').read_text(),'user edit')

    def test_interrupted_restore_can_resume(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
            state=publication.inspect(src,result['publication_id']); original=os.rename; calls=[]
            def fail_second(*args):
                calls.append(args)
                if len(calls)==2: raise OSError('injected restore failure')
                return original(*args)
            with patch('os.rename',side_effect=fail_second):
                with self.assertRaises(publication.PublicationUncertain): publication.restore(src,result['publication_id'],state['target_snapshot'],True)
            state=publication.inspect(src,result['publication_id']); self.assertEqual(state['target_state'],'absent')
            self.assertEqual(state['journal']['phase'],'recovery_saved')
            publication.restore(src,result['publication_id'],'absent',True)
            self.assertEqual((target/'index.html').read_text(),'old user data')

    def test_journal_write_failures_preserve_recoverable_data(self):
        for phase in ('preparing','prepared','backup_moved','installed','postcheck_started','published_unverified'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
                original=publication._journal
                def fail_at(run,journal):
                    if journal['phase']==phase: raise OSError('injected journal write failure')
                    return original(run,journal)
                with patch('tools.publication.plan',return_value=approved), patch('tools.publication._journal',side_effect=fail_at):
                    with self.assertRaises(publication.PublicationUncertain): publication.apply(src,path,digest,True)
                run=next((work/'publications').iterdir())
                if phase in ('preparing','prepared'):
                    self.assertEqual((target/'index.html').read_text(),'old user data')
                else:
                    state=publication.inspect(src,run.name)
                    self.assertTrue(state['backup_valid'])
                    publication.restore(src,run.name,state['target_snapshot'] or 'absent',True)
                    self.assertEqual((target/'index.html').read_text(),'old user data')

    def test_cli_reports_unknown_on_mutation_uncertainty(self):
        output=io.StringIO()
        with patch('tools.publication.apply',side_effect=publication.PublicationUncertain('synthetic failure')), contextlib.redirect_stdout(output):
            code=main(['publish-apply','--plan','unused','--sha256','0'*64,'--acknowledge-offline-writers','--json'])
        self.assertEqual(code,4); self.assertEqual(json.loads(output.getvalue())['operation'],'unknown')

    def test_real_replanning_rejects_each_input_changed_during_copy(self):
        for changed in ('source','queue','delivery','target'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
                original_plan=publication.plan; original_copy=publication._copy_snapshot
                def approved_only(*args,**kwargs):
                    return {**original_plan(*args,**kwargs),'apply_allowed':True}
                def copy_then_change(*args):
                    original_copy(*args)
                    if changed=='source': (src/'index.html').write_text('source changed')
                    elif changed=='queue':
                        queue=work/'PAGE-QUEUE.md'; queue.write_text(queue.read_text()+'external edit\n')
                    elif changed=='delivery': (work/'deliveries/candidate/index.html').write_text('delivery changed')
                    else: (target/'index.html').write_text('user edit')
                with patch('tools.publication.plan',side_effect=approved_only), patch('tools.publication._copy_snapshot',side_effect=copy_then_change):
                    with self.assertRaises(publication.PublicationUncertain): publication.apply(src,path,digest,True)
                self.assertEqual((target/'index.html').read_text(),'user edit' if changed=='target' else 'old user data')
                run=next((work/'publications').iterdir()); self.assertFalse((run/'previous').exists())

    def test_postcheck_fail_records_failure_and_allows_explicit_restore(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd(),invalid=True); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            with patch('tools.publication.plan',return_value=approved):
                with self.assertRaises(publication.PublicationUncertain): publication.apply(src,path,digest,True)
            run=next((work/'publications').iterdir()); state=publication.inspect(src,run.name)
            self.assertEqual(state['journal']['phase'],'postcheck_failed')
            self.assertEqual(state['journal']['postcheck']['status'],'FAIL')
            publication.restore(src,run.name,state['target_snapshot'],True)
            self.assertEqual((target/'index.html').read_text(),'old user data')

    def test_blocked_or_inconsistent_postcheck_is_unknown_and_never_published(self):
        for case in ('blocked','exception','bad-status','incomplete-with-issues','missing-warnings','snapshot-mismatch'):
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
                baseline=publication.diagnostic(src,work/'deliveries/candidate')
                post={**baseline,'status':'INCOMPLETE','issues':[]}
                if case=='blocked': post.update(status='BLOCKED',issues=['synthetic postcheck blocker'])
                elif case=='bad-status': post['status']='PASS'
                elif case=='incomplete-with-issues': post['issues']=['hidden failure']
                elif case=='missing-warnings': post.pop('warnings')
                elif case=='snapshot-mismatch': post['delivery_snapshot']='0'*64
                if case=='exception': effect=OSError('synthetic postcheck failure')
                else: effect=None
                with patch('tools.publication.plan',return_value=approved), patch('tools.publication.diagnostic',return_value=post,side_effect=effect):
                    with self.assertRaises(publication.PublicationUncertain): publication.apply(src,path,digest,True)
                    with self.assertRaises(ValueError): publication.apply(src,path,digest,True)
                run=next((work/'publications').iterdir()); state=publication.inspect(src,run.name)
                self.assertEqual(state['journal']['phase'],'postcheck_failed' if case=='blocked' else 'postcheck_started')
                if case=='blocked': self.assertEqual(state['journal']['postcheck']['status'],'BLOCKED')
                self.assertEqual(state['target_state'],'new'); self.assertTrue(state['backup_valid'])
                publication.restore(src,run.name,state['target_snapshot'],True)
                self.assertEqual((target/'index.html').read_text(),'old user data')
                self.assertIn('new version',(run/'recovery-preserved/index.html').read_text())

    def test_postcheck_rechecks_inputs_and_metadata_after_first_diagnostic(self):
        for changed in ('source','queue','target','target-mode'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
                original=publication.diagnostic; calls=0
                def drift_after(*args):
                    nonlocal calls
                    result=original(*args); calls+=1
                    if calls==1:
                        if changed=='source': (src/'index.html').write_text('source changed during postcheck')
                        elif changed=='queue':
                            queue=work/'PAGE-QUEUE.md'; queue.write_text(queue.read_text()+'external change\n')
                        elif changed=='target': (target/'index.html').write_text('external target change')
                        else: (target/'index.html').chmod(0o644 if (target/'index.html').stat().st_mode & 0o077 == 0 else 0o600)
                    return result
                with patch('tools.publication.plan',return_value=approved),patch('tools.publication.diagnostic',side_effect=drift_after):
                    with self.assertRaises(publication.PublicationUncertain): publication.apply(src,path,digest,True)
                run=next((work/'publications').iterdir()); state=publication.inspect(src,run.name)
                self.assertEqual(state['journal']['phase'],'postcheck_started'); self.assertTrue(state['backup_valid'])
                self.assertEqual((run/'previous/index.html').read_text(),'old user data')
                if changed in ('target','target-mode'):
                    self.assertEqual(state['target_state'],'unknown')
                    with self.assertRaises(ValueError): publication.restore(src,run.name,state['target_snapshot'],True)
                else:
                    publication.restore(src,run.name,state['target_snapshot'],True)
                    self.assertEqual((target/'index.html').read_text(),'old user data')

    def test_all_inputs_are_rechecked_after_copy_before_rename(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            changed={**approved,'source_snapshot':'0'*64}
            with patch('tools.publication.plan',side_effect=[approved,changed]):
                with self.assertRaisesRegex(publication.PublicationUncertain,'изменились'): publication.apply(src,path,digest,True)
            self.assertEqual((target/'index.html').read_text(),'old user data')
            run=next((work/'publications').iterdir()); self.assertTrue((run/'next/index.html').exists())
            self.assertFalse((run/'previous').exists())

    def test_target_change_blocks_before_rename(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            (target/'index.html').write_text('external edit')
            with patch('tools.publication.plan',return_value=approved):
                with self.assertRaises(ValueError): publication.apply(src,path,digest,True)
            self.assertEqual((target/'index.html').read_text(),'external edit')

    def test_sigkill_after_backup_requires_inspection_and_explicit_lock_clear(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,current=fixture(Path.cwd()); approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            # Import repository modules after chdir to a synthetic project.
            repo=Path(__file__).resolve().parent.parent
            script='''import json, os, sys
sys.path.insert(0,sys.argv[1])
from tools import publication
payload=json.loads(open(sys.argv[3]).read())['plan']
publication.plan=lambda *a,**kw: payload
original=os.rename
def kill_after_rename(*args):
    original(*args)
    os.kill(os.getpid(), 9)
os.rename=kill_after_rename
publication.apply(sys.argv[2],sys.argv[3],sys.argv[4],True)
'''
            proc=subprocess.run([sys.executable,'-c',script,str(repo),str(src),str(path),digest],check=False)
            self.assertEqual(proc.returncode,-signal.SIGKILL)
            run=next((work/'publications').iterdir()); state=publication.inspect(src,run.name)
            self.assertEqual(state['target_state'],'absent'); self.assertTrue(state['backup_valid'])
            with self.assertRaises(OSError): publication.restore(src,run.name,'absent',True)
            self.assertEqual(publication.restore(src,run.name,'absent',True,clear_stale_lock=True)['status'],'restored')
            self.assertEqual((target/'index.html').read_text(),'old user data')

if __name__=='__main__': unittest.main()
