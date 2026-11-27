"""Build a non-publishable materialized candidate from an explicit allowlist.

Not an OS isolation boundary; concurrent uncooperative writers remain a risk.
"""
from __future__ import annotations
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path

from .lifecycle import _site_root
from .queue_md import _path, _safe_read, _write_new, _sync_dir, _relpath
from .snapshot import take_snapshot
from . import posix_metadata


class DeliveryUncertain(OSError):
    pass


def _set_web_readable(output, snapshot):
    """Explicit opt-in: expose the complete selected tree to local readers.

    This only sets POSIX mode bits, not web-server traversal or OS isolation.
    Keep the root private until every child has been checked and updated.
    """
    before=posix_metadata.inventory(output,snapshot)
    rows=before['entries']
    files=[row for row in rows if row['type']=='file']
    dirs=sorted((row for row in rows if row['type']=='directory'),key=lambda row:row['path'].count('/')+bool(row['path']),reverse=True)
    for row in files+dirs:
        path=output/row['path'] if row['path'] else output
        flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
        if row['type']=='directory': flags|=getattr(os,'O_DIRECTORY',0)
        fd=os.open(path,flags)
        try:
            info=os.fstat(fd); named=path.lstat()
            kind_ok=(stat.S_ISREG(info.st_mode) and info.st_nlink==1) if row['type']=='file' else stat.S_ISDIR(info.st_mode)
            if (not kind_ok or (info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino) or
                    (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_mtime_ns)!=
                    (row['uid'],row['gid'],row['mode'],row['mtime_ns'])):
                raise ValueError('Объект delivery изменился при настройке прав')
            os.fchmod(fd,0o644 if row['type']=='file' else 0o755); os.fsync(fd)
        finally: os.close(fd)
    after=posix_metadata.inventory(output,snapshot)
    for old,new in zip(rows,after['entries']):
        expected={**old,'mode':0o644 if old['type']=='file' else 0o755}
        if new!=expected: raise ValueError('Метаданные delivery изменились при настройке прав')
    if len(rows)!=len(after['entries']): raise ValueError('Состав метаданных delivery изменился')
    return {'policy':after['policy'],'sha256':after['sha256']}


def materialize(source, site, selection_file, output, permission_profile='private', acknowledge_world_readable=False):
    if permission_profile not in ('private','web-readable') or type(acknowledge_world_readable) is not bool:
        raise ValueError('Недопустимый профиль прав delivery')
    if permission_profile=='web-readable' and (not acknowledge_world_readable or os.name!='posix'):
        raise ValueError('Web-readable требует POSIX и явного подтверждения локальной доступности файлов')
    if permission_profile=='private' and acknowledge_world_readable:
        raise ValueError('Подтверждение world-readable допустимо только для web-readable')
    source = Path(source).absolute(); work = source/'.work'
    if source.is_symlink() or not source.is_dir() or work.is_symlink(): raise ValueError('Недопустимая рабочая область')
    selection = _path(work, selection_file)
    raw = _safe_read(selection)
    paths = json.loads(raw.decode('utf8'))
    if not isinstance(paths,list) or not paths or len(paths) > 200000 or any(not isinstance(p,str) or not _relpath(p) for p in paths) or len(paths) != len(set(paths)):
        raise ValueError('Selection должен быть непустым JSON-массивом уникальных относительных путей')
    site = _site_root(site)
    if work.resolve().is_relative_to(site): raise ValueError('Кандидат не может содержать рабочую область')
    deliveries = _path(work, work/'deliveries', existing=False)
    output = _path(work, output, existing=False)
    if output.parent != deliveries or output.exists() or output.is_symlink() or output.name.startswith('.'):
        raise ValueError('Нужен новый каталог непосредственно внутри .work/deliveries')
    if output.is_relative_to(site) or site.is_relative_to(output): raise ValueError('Кандидат и delivery должны быть раздельными')
    before = take_snapshot(site, 'delivery')
    index = {e['path']:e for e in before['entries']}
    if any(p not in index for p in paths): raise ValueError('Выбран путь вне снимка кандидата')
    include = set(paths)
    for name in paths:
        parent = Path(name).parent
        while parent != Path('.'):
            include.add(parent.as_posix()); parent = parent.parent
    excluded = sorted(set(index)-include)
    created = False; parent_started = False
    try:
        if not deliveries.exists():
            parent_started = True
            deliveries.mkdir()
        # Once mkdir is attempted, an error can leave a partial destination.
        created = True
        output.mkdir(mode=0o700)
        if permission_profile=='web-readable': os.chmod(output,0o700)
        for name in sorted(include, key=lambda n:(n.count('/'), n)):
            entry = index[name]; dest = output/name
            if entry['type'] == 'directory':
                dest.mkdir(mode=0o700, exist_ok=True)
                if permission_profile=='web-readable': os.chmod(dest,0o700)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                original = site/name
                meta = original.lstat()
                if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1: raise ValueError('Исходный файл изменил тип')
                fd = os.open(original, os.O_RDONLY | getattr(os, 'O_NOFOLLOW',0) | getattr(os, 'O_BINARY',0))
                out_fd = -1
                try:
                    out_fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_BINARY',0), 0o600)
                    check = os.fstat(fd)
                    if (meta.st_dev,meta.st_ino)!=(check.st_dev,check.st_ino) or not stat.S_ISREG(check.st_mode) or check.st_nlink!=1: raise ValueError('Исходный файл изменился при копировании')
                    h=hashlib.sha256(); size=0
                    with os.fdopen(fd, 'rb') as src, os.fdopen(out_fd, 'wb') as dst:
                        fd=out_fd=-1
                        while True:
                            chunk=src.read(1024*1024)
                            if not chunk: break
                            size+=len(chunk); h.update(chunk); dst.write(chunk)
                        dst.flush()
                        if permission_profile=='web-readable': os.fchmod(dst.fileno(),0o600)
                        os.fsync(dst.fileno())
                    if size!=entry['size'] or h.hexdigest()!=entry['sha256']: raise ValueError('Содержимое кандидата изменилось при копировании')
                finally:
                    if fd!=-1: os.close(fd)
                    if out_fd!=-1: os.close(out_fd)
        after = take_snapshot(site, 'delivery'); delivery = take_snapshot(output, 'delivery')
        if before['digest'] != after['digest']: raise ValueError('Кандидат изменился во время копирования')
        if delivery['entries'] != [e for e in before['entries'] if e['path'] in include]: raise ValueError('Полученный состав не совпадает с выбором')
        metadata=_set_web_readable(output,delivery) if permission_profile=='web-readable' else None
        records = _path(work, work/'delivery-records', existing=False); records.mkdir(exist_ok=True)
        record = {'version':2 if metadata else 1,'site_snapshot':before['digest'],'delivery_snapshot':delivery['digest'],
                  'selection_sha256':hashlib.sha256(raw).hexdigest(), 'delivery':str(output),
                  'included':sorted(include),'excluded':excluded,'status':'unverified'}
        if metadata:
            record.update({'permission_profile':'web-readable-v1','delivery_metadata':metadata})
        record_path = records/(uuid.uuid4().hex+'.json')
        _write_new(record_path,(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
        _sync_dir(records); _sync_dir(deliveries)
        return {**record,'record':str(record_path),'operation':'applied'}
    except Exception as exc:
        if created or parent_started:
            exposure='; файлы могут быть доступны локальным пользователям' if permission_profile=='web-readable' and created else ''
            raise DeliveryUncertain(f'Delivery неполный или исход записи неизвестен; проверьте {output} и {deliveries}{exposure}; не использовать как проверенную поставку: {exc}') from exc
        raise
