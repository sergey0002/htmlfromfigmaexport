import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import synthetic_runner
from tools.cli import main


@unittest.skipUnless(os.name=='posix','requires POSIX process groups')
class SyntheticRunnerTests(unittest.TestCase):
    def test_requires_explicit_network_and_never_accepts_project_path(self):
        with patch('tools.synthetic_runner._supervise',side_effect=AssertionError('must not launch')):
            with self.assertRaises(ValueError): synthetic_runner.run()
            out=io.StringIO()
            with contextlib.redirect_stdout(out): code=main(['runner-synthetic','--json'])
            self.assertEqual(code,3); self.assertEqual(json.loads(out.getvalue())['operation'],'not_applied')
        result=subprocess.run([sys.executable,'-m','tools.cli','runner-synthetic','--source','source'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)

    def test_fixed_fixture_and_clear_untrusted_fault_environment(self):
        markers='\n'.join(synthetic_runner.REQUIRED)
        fake={'outcome':'completed','returncode':0,'output_bytes':len(markers),'output':markers}
        with patch.dict(os.environ,{'NETWORK_FIXTURE_FAULT':'kill-relay-a','NETWORK_ARTIFACT_FAULT':'corrupt'},clear=False), patch('tools.synthetic_runner._supervise',return_value=fake) as supervise:
            result=synthetic_runner.run(True,90)
        argv,env,timeout=supervise.call_args.args
        self.assertEqual(argv,[str(synthetic_runner.SCRIPT),'--synthetic-only']); self.assertEqual(timeout,90)
        self.assertNotIn('NETWORK_FIXTURE_FAULT',env); self.assertNotIn('NETWORK_ARTIFACT_FAULT',env)
        self.assertEqual(result['operation'],'applied'); self.assertEqual(result['status'],'INCOMPLETE')
        self.assertFalse(result['fixture']['authenticated']); self.assertFalse(result['fixture']['publication_eligible'])
        fake['output']='CLEANUP_OK'
        with patch('tools.synthetic_runner._supervise',return_value=fake): self.assertEqual(synthetic_runner.run(True)['operation'],'unknown')

    def test_supervisor_success_error_output_limit_and_timeout(self):
        env=dict(os.environ)
        for script,timeout,limit,expected in [('print("ok")',3,100,'completed'),
                  ('raise SystemExit(5)',3,100,'child_error'),
                  ('print("x"*10000)',3,100,'output_limit'),
                  ('import time; time.sleep(20)',1,100,'timeout')]:
            with self.subTest(expected=expected):
                result=synthetic_runner._supervise([sys.executable,'-c',script],env,timeout,limit)
                self.assertEqual(result['outcome'],expected); self.assertLessEqual(result['output_bytes'],limit)
        for timeout in (0,181,True):
            with self.assertRaises(ValueError): synthetic_runner._supervise([],env,timeout)

    def test_timeout_terminates_group_with_descendant(self):
        script='''import subprocess,sys,time
p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])
print(p.pid,flush=True)
time.sleep(30)
'''
        result=synthetic_runner._supervise([sys.executable,'-c',script],dict(os.environ),2)
        self.assertEqual(result['outcome'],'timeout'); pid=int(result['output'].strip())
        stat=Path(f'/proc/{pid}/stat')
        if stat.exists(): self.assertEqual(stat.read_text().split(') ')[1].split()[0],'Z')

    def test_term_interrupt_stops_child_group(self):
        script='''import os,sys
from tools.synthetic_runner import _supervise
r=_supervise([sys.executable,"-c","import os,time; print(os.getpid(),flush=True); time.sleep(30)"],dict(os.environ),30)
print(r['outcome'],r['output'].strip(),flush=True)
'''
        proc=subprocess.Popen([sys.executable,'-c',script],cwd=synthetic_runner.ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            # The outer process may need time to create its child before SIGTERM.
            import time; time.sleep(0.5); os.kill(proc.pid,signal.SIGTERM)
            stdout,stderr=proc.communicate(timeout=8)
            self.assertEqual(proc.returncode,0,stderr); self.assertTrue(stdout.startswith('interrupted '),stdout)
            pid=int(stdout.split()[1]); stat=Path(f'/proc/{pid}/stat')
            if stat.exists(): self.assertEqual(stat.read_text().split(') ')[1].split()[0],'Z')
        finally:
            if proc.poll() is None: proc.kill(); proc.wait()

if __name__=='__main__': unittest.main()
