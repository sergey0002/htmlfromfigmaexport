"""Run the viewport audit against URLs or a temporary Vite copy and static site.

This reduces accidental modifications; it is NOT an OS sandbox. Only run trusted
export code in an isolated environment. No deployment and no source edits.
"""
from __future__ import annotations
import functools
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .core import analyze, fingerprint
from .screen_audit import audit_urls


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def package_install(project: Path):
    """Choose a locked package-manager command, without shell or lifecycle scripts."""
    pkg = json.loads((project / 'package.json').read_text(encoding='utf8'))
    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    if 'vite' not in deps or not re.fullmatch(r'vite(?:\s+--(?:host|port|strictPort|open)(?:[=\s][\w.-]+)?)*', pkg.get('scripts', {}).get('dev', '')):
        raise ValueError('Поддерживается только Vite со стандартным скриптом dev; произвольные скрипты не запускаются')
    pnpm, npm = (project/'pnpm-lock.yaml').is_file(), (project/'package-lock.json').is_file()
    if pnpm == npm: raise ValueError('Нужен ровно один pnpm-lock.yaml или package-lock.json')
    if npm: return ['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund']
    if shutil.which('pnpm'): return ['pnpm', 'install', '--frozen-lockfile', '--ignore-scripts']
    version = ''
    manager = pkg.get('packageManager', '')
    if isinstance(manager, str) and re.fullmatch(r'pnpm@\d+\.\d+\.\d+', manager): version = manager[5:]
    mise = project / '.mise.toml'
    if not version and mise.is_file():
        match = re.search(r'^\s*"npm:pnpm"\s*=\s*"(\d+\.\d+\.\d+)"', mise.read_text(encoding='utf8'), re.M)
        if match: version = match.group(1)
    if not version: raise ValueError('Установите pnpm или укажите его точную версию в packageManager/.mise.toml')
    return ['npx', '--yes', f'pnpm@{version}', 'install', '--frozen-lockfile', '--ignore-scripts']


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); return sock.getsockname()[1]


def _spawn(command, **kwargs):
    if os.name == 'nt':
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, **kwargs)
    return subprocess.Popen(command, start_new_session=True, **kwargs)


def _stop(process):
    if not process: return
    try:
        if os.name != 'nt': os.killpg(process.pid, signal.SIGTERM)
        elif process.poll() is None: process.terminate()
    except ProcessLookupError: pass
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            if os.name != 'nt': os.killpg(process.pid, signal.SIGKILL)
            else: process.kill()
        except ProcessLookupError: pass
        process.wait()


def _copy_ignore(directory, names):
    return [name for name in names if name in {'.git', 'node_modules', 'dist', 'build', '.work', '.venv', '.cache', '.vite'} or name.startswith('.env') or 'Zone.Identifier' in name]


def brief_report(data):
    """Bounded, agent-friendly summary; full state and artifacts remain in summary.json."""
    notable = []
    for viewport in data.get('viewports', []):
        for state in viewport.get('states', []):
            for message in state.get('mismatches', []):
                notable.append({'viewport': [viewport['width'], viewport['height']], 'state': state['name'], 'issue': message})
            for kind in ('action', 'fullpage'):
                image = state.get(kind)
                if image and image.get('any_difference_ratio', 0) > 0:
                    notable.append({'viewport': [viewport['width'], viewport['height']], 'state': state['name'],
                        'kind': kind, 'status': image.get('status', 'REVIEW'),
                        'difference_ratio': image['difference_ratio'], 'any_difference_ratio': image['any_difference_ratio'],
                        'heatmap': image['heatmap'], 'overlay': image['overlay']})
            for screen in state.get('screens', []):
                if screen.get('any_difference_ratio', 0) > 0:
                    notable.append({'viewport': [viewport['width'], viewport['height']], 'state': state['name'],
                        'screen': screen['index'], 'status': screen['status'],
                        'difference_ratio': screen['difference_ratio'], 'any_difference_ratio': screen['any_difference_ratio'],
                        'heatmap': screen['heatmap'], 'overlay': screen['overlay']})
    notable.sort(key=lambda item: (item.get('issue') is not None, item.get('difference_ratio', 0), item.get('any_difference_ratio', 0)), reverse=True)
    warnings = list(dict.fromkeys(data.get('warnings', [])))
    # Prioritize incomplete full-page coverage over routine resource warnings.
    warnings.sort(key=lambda message: 'Не удалось снять/сравнить длинную страницу' in message, reverse=True)
    return {'schema_version': 1, 'status': data['status'], 'coverage': data.get('coverage'),
            'behavior': data.get('behavior'), 'issues': data.get('issues', [])[:8],
            'warnings': warnings[:8], 'warnings_total': len(warnings), 'notable': notable[:8],
            'notable_total': len(notable), 'details': 'summary.json',
            'next': data.get('next', 'Изучить отчёт и ограничения.')}


def run(source: Path, site: Path, output: Path, scenarios, route='/', threshold=0.001, font_css=None,
        trust_source=False, reference_url=None, candidate_url=None, channel_tolerance=12):
    output = output.resolve()
    work = Path('.work').resolve()
    if not output.is_relative_to(work) or output == work or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        return {'schema_version':1, 'status':'BLOCKED', 'issues':['Выберите новый или пустой подкаталог внутри .work/'], 'warnings':[]}
    output.mkdir(parents=True, exist_ok=True)
    result = None
    def finish(data):
        data.setdefault('warnings', [])
        (output/'summary.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        (output/'brief.json').write_text(json.dumps(brief_report(data), ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        return data
    if bool(reference_url) != bool(candidate_url):
        return finish({'schema_version':1,'status':'BLOCKED','issues':['Нужно указать оба URL или ни одного']})
    if reference_url:
        result = audit_urls(reference_url, candidate_url, output, scenarios, route, threshold, font_css, channel_tolerance)
        return finish(result)
    if not trust_source:
        return finish({'schema_version':1,'status':'BLOCKED','issues':['Для запуска чужого кода сначала проверьте проект и изоляцию, затем укажите --trust-source']})
    source, site = source.resolve(), site.resolve()
    preflight = analyze(source)
    if preflight.get('status') == 'BLOCKED':
        return finish({'schema_version':1,'status':'BLOCKED','issues':preflight.get('issues',[]),'warnings':preflight.get('warnings',[])})
    project = Path(preflight['root'])
    if not site.is_dir() or not (site/'index.html').is_file():
        return finish({'schema_version':1,'status':'BLOCKED','issues':['Не найдена папка результата или её index.html'],'warnings':preflight.get('warnings',[])})
    if any(p.is_symlink() for p in site.rglob('*')):
        return finish({'schema_version':1,'status':'BLOCKED','issues':['Символические ссылки в результате требуют ручной проверки'],'warnings':preflight.get('warnings',[])})
    process = None; httpd = None; thread = None
    try:
        command = package_install(project)
        source_hash, site_hash = fingerprint(project), fingerprint(site)
        with tempfile.TemporaryDirectory(prefix='browser-run-', dir=work) as temp:
            try:
                tmp = Path(temp); copy = tmp/'source'; home = tmp/'home'; home.mkdir()
                shutil.copytree(project, copy, symlinks=True, ignore=_copy_ignore)
                # The environment does not contain credentials, but this is not filesystem or network isolation.
                env = {'PATH':os.environ.get('PATH',''), 'HOME':str(home), 'TMPDIR':str(tmp),
                       'npm_config_ignore_scripts':'true', 'npm_config_audit':'false', 'npm_config_fund':'false'}
                for key in ('SYSTEMROOT', 'WINDIR', 'PATHEXT', 'COMSPEC'):
                    if key in os.environ: env[key] = os.environ[key]
                with (output/'install.log').open('w', encoding='utf8') as log:
                    proc = _spawn(command, cwd=copy, env=env, stdout=log, stderr=subprocess.STDOUT)
                    try:
                        code = proc.wait(timeout=240)
                    except subprocess.TimeoutExpired as exc:
                        raise RuntimeError('Установка зависимостей превысила 240 секунд; см. install.log') from exc
                    finally:
                        _stop(proc)
                if code: raise RuntimeError(f'Установка зависимостей завершилась с кодом {code}; см. install.log')
                vite = copy/'node_modules'/'vite'/'bin'/'vite.js'
                if not vite.is_file(): raise RuntimeError('После установки не найден Vite')
                handler = functools.partial(Quiet, directory=str(site))
                httpd = http.server.ThreadingHTTPServer(('127.0.0.1',0), handler)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
                port = _free_port(); env.update({'PORT':str(port), 'FIGMA_DEV_SERVER_HOST':'127.0.0.1'})
                with (output/'reference.log').open('w', encoding='utf8') as log:
                    process = _spawn(['node',str(vite),'--host','127.0.0.1','--port',str(port),'--strictPort'], cwd=copy, env=env, stdout=log, stderr=subprocess.STDOUT)
                    deadline = time.monotonic()+45
                    while time.monotonic() < deadline:
                        if process.poll() is not None: raise RuntimeError('Vite остановился; см. reference.log')
                        try:
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
                                if response.status == 200: break
                        except (OSError, urllib.error.URLError): pass
                        time.sleep(.2)
                    else: raise RuntimeError('Vite не запустился за 45 секунд; см. reference.log')
                    result = audit_urls(f'http://127.0.0.1:{port}', f'http://127.0.0.1:{httpd.server_port}', output, scenarios, route, threshold, font_css, channel_tolerance)
                    result.update({'source_fingerprint':source_hash,'candidate_fingerprint':site_hash,'preflight':preflight,
                                   'install_command':command,'isolation':'temporary copy and limited environment; NOT an OS sandbox'})
                    result['warnings'].extend(preflight.get('warnings', []))
                    if fingerprint(project) != source_hash or fingerprint(site) != site_hash:
                        result['status'] = 'BLOCKED'; result['issues'].append('Файлы входа или результата изменились во время сравнения; повторите прогон')
            finally:
                # Shut down Vite and HTTP before TemporaryDirectory removes the copy.
                if process:
                    _stop(process); process = None
                if httpd: httpd.shutdown(); httpd.server_close(); httpd = None
                if thread: thread.join(timeout=5); thread = None
    except Exception as e:
        result = {'schema_version':1,'status':'BLOCKED','issues':[f'{type(e).__name__}: {e}'], 'warnings':preflight.get('warnings',[])}
    finally:
        if process: _stop(process)
        if httpd: httpd.shutdown(); httpd.server_close()
        if thread: thread.join(timeout=5)
    return finish(result)
