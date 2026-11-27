import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.snapshot import take_snapshot, read_snapshot_file, read_snapshot_prefix
from tools.core import fingerprint, analyze
from tools import facts


class SnapshotTests(unittest.TestCase):
    def test_fixed_delivery_vector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'empty').mkdir(); (root/'hello.txt').write_bytes(b'hello')
            snapshot = take_snapshot(root, 'delivery')
            self.assertEqual(snapshot['digest'], '9640f2bc75af6a0b99aab6559e1bd656e4c4204c58daa3dfd62f7e30a40a8a66')
            self.assertEqual([x['path'] for x in snapshot['entries']], ['empty','hello.txt'])

    def test_legacy_ambiguity_is_separated(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            a, b = Path(a), Path(b)
            (a/'a').write_bytes(b'1\0b\x002'); (b/'a').write_bytes(b'1'); (b/'b').write_bytes(b'2')
            self.assertEqual(fingerprint(a), fingerprint(b))
            self.assertNotEqual(take_snapshot(a)['digest'], take_snapshot(b)['digest'])

    def test_source_and_delivery_have_distinct_policies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'nested').mkdir(); (root/'nested/a').write_text('a')
            (root/'.env').write_text('secret'); (root/'node_modules').mkdir(); (root/'node_modules/a').write_text('one')
            before=take_snapshot(root); delivery=take_snapshot(root,'delivery')
            self.assertEqual({x['path'] for x in before['excluded']},{'.env','node_modules'})
            (root/'node_modules/a').write_text('two')
            self.assertEqual(before['digest'],take_snapshot(root)['digest'])
            self.assertNotEqual(delivery['digest'],take_snapshot(root,'delivery')['digest'])
            (root/'nested/a').write_text('b')
            self.assertNotEqual(before['digest'],take_snapshot(root)['digest'])

    def test_links_and_special_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'file').write_text('a')
            try: os.link(root/'file',root/'hard')
            except OSError: self.skipTest('hardlink unsupported')
            with self.assertRaises(ValueError): take_snapshot(root,'delivery')
            (root/'hard').unlink()
            try: (root/'link').symlink_to('file')
            except OSError: self.skipTest('symlink unsupported')
            with self.assertRaises(ValueError): take_snapshot(root,'delivery')
            (root/'link').unlink()
            if hasattr(os,'mkfifo'):
                os.mkfifo(root/'pipe')
                with self.assertRaises(ValueError): take_snapshot(root,'delivery')

    def test_source_refuses_case_variants_without_reading_or_descending(self):
        for name in ('.ENV', '.Env.local.js', '.WORK', '.GIT', 'NODE_MODULES'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); (root/'index.html').write_text('<p>ok</p>')
                candidate=root/name
                if name in ('.WORK','.GIT','NODE_MODULES'):
                    candidate.mkdir(); (candidate/'sensitive.js').write_text('secret')
                else: candidate.write_text('secret')
                original=os.open
                def checked_open(path, *args, **kwargs):
                    if Path(path)==candidate or candidate in Path(path).parents:
                        self.fail('attempt to read excluded variant')
                    return original(path,*args,**kwargs)
                with patch('os.open',side_effect=checked_open):
                    with self.assertRaisesRegex(ValueError,'Неоднозначное имя'): take_snapshot(root)
                    if name.casefold().startswith('.env') or name.casefold()=='.work':
                        with self.assertRaises(ValueError): fingerprint(root)
                        self.assertEqual(analyze(root)['status'],'BLOCKED')

    def test_bounded_snapshot_read_rejects_mutation_links_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'a.html'; path.write_text('hello')
            entry=take_snapshot(root)['entries'][0]
            self.assertEqual(read_snapshot_file(path,entry,5),b'hello')
            with self.assertRaises(ValueError): read_snapshot_file(path,entry,4)
            path.write_text('other')
            with self.assertRaises(ValueError): read_snapshot_file(path,entry,5)
            path.unlink(); other=root/'outside'; other.write_text('hello')
            try: path.symlink_to(other)
            except OSError: self.skipTest('symlink unsupported')
            with self.assertRaises(ValueError): read_snapshot_file(path,entry,5)
            path.unlink()
            try: os.link(other,path)
            except OSError: self.skipTest('hardlink unsupported')
            with self.assertRaises(ValueError): read_snapshot_file(path,entry,5)

    def test_snapshot_prefix_streams_and_checks_the_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'resource'; path.write_bytes(b'prefix'+b'A'*(3*1024*1024))
            entry=take_snapshot(root,'delivery')['entries'][0]; original=os.read; requested=[]
            def bounded(fd,n): requested.append(n); return original(fd,n)
            with patch('tools.snapshot.os.read',side_effect=bounded):
                self.assertEqual(read_snapshot_prefix(path,entry,6),b'prefix')
            self.assertGreater(len(requested),3); self.assertLessEqual(max(requested),1024*1024)
            with path.open('r+b') as file: file.seek(-1,2); file.write(b'B')
            with self.assertRaisesRegex(ValueError,'изменился'): read_snapshot_prefix(path,entry,6)
            with self.assertRaises(ValueError): read_snapshot_prefix(path,entry,65537)

    def test_facts_fail_if_file_changes_between_snapshot_and_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'index.html'; path.write_text('<p>safe</p>')
            original=facts.read_snapshot_file
            def replace_before_read(candidate,entry,limit):
                path.write_text('<p>evil</p>')
                return original(candidate,entry,limit)
            with patch('tools.facts.read_snapshot_file',side_effect=replace_before_read):
                with self.assertRaisesRegex(ValueError,'изменился'): facts.scan_facts(root,include_text=True)

    @unittest.skipUnless(hasattr(os,'mkfifo') and hasattr(os,'O_NONBLOCK'), 'requires POSIX FIFO')
    def test_fifo_swap_before_open_fails_without_waiting_for_writer(self):
        # Subprocess timeout makes a regression safe even if O_NONBLOCK is lost.
        script='''import os, tempfile, sys
from pathlib import Path
from unittest.mock import patch
from tools.snapshot import take_snapshot, read_snapshot_prefix
from tools.queue_md import _safe_read
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); file=root/'a'; file.write_bytes(b'data')
    entry=take_snapshot(root,'delivery')['entries'][0]
    original=os.open
    def swap(path, flags, *args, **kwargs):
        if Path(path)==file:
            file.unlink(); os.mkfifo(file)
        return original(path, flags, *args, **kwargs)
    try:
        with patch('os.open',side_effect=swap):
            if sys.argv[1]=='snapshot': take_snapshot(root)
            elif sys.argv[1]=='safe-read': _safe_read(file)
            else: read_snapshot_prefix(file,entry,2)
    except ValueError: pass
    else: raise AssertionError('FIFO swap accepted')
'''
        for kind in ('snapshot','safe-read','prefix'):
            with self.subTest(kind=kind):
                result=subprocess.run([sys.executable,'-c',script,kind],capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_case_and_unicode_collision_rejected_if_fs_supports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'A').write_text('a'); (root/'a').write_text('b')
            if len(list(root.iterdir())) != 2: self.skipTest('case-insensitive filesystem')
            with self.assertRaises(ValueError): take_snapshot(root)
