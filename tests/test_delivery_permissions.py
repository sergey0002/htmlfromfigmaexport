"""Explicit POSIX delivery modes on synthetic data, not publication approval."""
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import delivery, publication, posix_metadata
from tools.cli import main
from tools.snapshot import take_snapshot
from test_delivery import setup
from test_publication_transaction import cd, fixture, report


@unittest.skipUnless(os.name=='posix' and hasattr(os,'listxattr'),'POSIX mode/xattrs required')
class DeliveryPermissionTests(unittest.TestCase):
    def test_web_readable_requires_explicit_ack_and_never_reuses_output(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,site,selection,out=setup(Path(tmp).absolute())
            with self.assertRaisesRegex(ValueError,'явного подтверждения'):
                delivery.materialize(src,site,selection,out,'web-readable')
            self.assertFalse(out.exists())
            with self.assertRaises(ValueError): delivery.materialize(src,site,selection,out,'private',True)
            with self.assertRaises(ValueError): delivery.materialize(src,site,selection,out,'anything',True)
            self.assertFalse(out.exists())
            mask=os.umask(0o077)
            try: result=delivery.materialize(src,site,selection,out,'web-readable',True)
            finally: os.umask(mask)
            self.assertEqual(result['version'],2);self.assertEqual(result['permission_profile'],'web-readable-v1')
            self.assertEqual(result['status'],'unverified')
            self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o755)
            for folder in (out/'assets',out/'empty'): self.assertEqual(stat.S_IMODE(folder.stat().st_mode),0o755)
            for file in (out/'index.html',out/'assets/style.css'): self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o644)
            self.assertFalse((out/'other.html').exists())
            self.assertEqual(result['delivery_metadata']['sha256'],posix_metadata.inventory(out)['sha256'])
            self.assertEqual(result['delivery_snapshot'],take_snapshot(out,'delivery')['digest'])
            with self.assertRaises(ValueError): delivery.materialize(src,site,selection,out,'web-readable',True)

    def test_cli_exposes_warning_and_default_remains_private(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,site,selection,out=setup(Path(tmp).absolute())
            default=delivery.materialize(src,site,selection,out)
            self.assertEqual(default['version'],1)
            self.assertEqual(stat.S_IMODE((out/'index.html').stat().st_mode)&0o077,0)
            output=io.StringIO(); new=work/'deliveries'/'web'
            argv=['materialize','--source',str(src),'--site',str(site),'--selection',str(selection),'--output',str(new),'--permission-profile','web-readable','--json']
            with contextlib.redirect_stdout(output): code=main(argv)
            self.assertEqual(code,3);self.assertFalse(new.exists())
            output=io.StringIO()
            with contextlib.redirect_stdout(output): code=main(argv+['--acknowledge-world-readable'])
            result=json.loads(output.getvalue())
            self.assertEqual(code,2);self.assertEqual(result['operation'],'applied');self.assertEqual(result['delivery']['permission_profile'],'web-readable-v1')
            self.assertTrue(any('локальным пользователям' in warning for warning in result['warnings']))
            self.assertFalse((work/'vanilla').exists())

    def test_metadata_policy_error_leaves_private_incomplete_copy(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,site,selection,out=setup(Path(tmp).absolute())
            with patch('tools.posix_metadata.os.listxattr',return_value=['user.synthetic']):
                with self.assertRaisesRegex(delivery.DeliveryUncertain,'могут быть доступны'):
                    delivery.materialize(src,site,selection,out,'web-readable',True)
            self.assertTrue(out.exists());self.assertEqual(stat.S_IMODE(out.stat().st_mode)&0o077,0)
            self.assertFalse((work/'delivery-records').exists())

    def test_chmod_error_fails_closed_and_preserves_partial(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,site,selection,out=setup(Path(tmp).absolute())
            original=delivery._set_web_readable
            def fail_during(output,snapshot):
                with patch('tools.delivery.os.fsync',side_effect=OSError('injected sync failure')):
                    return original(output,snapshot)
            with patch('tools.delivery._set_web_readable',side_effect=fail_during):
                with self.assertRaises(delivery.DeliveryUncertain): delivery.materialize(src,site,selection,out,'web-readable',True)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode)&0o077,0)
            self.assertTrue((out/'index.html').exists());self.assertFalse((work/'delivery-records').exists())

    def test_plan_binds_profile_metadata_and_detects_permission_drift(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,_=fixture(Path.cwd()); site=work/'staging/candidate'; selection=work/'selection.json'
            out=work/'deliveries/web'; record=delivery.materialize(src,site,selection,out,'web-readable',True)
            plan=publication.plan(src,record['record'],target)
            self.assertEqual(plan['delivery_metadata']['sha256'],record['delivery_metadata']['sha256'])
            self.assertFalse(plan['apply_allowed'])
            (out/'index.html').chmod(0o600)
            self.assertEqual(take_snapshot(out,'delivery')['digest'],record['delivery_snapshot'])
            with self.assertRaisesRegex(ValueError,'Метаданные delivery'): publication.plan(src,record['record'],target)
            self.assertEqual((target/'index.html').read_text(),'old user data')

    def test_mode_survives_synthetic_apply_and_explicit_restore(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,_=fixture(Path.cwd()); site=work/'staging/candidate'; selection=work/'selection.json'
            out=work/'deliveries/web'; record=delivery.materialize(src,site,selection,out,'web-readable',True)
            current=publication.plan(src,record['record'],target); path,digest=report(work,current)
            with self.assertRaisesRegex(ValueError,'заблокирована'): publication.apply(src,path,digest,True)
            approved={**current,'apply_allowed':True}; path,digest=report(work,approved)
            with patch('tools.publication.plan',return_value=approved):
                result=publication.apply(src,path,digest,True)
            self.assertEqual(result['status'],'published_unverified')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o755)
            self.assertEqual(stat.S_IMODE((target/'index.html').stat().st_mode),0o644)
            self.assertEqual(posix_metadata.inventory(target)['sha256'],record['delivery_metadata']['sha256'])
            state=publication.inspect(src,result['publication_id'])
            publication.restore(src,result['publication_id'],state['target_snapshot'],True)
            self.assertEqual((target/'index.html').read_text(),'old user data')
            run=work/'publications'/result['publication_id']
            self.assertEqual(stat.S_IMODE((run/'recovery-preserved/index.html').stat().st_mode),0o644)

    def test_forged_profile_with_matching_wrong_mode_hash_is_rejected(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            src,work,target,_=fixture(Path.cwd()); site=work/'staging/candidate'; selection=work/'selection.json'
            out=work/'deliveries/web'; record=delivery.materialize(src,site,selection,out,'web-readable',True)
            (out/'index.html').chmod(0o600)
            record_path=Path(record['record']); saved=json.loads(record_path.read_text())
            saved['delivery_metadata']['sha256']=posix_metadata.inventory(out)['sha256']
            record_path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError,'Профиль прав delivery'): publication.plan(src,record_path,target)
            self.assertEqual((target/'index.html').read_text(),'old user data')

if __name__=='__main__': unittest.main()
