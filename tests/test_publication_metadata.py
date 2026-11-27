"""Experimental publication metadata contracts on synthetic trees, never real apply."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import publication
from test_publication_transaction import cd, fixture, report


@unittest.skipUnless(os.name=='posix' and hasattr(os,'listxattr'),'POSIX xattrs required')
class PublicationMetadataTests(unittest.TestCase):
    def setup_tx(self, root):
        src,work,target,current=fixture(root)
        approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
        return src,work,target,approved,path,digest

    def test_plan_binds_modes_and_time_to_target_and_delivery(self):
        for changed in ('target-mode','target-time','delivery-mode','delivery-time'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src,work,target,approved,path,digest=self.setup_tx(Path.cwd())
                item=target/'index.html' if changed.startswith('target') else work/'deliveries/candidate/index.html'
                if changed.endswith('mode'): item.chmod(0o640 if item.stat().st_mode & 0o777 != 0o640 else 0o600)
                else:
                    stat=item.stat(); os.utime(item,ns=(stat.st_atime_ns,stat.st_mtime_ns-1_000_000_000))
                # Even if a caller mocks the eligibility gate, the transaction
                # checks the actual metadata again before touching the target.
                with patch('tools.publication.plan',return_value=approved):
                    with self.assertRaisesRegex(ValueError,'метаданные изменились'):
                        publication.apply(src,path,digest,True)
                self.assertEqual((target/'index.html').read_text(),'old user data')
                self.assertFalse((work/'publications').exists())

    def test_target_or_backup_metadata_drift_blocks_restore(self):
        for changed in ('target-mode','backup-mode','backup-time'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                src,work,target,approved,path,digest=self.setup_tx(Path.cwd())
                with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
                run=work/'publications'/result['publication_id']
                before=publication.inspect(src,run.name)
                item=target/'index.html' if changed.startswith('target') else run/'previous/index.html'
                if changed.endswith('mode'): item.chmod(0o640)
                else:
                    info=item.stat(); os.utime(item,ns=(info.st_atime_ns,info.st_mtime_ns-1_000_000_000))
                state=publication.inspect(src,run.name)
                self.assertEqual(state['target_snapshot'],before['target_snapshot'])
                if changed.startswith('target'): self.assertEqual(state['target_state'],'unknown')
                else: self.assertFalse(state['backup_valid'])
                with self.assertRaisesRegex(ValueError,'Неизвестная цель или backup'):
                    publication.restore(src,run.name,state['target_snapshot'],True)
                self.assertFalse((run/'recovery-preserved').exists())
                self.assertIn('new version',(target/'index.html').read_text())

    def test_restore_copy_mode_drift_blocks_before_rename(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,approved,path,digest=self.setup_tx(Path.cwd())
            with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
            run=work/'publications'/result['publication_id']; state=publication.inspect(src,run.name)
            original=publication._copy_snapshot
            def alter_copy(source,destination,snapshot):
                original(source,destination,snapshot)
                (destination/'index.html').chmod(0o600)
            with patch('tools.publication._copy_snapshot',side_effect=alter_copy):
                with self.assertRaisesRegex(publication.PublicationUncertain,'копия восстановления отличается'):
                    publication.restore(src,run.name,state['target_snapshot'],True)
            self.assertFalse((run/'recovery-preserved').exists())
            self.assertIn('new version',(target/'index.html').read_text())
            self.assertEqual((run/'previous/index.html').read_text(),'old user data')

    def test_legacy_journal_is_inspectable_but_restore_refuses(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,approved,path,digest=self.setup_tx(Path.cwd())
            with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
            run=work/'publications'/result['publication_id']; journal_path=run/'journal.json'
            journal=json.loads(journal_path.read_text()); journal['version']=1
            journal.pop('old_metadata'); journal.pop('new_metadata'); journal_path.write_text(json.dumps(journal))
            state=publication.inspect(src,run.name)
            self.assertFalse(state['metadata_policy_recorded']); self.assertFalse(state['backup_valid'])
            with self.assertRaisesRegex(ValueError,'Журнал v1'):
                publication.restore(src,run.name,state['target_snapshot'],True)
            self.assertIn('new version',(target/'index.html').read_text())
            self.assertEqual((run/'previous/index.html').read_text(),'old user data')

    def test_metadata_write_failure_does_not_replace_target(self):
        import errno
        for operation in ('fchmod','utime','fsync'):
            for during in ('apply','restore'):
                with self.subTest(operation=operation,during=during), tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
                    src,work,target,approved,path,digest=self.setup_tx(Path.cwd())
                    if during=='restore':
                        with patch('tools.publication.plan',return_value=approved): result=publication.apply(src,path,digest,True)
                        run=work/'publications'/result['publication_id']; state=publication.inspect(src,run.name)
                    # Patch only while copy_checked runs, so journal fsync is not intercepted.
                    original=publication.posix_metadata.copy_checked
                    def fail_during_copy(*args):
                        with patch.object(publication.posix_metadata.os,operation,side_effect=OSError(errno.EIO,'injected metadata failure')):
                            return original(*args)
                    with patch('tools.publication._copy_snapshot',side_effect=lambda source,destination,snapshot: fail_during_copy(
                            source,destination,snapshot,publication.posix_metadata.inventory(source,snapshot))):
                        if during=='apply':
                            with patch('tools.publication.plan',return_value=approved):
                                with self.assertRaises(publication.PublicationUncertain): publication.apply(src,path,digest,True)
                            self.assertEqual((target/'index.html').read_text(),'old user data')
                            run=next((work/'publications').iterdir()); self.assertFalse((run/'previous').exists())
                        else:
                            with self.assertRaises(publication.PublicationUncertain): publication.restore(src,run.name,state['target_snapshot'],True)
                            self.assertIn('new version',(target/'index.html').read_text())
                            self.assertFalse((run/'recovery-preserved').exists())
                            self.assertEqual((run/'previous/index.html').read_text(),'old user data')

    def test_unsupported_xattrs_are_visible_in_plan_and_never_applied(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,approved,path,digest=self.setup_tx(Path.cwd())
            with patch('tools.posix_metadata.os.listxattr',return_value=['user.synthetic']):
                proposed=publication.plan(src,approved['delivery_record'],target)
                self.assertEqual(proposed['target_metadata']['status'],'unsupported')
                self.assertEqual(proposed['delivery_metadata']['status'],'unsupported')
                self.assertFalse(proposed['apply_allowed'])
                forged={**proposed,'apply_allowed':True}; path,digest=report(work,forged)
                with patch('tools.publication.plan',return_value=forged):
                    with self.assertRaisesRegex(ValueError,'Неподдерживаемые метаданные'):
                        publication.apply(src,path,digest,True)
            self.assertEqual((target/'index.html').read_text(),'old user data')
            self.assertFalse((work/'publications').exists())

if __name__=='__main__': unittest.main()
