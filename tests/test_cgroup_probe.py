import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import cgroup_probe, runner_profiles


def fixture(base, *, root='/', process='/tenant', mount_options='rw', controllers='cpu memory pids', enabled='cpu memory'):
    mount=base/'cgroup'; mount.mkdir(); group=mount/'tenant'; group.mkdir()
    (group/'cgroup.controllers').write_text(controllers+'\n')
    (group/'cgroup.subtree_control').write_text(enabled+'\n')
    (group/'cgroup.type').write_text('domain\n')
    (group/'cgroup.kill').write_text('')
    cg=base/'self-cgroup'; cg.write_text('0::'+process+'\n')
    mi=base/'mountinfo'; mi.write_text(f'30 23 0:25 {root} {mount} {mount_options},nosuid - cgroup2 cgroup2 rw\n')
    return cg,mi,group


class CgroupProbeTests(unittest.TestCase):
    def test_observation_is_read_only_and_never_proves_delegation(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            cg,mi,group=fixture(Path(tmp).absolute())
            before={p:p.read_bytes() for p in group.iterdir()}
            original=os.open
            def read_only(path,flags,*args,**kwargs):
                self.assertEqual(flags & os.O_ACCMODE,os.O_RDONLY)
                self.assertFalse(flags & (os.O_CREAT|os.O_TRUNC))
                return original(path,flags,*args,**kwargs)
            with patch('tools.cgroup_probe.os.open',side_effect=read_only),patch('subprocess.run',side_effect=AssertionError('must not execute')):
                result=cgroup_probe.inspect(cg,mi)
            self.assertEqual(result['status'],'observed'); self.assertEqual(result['current_group'],str(group))
            self.assertEqual(result['missing_controllers'],[]); self.assertTrue(result['kill_file_present'])
            self.assertFalse(result['delegation_verified']); self.assertFalse(result['aggregate_limits_verified'])
            self.assertEqual(result['disk_quota'],'unknown'); self.assertFalse(result['executes_project'])
            self.assertEqual({p:p.read_bytes() for p in group.iterdir()},before)

    def test_readonly_or_missing_controllers_are_hints_not_eligibility(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            cg,mi,_=fixture(Path(tmp).absolute(),mount_options='ro',controllers='cpu',enabled='')
            with patch('tools.cgroup_probe.os.access',return_value=False): result=cgroup_probe.inspect(cg,mi)
            self.assertEqual(result['status'],'observed'); self.assertTrue(result['mount_read_only'])
            self.assertFalse(result['directory_write_hint']); self.assertEqual(result['missing_controllers'],['memory','pids'])
            self.assertFalse(result['delegation_verified'])
        profiles=runner_profiles.inspect()['profiles']
        self.assertFalse(profiles['managed-isolated']['available']); self.assertFalse(profiles['managed-local']['available'])

    def test_malformed_or_ambiguous_proc_data_never_guesses(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            cg,mi,_=fixture(Path(tmp).absolute())
            original=cg.read_text()
            for content in ('0::/tenant/../escape\n','0::/tenant\n0::/tenant\n','1:cpu:/\n',''):
                with self.subTest(content=content):
                    cg.write_text(content); result=cgroup_probe.inspect(cg,mi)
                    self.assertEqual(result['status'],'unknown'); self.assertFalse(result['delegation_verified'])
            cg.write_text(original); mi.write_text(mi.read_text()*2)
            self.assertEqual(cgroup_probe.inspect(cg,mi)['status'],'unknown')

    def test_missing_or_symlinked_control_file_remains_unknown(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            cg,mi,group=fixture(Path(tmp).absolute()); controls=group/'cgroup.controllers'; controls.unlink()
            self.assertEqual(cgroup_probe.inspect(cg,mi)['status'],'unknown')
            try: controls.symlink_to(cg)
            except OSError: self.skipTest('symlink unavailable')
            self.assertEqual(cgroup_probe.inspect(cg,mi)['status'],'unknown')

    def test_mount_root_mapping_and_escaped_spaces(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            base=Path(tmp).absolute(); mount=base/'mount space'; mount.mkdir(); group=mount/'child'; group.mkdir()
            for key,value in (('cgroup.controllers','cpu memory pids'),('cgroup.subtree_control',''),('cgroup.type','domain')):
                (group/key).write_text(value)
            cg=base/'cg'; cg.write_text('0::/parent/child\n')
            mi=base/'mi'; escaped=str(mount).replace(' ','\\040')
            mi.write_text(f'30 23 0:25 /parent {escaped} rw - cgroup2 cgroup2 rw\n')
            result=cgroup_probe.inspect(cg,mi)
            self.assertEqual(result['status'],'observed'); self.assertEqual(result['current_group'],str(group))
            self.assertFalse(result['kill_file_present']); self.assertFalse(result['delegation_verified'])

if __name__=='__main__': unittest.main()
