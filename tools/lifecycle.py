"""Evidence freshness and conservative, reversible local publication."""
from __future__ import annotations
import hashlib
import contextlib
import functools
import http.server
import threading
import json
import os
import stat
from urllib.parse import unquote, urlsplit
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .core import analyze, fingerprint
from .queue import load, save, check_manifest


class MutationUncertainError(OSError):
    """A storage operation may have partially changed project data."""


def _site_root(site):
    path=Path(site).absolute()
    if path.name.startswith('.') or not path.is_dir() or path.is_symlink() or any(p.is_symlink() for p in path.parents) or any(p.is_symlink() for p in path.rglob('*')):
        raise ValueError('Каталог сайта отсутствует или содержит symlink')
    for item in path.rglob('*'):
        if item.name.startswith('.'):
            raise ValueError(f'Скрытые файлы/каталоги нельзя раздавать: {item.name}')
        info = item.lstat()
        if getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
            raise ValueError('Reparse point запрещён')
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise ValueError('Файлы с несколькими жёсткими ссылками запрещены')
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError('Специальные файлы запрещены')
    if not path.resolve().is_relative_to(Path.cwd().resolve()): raise ValueError('Сайт должен быть в рабочем каталоге')
    return path.resolve()


def _source_hash(source):
    data=analyze(Path(source))
    if data.get('status')=='BLOCKED': raise ValueError('Исходник не прошёл предварительную проверку')
    return data['fingerprint']


def _work_file(work, path):
    work=Path(work).resolve(); path=Path(path).absolute()
    if not path.resolve().is_relative_to(work) or path.is_symlink() or not path.is_file(): raise ValueError('Доказательство должно быть файлом внутри рабочей области проекта')
    return path.resolve()


@contextlib.contextmanager
def serve_site(site):
    """Serve only a symlink-free candidate on a temporary loopback port."""
    site=_site_root(site)
    # Freeze the set of ordinary files visible when the server starts. This
    # limits accidental additions, but is not a content snapshot or a sandbox.
    allowed = {p.relative_to(site).as_posix() for p in site.rglob('*') if p.is_file() and not p.is_symlink()}
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args): pass

        def list_directory(self, path):
            self.send_error(404)
            return None

        def send_head(self):
            # Recheck per request too: files can change after the initial scan.
            # This is not a race-free sandbox against a concurrent adversary.
            raw = unquote(urlsplit(self.path).path)
            parts = raw.split('/')
            if '\\' in raw or '\x00' in raw or any(x.startswith('.') for x in parts if x):
                self.send_error(404); return None
            target = site.joinpath(*(x for x in parts if x))
            try:
                if not target.resolve().is_relative_to(site):
                    self.send_error(404); return None
                cursor = site
                for name in (x for x in parts if x):
                    cursor = cursor / name
                    meta = cursor.lstat()
                    if cursor.is_symlink() or getattr(meta, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                        self.send_error(404); return None
                if target.is_dir():
                    target = next((target / name for name in ('index.html', 'index.htm') if (target / name).exists() or (target / name).is_symlink()), None)
                    if target is None:
                        self.send_error(404); return None
                if target.relative_to(site).as_posix() not in allowed:
                    self.send_error(404); return None
                info = target.lstat()
                if target.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                    self.send_error(404); return None
            except (OSError, ValueError):
                self.send_error(404); return None
            return super().send_head()
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(site)))
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def snapshot(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(source, site, page_id, kind, status, report):
    if kind not in ('static','browser','manual') or status not in ('checked','incomplete','fail','blocked','review'): raise ValueError('Недопустимая проверка или статус')
    if status == 'checked':
        raise ValueError('Запись checked временно отключена: v1 не связывает доказательства с требованиями и не подтверждает происхождение отчёта')
    source=Path(source); work=source/'.work'
    if source.is_symlink() or work.is_symlink(): raise ValueError('Symlink рабочей области запрещён')
    manifest=work/'manifest.json'; expected=snapshot(manifest); data=load(manifest)
    source_hash=_source_hash(source)
    if data['source'].get('fingerprint')!=source_hash: raise ValueError('Очередь устарела; сначала повторите discover')
    site=_site_root(site); site_hash=fingerprint(site); report=_work_file(work,report)
    pages=[p for p in data['pages'] if p['id']==page_id] if page_id else [p for p in data['pages'] if p['confirmation']=='confirmed']
    if not pages: raise ValueError('Нет выбранных страниц')
    evidence={'source_fingerprint':source_hash,'site_fingerprint':site_hash,'site':os.path.relpath(site,Path.cwd()),
              'report':report.relative_to(work.resolve()).as_posix(),'report_sha256':snapshot(report),
              'time':datetime.now(timezone.utc).isoformat()}
    for page in pages:
        page.setdefault('checks',{})[kind]=status
        page.setdefault('check_evidence',{})[kind]=evidence.copy()
    try:
        save(manifest,data,expected_hash=expected)
    except Exception as exc:
        raise MutationUncertainError(f'Состояние записи очереди неизвестно; проверьте manifest и Markdown перед повтором: {exc}') from exc
    return {'status':'INCOMPLETE','operation':'applied','issues':[], 'warnings':[], 'pages_recorded':[p['id'] for p in pages], 'next':'Проверка отдельной области не является полной приёмкой.'}


def stale_checks(data, source):
    source=Path(source)
    if source.is_symlink() or (source/'.work').is_symlink(): raise ValueError('Symlink рабочей области запрещён')
    current=_source_hash(source); root=Path.cwd().resolve(); work=(source/'.work').resolve(); cache={}
    for page in data['pages']:
        for kind,value in list(page.get('checks',{}).items()):
            if value in ('not_run','stale'): continue
            # v1 evidence does not bind requirements or reference provenance.
            if value == 'checked':
                page['checks'][kind] = 'stale'
                continue
            e=page.get('check_evidence',{}).get(kind)
            stale=not isinstance(e,dict) or e.get('source_fingerprint')!=current
            if not stale:
                site=(root/e.get('site','')).absolute()
                report=(work/e.get('report','')).resolve()
                if not site.resolve().is_relative_to(root) or not report.is_relative_to(work) or not site.is_dir() or not report.is_file(): stale=True
                else:
                    try:
                        if site not in cache: cache[site]=fingerprint(_site_root(site))
                        stale=cache[site]!=e.get('site_fingerprint') or snapshot(report)!=e.get('report_sha256')
                    except (OSError,ValueError): stale=True
            if stale: page['checks'][kind]='stale'
    return data


def publish(source, site, target='vanilla', replace=False):
    """Fail closed while versioned delivery/evidence and recovery are implemented."""
    raise ValueError('Публикация временно отключена: v1 не проверяет полный снимок поставки и актуальность требований')
