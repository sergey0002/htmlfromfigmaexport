"""Versioned, length-framed snapshots. A digest is not an authenticity proof.

Source snapshots exclude working/generated trees and secret-like .env files.
Delivery snapshots include every entry. Special files and links are rejected.
"""
from __future__ import annotations

import hashlib
import os
import stat
import struct
import unicodedata
from pathlib import Path

MAGIC = b'htmlfromfigma.snapshot.v2\0'
SOURCE_IGNORED = {'.work', '.git', '.cache', '.venv', 'node_modules', 'dist', 'build', '.vite', '__pycache__'}
POLICIES = {'source': 'source-v2', 'delivery': 'delivery-v2'}


def _framed(value: bytes) -> bytes:
    return struct.pack('>Q', len(value)) + value


def _file_hash(path: Path, expected):
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f'Недопустимый тип файла или hardlink: {path}')
        if (before.st_dev, before.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError(f'Файл изменился при открытии: {path}')
        h = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError(f'Файл изменился во время чтения: {path}')
        return before.st_size, h.hexdigest()
    finally:
        os.close(fd)


def read_snapshot_file(path: Path, entry: dict, limit: int) -> bytes:
    """Read bounded bytes only if they still match a previous snapshot entry.

    O_NOFOLLOW protects the final component where supported, not ancestors or
    concurrent hostile writers. This is not an adversarial filesystem boundary.
    """
    if (entry.get('type') != 'file' or type(entry.get('size')) is not int or
            entry['size'] < 0 or entry['size'] > limit):
        raise ValueError('Недопустимый размер или тип файла snapshot')
    named = Path(path).lstat()
    if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1 or
            getattr(named, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
        raise ValueError('Файл snapshot изменил тип или стал ссылкой')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != entry['size'] or
                (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino)):
            raise ValueError('Файл snapshot изменил тип или размер')
        chunks=[]; remaining=limit+1
        while remaining:
            chunk=os.read(fd,min(1024*1024,remaining))
            if not chunk: break
            chunks.append(chunk); remaining-=len(chunk)
        content=b''.join(chunks)
        after=os.fstat(fd)
        if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns,before.st_nlink) !=
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_nlink) or
                len(content)!=entry['size'] or hashlib.sha256(content).hexdigest()!=entry.get('sha256')):
            raise ValueError('Файл snapshot изменился во время чтения')
        return content
    finally:
        os.close(fd)


def read_snapshot_prefix(path: Path, entry: dict, prefix_limit: int) -> bytes:
    """Stream-verify an entire snapshotted file, retaining only a bounded prefix.

    Protects the final component against links/FIFOs where the platform supports
    the open flags; it is not protection from adversarial ancestor races.
    """
    if (not isinstance(entry,dict) or entry.get('type')!='file' or type(entry.get('size')) is not int or
            entry['size']<0 or type(prefix_limit) is not int or prefix_limit<0 or prefix_limit>65536 or
            not isinstance(entry.get('sha256'),str)):
        raise ValueError('Недопустимая запись snapshot или лимит префикса')
    named=Path(path).lstat()
    if (not stat.S_ISREG(named.st_mode) or named.st_nlink!=1 or
            getattr(named,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):
        raise ValueError('Файл snapshot изменил тип или стал ссылкой')
    flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
    fd=os.open(path,flags)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size!=entry['size'] or
                (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino)):
            raise ValueError('Файл snapshot изменил тип или размер')
        digest=hashlib.sha256(); total=0; prefix=bytearray()
        while True:
            chunk=os.read(fd,1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>entry['size']: raise ValueError('Файл snapshot увеличился при чтении')
            digest.update(chunk)
            if len(prefix)<prefix_limit: prefix.extend(chunk[:prefix_limit-len(prefix)])
        after=os.fstat(fd)
        if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns,before.st_nlink) !=
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_nlink) or
                total!=entry['size'] or digest.hexdigest()!=entry['sha256']):
            raise ValueError('Файл snapshot изменился во время чтения')
        return bytes(prefix)
    finally:
        os.close(fd)


def take_snapshot(root: Path, kind: str = 'source') -> dict:
    """Create a snapshot without executing or modifying the tree.

    Link checks and repeated verification reduce races but do not protect against
    an adversary with concurrent filesystem access. Callers must recheck before
    applying any operation.
    """
    if kind not in POLICIES:
        raise ValueError('Неизвестная политика snapshot')
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Корень snapshot должен быть обычным каталогом')
    entries, excluded, seen = [], [], {}

    def visit(folder):
        with os.scandir(folder) as it:
            children = sorted(it, key=lambda item: os.fsencode(item.name))
        for item in children:
            path = Path(item.path)
            relative = path.relative_to(root).as_posix()
            try:
                encoded = relative.encode('utf-8', errors='strict')
            except UnicodeEncodeError as exc:
                raise ValueError(f'Имя не представимо в UTF-8: {relative!r}') from exc
            if kind == 'source':
                if item.name in SOURCE_IGNORED or item.name.startswith('.env'):
                    excluded.append({'path': relative, 'reason': 'source-policy'})
                    continue
                # Do not silently change source-v2 identity by introducing new
                # exclusions. Refuse case variants before reading or descending.
                folded = unicodedata.normalize('NFC', item.name).casefold()
                if folded in SOURCE_IGNORED or folded.startswith('.env'):
                    raise ValueError(f'Неоднозначное имя исключения source-v2: {relative!r}; требуется ручной разбор')
            key = unicodedata.normalize('NFC', relative).casefold()
            if key in seen:
                raise ValueError(f'Конфликт имён: {seen[key]} и {relative}')
            seen[key] = relative
            meta = item.stat(follow_symlinks=False)
            if stat.S_ISLNK(meta.st_mode) or getattr(meta, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                raise ValueError(f'Ссылка запрещена: {relative}')
            if stat.S_ISDIR(meta.st_mode):
                entries.append({'type': 'directory', 'path': relative, 'size': 0, 'sha256': '0' * 64})
                visit(path)
            elif stat.S_ISREG(meta.st_mode):
                size, digest = _file_hash(path, meta)
                entries.append({'type': 'file', 'path': relative, 'size': size, 'sha256': digest})
            else:
                raise ValueError(f'Специальный файл запрещён: {relative}')
            if len(entries) > 200000:
                raise ValueError('Слишком много файлов в snapshot')

    visit(root)
    entries.sort(key=lambda item: item['path'].encode('utf8'))
    h = hashlib.sha256(MAGIC)
    h.update(_framed(kind.encode()))
    h.update(_framed(POLICIES[kind].encode()))
    h.update(struct.pack('>Q', len(entries)))
    for entry in entries:
        h.update(_framed(entry['type'].encode()))
        h.update(_framed(entry['path'].encode('utf8')))
        h.update(struct.pack('>Q', entry['size']))
        h.update(bytes.fromhex(entry['sha256']))
    return {'version': 2, 'kind': kind, 'policy_id': POLICIES[kind],
            'digest': h.hexdigest(), 'entries': entries, 'excluded': excluded}
