import base64
import contextlib
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from tools import locked_npm, locked_pnpm, pnpm_tree
from tools.cli import main
from tools.snapshot import take_snapshot


def archive(name,version,script,extra=None):
    data=io.BytesIO()
    with tarfile.open(fileobj=data,mode='w:gz') as tar:
        for path,content in [('package/package.json',json.dumps({'name':name,'version':version,'scripts':{'postinstall':'NEVER'}}).encode()),('package/index.js',script.encode())]:
            info=tarfile.TarInfo(path); info.size=len(content); tar.addfile(info,io.BytesIO(content))
        if extra:
            info=tarfile.TarInfo('package/link'); info.type=tarfile.SYMTYPE; info.linkname=extra; tar.addfile(info)
    return data.getvalue()


def setup(root,malicious=False):
    src=root/'source'; src.mkdir(); work=src/'.work'; work.mkdir(); cache=work/'npm-tar-cache'; cache.mkdir()
    package={'dependencies':{'foo':'1.0.0'},'scripts':{'preinstall':'NEVER'}}
    foo=archive('foo','1.0.0',"module.exports = require('@example/bar')",'/etc/passwd' if malicious else None)
    bar=archive('@example/bar','2.0.0',"module.exports = 'ok'")
    blobs=[foo,bar]; ints=['sha512-'+base64.b64encode(hashlib.sha512(b).digest()).decode() for b in blobs]
    for b in blobs: (cache/(hashlib.sha512(b).hexdigest()+'.tgz')).write_bytes(b)
    lock={'lockfileVersion':'9.0','importers':{'.':{'dependencies':{'foo':{'specifier':'1.0.0','version':'1.0.0(@example/bar@2.0.0)'}}}},
          'packages':{'foo@1.0.0':{'resolution':{'integrity':ints[0]}},
                      '@example/bar@2.0.0':{'resolution':{'integrity':ints[1]}},
                      'windows-only@1.0.0':{'resolution':{'integrity':ints[0]},'os':['win32']}},
          'snapshots':{'foo@1.0.0(@example/bar@2.0.0)':{'dependencies':{'@example/bar':'2.0.0'},'optionalDependencies':{'windows-only':'1.0.0'}},
                       '@example/bar@2.0.0':{'dependencies':{'foo':'1.0.0(@example/bar@2.0.0)'}},
                       'windows-only@1.0.0':{'optional':True}}}
    (src/'package.json').write_text(json.dumps(package)); (src/'pnpm-lock.yaml').write_text(yaml.safe_dump(lock,sort_keys=False))
    return src,work,lock


def save(src,lock): (src/'pnpm-lock.yaml').write_text(yaml.safe_dump(lock,sort_keys=False))


@unittest.skipUnless(platform.system()=='Linux' and platform.machine()=='x86_64' and platform.libc_ver()[0]=='glibc','Linux x64 glibc only')
class PnpmTreeTests(unittest.TestCase):
    def test_offline_build_cycle_scoped_peers_and_inspect(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,lock=setup(Path(tmp).absolute()); before=take_snapshot(src,'source')['digest']
            with patch('subprocess.run',side_effect=AssertionError('must not execute')),patch('subprocess.Popen',side_effect=AssertionError('must not execute')),patch('tools.locked_npm._download',side_effect=AssertionError('must not access network')):
                item=pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')
            self.assertEqual(item['packages'],2); self.assertEqual(item['skipped'],1)
            self.assertFalse(item['scripts_executed']); self.assertFalse(item['publication_eligible'])
            self.assertTrue((work/'pnpm-deps/tree/node_modules/foo').is_symlink())
            self.assertFalse((work/'pnpm-deps/tree/node_modules/.bin').exists())
            self.assertEqual(take_snapshot(src,'source')['digest'],before)
            state=pnpm_tree.inspect(src,item['record'],item['sha256']); self.assertEqual(state['freshness'],'current')
            if shutil.which('node'):
                # Execute only our own fixed synthetic modules; never the user's project.
                result=subprocess.run(['node','-e',"console.log(require('foo'))"],cwd=work/'pnpm-deps/tree',capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr); self.assertEqual(result.stdout.strip(),'ok')
            (src/'new').write_text('source drift')
            self.assertEqual(pnpm_tree.inspect(src,item['record'],item['sha256'])['changed'],['source_snapshot'])
            out=io.StringIO()
            with contextlib.redirect_stdout(out): code=main(['pnpm-tree-inspect','--source',str(src),'--file',item['record'],'--sha256',item['sha256'],'--json'])
            self.assertEqual(code,2); self.assertEqual(json.loads(out.getvalue())['pnpm_tree']['freshness'],'stale')

    def test_corrupt_file_missing_link_and_escaping_link_detected(self):
        for mode in ('file','missing','escape','extra'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(dir='.') as tmp:
                src,work,_=setup(Path(tmp).absolute()); item=pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')
                root=work/'pnpm-deps/tree'; link=root/'node_modules/foo'
                if mode=='file':
                    file=link.resolve()/'index.js'; file.write_text('changed')
                    self.assertEqual(pnpm_tree.inspect(src,item['record'],item['sha256'])['changed'],['tree_snapshot'])
                elif mode=='missing':
                    link.unlink()
                    with self.assertRaises(ValueError): pnpm_tree.inspect(src,item['record'],item['sha256'])
                elif mode=='escape':
                    link.unlink(); link.symlink_to('/etc')
                    with self.assertRaises(ValueError): pnpm_tree.inspect(src,item['record'],item['sha256'])
                else:
                    (root/'node_modules/evil').symlink_to('/etc')
                    with self.assertRaises(ValueError): pnpm_tree.inspect(src,item['record'],item['sha256'])

    def test_platform_filtered_cache_ignores_incompatible_optional_artifact(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,lock=setup(Path(tmp).absolute())
            absent=hashlib.sha512(b'not downloaded').digest()
            lock['packages']['windows-only@1.0.0']['resolution']['integrity']='sha512-'+base64.b64encode(absent).decode()
            save(src,lock)
            with patch('tools.locked_npm._download',side_effect=AssertionError('must not access network')):
                result=locked_pnpm.cache_tarballs(src,selected_platform=True)
                self.assertEqual(result['packages_checked'],2); self.assertTrue(result['selected_platform'])
                self.assertEqual(result['operation'],'not_applied')
                with self.assertRaisesRegex(ValueError,'сеть'): locked_pnpm.cache_tarballs(src)
            item=pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree'); self.assertEqual(item['skipped'],1)

    def test_reject_missing_cache_incompatible_required_and_bad_integrity(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,lock=setup(Path(tmp).absolute()); cache=work/'npm-tar-cache'
            for file in cache.iterdir(): file.unlink()
            with self.assertRaises(ValueError): pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')
            self.assertFalse((work/'pnpm-deps/tree').exists())
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,lock=setup(Path(tmp).absolute()); lock['packages']['foo@1.0.0']['os']=['win32']; save(src,lock)
            with self.assertRaisesRegex(ValueError,'несовместима'): pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')
            self.assertFalse((work/'pnpm-deps/tree').exists())
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,lock=setup(Path(tmp).absolute())
            next((work/'npm-tar-cache').iterdir()).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'Integrity'): pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')

    def test_incompatible_required_child_of_optional_parent_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,lock=setup(Path(tmp).absolute())
            lock['packages']['windows-only@1.0.0'].pop('os')
            lock['packages']['@example/bar@2.0.0']['os']=['win32']
            lock['snapshots']['foo@1.0.0(@example/bar@2.0.0)']['dependencies'].pop('@example/bar')
            lock['snapshots']['windows-only@1.0.0']['dependencies']={'@example/bar':'2.0.0'}
            save(src,lock)
            with self.assertRaisesRegex(ValueError,'несовместима'):
                pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')
            self.assertFalse((work/'pnpm-deps/tree').exists())

    def test_archive_symlink_failure_is_unknown_and_retains_partial_tree(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,_=setup(Path(tmp).absolute(),malicious=True); out=io.StringIO()
            with contextlib.redirect_stdout(out): code=main(['pnpm-tree-prepare','--source',str(src),'--output',str(work/'pnpm-deps/tree'),'--json'])
            self.assertEqual(code,4); self.assertEqual(json.loads(out.getvalue())['operation'],'unknown')
            self.assertTrue((work/'pnpm-deps/tree').exists()); self.assertFalse((work/'pnpm-deps-records').exists())

    def test_unknown_outcome_when_source_changes_after_tree_creation(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,_=setup(Path(tmp).absolute()); original=locked_npm._extract
            def change(*args):
                result=original(*args); (src/'changed').write_text('new'); return result
            with patch('tools.pnpm_tree.npm._extract',side_effect=change):
                with self.assertRaises(locked_npm.DependenciesUncertain): pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')
            self.assertFalse((work/'pnpm-deps-records').exists())

    def test_execute_bits_are_bound_to_snapshot(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src,work,_=setup(Path(tmp).absolute()); item=pnpm_tree.prepare(src,'.',work/'pnpm-deps/tree')
            file=(work/'pnpm-deps/tree/node_modules/foo').resolve()/'index.js'; file.chmod(file.stat().st_mode|0o111)
            self.assertEqual(pnpm_tree.inspect(src,item['record'],item['sha256'])['changed'],['tree_snapshot'])

if __name__=='__main__': unittest.main()
