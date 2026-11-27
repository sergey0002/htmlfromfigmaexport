"""Read-only cgroup v2 capability hints; never a sandbox or delegation proof.

No cgroups or processes are created or modified. A writable-looking directory,
controller list, or mount option does not prove a usable delegated subtree.
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path, PurePosixPath

_MAX=65536
_REQUIRED={'cpu','memory','pids'}


def _read(path):
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_BINARY',0)
    fd=os.open(path,flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('Файл cgroup не является обычным')
        chunks=[]; remaining=_MAX+1
        while remaining:
            chunk=os.read(fd,min(remaining,4096))
            if not chunk: break
            chunks.append(chunk); remaining-=len(chunk)
        raw=b''.join(chunks)
        if len(raw)>_MAX: raise ValueError('Слишком большой файл cgroup')
        return raw.decode('utf8')
    finally:
        os.close(fd)


def _decode_mount(value):
    escapes={'040':' ','011':'\t','012':'\n','134':'\\'}
    def sub(match):
        code=match.group(1)
        if code not in escapes: raise ValueError('Неизвестное экранирование mountinfo')
        return escapes[code]
    return re.sub(r'\\([0-7]{3})',sub,value)


def _absolute(value):
    if not isinstance(value,str) or not value.startswith('/') or '\x00' in value or any(part=='..' for part in value.split('/')):
        raise ValueError('Недопустимый путь cgroup')
    return PurePosixPath(value)


def _locate(cgroup_text,mountinfo_text):
    paths=[]
    for line in cgroup_text.splitlines():
        parts=line.split(':',2)
        if len(parts)==3 and parts[0]=='0' and parts[1]=='': paths.append(_absolute(parts[2]))
    if len(paths)!=1: raise ValueError('Не удалось однозначно определить cgroup v2 процесса')
    process=paths[0]; candidates=[]
    for line in mountinfo_text.splitlines():
        left,sep,right=line.partition(' - ')
        if not sep: continue
        a=left.split(); b=right.split()
        if len(a)<6 or len(b)<3 or b[0]!='cgroup2': continue
        root=_absolute(_decode_mount(a[3])); mount=_absolute(_decode_mount(a[4]))
        if process.is_relative_to(root):
            options=set(a[5].split(',')) | set(b[2].split(','))
            candidates.append((len(root.parts),root,mount,options))
    if not candidates: raise ValueError('Не найден совместимый mount cgroup v2')
    best=max(item[0] for item in candidates); matches=[item for item in candidates if item[0]==best]
    if len(matches)!=1: raise ValueError('Неоднозначный mount cgroup v2')
    _,root,mount,options=matches[0]
    relative=process.relative_to(root)
    return Path(str(mount)),Path(str(mount)).joinpath(*relative.parts),options


def _access(path,mode):
    try: return bool(os.access(path,mode,effective_ids=True))
    except (TypeError,NotImplementedError,OSError): return None


def inspect(proc_cgroup='/proc/self/cgroup', proc_mountinfo='/proc/self/mountinfo'):
    base={'status':'unknown','delegation_verified':False,'aggregate_limits_verified':False,
          'disk_quota':'unknown','executes_project':False,
          'limitations':['Только чтение и подсказки: права, mount и список controllers не доказывают делегирование или работу лимитов.',
                         'Дисковая квота, изоляция, безопасность передачи артефактов и происхождение не проверяются.']}
    try:
        mount,directory,options=_locate(_read(proc_cgroup),_read(proc_mountinfo))
        if any(path.is_symlink() for path in (mount,*mount.parents,directory,*directory.parents)):
            raise ValueError('Symlink в пути cgroup не поддерживается')
        if not directory.is_dir(): raise ValueError('Каталог текущей cgroup не найден')
        controllers=set(_read(directory/'cgroup.controllers').split())
        enabled=set(_read(directory/'cgroup.subtree_control').split())
        group_type=_read(directory/'cgroup.type').strip()
        if not group_type: raise ValueError('Неизвестный тип cgroup')
        result={**base,'status':'observed','mount':str(mount),'current_group':str(directory),
                'mount_read_only':True if 'ro' in options else False if 'rw' in options else None,
                'directory_write_hint':_access(directory,os.W_OK|os.X_OK),
                'available_controllers':sorted(controllers),'enabled_for_children':sorted(enabled),
                'missing_controllers':sorted(_REQUIRED-controllers),'cgroup_type':group_type,
                'kill_file_present':(directory/'cgroup.kill').is_file()}
        return result
    except (OSError,ValueError,UnicodeError) as exc:
        return {**base,'reason':str(exc)}
