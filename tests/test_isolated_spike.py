"""Contract and real Linux-only tests for the synthetic isolation experiment."""
import os
import select
import signal
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SCRIPT=ROOT/'tools/spikes/isolated-vite-separated.sh'
NETWORK_SCRIPT=ROOT/'tools/spikes/isolated-vite-network.sh'


def group_processes(group):
    result=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            stat=(path/'stat').read_text(); fields=stat[stat.rfind(')')+2:].split()
            if int(fields[2])!=group or fields[0]=='Z': continue
            result.append((int(path.name),(path/'cmdline').read_bytes().decode('utf8','replace')))
        except (OSError,ValueError,IndexError): pass
    return result


def descendants(root):
    table={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            stat=(path/'stat').read_text(); fields=stat[stat.rfind(')')+2:].split()
            table[int(path.name)]=(int(fields[1]),fields[0])
        except (OSError,ValueError,IndexError): pass
    found=set(); pending=[root]
    while pending:
        parent=pending.pop()
        children=[pid for pid,(ppid,state) in table.items() if ppid==parent and pid not in found and state!='Z']
        found.update(children); pending.extend(children)
    return found


def running(pid):
    try:
        stat=Path(f'/proc/{pid}/stat').read_text(); return stat[stat.rfind(')')+2:].split()[0]!='Z'
    except (OSError,IndexError): return False


class SyntheticIsolationContractTests(unittest.TestCase):
    def test_never_accepts_a_user_export_path(self):
        for args in ([],['--help'],['--synthetic-only','source'],['source']):
            with self.subTest(args=args):
                result=subprocess.run([str(SCRIPT),*args],cwd=ROOT,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,2); self.assertIn('synthetic-only',result.stderr)


class SyntheticNetworkContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'node is not installed')
    def test_http_gate_rejects_unsafe_requests_without_forwarding(self):
        script=ROOT/'tests/fixtures/isolated-vite/network-http-gate-test.cjs'
        result=subprocess.run(['node',str(script)],cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('HTTP_GATE_TEST_OK',result.stdout)

    def test_network_fixture_never_accepts_a_user_export_path(self):
        for args in ([],['source'],['--synthetic-only','source'],['--help']):
            with self.subTest(args=args):
                result=subprocess.run([str(NETWORK_SCRIPT),*args],cwd=ROOT,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,2); self.assertIn('synthetic-only',result.stderr)


@unittest.skipUnless(os.environ.get('RUN_ISOLATION_TESTS')=='1' and sys.platform=='linux',
                     'isolated synthetic fixture not requested on Linux')
class SyntheticIsolationIntegrationTests(unittest.TestCase):
    def test_separated_namespaces_renderer_filter_and_endpoint_ownership(self):
        result=subprocess.run([str(SCRIPT),'--synthetic-only','--browser-sandbox'],cwd=ROOT,capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        for phrase in ('PREPARED_NO_SCRIPTS packages=', 'READY a:', 'READY b:', 'CONFLICT_OK', 'BROWSER_SANDBOX_REQUESTED',
                       'RENDERER_FILTER_OK', 'BROWSER_OK', 'CLEANUP_OK'):
            self.assertIn(phrase,result.stdout)

    def test_pnpm_shaped_synthetic_tree_runs_in_separated_fixture(self):
        env={**os.environ,'SPIKE_PYTHON':sys.executable}
        result=subprocess.run([str(SCRIPT),'--synthetic-only','--browser-sandbox','--pnpm-fixture'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        for phrase in ('PREPARED_PNPM_SYNTHETIC_NO_SCRIPTS packages=', 'READY a:', 'READY b:', 'CONFLICT_OK', 'RENDERER_FILTER_OK', 'BROWSER_OK', 'CLEANUP_OK'):
            self.assertIn(phrase,result.stdout)

    def test_sigkill_namespace_init_reaps_children_and_cleans_temporary_roots(self):
        env={**os.environ,'SPLIT_FIXTURE_HOLD':'1'}
        proc=subprocess.Popen([str(SCRIPT),'--synthetic-only','--browser-sandbox'],cwd=ROOT,env=env,
                              stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              start_new_session=True,close_fds=True)
        output=b''
        try:
            deadline=time.monotonic()+45
            while b'HOLD_READY' not in output and time.monotonic()<deadline:
                if proc.poll() is not None: self.fail('experiment exited early: '+output.decode('utf8','replace'))
                ready,_,_=select.select([proc.stdout],[],[],0.5)
                if ready:
                    part=os.read(proc.stdout.fileno(),65536)
                    if not part: self.fail('experiment output closed before hold')
                    output+=part
            self.assertIn(b'HOLD_READY',output,output.decode('utf8','replace'))
            members=group_processes(proc.pid)
            controllers=[pid for pid,cmd in members if len(cmd.split('\0'))>1 and Path(cmd.split('\0')[0]).name.startswith('python') and cmd.split('\0')[1].endswith('/separated-controller.py')]
            self.assertEqual(len(controllers),1,members)
            # Capture this synthetic run's unique temp root for later cleanup verification.
            cmdline=next(cmd for pid,cmd in members if pid==controllers[0])
            roots=[part for part in cmdline.split('\0') if '/.cache/split-vite-' in part and part.endswith('/roots')]
            self.assertEqual(len(roots),1,cmdline); temp_root=Path(roots[0]).parent
            self.assertTrue(temp_root.is_dir())
            child_pids=descendants(controllers[0]); self.assertGreaterEqual(len(child_pids),4,child_pids)
            os.kill(controllers[0],signal.SIGKILL)
            proc.wait(timeout=30)
            self.assertNotEqual(proc.returncode,0)
            deadline=time.monotonic()+5
            while group_processes(proc.pid) and time.monotonic()<deadline: time.sleep(0.05)
            self.assertEqual(group_processes(proc.pid),[])
            self.assertFalse([pid for pid in child_pids if running(pid)],child_pids)
            self.assertFalse(temp_root.exists())
        finally:
            if proc.poll() is None:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                proc.wait(timeout=10)
            if proc.stdout: proc.stdout.close()

@unittest.skipUnless(os.environ.get('RUN_ISOLATION_TESTS')=='1' and sys.platform=='linux',
                     'synthetic network isolation fixture not requested on Linux')
class SyntheticNetworkIntegrationTests(unittest.TestCase):
    def test_independent_networks_and_browser_bridges(self):
        env={**os.environ,'SPIKE_PYTHON':sys.executable}
        result=subprocess.run([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        for phrase in ('PREPARED_PNPM_SYNTHETIC_NO_SCRIPTS', 'READY a:', 'READY b:',
                       'CROSS_NETWORK_BLOCKED', 'RELAY_NETWORK_BOUND', 'HTTP_GATE_POLICY_OK', 'CONFLICT_OK', 'LIMITS_OWNER_OK',
                       'BROWSER_NETWORK_SEPARATE','BROWSER_DIRECT_ENDPOINTS_BLOCKED',
                       'BROWSER_BRIDGES_READY','CROSS_NETWORK_STILL_BLOCKED',
                       'RENDERER_FILTER_OK','ARTIFACT_FD_OBSERVATION','BROWSER_OK',
                       'ARTIFACT_TRANSFER_OK frames=2 size=390x844 authenticated=false','CLEANUP_OK'):
            self.assertIn(phrase,result.stdout)

    def test_synthetic_per_process_resource_limits_and_negative_probes(self):
        env={**os.environ,'NETWORK_FIXTURE_FAULT':'resource-probe','SPIKE_PYTHON':sys.executable}
        result=subprocess.run([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        for phrase in ('RESOURCE_PROBE_OK hard limits, EMFILE, EFBIG, ENOMEM, CPU SIGKILL',
                       'LIMITS_OWNER_OK','SYNTHETIC_RLIMITS_OK browser','BROWSER_OK','CLEANUP_OK'):
            self.assertIn(phrase,result.stdout)
        roots=[line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('SYNTHETIC_ROOT ')]
        self.assertEqual(len(roots),1,result.stdout); self.assertFalse(Path(roots[0]).exists())

    def test_service_log_flood_during_capture_fails_closed(self):
        env={**os.environ,'NETWORK_FIXTURE_FAULT':'server-output-flood','SPIKE_PYTHON':sys.executable}
        result=subprocess.run([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        self.assertNotEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('SERVICE_FLOOD_INJECTED',result.stdout)
        self.assertIn('fixture service log limit exceeded',result.stderr)
        self.assertNotIn('ARTIFACT_TRANSFER_OK',result.stdout)
        roots=[line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('SYNTHETIC_ROOT ')]
        self.assertEqual(len(roots),1,result.stdout); self.assertFalse(Path(roots[0]).exists())

    def test_lost_relay_fails_closed_and_cleans_up(self):
        env={**os.environ,'NETWORK_FIXTURE_FAULT':'kill-relay-a','SPIKE_PYTHON':sys.executable}
        result=subprocess.run([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        self.assertNotEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('RELAY_FAULT_INJECTED',result.stdout)
        self.assertNotIn('BROWSER_OK',result.stdout)
        roots=[line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('SYNTHETIC_ROOT ')]
        self.assertEqual(len(roots),1,result.stdout); self.assertFalse(Path(roots[0]).exists())

    def test_corrupted_artifact_is_rejected_and_temporary_roots_removed(self):
        env={**os.environ,'NETWORK_ARTIFACT_FAULT':'corrupt','SPIKE_PYTHON':sys.executable}
        result=subprocess.run([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        self.assertNotEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('BROWSER_OK',result.stdout)
        self.assertNotIn('ARTIFACT_TRANSFER_OK',result.stdout)
        self.assertIn('CRC mismatch',result.stderr)
        roots=[line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('SYNTHETIC_ROOT ')]
        self.assertEqual(len(roots),1,result.stdout);self.assertFalse(Path(roots[0]).exists())

    def test_mismatched_declared_artifact_hash_is_rejected(self):
        env={**os.environ,'NETWORK_ARTIFACT_FAULT':'wronghash','SPIKE_PYTHON':sys.executable}
        result=subprocess.run([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        self.assertNotEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('BROWSER_OK',result.stdout);self.assertNotIn('ARTIFACT_TRANSFER_OK',result.stdout)
        self.assertIn('hashes differ',result.stderr)
        roots=[line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('SYNTHETIC_ROOT ')]
        self.assertEqual(len(roots),1,result.stdout);self.assertFalse(Path(roots[0]).exists())

    def test_malformed_frames_and_browser_sigkill_fail_closed(self):
        for fault,reason in (('truncate','synthetic PNG'),('oversize','synthetic frame length'),('kill-browser','browser fixture failed')):
            with self.subTest(fault=fault):
                env={**os.environ,'NETWORK_ARTIFACT_FAULT':fault,'SPIKE_PYTHON':sys.executable}
                result=subprocess.run([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
                self.assertNotEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
                self.assertNotIn('ARTIFACT_TRANSFER_OK',result.stdout)
                self.assertIn(reason,result.stderr)
                if fault=='kill-browser':
                    self.assertIn('BROWSER_KILL_INJECTED after first frame',result.stdout)
                    self.assertNotIn('BROWSER_OK',result.stdout)
                roots=[line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('SYNTHETIC_ROOT ')]
                self.assertEqual(len(roots),1,result.stdout);self.assertFalse(Path(roots[0]).exists())

    def test_sigkill_controller_reaps_servers_relays_and_temporary_roots(self):
        env={**os.environ,'SPLIT_FIXTURE_HOLD':'1','SPIKE_PYTHON':sys.executable}
        proc=subprocess.Popen([str(NETWORK_SCRIPT),'--synthetic-only'],cwd=ROOT,env=env,
                              stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              start_new_session=True,close_fds=True)
        output=b''
        try:
            deadline=time.monotonic()+50
            while b'HOLD_READY' not in output and time.monotonic()<deadline:
                if proc.poll() is not None: self.fail('experiment exited early: '+output.decode('utf8','replace'))
                ready,_,_=select.select([proc.stdout],[],[],0.5)
                if ready:
                    data=os.read(proc.stdout.fileno(),65536)
                    if not data: self.fail('experiment output closed before hold')
                    output+=data
            self.assertIn(b'HOLD_READY',output,output.decode('utf8','replace'))
            members=group_processes(proc.pid)
            controllers=[pid for pid,cmd in members if len(cmd.split('\0'))>1 and Path(cmd.split('\0')[0]).name.startswith('python') and cmd.split('\0')[1].endswith('/network-controller.py')]
            self.assertEqual(len(controllers),1,members)
            cmdline=next(cmd for pid,cmd in members if pid==controllers[0])
            roots=[part for part in cmdline.split('\0') if '/.cache/split-vite-' in part and part.endswith('/roots')]
            self.assertEqual(len(roots),1,cmdline); temp_root=Path(roots[0]).parent
            self.assertTrue(temp_root.is_dir())
            child_pids=descendants(controllers[0]); self.assertGreaterEqual(len(child_pids),8,child_pids)
            os.kill(controllers[0],signal.SIGKILL)
            proc.wait(timeout=30); self.assertNotEqual(proc.returncode,0)
            deadline=time.monotonic()+5
            while any(running(pid) for pid in child_pids) and time.monotonic()<deadline: time.sleep(0.05)
            self.assertFalse([pid for pid in child_pids if running(pid)],child_pids)
            self.assertFalse(temp_root.exists())
        finally:
            if proc.poll() is None:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                proc.wait(timeout=10)
            if proc.stdout: proc.stdout.close()

if __name__=='__main__': unittest.main()
