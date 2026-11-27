import base64
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from tools import locked_pnpm
from tools.cli import main
from tools.snapshot import take_snapshot


def sample(root):
    source=root/'source'; source.mkdir(); (source/'.work').mkdir()
    package={'name':'app','version':'1.0.0','dependencies':{'foo':'^1.0.0'},'scripts':{'postinstall':'do not run'}}
    integrity='sha512-'+base64.b64encode(hashlib.sha512(b'tarball').digest()).decode()
    lock={'lockfileVersion':'9.0','settings':{'autoInstallPeers':True},
          'importers':{'.':{'dependencies':{'foo':{'specifier':'^1.0.0','version':'1.0.0(bar@2.0.0)'}}}},
          'packages':{'foo@1.0.0':{'resolution':{'integrity':integrity}},
                      'bar@2.0.0':{'resolution':{'integrity':integrity}}},
          'snapshots':{'foo@1.0.0(bar@2.0.0)':{'dependencies':{'bar':'2.0.0'}},'bar@2.0.0':{}}}
    (source/'package.json').write_text(json.dumps(package))
    (source/'pnpm-lock.yaml').write_text(yaml.safe_dump(lock,sort_keys=False))
    return source,package,lock


def save(source,lock):
    (source/'pnpm-lock.yaml').write_text(yaml.safe_dump(lock,sort_keys=False))


class PnpmInventoryTests(unittest.TestCase):
    def test_read_only_inventory_closure_and_cli(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source,_,_=sample(Path(tmp).absolute()); before=take_snapshot(source,'source')['digest']
            with patch('subprocess.run',side_effect=AssertionError('must not execute')), patch('subprocess.Popen',side_effect=AssertionError('must not execute')), patch('urllib.request.urlopen',side_effect=AssertionError('network')):
                result=locked_pnpm.inventory(source)
            self.assertEqual(result['packages'],2); self.assertEqual(result['reachable_snapshots'],2)
            self.assertEqual(result['edges']['dependencies'],1); self.assertFalse(result['installed_dependencies'])
            self.assertFalse(result['publication_eligible']); self.assertEqual(take_snapshot(source,'source')['digest'],before)
            self.assertEqual(list((source/'.work').iterdir()),[])
            output=io.StringIO()
            with contextlib.redirect_stdout(output): code=main(['pnpm-lock-inventory','--source',str(source),'--json'])
            self.assertEqual(code,2); self.assertEqual(json.loads(output.getvalue())['operation'],'not_applied')

    def test_cache_is_offline_by_default_and_integrity_checked(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source,_,_=sample(Path(tmp).absolute()); cache=source/'.work/npm-tar-cache'
            with patch('tools.locked_npm._download',side_effect=AssertionError('network forbidden')):
                with self.assertRaisesRegex(ValueError,'сеть'): locked_pnpm.cache_tarballs(source)
            self.assertFalse(cache.exists())
            with patch('tools.locked_npm._download',return_value=b'bad'):
                with self.assertRaisesRegex(ValueError,'Integrity'): locked_pnpm.cache_tarballs(source,allow_network=True)
            self.assertFalse(cache.exists())
            with patch('tools.locked_npm._download',return_value=b'tarball') as download:
                result=locked_pnpm.cache_tarballs(source,allow_network=True)
            self.assertEqual(result['operation'],'applied'); self.assertEqual(result['archives_fetched'],1)
            self.assertEqual(result['archives_reused'],1); self.assertEqual(download.call_count,1)
            self.assertFalse(result['installed_dependencies']); self.assertFalse(result['publication_eligible'])
            self.assertTrue(download.call_args.args[0].startswith('https://registry.npmjs.org/'))
            with patch('tools.locked_npm._download',side_effect=AssertionError('network forbidden')):
                again=locked_pnpm.cache_tarballs(source)
            self.assertEqual(again['operation'],'not_applied'); self.assertEqual(again['archives_reused'],2)
            target=cache/(hashlib.sha512(b'tarball').hexdigest()+'.tgz'); target.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'Integrity'): locked_pnpm.cache_tarballs(source)

    def test_cache_failure_after_first_mutation_is_unknown(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source,_,lock=sample(Path(tmp).absolute())
            second=b'another'; lock['packages']['bar@2.0.0']['resolution']['integrity']='sha512-'+base64.b64encode(hashlib.sha512(second).digest()).decode()
            save(source,lock)
            with patch('tools.locked_npm._download',side_effect=[b'tarball',OSError('failure')]),contextlib.redirect_stdout(io.StringIO()) as out:
                code=main(['pnpm-lock-cache','--source',str(source),'--allow-registry-network','--json'])
            self.assertEqual(code,4); self.assertEqual(json.loads(out.getvalue())['operation'],'unknown')
            self.assertTrue((source/'.work/npm-tar-cache'/(hashlib.sha512(b'tarball').hexdigest()+'.tgz')).is_file())

    def test_cache_drift_is_unknown_if_it_already_wrote(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source,_,_=sample(Path(tmp).absolute())
            def mutate(url,limit):
                (source/'drift.txt').write_text('new')
                return b'tarball'
            with patch('tools.locked_npm._download',side_effect=mutate):
                with self.assertRaises(locked_pnpm.locked_npm.DependenciesUncertain):
                    locked_pnpm.cache_tarballs(source,allow_network=True)

    def test_alias_duplicate_tags_and_limits_rejected(self):
        cases=[b'a: &x {x: y}\nb: *x\n', b'a: 1\na: 2\n',b'a: !!python/object/apply:os.system [id]\n',
               b'a: !!binary SGVsbG8=\n', b'a: ['*60+b'1'+b']'*60, b'a: '+b'x'*5000]
        for raw in cases:
            with self.subTest(raw=raw[:60]):
                if b'!!binary' in raw:
                    # SafeLoader allows binary; the typed pnpm schema rejects it later.
                    self.assertIsInstance(locked_pnpm._parse_yaml(raw)['a'],bytes)
                else:
                    with self.assertRaises(ValueError): locked_pnpm._parse_yaml(raw)

    def test_invalid_graph_or_unsupported_resolutions_are_rejected(self):
        mutations=[lambda x:x['snapshots']['foo@1.0.0(bar@2.0.0)']['dependencies'].update({'bar':'3.0.0'}),
                   lambda x:x['packages']['bar@2.0.0']['resolution'].update({'tarball':'https://evil.example/secret'}),
                   lambda x:x['packages']['bar@2.0.0']['resolution'].update({'integrity':'sha1-invalid'}),
                   lambda x:x['importers']['.']['dependencies']['foo'].update({'specifier':'^9'}),
                   lambda x:x['importers'].update({'other':{}}),
                   lambda x:x.update({'patchedDependencies':{'foo@1.0.0':'patch'}}),
                   lambda x:x['snapshots'].update({'foo@1.0.0(bar@2.0.0':{}}),
                   lambda x:x['snapshots']['foo@1.0.0(bar@2.0.0)']['dependencies'].update({'bar':'file:../x'})]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory(dir='.') as tmp:
                source,_,lock=sample(Path(tmp).absolute()); mutate(lock); save(source,lock)
                with self.assertRaises(ValueError): locked_pnpm.inventory(source)

    def test_yml_symlink_and_excluded_project_blocked(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source,_,_=sample(Path(tmp).absolute()); path=source/'pnpm-lock.yaml'; data=path.read_bytes(); path.unlink()
            outside=source/'else.yaml'; outside.write_bytes(data); path.symlink_to(outside)
            with self.assertRaises(ValueError): locked_pnpm.inventory(source)
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source,_,_=sample(Path(tmp).absolute()); hidden=source/'.work'/'project'; hidden.mkdir()
            (hidden/'package.json').write_text('{}'); (hidden/'pnpm-lock.yaml').write_text('lockfileVersion: 9.0')
            with self.assertRaises(ValueError): locked_pnpm.inventory(source,'.work/project')

    def test_source_drift_during_inventory_is_rejected(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            source,_,_=sample(Path(tmp).absolute()); original=locked_pnpm._parse_yaml
            def tamper(raw):
                result=original(raw); (source/'new.txt').write_text('new'); return result
            with patch('tools.locked_pnpm._parse_yaml',side_effect=tamper),self.assertRaisesRegex(ValueError,'изменился'):
                locked_pnpm.inventory(source)

if __name__=='__main__': unittest.main()
