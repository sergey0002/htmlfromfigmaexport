"""Trusted controller for synthetic separate-network experiment only."""
import os
import re
import select
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from artifact_transfer import MAX_STREAM, parse_frames, write_artifacts

base=Path(sys.argv[1]).absolute()
host_port=sys.argv[2]
browser_sandbox=sys.argv[3]=='1'
hold=sys.argv[4]=='1'
fault=os.environ.get('NETWORK_FIXTURE_FAULT','none')
artifact_fault=os.environ.get('NETWORK_ARTIFACT_FAULT','none')
if sys.argv[3] not in ('0','1') or sys.argv[4] not in ('0','1') or fault not in ('none','kill-relay-a','resource-probe','server-output-flood') or artifact_fault not in ('none','corrupt','truncate','oversize','wronghash','kill-browser') or not host_port.isdigit() or not base.is_dir(): raise SystemExit('invalid fixture arguments')
children=[]
artifact_read=None; artifact_write=None


def command(root,script,*args,join=None):
    # Shell code is constant; values are positional parameters and no project
    # source is read until after chroot and the capability drop.
    sandboxed=root.name=='browser' and browser_sandbox
    prefix=('exec "$1/usr/bin/pivot-helper" "$1" /usr/bin/unshare --user --map-user=1000 --map-group=1000 '
            '/usr/bin/setpriv --no-new-privs ' if sandboxed else
            'exec /usr/sbin/chroot "$1" /usr/bin/setpriv --bounding-set=-all '
            '--inh-caps=-all --ambient-caps=-all --no-new-privs ')
    proc_opts='nosuid,nodev,noexec' if sandboxed else 'nosuid,nodev,noexec,ro'
    shell=('mount --make-rprivate / && ip link set lo up && '
           'mount -t proc -o '+proc_opts+' proc "$1/proc" && '+prefix+
           '/bin/node "$2" "$3" "$4" "$5"')
    enter=['nsenter',f'--net=/proc/{join}/ns/net','--'] if join is not None else []
    net=[] if join is not None else ['--net']
    argv=enter+['unshare',*net,'--mount','--pid','--fork','--kill-child','/bin/sh','-c',shell,'fixture',str(root),script,*args]
    while len(argv)<14: argv.append('')
    return argv


def launch(root,script,*args,join=None,pass_fds=(),extra_env=None):
    env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/tmp','LD_LIBRARY_PATH':'/lib/browser',
         'NODE_ENV':'development','LANG':'C','FIXTURE_BROWSER_SANDBOX':'1' if browser_sandbox else '0'}
    if extra_env: env.update(extra_env)
    # Per-process rlimits, inherited by descendants. These do not bound the
    # whole process tree or replace a delegated cgroup and filesystem quota.
    if root.name=='browser':
        limits=['--cpu=60:60','--nofile=512:512','--fsize=67108864:67108864','--core=0:0']
    else:
        limits=['--cpu=30:30','--nofile=256:256','--fsize=33554432:33554432','--core=0:0','--as=68719476736:68719476736']
    child=subprocess.Popen(['prlimit',*limits,'--',*command(root,script,*args,join=join)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           env=env,start_new_session=True,close_fds=True,pass_fds=pass_fds)
    children.append(child)
    return child


def listener_inodes(port,pid=None):
    found=set()
    prefix=f'/proc/{pid}/net' if pid is not None else '/proc/net'
    for filename in (prefix+'/tcp',prefix+'/tcp6'):
        try: lines=Path(filename).read_text().splitlines()[1:]
        except FileNotFoundError: continue
        for line in lines:
            cols=line.split()
            if len(cols)>9 and cols[3]=='0A' and int(cols[1].split(':')[1],16)==port:
                found.add(cols[9])
    return found


def owner_in_group(child,port):
    inodes=listener_inodes(port,child.pid)
    if not inodes: return False
    for process in Path('/proc').iterdir():
        if not process.name.isdigit(): continue
        try:
            stat=(process/'stat').read_text(); parts=stat[stat.rfind(')')+2:].split()
            if int(parts[2])!=child.pid: continue
            for fd in (process/'fd').iterdir():
                try:
                    link=os.readlink(fd)
                    if link.startswith('socket:[') and link[8:-1] in inodes: return int(process.name)
                except OSError: pass
        except (OSError,ValueError,IndexError): pass
    return None


def fixture_pid(child,script):
    for process in Path('/proc').iterdir():
        if not process.name.isdigit(): continue
        try:
            stat=(process/'stat').read_text(); parts=stat[stat.rfind(')')+2:].split()
            argv=(process/'cmdline').read_bytes().split(b'\0')
            if int(parts[2])==child.pid and len(argv)>1 and argv[0]==b'/bin/node' and argv[1]==script.encode():
                return int(process.name)
        except (OSError,ValueError,IndexError): pass
    raise RuntimeError('fixture process not visible for independent limit check')


def verify_limits(pid,browser=False):
    expected={'Max cpu time':'60' if browser else '30',
              'Max file size':'67108864' if browser else '33554432',
              'Max core file size':'0','Max open files':'512' if browser else '256'}
    if not browser: expected['Max address space']='68719476736'
    rows=Path(f'/proc/{pid}/limits').read_text().splitlines()
    for name,value in expected.items():
        matches=[row for row in rows if row.startswith(name+' ')]
        if len(matches)!=1 or matches[0][len(name):].split()[:2]!=[value,value]:
            raise RuntimeError(f'independent fixture limit mismatch: pid={pid} {name}')


def wait_server(child,name,port):
    data=b''; deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        if child.poll() is not None: raise RuntimeError(f'{name}: process exited {child.returncode}: {data[-4000:]!r}')
        ready,_,_=select.select([child.stdout],[],[],0.2)
        if ready:
            part=os.read(child.stdout.fileno(),8192)
            if not part: raise RuntimeError(f'{name}: unexpected EOF: {data[-4000:]!r}')
            data+=part
            if len(data)>100000: raise RuntimeError(f'{name}: excessive output')
        owner=owner_in_group(child,port) if b'PROBE_OK '+name.encode() in data and b'Local:' in data else None
        if owner:
            if b'SYNTHETIC_RLIMITS_OK site' not in data: raise RuntimeError('site limits not confirmed')
            verify_limits(owner)
            if name=='a' and fault=='resource-probe':
                if b'RESOURCE_PROBE_OK' not in data: raise RuntimeError('synthetic resource probe missing')
                print('RESOURCE_PROBE_OK hard limits, EMFILE, EFBIG, ENOMEM, CPU SIGKILL',flush=True)
            print(f'READY {name}: endpoint 127.0.0.1:{port} owned by managed process group; synthetic rlimits confirmed',flush=True)
            return
    raise RuntimeError(f'{name}: startup/ownership timeout: {data[-4000:]!r}')


def wait_relay(child,port):
    data=read_until(child,f'RELAY_READY {port}'.encode(),15).decode('utf8','replace')
    if 'SYNTHETIC_RLIMITS_OK relay' not in data or child.poll() is not None:
        raise RuntimeError('relay failed or limits unconfirmed: '+data)
    verify_limits(fixture_pid(child,'/app/network-relay.cjs'))
    socket_path=base.parent/'bridge'/('a' if port==4311 else 'b')/'target.sock'
    if not socket_path.is_socket(): raise RuntimeError('relay socket missing')


def verify_http_gate(name,port):
    path=base.parent/'bridge'/name/'target.sock'
    host=f'127.0.0.1:{port}'
    tests=[(200,f'GET / HTTP/1.1\r\nHost: {host}\r\n\r\n'),
           (200,f'HEAD / HTTP/1.1\r\nHost: {host}\r\n\r\n'),
           (405,f'POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 0\r\n\r\n'),
           (403,f'GET / HTTP/1.1\r\nHost: {host}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n'),
           (400,f'GET / HTTP/1.1\r\nHost: wrong.invalid\r\n\r\n'),
           (400,f'GET / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 1\r\n\r\nx')]
    for expected,request in tests:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(8); client.connect(str(path)); client.sendall(request.encode('ascii'))
            data=b''
            while b'\r\n' not in data and len(data)<4096:
                part=client.recv(1024)
                if not part: break
                data+=part
            status=data.split(b'\r\n',1)[0].split()
            if len(status)<2 or status[1]!=str(expected).encode():
                raise RuntimeError(f'fixture HTTP gate {name} expected {expected}: {data[:300]!r}')


def verify_no_cross_network(pid,own_port,other_port):
    code=("import socket,sys; "
          "s=socket.socket(); s.settimeout(2); r=s.connect_ex(('127.0.0.1',int(sys.argv[1]))); "
          "s.close(); sys.exit(0 if r!=0 else 1)")
    result=subprocess.run(['nsenter',f'--net=/proc/{pid}/ns/net','--',sys.executable,'-c',code,str(other_port)],
                          stdin=subprocess.DEVNULL,capture_output=True,timeout=6)
    if result.returncode!=0: raise RuntimeError(f'peer endpoint reachable from isolated network {own_port}')


def read_until(child, marker, timeout):
    data=b''; deadline=time.monotonic()+timeout
    while marker not in data and time.monotonic()<deadline:
        if child.poll() is not None: raise RuntimeError('fixture exited before marker: '+repr(data[-4000:]))
        ready,_,_=select.select([child.stdout],[],[],0.2)
        if ready:
            part=os.read(child.stdout.fileno(),8192)
            if not part: raise RuntimeError('fixture output closed')
            data+=part
            if len(data)>100000: raise RuntimeError('fixture excessive output')
    if marker not in data: raise RuntimeError('fixture marker timed out: '+repr(data[-4000:]))
    return data


def collect_browser(child,initial,artifact_fd,timeout,services):
    outputs={child.stdout.fileno():bytearray(initial),artifact_fd:bytearray()}
    active=set(outputs); monitored={proc.stdout.fileno():proc for proc in services}
    log_sizes={fd:0 for fd in monitored}; deadline=time.monotonic()+timeout; killed=False
    while active:
        remaining=deadline-time.monotonic()
        if remaining<=0: raise RuntimeError('browser/artifact transfer timed out')
        if any(proc.poll() is not None for proc in services): raise RuntimeError('fixture service exited during capture')
        ready,_,_=select.select(list(active|set(monitored)),[],[],min(remaining,0.5))
        for fd in ready:
            part=os.read(fd,65536)
            if fd in monitored:
                if not part: raise RuntimeError('fixture service output closed during capture')
                log_sizes[fd]+=len(part)
                if log_sizes[fd]>65536: raise RuntimeError('fixture service log limit exceeded')
                continue
            if not part:
                active.remove(fd); continue
            outputs[fd].extend(part)
            limit=MAX_STREAM if fd==artifact_fd else 100000
            if len(outputs[fd])>limit: raise RuntimeError('fixture output exceeds limit')
            if fd==artifact_fd and artifact_fault=='kill-browser' and not killed and len(outputs[fd])>=4:
                length=int.from_bytes(outputs[fd][:4],'big')
                if 0<length<=2_000_000 and len(outputs[fd])>=length+4:
                    os.killpg(child.pid,signal.SIGKILL); killed=True
                    print('BROWSER_KILL_INJECTED after first frame',flush=True)
    child.wait(timeout=5)
    if any(proc.poll() is not None for proc in services): raise RuntimeError('fixture service exited before capture completed')
    return bytes(outputs[child.stdout.fileno()]),bytes(outputs[artifact_fd])


def terminate(child):
    if child.poll() is None:
        try: os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait(timeout=5)


try:
    fixture_env=({'NETWORK_RESOURCE_PROBE':'1'} if fault=='resource-probe' else
                 {'NETWORK_OUTPUT_FLOOD':'1'} if fault=='server-output-flood' else None)
    a=launch(base/'a','/app/network-server.cjs','a','4311',host_port,extra_env=fixture_env); wait_server(a,'a',4311)
    b=launch(base/'b','/app/network-server.cjs','b','4312',host_port); wait_server(b,'b',4312)
    verify_no_cross_network(a.pid,4311,4312); verify_no_cross_network(b.pid,4312,4311)
    if os.readlink(f'/proc/{a.pid}/ns/net')==os.readlink(f'/proc/{b.pid}/ns/net'):
        raise RuntimeError('reference and candidate share network namespace')
    print('CROSS_NETWORK_BLOCKED reference and candidate loopbacks differ',flush=True)
    relay_a=launch(base/'relay-a','/app/network-relay.cjs','/bridge/target.sock','4311','',join=a.pid); wait_relay(relay_a,4311)
    relay_b=launch(base/'relay-b','/app/network-relay.cjs','/bridge/target.sock','4312','',join=b.pid); wait_relay(relay_b,4312)
    if (os.readlink(f'/proc/{relay_a.pid}/ns/net')!=os.readlink(f'/proc/{a.pid}/ns/net') or
            os.readlink(f'/proc/{relay_b.pid}/ns/net')!=os.readlink(f'/proc/{b.pid}/ns/net')):
        raise RuntimeError('relay network namespace does not match endpoint')
    print('RELAY_NETWORK_BOUND relays match their intended endpoints',flush=True)
    verify_http_gate('a',4311); verify_http_gate('b',4312)
    print('HTTP_GATE_POLICY_OK GET/HEAD allowed; unsafe methods, upgrade and bad framing denied',flush=True)
    if fault=='kill-relay-a':
        terminate(relay_a)
        print('RELAY_FAULT_INJECTED relay-a terminated',flush=True)
    if hold:
        print('HOLD_READY for synthetic SIGKILL cleanup test',flush=True)
        time.sleep(60)
        raise RuntimeError('SIGKILL test did not interrupt controller')
    conflict=launch(base/'a','/app/network-server.cjs','a','4311',host_port,join=a.pid)
    try: output=conflict.communicate(timeout=15)[0].decode('utf8','replace')
    except subprocess.TimeoutExpired:
        terminate(conflict); raise RuntimeError('port conflict did not terminate')
    if conflict.returncode==0 or not any(text in output for text in ('EADDRINUSE','already in use','Port 4311 is already in use')):
        raise RuntimeError('strict port collision not rejected: '+output[-4000:])
    if not owner_in_group(a,4311): raise RuntimeError('original reference lost endpoint ownership')
    print('CONFLICT_OK port owner remains the original managed process',flush=True)
    artifact_read,artifact_write=os.pipe()
    browser=launch(base/'browser','/app/network-browser.cjs',host_port,'','',pass_fds=(artifact_write,),
                   extra_env={'FIXTURE_ARTIFACT_FD':str(artifact_write),'NETWORK_ARTIFACT_FAULT':artifact_fault})
    os.close(artifact_write); artifact_write=None
    initial=read_until(browser,b'BROWSER_BRIDGES_READY',20)
    verify_limits(fixture_pid(browser,'/app/network-browser.cjs'),browser=True)
    print('LIMITS_OWNER_OK observed Vite listeners, relays and browser controller',flush=True)
    browser_ns=os.readlink(f'/proc/{browser.pid}/ns/net')
    namespaces={browser_ns,os.readlink(f'/proc/{a.pid}/ns/net'),os.readlink(f'/proc/{b.pid}/ns/net'),os.readlink('/proc/self/ns/net')}
    if len(namespaces)!=4: raise RuntimeError('browser or servers share an unintended network namespace')
    print('BROWSER_NETWORK_SEPARATE browser has distinct loopback',flush=True)
    verify_no_cross_network(a.pid,4311,4312); verify_no_cross_network(b.pid,4312,4311)
    print('CROSS_NETWORK_STILL_BLOCKED after browser bridges',flush=True)
    if fault=='server-output-flood':
        os.kill(fixture_pid(a,'/app/network-server.cjs'),signal.SIGUSR2)
        print('SERVICE_FLOOD_INJECTED',flush=True)
    output_bytes,stream=collect_browser(browser,initial,artifact_read,40,[a,b,relay_a,relay_b])
    os.close(artifact_read); artifact_read=None
    output=output_bytes.decode('utf8','replace'); print(output,flush=True)
    if browser.returncode!=0 or 'BROWSER_OK' not in output or 'SYNTHETIC_RLIMITS_OK browser' not in output:
        raise RuntimeError('browser fixture failed or limits unconfirmed')
    images=parse_frames(stream)
    declared=re.findall(r'^SCREEN_SHA256 ([0-9a-f]{64})$',output,re.MULTILINE)
    if declared!=[image['sha256'] for image in images]: raise RuntimeError('synthetic capture hashes differ from declarations')
    stored=write_artifacts(base.parent/'artifact-results',images)
    print('ARTIFACT_TRANSFER_OK frames=2 size=390x844 authenticated=false manifest_sha256='+stored['manifest_sha256'],flush=True)
finally:
    for fd in (artifact_read,artifact_write):
        if fd is not None:
            try: os.close(fd)
            except OSError: pass
    for child in reversed(children): terminate(child)
    # Individual network namespaces disappear with their last process.
    if any(child.poll() is None for child in children):
        raise RuntimeError('cleanup failed: fixture process still running')
print('CLEANUP_OK fixture endpoints and namespaces exited',flush=True)
