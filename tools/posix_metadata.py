"""Experimental narrow POSIX metadata inventory/copy for publication fixtures.

This is not a backup format or an adversarial filesystem boundary. Callers must
stop other writers. Only ordinary single-link files and directories with no
visible xattrs/ACLs, no special mode bits, and usable owner permissions are
supported. atime, ctime, birth time, mount attributes and OS-specific metadata
are not preserved or authenticated. Numeric ownership must already match newly
created objects; this module never calls chown. No Windows support is claimed.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from . import queue_md as md
from .snapshot import take_snapshot

POLICY = 'posix-mode-owner-mtime-no-xattrs-v1'


def _entry(path, name, kind):
    meta = path.lstat()
    valid = stat.S_ISDIR(meta.st_mode) if kind == 'directory' else stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1
    if not valid: raise ValueError('Недопустимый тип объекта при проверке метаданных: ' + name)
    mode = stat.S_IMODE(meta.st_mode)
    if mode & 0o7000: raise ValueError('Специальные биты прав не поддерживаются: ' + name)
    if (mode & 0o500 != 0o500 if kind == 'directory' else mode & 0o400 == 0):
        raise ValueError('Недостаточно прав владельца для проверяемой копии: ' + name)
    if not hasattr(os, 'listxattr'): raise ValueError('Проверка xattrs недоступна')
    # An unreadable/unsupported xattr listing is a refusal, not an empty list.
    attrs = os.listxattr(path, follow_symlinks=False)
    if attrs: raise ValueError('xattrs или ACL не поддерживаются: ' + name)
    return {'path':name, 'type':kind, 'mode':mode, 'uid':meta.st_uid, 'gid':meta.st_gid, 'mtime_ns':meta.st_mtime_ns}


def inventory(root, snapshot=None):
    if os.name != 'posix': raise ValueError('Метаданные поддерживаются только в экспериментальном POSIX-профиле')
    root = Path(root).absolute()
    before = snapshot or take_snapshot(root, 'delivery')
    if before.get('kind') != 'delivery': raise ValueError('Требуется delivery snapshot')
    rows = [_entry(root, '', 'directory')]
    for entry in before['entries']:
        rows.append(_entry(md._path(root, root/entry['path']), entry['path'], entry['type']))
    if take_snapshot(root, 'delivery')['digest'] != before['digest']:
        raise ValueError('Дерево изменилось при проверке метаданных')
    raw = json.dumps({'policy':POLICY,'entries':rows},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
    return {'policy':POLICY, 'sha256':hashlib.sha256(raw).hexdigest(), 'entries':rows}


def copy_checked(source, destination, snapshot, metadata):
    """Create a new copy with a validated narrow metadata subset and fsync.

    Errors leave the incomplete directory for inspection, never overwrite it.
    Unsupported ownership or attributes fail before publication/restore rename.
    """
    source = Path(source).absolute(); destination = Path(destination).absolute()
    if metadata != inventory(source, snapshot): raise ValueError('Метаданные исходного дерева изменились')
    index = {row['path']:row for row in metadata['entries']}
    destination.mkdir(mode=0o700)
    os.chmod(destination, 0o700)
    dirs = [(destination, index[''])]
    for entry in snapshot['entries']:
        name = entry['path']; original = md._path(source, source/name); out = destination/name
        row = index[name]
        if entry['type'] == 'directory':
            out.mkdir(mode=0o700); os.chmod(out, 0o700)
            dirs.append((out,row)); continue
        src_fd = os.open(original, os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
        dst_fd = -1
        try:
            current = os.fstat(src_fd)
            meta = original.lstat()
            if (current.st_dev,current.st_ino)!=(meta.st_dev,meta.st_ino) or not stat.S_ISREG(current.st_mode) or current.st_nlink!=1:
                raise ValueError('Исходный файл изменился при открытии')
            dst_fd = os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            target = os.fstat(dst_fd)
            if (target.st_uid,target.st_gid)!=(row['uid'],row['gid']): raise ValueError('Владелец или группа не могут быть сохранены')
            h=hashlib.sha256(); size=0
            with os.fdopen(src_fd,'rb') as src, os.fdopen(dst_fd,'wb') as dst:
                src_fd=dst_fd=-1
                while True:
                    chunk=src.read(1024*1024)
                    if not chunk: break
                    h.update(chunk); size+=len(chunk); dst.write(chunk)
                dst.flush()
                if size!=entry['size'] or h.hexdigest()!=entry['sha256']: raise ValueError('Файл изменился при копировании')
                os.fchmod(dst.fileno(),row['mode'])
                os.utime(dst.fileno(),ns=(os.fstat(dst.fileno()).st_atime_ns,row['mtime_ns']))
                os.fsync(dst.fileno())
        finally:
            if src_fd!=-1: os.close(src_fd)
            if dst_fd!=-1: os.close(dst_fd)
    # Apply directory modes and times bottom-up after creating all children.
    for path,row in sorted(dirs,key=lambda pair:len(pair[0].parts),reverse=True):
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0)|getattr(os,'O_NOFOLLOW',0))
        try:
            target=os.fstat(fd)
            if (target.st_uid,target.st_gid)!=(row['uid'],row['gid']): raise ValueError('Владелец или группа каталога не могут быть сохранены')
            os.fchmod(fd,row['mode']); os.utime(fd,ns=(target.st_atime_ns,row['mtime_ns'])); os.fsync(fd)
        finally: os.close(fd)
    if inventory(source, snapshot)!=metadata: raise ValueError('Метаданные исходного дерева изменились при копировании')
    if take_snapshot(destination,'delivery')['digest']!=snapshot['digest'] or inventory(destination)['sha256']!=metadata['sha256']:
        raise ValueError('Копия или её метаданные не совпадают')
