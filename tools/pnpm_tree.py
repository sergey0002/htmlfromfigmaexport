"""Experimental offline pnpm-shaped tree, not an installer or security boundary.

A restricted lock graph is materialized with internal relative symlinks. This
never executes a package manager, project code or scripts. pnpm's complete
resolution semantics, native modules and compatibility are NOT reproduced.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import unicodedata
import uuid
from pathlib import Path, PurePosixPath

from . import locked_npm as npm, locked_pnpm as pnpm, queue_md as md
from .snapshot import _file_hash, take_snapshot

MAX_TREE_FILES=100_000
MAX_TREE_BYTES=512_000_000


def _key_info(key,metadata):
    name,version,base=pnpm._identity(key,peer_allowed=True)
    return name,metadata[base]


def _select(metadata,graph,roots):
    if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
        raise ValueError('Поддерживается только Linux x86_64')
    libc=platform.libc_ver()[0]
    if libc!='glibc': raise ValueError('Этот эксперимент проверяется только на Linux glibc')
    selected={}; skipped=set()
    pending=[(key,kind!='optionalDependencies') for key,kind in roots]
    while pending:
        key,required=pending.pop()
        _,item=_key_info(key,metadata)
        compatible=(npm._compatible(item['os'],'linux') and npm._compatible(item['cpu'],'x64')
                    and npm._compatible(item['libc'],'glibc'))
        if not compatible:
            if required: raise ValueError('Обязательная зависимость несовместима с Linux x64 glibc')
            skipped.add(key); continue
        skipped.discard(key)
        if key in selected and (selected[key] or not required): continue
        selected[key]=required
        # A normal dependency of an optional package is still required if
        # that parent is kept. Do not silently build a broken parent; reject
        # instead of trying to reproduce pnpm's optional-subtree semantics.
        for child,kind in graph[key]: pending.append((child,kind!='optionalDependencies'))
    return selected,skipped


def _layout(metadata,graph,roots,selected):
    """Use deterministic snapshot IDs, including peer suffixes, for isolation."""
    locations={}
    for key in selected:
        name,_=_key_info(key,metadata)
        token=hashlib.sha256(key.encode('utf8')).hexdigest()
        locations[key]=f'node_modules/.pnpm/{token}/node_modules/{name}'
    if len(set(locations.values()))!=len(locations): raise ValueError('Конфликт snapshot ID')
    links={}
    def add(path,target):
        if path in links and links[path]!=target: raise ValueError('Конфликт зависимостей в pnpm graph')
        links[path]=target
    for key in selected:
        own,_=_key_info(key,metadata)
        base=locations[key][:-len(own)]
        for child,_ in graph[key]:
            if child not in selected: continue
            name,_=_key_info(child,metadata)
            if name==own: raise ValueError('Самозависимость с тем же именем не поддерживается')
            add(base+name,locations[child])
    for key,_kind in roots:
        if key in selected:
            name,_=_key_info(key,metadata); add('node_modules/'+name,locations[key])
    return locations,links


def _safe_rel(name):
    if not isinstance(name,str) or not name or name.startswith('/') or '\\' in name or any(ord(c)<32 or ord(c)==127 for c in name):
        return False
    parts=name.split('/')
    return len(parts)<=140 and all(p not in ('','.','..') for p in parts)


def tree_snapshot(root, links):
    """Hash regular files, execute bits, directories and explicitly listed links.

    No symlink is followed when walking. Link paths and destinations must match
    the supplied graph, remain internal and resolve to ordinary directories.
    This detects drift, not a concurrent hostile writer or authenticity.
    """
    root=Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or not isinstance(links,dict): raise ValueError('Некорректное дерево зависимостей')
    for link,target in links.items():
        if not _safe_rel(link) or not _safe_rel(target): raise ValueError('Некорректная ссылка графа')
    found=set(); entries=[]; total=0; seen={}
    def visit(folder):
        nonlocal total
        with os.scandir(folder) as iterator: children=sorted(iterator,key=lambda x:os.fsencode(x.name))
        for child in children:
            path=Path(child.path); rel=path.relative_to(root).as_posix()
            if not _safe_rel(rel): raise ValueError('Некорректный путь зависимостей')
            try: rel.encode('utf8',errors='strict')
            except UnicodeEncodeError as exc: raise ValueError('Имя зависимостей не UTF-8') from exc
            key=unicodedata.normalize('NFC',rel).casefold()
            if key in seen: raise ValueError('Конфликт имён в дереве зависимостей')
            seen[key]=rel
            meta=child.stat(follow_symlinks=False)
            if stat.S_ISLNK(meta.st_mode):
                if rel not in links: raise ValueError('Неожиданная ссылка в дереве')
                value=os.readlink(path)
                if os.path.isabs(value) or '\\' in value: raise ValueError('Недопустимая ссылка зависимостей')
                dest=os.path.normpath(os.path.join(os.path.dirname(rel),value)).replace(os.sep,'/')
                if dest!=links[rel]: raise ValueError('Ссылка зависимостей изменена')
                found.add(rel); entries.append(['link',rel,value])
            elif stat.S_ISDIR(meta.st_mode):
                entries.append(['directory',rel]); visit(path)
            elif stat.S_ISREG(meta.st_mode):
                size,digest=_file_hash(path,meta); total+=size
                if total>MAX_TREE_BYTES: raise ValueError('Слишком большое дерево зависимостей')
                entries.append(['file',rel,size,digest,meta.st_mode & 0o111])
            else: raise ValueError('Специальный файл зависимостей запрещён')
            if len(entries)>MAX_TREE_FILES: raise ValueError('Слишком много файлов зависимостей')
    visit(root)
    if found!=set(links): raise ValueError('Ссылки графа отсутствуют')
    for target in links.values():
        cursor=root
        for part in PurePosixPath(target).parts:
            cursor=cursor/part
            if cursor.is_symlink() or not cursor.is_dir(): raise ValueError('Цель ссылки не является обычным каталогом')
    data=json.dumps(entries,ensure_ascii=True,separators=(',',':')).encode('ascii')
    return {'digest':hashlib.sha256(b'htmlfromfigma.pnpm-tree.v1\0'+data).hexdigest(), 'entries':len(entries),'bytes':total}


def prepare(source, project, output):
    source=Path(source).absolute(); work=source/'.work'
    current,metadata,graph,roots=pnpm._inventory(source,project)
    selected,skipped=_select(metadata,graph,roots)
    if not selected: raise ValueError('Не выбраны совместимые пакеты')
    locations,links=_layout(metadata,graph,roots,selected)
    if len(json.dumps(links,ensure_ascii=False).encode('utf8'))>pnpm.MAX_LOCK//2:
        raise ValueError('Слишком большой граф ссылок для записи')
    root=md._path(work,work/'pnpm-deps',existing=False); output=md._path(work,output,existing=False)
    if output.parent!=root or output.exists() or output.name.startswith('.'):
        raise ValueError('Нужен новый каталог непосредственно в .work/pnpm-deps')
    cache=md._path(work,work/'npm-tar-cache',existing=False)
    archives={}
    for key in selected:
        _,item=_key_info(key,metadata)
        path=md._path(work,cache/(item['sha512']+'.tgz'))
        raw=md._safe_read(path,npm.MAX_TARBALL)
        if hashlib.sha512(raw).hexdigest()!=item['sha512']: raise ValueError('Integrity tarball в кэше не совпадает')
        archives[key]=path
    if pnpm.inventory(source,project)!=current: raise ValueError('Source или lock изменились перед подготовкой')
    touched=False
    try:
        touched=True; root.mkdir(exist_ok=True); output.mkdir(mode=0o700)
        size=0; members=0
        for key,path in archives.items():
            name,item=_key_info(key,metadata)
            raw=md._safe_read(md._path(work,path),npm.MAX_TARBALL)
            if hashlib.sha512(raw).hexdigest()!=item['sha512']: raise ValueError('Tarball изменился при подготовке')
            dest=output/locations[key]; dest.mkdir(parents=True,exist_ok=False)
            extracted,count=npm._extract(raw,dest,name,item['version'],npm.MAX_EXTRACT-size)
            size+=extracted; members+=count
            if members>npm.MAX_MEMBERS: raise ValueError('Слишком много файлов пакетов')
        for link,target in sorted(links.items()):
            path=output/link; path.parent.mkdir(parents=True,exist_ok=True)
            os.symlink(os.path.relpath(output/target,path.parent),path)
        if pnpm.inventory(source,project)!=current: raise ValueError('Source или lock изменились при подготовке')
        for folder,dirs,_ in os.walk(output,topdown=False,followlinks=False): md._sync_dir(Path(folder))
        snapshot=tree_snapshot(output,links)
        records=md._path(work,work/'pnpm-deps-records',existing=False); records.mkdir(exist_ok=True)
        record={'version':1,'kind':'pnpm-shaped-tree','source_snapshot':current['source_snapshot'],
                'lock_sha256':current['lock_sha256'],'dependencies':str(output),'tree_snapshot':snapshot['digest'],
                'links':links,'packages':len(selected),'skipped':len(skipped),'scripts_executed':False,
                'isolated':False,'publication_eligible':False}
        raw=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf8')
        if len(raw)>pnpm.MAX_LOCK: raise ValueError('Слишком большая запись дерева')
        record_path=records/(uuid.uuid4().hex+'.json'); md._write_new(record_path,raw); md._sync_dir(records); md._sync_dir(root)
        return {'operation':'applied','record':str(record_path),'sha256':md.sha(raw),'dependencies':str(output),
                'tree_snapshot':snapshot['digest'],'packages':len(selected),'skipped':len(skipped),
                'scripts_executed':False,'isolated':False,'publication_eligible':False,
                'limitations':['Экспериментальное pnpm-shaped дерево, не pnpm install и не sandbox.',
                               'Семантика peers, native bindings, scripts и node_modules/.bin полностью не проверена.',
                               'Запуск проекта и публикация не разрешены; внешние писатели могут обойти проверки.']}
    except Exception as exc:
        if touched: raise npm.DependenciesUncertain(f'Дерево или запись могли быть созданы частично: {output}: {exc}') from exc
        raise


def inspect(source, file, expected_sha256):
    source=Path(source).absolute(); work=source/'.work'; path=md._path(work,file)
    if path.parent!=work/'pnpm-deps-records' or not isinstance(expected_sha256,str) or not md.HEX.fullmatch(expected_sha256):
        raise ValueError('Нужна запись pnpm-deps и её SHA-256')
    raw=md._safe_read(path,pnpm.MAX_LOCK)
    if md.sha(raw)!=expected_sha256: raise ValueError('Запись зависимостей изменена')
    record=npm._json(raw,'запись pnpm-deps')
    if (type(record.get('version')) is not int or record['version']!=1 or record.get('kind')!='pnpm-shaped-tree'
            or record.get('scripts_executed') is not False or record.get('isolated') is not False
            or record.get('publication_eligible') is not False): raise ValueError('Неизвестная запись pnpm-deps')
    dep=record.get('dependencies')
    if not isinstance(dep,str): raise ValueError('Путь зависимостей отсутствует')
    dep=md._path(work,dep)
    if dep.parent!=work/'pnpm-deps' or not dep.is_dir(): raise ValueError('Недопустимый путь зависимостей')
    source_now=take_snapshot(source,'source')['digest']; tree=tree_snapshot(dep,record.get('links'))
    changed=[]
    if source_now!=record.get('source_snapshot'): changed.append('source_snapshot')
    if tree['digest']!=record.get('tree_snapshot'): changed.append('tree_snapshot')
    if md._safe_read(path,pnpm.MAX_LOCK)!=raw: raise ValueError('Запись изменилась при проверке')
    return {'operation':'not_applied','freshness':'stale' if changed else 'current','changed':changed,
            'record':str(path),'dependencies':str(dep),'tree_snapshot':tree['digest'],
            'isolated':False,'publication_eligible':False}
