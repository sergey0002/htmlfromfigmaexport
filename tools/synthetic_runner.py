"""Supervise the fixed synthetic network spike, never a user project.

This controller is diagnostic, not an isolated production runner. It bounds
wall time and captured output, and signals the child's POSIX process group on
normal exit or catchable interruption. SIGKILL of this controller, hostile
processes escaping the group, host resource exhaustion and power loss are not
covered by this mechanism. The underlying fixture uses its own namespaces.
"""
from __future__ import annotations
import os
import selectors
import signal
import subprocess
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SCRIPT=ROOT/'tools/spikes/isolated-vite-network.sh'
MAX_OUTPUT=512*1024
MAX_TIMEOUT=180
REQUIRED=('PREPARED_PNPM_SYNTHETIC_NO_SCRIPTS','READY a:','READY b:',
          'CROSS_NETWORK_BLOCKED','HTTP_GATE_POLICY_OK','CONFLICT_OK',
          'BROWSER_BRIDGES_READY','RENDERER_FILTER_OK',
          'ARTIFACT_TRANSFER_OK frames=2 size=390x844 authenticated=false','CLEANUP_OK')
ENV_ALLOW=('PATH','HOME','LANG','LC_ALL','TMPDIR','LD_LIBRARY_PATH',
           'PLAYWRIGHT_CHROMIUM_EXECUTABLE','PLAYWRIGHT_CHROMIUM_LIB',
           'PLAYWRIGHT_DRIVER_PACKAGE','SPIKE_PYTHON')


class Interrupted(Exception):
    pass


def _stop_group(process):
    # A process-group boundary is not a cgroup: an adversary can escape it.
    for sig in (signal.SIGTERM,signal.SIGKILL):
        try: os.killpg(process.pid,sig)
        except ProcessLookupError: break
        if sig==signal.SIGTERM:
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired: pass


def _supervise(argv, env, timeout, limit=MAX_OUTPUT):
    if os.name!='posix': raise ValueError('Синтетический контроллер требует POSIX process group')
    if type(timeout) is not int or not 1<=timeout<=MAX_TIMEOUT or type(limit) is not int or not 1<=limit<=MAX_OUTPUT:
        raise ValueError('Недопустимый timeout или лимит вывода')
    old={}
    def interrupt(signum,frame): raise Interrupted(f'Получен сигнал {signum}')
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM,signal.SIGHUP): old[sig]=signal.signal(sig,interrupt)
    proc=None; chunks=[]; total=0; outcome=None
    try:
        proc=subprocess.Popen(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              start_new_session=True,close_fds=True)
        deadline=time.monotonic()+timeout
        with selectors.DefaultSelector() as sel:
            os.set_blocking(proc.stdout.fileno(),False); sel.register(proc.stdout,selectors.EVENT_READ)
            while sel.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0: outcome='timeout'; break
                for key,_ in sel.select(min(remaining,0.25)):
                    try: data=os.read(key.fd,min(65536,limit-total+1))
                    except BlockingIOError: continue
                    if not data:
                        sel.unregister(key.fileobj); break
                    total+=len(data)
                    if total>limit: outcome='output_limit'; break
                    chunks.append(data)
                if outcome: break
            if outcome is None:
                try: proc.wait(timeout=max(0.001,deadline-time.monotonic()))
                except subprocess.TimeoutExpired: outcome='timeout'
        if outcome is None: outcome='completed' if proc.returncode==0 else 'child_error'
    except (Interrupted,KeyboardInterrupt):
        outcome='interrupted'
    finally:
        if proc is not None:
            _stop_group(proc)
            if proc.stdout: proc.stdout.close()
        for sig,handler in old.items(): signal.signal(sig,handler)
    return {'outcome':outcome,'returncode':None if proc is None else proc.returncode,
            'output_bytes':sum(map(len,chunks)), 'output':b''.join(chunks).decode('utf8','replace')}


def run(allow_fixture_registry_network=False, timeout=120):
    if allow_fixture_registry_network is not True:
        raise ValueError('Нужно явно разрешить registry-сеть только для синтетической фикстуры')
    if not SCRIPT.is_file(): raise ValueError('Синтетическая фикстура отсутствует')
    env={key:os.environ[key] for key in ENV_ALLOW if key in os.environ}
    observed=_supervise([str(SCRIPT),'--synthetic-only'],env,timeout)
    missing=[marker for marker in REQUIRED if marker not in observed['output']]
    success=observed['outcome']=='completed' and not missing
    return {'status':'INCOMPLETE' if success else 'ERROR',
            'operation':'applied' if success else 'unknown',
            'execution':'completed' if success else observed['outcome'],
            'issues':[] if success else ['Синтетический runner не завершён или контрольные маркеры отсутствуют'],
            'warnings':['Только синтетическая фикстура: вывод не доказывает изоляцию, provenance или право публикации.',
                        'Контроллер не обеспечивает очистку при собственном SIGKILL и не ограничивает суммарные ресурсы.'],
            'fixture':{'outcome':observed['outcome'],'returncode':observed['returncode'],
                       'output_bytes':observed['output_bytes'],'missing_markers':missing,
                       'log_tail':observed['output'][-8192:], 'authenticated':False,'publication_eligible':False},
            'next':'Не запускать пользовательский экспорт через экспериментальный профиль.'}
