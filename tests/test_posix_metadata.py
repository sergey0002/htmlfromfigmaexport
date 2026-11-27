"""Narrow POSIX metadata prototype tests on synthetic temporary trees only."""
import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import posix_metadata as meta
from tools.snapshot import take_snapshot


@unittest.skipUnless(os.name=='posix' and hasattr(os,'listxattr'), 'POSIX xattrs required')
class PosixMetadataTests(unittest.TestCase):
    def fixture(self, root):
        source=root/'source'; source.mkdir(); (source/'dir').mkdir(); (source/'empty').mkdir()
        (source/'dir/file.txt').write_text('fixture')
        source.chmod(0o750); (source/'dir').chmod(0o751); (source/'empty').chmod(0o755)
        (source/'dir/file.txt').chmod(0o640)
        for index,path in enumerate((source/'dir/file.txt',source/'dir',source/'empty',source)):
            value=1_600_000_000_000_000_000 + index*1_000_000_000
            os.utime(path,ns=(value,value))
        return source

    def test_copy_preserves_supported_modes_owner_group_and_mtime(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            root=Path(tmp).absolute(); source=self.fixture(root); snap=take_snapshot(source,'delivery'); before=meta.inventory(source,snap)
            old_umask=os.umask(0o077)
            try: meta.copy_checked(source,root/'copy',snap,before)
            finally: os.umask(old_umask)
            after=meta.inventory(root/'copy')
            self.assertEqual(before,after)
            self.assertEqual(stat.S_IMODE((root/'copy/dir/file.txt').stat().st_mode),0o640)
            self.assertEqual((root/'copy/dir/file.txt').stat().st_mtime_ns,(source/'dir/file.txt').stat().st_mtime_ns)
            self.assertEqual(take_snapshot(root/'copy','delivery')['digest'],snap['digest'])
            with self.assertRaises(FileExistsError): meta.copy_checked(source,root/'copy',snap,before)

    def test_mode_and_time_drift_change_metadata_not_content_hash(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source=self.fixture(Path(tmp).absolute()); snap=take_snapshot(source,'delivery'); original=meta.inventory(source,snap)
            (source/'dir/file.txt').chmod(0o600)
            self.assertEqual(take_snapshot(source,'delivery')['digest'],snap['digest'])
            self.assertNotEqual(meta.inventory(source)['sha256'],original['sha256'])
            with self.assertRaisesRegex(ValueError,'метаданные|Метаданные'):
                meta.copy_checked(source,source.parent/'copy',snap,original)
            self.assertFalse((source.parent/'copy').exists())

    def test_rejects_special_modes_links_and_xattr(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source=self.fixture(Path(tmp).absolute()); snap=take_snapshot(source,'delivery')
            (source/'dir/file.txt').chmod(0o4640)
            with self.assertRaisesRegex(ValueError,'Специальные биты'): meta.inventory(source,snap)
            (source/'dir/file.txt').chmod(0o640)
            with patch('tools.posix_metadata.os.listxattr',return_value=['user.example']):
                with self.assertRaisesRegex(ValueError,'xattrs или ACL'): meta.inventory(source,snap)
            with patch('tools.posix_metadata.os.listxattr',side_effect=OSError(errno.EOPNOTSUPP,'no support')):
                with self.assertRaises(OSError): meta.inventory(source,snap)
            (source/'alias').symlink_to('dir/file.txt')
            with self.assertRaises(ValueError): meta.inventory(source)

    def test_real_user_xattr_blocks_inventory_when_supported(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source=self.fixture(Path(tmp).absolute()); path=source/'dir/file.txt'
            try: os.setxattr(path,'user.synthetic-test',b'fixture',follow_symlinks=False)
            except OSError as exc:
                if exc.errno in (errno.ENOTSUP,errno.EOPNOTSUPP,errno.EPERM,errno.EACCES): self.skipTest('filesystem does not permit user xattrs')
                raise
            self.assertIn('user.synthetic-test',os.listxattr(path,follow_symlinks=False))
            with self.assertRaisesRegex(ValueError,'xattrs или ACL'): meta.inventory(source)

    def test_ownership_mismatch_or_drift_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            root=Path(tmp).absolute(); source=self.fixture(root); snap=take_snapshot(source,'delivery'); before=meta.inventory(source,snap)
            original=meta.os.fstat
            def wrong_gid(fd):
                result=original(fd)
                # A newly created regular destination is detected via its fd path.
                try: path=os.readlink('/proc/self/fd/'+str(fd))
                except OSError: return result
                if path == str(root/'copy/dir/file.txt'):
                    values=list(result); values[5]=result.st_gid+1
                    return os.stat_result(values)
                return result
            with patch('tools.posix_metadata.os.fstat',side_effect=wrong_gid):
                with self.assertRaisesRegex(ValueError,'Владелец или группа'): meta.copy_checked(source,root/'copy',snap,before)
            self.assertEqual((source/'dir/file.txt').read_text(),'fixture')
            self.assertTrue((root/'copy').exists())

if __name__=='__main__': unittest.main()
