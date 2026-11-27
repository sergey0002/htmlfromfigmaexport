import base64
import contextlib
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import locked_npm
from tools.cli import main
from tools.snapshot import take_snapshot


def archive(extra=(),name='foo',version='1.0.0'):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz') as tf:
        data=json.dumps({'name':name,'version':version,'scripts':{'postinstall':'do not execute'}}).encode()
        info=tarfile.TarInfo('package/package.json'); info.size=len(data); tf.addfile(info,io.BytesIO(data))
        data=b'export default 42;'; info=tarfile.TarInfo('package/index.js'); info.size=len(data); tf.addfile(info,io.BytesIO(data))
        for kind,path,payload in extra:
            info=tarfile.TarInfo(path)
            if kind=='file': info.size=len(payload); tf.addfile(info,io.BytesIO(payload))
            elif kind=='link': info.type=tarfile.SYMTYPE; info.linkname=payload; tf.addfile(info)
            elif kind=='hardlink': info.type=tarfile.LNKTYPE; info.linkname=payload; tf.addfile(info)
    return out.getvalue()


def setup(root,blob=None):
    source=root/'source'; source.mkdir(); work=source/'.work'; work.mkdir()
    package={'name':'app','version':'1.0.0','dependencies':{'foo':'1.0.0'},'scripts':{'preinstall':'untrusted'}}
    (source/'package.json').write_text(json.dumps(package)); (source/'.env').write_text('private')
    blob=blob or archive(); integrity='sha512-'+base64.b64encode(hashlib.sha512(blob).digest()).decode()
    lock={'name':'app','lockfileVersion':3,'packages':{'':{'name':'app','version':'1.0.0','dependencies':{'foo':'1.0.0'}},
          'node_modules/foo':{'version':'1.0.0','resolved':'https://registry.npmjs.org/foo/-/foo-1.0.0.tgz','integrity':integrity,'hasInstallScript':True},
          'node_modules/optional-win':{'version':'1.0.0','optional':True,'os':['win32'],'resolved':'https://registry.npmjs.org/optional-win/-/optional-win-1.0.0.tgz','integrity':integrity}}}
    (source/'package-lock.json').write_text(json.dumps(lock)); return source,work,lock,blob


def cache(work,blob):
    root=work/'npm-tar-cache'; root.mkdir(exist_ok=True)
    (root/(hashlib.sha512(blob).hexdigest()+'.tgz')).write_bytes(blob)


@unittest.skipUnless(__import__('platform').system()=='Linux' and __import__('platform').machine() in ('x86_64','AMD64'),'adapter supports Linux x64')
class LockedNpmTests(unittest.TestCase):
    def test_offline_prepare_never_executes_scripts_and_keeps_source_unchanged(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,lock,blob=setup(Path(t).absolute()); cache(work,blob); before=take_snapshot(src,'source')['digest']
            with patch('subprocess.run',side_effect=AssertionError('execution forbidden')), patch('subprocess.Popen',side_effect=AssertionError('execution forbidden')), patch('tools.locked_npm._download',side_effect=AssertionError('network forbidden')):
                plan=locked_npm.plan(src); result=locked_npm.prepare(src,'.',work/'npm-deps'/'one')
            self.assertEqual(len(plan['packages']),1); self.assertEqual(len(plan['skipped']),1)
            self.assertTrue(plan['packages'][0]['has_install_script']); self.assertFalse(result['scripts_executed'])
            self.assertFalse(result['publication_eligible']); self.assertEqual(result['operation'],'applied')
            self.assertEqual((work/'npm-deps/one/node_modules/foo/index.js').read_text(),'export default 42;')
            self.assertFalse((work/'npm-deps/one/node_modules/.bin').exists())
            self.assertEqual(take_snapshot(src,'source')['digest'],before)
            self.assertEqual(take_snapshot(work/'npm-deps/one','delivery')['digest'],result['dependency_snapshot'])
            self.assertEqual((src/'.env').read_text(),'private')

    def test_inspect_detects_source_tree_and_record_drift(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,_,blob=setup(Path(t).absolute()); cache(work,blob)
            result=locked_npm.prepare(src,'.',work/'npm-deps/one')
            def inspect(): return locked_npm.inspect(src,result['record'],result['sha256'])
            self.assertEqual(inspect()['freshness'],'current')
            (work/'npm-deps/one/node_modules/foo/index.js').write_text('changed')
            self.assertEqual(inspect()['changed'],['dependency_snapshot'])
            (src/'extra.txt').write_text('changed')
            self.assertEqual(inspect()['changed'],['source_snapshot','dependency_snapshot'])
            self.assertFalse(inspect()['publication_eligible'])
            with self.assertRaisesRegex(ValueError,'изменена'):
                locked_npm.inspect(src,result['record'],'0'*64)
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=main(['npm-lock-inspect','--source',str(src),'--file',result['record'],'--sha256',result['sha256'],'--json'])
            self.assertEqual(code,2); self.assertEqual(json.loads(output.getvalue())['dependency_inspect']['freshness'],'stale')

    def test_network_is_opt_in_and_integrity_checked(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,lock,blob=setup(Path(t).absolute()); target=work/'npm-deps/one'
            with patch('tools.locked_npm._download',side_effect=AssertionError('network forbidden')):
                with self.assertRaisesRegex(ValueError,'сеть'): locked_npm.prepare(src,'.',target)
            self.assertFalse(target.exists())
            with patch('tools.locked_npm._download',return_value=b'incorrect'):
                with self.assertRaisesRegex(ValueError,'Integrity'): locked_npm.prepare(src,'.',target,True)
            self.assertFalse(target.exists())
            with patch('tools.locked_npm._download',return_value=blob) as download:
                result=locked_npm.prepare(src,'.',target,True)
            self.assertEqual(download.call_count,1); self.assertEqual(result['packages'],1)
            self.assertTrue((work/'npm-tar-cache'/(hashlib.sha512(blob).hexdigest()+'.tgz')).is_file())

    def test_failed_second_download_reports_cache_side_effect(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,lock,blob=setup(Path(t).absolute())
            # foo sorts before zoo; only the first archive reaches the cache.
            lock['packages']['node_modules/zoo']={'version':'1.0.0', 'resolved':'https://registry.npmjs.org/zoo/-/zoo-1.0.0.tgz',
                'integrity':'sha512-'+base64.b64encode(hashlib.sha512(b'other').digest()).decode()}
            (src/'package-lock.json').write_text(json.dumps(lock))
            with patch('tools.locked_npm._download',side_effect=[blob,OSError('registry failure')]):
                with self.assertRaisesRegex(locked_npm.DependenciesUncertain,'Кэш'): locked_npm.prepare(src,'.',work/'npm-deps/one',True)
            self.assertTrue((work/'npm-tar-cache'/(hashlib.sha512(blob).hexdigest()+'.tgz')).exists())
            self.assertFalse((work/'npm-deps/one').exists())

    def test_rejects_bad_locks_urls_scripts_are_not_executed(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,lock,blob=setup(Path(t).absolute()); file=src/'package-lock.json'
            for url in ('http://registry.npmjs.org/foo.tgz','https://evil.example/foo.tgz','https://user@registry.npmjs.org/foo.tgz','https://registry.npmjs.org/foo.tgz?token=secret'):
                lock['packages']['node_modules/foo']['resolved']=url; file.write_text(json.dumps(lock))
                with self.subTest(url=url),self.assertRaises(ValueError): locked_npm.plan(src)
            lock['packages']['node_modules/foo']['resolved']='https://registry.npmjs.org/foo.tgz'
            lock['packages']['node_modules/foo']['integrity']='sha1-abc'; file.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError,'sha512'): locked_npm.plan(src)
            lock['packages']['node_modules/foo']['integrity']='sha512-'+base64.b64encode(hashlib.sha512(blob).digest()).decode()
            lock['packages']['node_modules/foo']['link']=True; file.write_text(json.dumps(lock))
            with self.assertRaises(ValueError): locked_npm.plan(src)
            file.write_text('{"lockfileVersion":3,"lockfileVersion":3,"packages":{}}')
            with self.assertRaises(ValueError): locked_npm.plan(src)
            with self.assertRaises(ValueError): locked_npm._NoRedirect().redirect_request(None,None,None,None,None,'https://evil.example')

    def test_malicious_archive_rejected_and_partial_output_reported_unknown(self):
        cases=[('traversal',[('file','package/../../escape',b'evil')]),
               ('symlink',[('link','package/link','/etc/passwd')]),
               ('hardlink',[('hardlink','package/hard','package/index.js')]),
               ('duplicate',[('file','package/index.js',b'evil')]),
               ('case-conflict',[('file','package/INDEX.js',b'evil')]),
               ('nested-dependencies',[('file','package/node_modules/evil/index.js',b'evil')])]
        for name,extra in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir='.') as t:
                root=Path(t).absolute(); blob=archive(extra); src,work,_,_=setup(root,blob); cache(work,blob)
                with self.assertRaises(locked_npm.DependenciesUncertain): locked_npm.prepare(src,'.',work/'npm-deps/one')
                self.assertFalse((root/'escape').exists()); self.assertFalse((work/'npm-deps-records').exists())
                self.assertTrue((work/'npm-deps/one').is_dir())

    def test_wrong_metadata_limit_and_tampered_cache(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            blob=archive(name='wrong'); src,work,_,_=setup(Path(t).absolute(),blob); cache(work,blob)
            with self.assertRaisesRegex(locked_npm.DependenciesUncertain,'Имя или версия'): locked_npm.prepare(src,'.',work/'npm-deps/one')
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,_,blob=setup(Path(t).absolute()); cache(work,blob)
            with patch('tools.locked_npm.MAX_EXTRACT',5):
                with self.assertRaisesRegex(locked_npm.DependenciesUncertain,'лимит'): locked_npm.prepare(src,'.',work/'npm-deps/one')
            (work/'npm-tar-cache'/(hashlib.sha512(blob).hexdigest()+'.tgz')).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'Integrity'): locked_npm.prepare(src,'.',work/'npm-deps/two')

    def test_cli_returns_plan_and_uncertain_outcome(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,_,blob=setup(Path(t).absolute()); cache(work,blob); output=io.StringIO()
            with contextlib.redirect_stdout(output): code=main(['npm-lock-plan','--source',str(src),'--json'])
            self.assertEqual(code,2); self.assertEqual(json.loads(output.getvalue())['operation'],'not_applied')
            output=io.StringIO()
            with patch('tools.locked_npm._extract',side_effect=OSError('synthetic failure')),contextlib.redirect_stdout(output):
                code=main(['npm-lock-prepare','--source',str(src),'--output',str(work/'npm-deps/one'),'--json'])
            self.assertEqual(code,4); self.assertEqual(json.loads(output.getvalue())['operation'],'unknown')

if __name__=='__main__': unittest.main()
