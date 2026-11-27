"""Trusted controller for synthetic split-namespace experiment only."""
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

base=Path(sys.argv[1]).absolute()
host_port=sys.argv[2]
browser_sandbox=sys.argv[3]=='1'
hold=sys.argv[4]=='1'
if sys.argv[3] not in ('0','1') or sys.argv[4] not in ('0','1') or not host_port.isdigit() or not base.is_dir(): raise SystemExit('invalid fixture arguments')
children=[]


def command(root,script,*args):
    # Shell code is constant; values are positional parameters and no project
    # source is read until after chroot and the capability drop.
    sandboxed=root.name=='browser' and browser_sandbox
    prefix=('exec "$1/usr/bin/pivot-helper" "$1" /usr/bin/unshare --user --map-user=1000 --map-group=1000 '
            '/usr/bin/setpriv --no-new-privs ' if sandboxed else
            'exec /usr/sbin/chroot "$1" /usr/bin/setpriv --bounding-set=-all '
            '--inh-caps=-all --ambient-caps=-all --no-new-privs ')
    proc_opts='nosuid,nodev,noexec' if sandboxed else 'nosuid,nodev,noexec,ro'
    shell=('mount --make-rprivate / && '
           'mount -t proc -o '+proc_opts+' proc "$1/proc" && '+prefix+
           '/bin/node "$2" "$3" "$4" "$5"')
    argv=['unshare','--mount','--pid','--fork','--kill-child','/bin/sh','-c',shell,'fixture',str(root),script,*args]
    while len(argv)<14: argv.append('')
    return argv


def launch(root,script,*args):
    child=subprocess.Popen(command(root,script,*args),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/tmp','LD_LIBRARY_PATH':'/lib/browser',
                                'NODE_ENV':'development','LANG':'C','FIXTURE_BROWSER_SANDBOX':'1' if browser_sandbox else '0'},start_new_session=True,close_fds=True)
    children.append(child)
    return child


def listener_inodes(port):
    found=set()
    for filename in ('/proc/net/tcp','/proc/net/tcp6'):
        try: lines=Path(filename).read_text().splitlines()[1:]
        except FileNotFoundError: continue
        for line in lines:
            cols=line.split()
            if len(cols)>9 and cols[3]=='0A' and int(cols[1].split(':')[1],16)==port:
                found.add(cols[9])
    return found


def owner_in_group(child,port):
    inodes=listener_inodes(port)
    if not inodes: return False
    for process in Path('/proc').iterdir():
        if not process.name.isdigit(): continue
        try:
            stat=(process/'stat').read_text(); parts=stat[stat.rfind(')')+2:].split()
            if int(parts[2])!=child.pid: continue
            for fd in (process/'fd').iterdir():
                try:
                    link=os.readlink(fd)
                    if link.startswith('socket:[') and link[8:-1] in inodes: return True
                except OSError: pass
        except (OSError,ValueError,IndexError): pass
    return False


def wait_server(child,name,port):
    data=b''; deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        if child.poll() is not None: raise RuntimeError(f'{name}: process exited {child.returncode}: {data[-4000:]!r}')
        ready,_,_=select.select([child.stdout],[],[],0.2)
        if ready:
            part=os.read(child.stdout.fileno(),8192)
            if not part: raise RuntimeError(f'{name}: unexpected EOF')
            data+=part
            if len(data)>100000: raise RuntimeError(f'{name}: excessive output')
        if b'PROBE_OK '+name.encode() in data and b'Local:' in data and owner_in_group(child,port):
            print(f'READY {name}: endpoint 127.0.0.1:{port} owned by managed process group',flush=True)
            return
    raise RuntimeError(f'{name}: startup/ownership timeout: {data[-4000:]!r}')


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
    a=launch(base/'a','/app/separated-server.cjs','a','4311',host_port); wait_server(a,'a',4311)
    b=launch(base/'b','/app/separated-server.cjs','b','4312',host_port); wait_server(b,'b',4312)
    if hold:
        print('HOLD_READY for synthetic SIGKILL cleanup test',flush=True)
        time.sleep(60)
        raise RuntimeError('SIGKILL test did not interrupt controller')
    conflict=launch(base/'a','/app/separated-server.cjs','a','4311',host_port)
    try: output=conflict.communicate(timeout=15)[0].decode('utf8','replace')
    except subprocess.TimeoutExpired:
        terminate(conflict); raise RuntimeError('port conflict did not terminate')
    if conflict.returncode==0 or not any(text in output for text in ('EADDRINUSE','already in use','Port 4311 is already in use')):
        raise RuntimeError('strict port collision not rejected: '+output[-4000:])
    if not owner_in_group(a,4311): raise RuntimeError('original reference lost endpoint ownership')
    print('CONFLICT_OK port owner remains the original managed process',flush=True)
    browser=launch(base/'browser','/app/separated-browser.cjs',host_port,'','')
    try: output=browser.communicate(timeout=40)[0].decode('utf8','replace')
    except subprocess.TimeoutExpired:
        terminate(browser); raise RuntimeError('browser timed out')
    print(output,flush=True)
    if browser.returncode!=0 or 'BROWSER_OK' not in output: raise RuntimeError('browser fixture failed')
finally:
    for child in reversed(children): terminate(child)
    # No process in these namespaces should still own either endpoint.
    if listener_inodes(4311) or listener_inodes(4312):
        raise RuntimeError('cleanup failed: fixture port still listening')
print('CLEANUP_OK fixture endpoints and namespaces exited',flush=True)
