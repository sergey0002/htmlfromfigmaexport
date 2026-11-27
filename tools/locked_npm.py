"""Prepare a bounded npm lockfile-v3 dependency tree without executing npm.

Only Linux x86-64 registry tarballs with SHA-512 integrity are supported. This
is a constrained adapter, not an npm replacement, isolation boundary or proof
that dependencies are safe. Lifecycle scripts are never executed.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import platform
import re
import tarfile
import unicodedata
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import queue_md as md
from .snapshot import take_snapshot

MAX_LOCK=16_000_000
MAX_TARBALL=64_000_000
MAX_TOTAL_DOWNLOAD=512_000_000
MAX_EXTRACT=512_000_000
MAX_MEMBERS=100_000
NAME=r'(?:@[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*|[a-z0-9][a-z0-9._-]*)'
PACKAGE_PATH=re.compile(r'^node_modules/'+NAME+r'(?:/node_modules/'+NAME+r')*$')


class DependenciesUncertain(OSError):
    pass


def _json(raw, name):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('Повторный ключ JSON')
            result[key]=value
        return result
    try: result=json.loads(raw.decode('utf8'),object_pairs_hook=unique)
    except (UnicodeError,ValueError) as exc: raise ValueError(f'Некорректный {name}') from exc
    if not isinstance(result,dict): raise ValueError(f'{name} должен быть объектом')
    return result


def _compatible(rules, value):
    if rules is None: return True
    if not isinstance(rules,list) or any(not isinstance(x,str) or not x or x=='!' for x in rules):
        raise ValueError('Некорректные ограничения os/cpu')
    positive=[x for x in rules if not x.startswith('!')]
    return value not in [x[1:] for x in rules if x.startswith('!')] and (not positive or value in positive)


def _sha512(integrity):
    if not isinstance(integrity,str) or not integrity.startswith('sha512-') or ' ' in integrity:
        raise ValueError('Нужна единственная integrity sha512')
    try: digest=base64.b64decode(integrity[7:],validate=True)
    except (ValueError,binascii.Error) as exc: raise ValueError('Некорректная integrity sha512') from exc
    if len(digest)!=64: raise ValueError('Некорректная длина sha512')
    return digest.hex()


def _registry_url(url):
    if not isinstance(url,str): raise ValueError('Отсутствует resolved URL пакета')
    try: parsed=urllib.parse.urlsplit(url)
    except ValueError as exc: raise ValueError('Некорректный resolved URL') from exc
    if (parsed.scheme!='https' or parsed.hostname!='registry.npmjs.org' or parsed.username is not None or
            parsed.password is not None or parsed.port not in (None,443) or not parsed.path.startswith('/') or
            parsed.query or parsed.fragment or any(ord(c)<32 for c in url) or '\\' in url):
        raise ValueError('Разрешены только HTTPS tarballs registry.npmjs.org без credentials и query')
    return url


def plan(source, project='.'):
    source=Path(source).absolute(); work=source/'.work'
    if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
        raise ValueError('Этот adapter проверяется только для Linux x86_64')
    md._path(work,work/'_probe',existing=False)
    if project=='.': root=source
    elif isinstance(project,str) and md._relpath(project): root=md._path(source,source/project)
    else: raise ValueError('Недопустимый путь npm project')
    if not root.is_dir(): raise ValueError('npm project не найден')
    snapshot=take_snapshot(source,'source'); index={e['path']:e for e in snapshot['entries']}
    def read(name):
        path=md._path(source,root/name)
        rel=path.relative_to(source).as_posix()
        if rel not in index or index[rel]['type']!='file': raise ValueError('Файл проекта исключён source snapshot')
        raw=md._safe_read(path,MAX_LOCK)
        if md.sha(raw)!=index[rel]['sha256']: raise ValueError('Файл изменился во время чтения')
        return raw
    package_raw=read('package.json'); lock_raw=read('package-lock.json')
    package=_json(package_raw,'package.json'); lock=_json(lock_raw,'package-lock.json')
    packages=lock.get('packages')
    if type(lock.get('lockfileVersion')) is not int or lock['lockfileVersion']!=3 or not isinstance(packages,dict) or not isinstance(packages.get(''),dict):
        raise ValueError('Поддерживается только npm package-lock v3 с packages')
    if len(packages)>2001: raise ValueError('Слишком много пакетов в lock')
    root_lock=packages['']
    for field in ('dependencies','devDependencies','optionalDependencies'):
        a=package.get(field,{}) or {}; b=root_lock.get(field,{}) or {}
        if not isinstance(a,dict) or not isinstance(b,dict) or a!=b: raise ValueError(f'package.json и lock различаются: {field}')
    install=[]; skipped=[]
    for path, item in sorted(packages.items()):
        if path=='': continue
        if not isinstance(path,str) or not PACKAGE_PATH.fullmatch(path) or not isinstance(item,dict) or item.get('link'):
            raise ValueError('Lock содержит workspace, ссылку или недопустимый путь пакета')
        name=path.rsplit('/node_modules/',1)[-1].removeprefix('node_modules/')
        if not _compatible(item.get('os'),'linux') or not _compatible(item.get('cpu'),'x64'):
            if item.get('optional') is not True: raise ValueError(f'Обязательный пакет несовместим с Linux x64: {path}')
            skipped.append({'path':path,'reason':'optional-incompatible-platform'}); continue
        version=item.get('version')
        if not isinstance(version,str) or not version or len(version)>200: raise ValueError('У пакета нет версии')
        install.append({'path':path,'name':name,'version':version,'resolved':_registry_url(item.get('resolved')),
                        'sha512':_sha512(item.get('integrity')),
                        'has_install_script':item.get('hasInstallScript') is True})
    if not install: raise ValueError('В lock нет устанавливаемых пакетов')
    if take_snapshot(source,'source')['digest']!=snapshot['digest']: raise ValueError('Source изменился во время чтения lock')
    return {'version':1,'kind':'locked-npm-plan','project':str(root),'source_snapshot':snapshot['digest'],
            'package_sha256':md.sha(package_raw),'lock_sha256':md.sha(lock_raw),'packages':install,'skipped':skipped,
            'platform':'linux-x64','scripts_executed':False,'isolated':False,'publication_eligible':False,
            'limitations':['Lifecycle-скрипты и npm не выполняются; ссылки .bin не создаются.',
                           'Поддерживаются только registry SHA-512 tarballs и npm lockfile v3; pnpm и workspaces не поддерживаются.',
                           'Подготовка зависимостей не запускает проект и не доказывает безопасность содержимого.']}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('Перенаправления registry tarball запрещены')


def _download(url, max_bytes):
    _registry_url(url)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    request=urllib.request.Request(url,headers={'User-Agent':'htmlfromfigma-locked-npm/1','Accept':'application/octet-stream'})
    with opener.open(request,timeout=30) as response:
        if response.status!=200: raise ValueError('Registry вернул неожиданный статус')
        length=response.headers.get('Content-Length')
        if length and (not length.isdigit() or int(length)>max_bytes): raise ValueError('Слишком большой tarball')
        raw=response.read(max_bytes+1)
    if len(raw)>max_bytes: raise ValueError('Слишком большой tarball')
    return raw


def _tar_name(name, root, expected_name):
    if (not isinstance(name,str) or not name or name.startswith('/') or len(name)>4096 or '\\' in name or
            any(ord(c)<32 or ord(c)==127 for c in name)):
        raise ValueError('Недопустимый путь tarball')
    parts=name.rstrip('/').split('/')
    if not parts or len(parts)>128 or any(x in ('','.','..','node_modules') for x in parts):
        raise ValueError('Недопустимый путь tarball')
    # Most npm tarballs use package/; DefinitelyTyped also publishes a root
    # named after the unscoped package. Never accept an arbitrary prefix.
    if root is None:
        if parts[0] not in ('package',expected_name.rsplit('/',1)[-1]): raise ValueError('Неизвестный корень tarball')
        root=parts[0]
    if parts[0]!=root: raise ValueError('Несколько корней tarball запрещены')
    return root, '/'.join(parts[1:]) or None


def _extract(raw, dest, expected_name, expected_version, budget):
    seen={}; count=0; total=0; root_name=None
    try:
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r|gz') as archive:
            for member in archive:
                count+=1
                if count>MAX_MEMBERS or not (member.isfile() or member.isdir()): raise ValueError('Недопустимый объект или слишком много файлов tarball')
                root_name,name=_tar_name(member.name,root_name,expected_name)
                if name is None:
                    if not member.isdir(): raise ValueError('Корень tarball должен быть каталогом')
                    continue
                key=unicodedata.normalize('NFC',name).casefold()
                if key in seen and (seen[key]!=('directory',name) or not member.isdir()):
                    raise ValueError('Повторные или конфликтующие пути tarball')
                seen[key]=('directory' if member.isdir() else 'file',name)
                out=dest/name
                if member.isdir(): out.mkdir(parents=True,exist_ok=True); continue
                if member.size<0: raise ValueError('Некорректный размер tarball')
                total+=member.size
                if total>budget: raise ValueError('Превышен лимит распакованных пакетов')
                out.parent.mkdir(parents=True,exist_ok=True)
                fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o700 if member.mode&0o111 else 0o600)
                try:
                    content=archive.extractfile(member)
                    if content is None: raise ValueError('Файл tarball недоступен')
                    remaining=member.size
                    with os.fdopen(fd,'wb') as f:
                        fd=-1
                        while remaining:
                            chunk=content.read(min(1024*1024,remaining))
                            if not chunk: raise ValueError('Обрезанный tarball')
                            f.write(chunk); remaining-=len(chunk)
                        f.flush(); os.fsync(f.fileno())
                finally:
                    if fd!=-1: os.close(fd)
    except (tarfile.TarError,EOFError) as exc: raise ValueError('Повреждённый tarball') from exc
    package=_json(md._safe_read(dest/'package.json',MAX_LOCK),'package.json зависимости')
    if package.get('name')!=expected_name or package.get('version')!=expected_version:
        raise ValueError('Имя или версия tarball не соответствуют lock')
    for folder,dirs,_ in os.walk(dest,topdown=False): md._sync_dir(Path(folder))
    return total,count


def prepare(source, project, output, allow_network=False):
    source=Path(source).absolute(); work=source/'.work'
    current=plan(source,project)
    root=md._path(work,work/'npm-deps',existing=False); output=md._path(work,output,existing=False)
    if output.parent!=root or output.exists() or output.name.startswith('.'):
        raise ValueError('Нужен новый каталог непосредственно в .work/npm-deps')
    cache=md._path(work,work/'npm-tar-cache',existing=False)
    # Validate all required tarballs before creating the destination. Network is
    # opt-in and only the registry host is accepted, without redirects/proxies.
    started=False
    try:
        blobs=[]; downloaded=0; cache_touched=False
        for package in current['packages']:
            file=md._path(work,cache/(package['sha512']+'.tgz'),existing=False)
            if file.exists(): raw=md._safe_read(file,MAX_TARBALL)
            else:
                if not allow_network: raise ValueError('Нет tarball в кэше; сеть требует явного разрешения')
                raw=_download(package['resolved'],MAX_TARBALL); downloaded+=len(raw)
                if downloaded>MAX_TOTAL_DOWNLOAD: raise ValueError('Превышен лимит загрузки')
                if hashlib.sha512(raw).hexdigest()!=package['sha512']: raise ValueError('Integrity загруженного tarball не совпадает')
                cache_touched=True
                cache.mkdir(exist_ok=True)
                try: md._write_new(file,raw); md._sync_dir(cache)
                except FileExistsError:
                    if md._safe_read(file,MAX_TARBALL)!=raw: raise ValueError('Кэш изменён параллельно')
            if hashlib.sha512(raw).hexdigest()!=package['sha512']: raise ValueError('Integrity tarball в кэше не совпадает')
            blobs.append((package,file))
        if plan(source,project)!=current: raise ValueError('Lock или source изменились до подготовки')
        cache_touched=True
        root.mkdir(exist_ok=True)
    except Exception as exc:
        if cache_touched: raise DependenciesUncertain(f'Кэш или рабочий каталог могли измениться до создания результата: {cache}: {exc}') from exc
        raise
    try:
        output.mkdir(mode=0o700); started=True
        total=0; members=0
        for package,file in blobs:
            raw=md._safe_read(md._path(work,file),MAX_TARBALL)
            if hashlib.sha512(raw).hexdigest()!=package['sha512']: raise ValueError('Tarball изменился во время подготовки')
            dest=output/package['path']; dest.mkdir(parents=True,exist_ok=False)
            size,count=_extract(raw,dest,package['name'],package['version'],MAX_EXTRACT-total)
            total+=size; members+=count
            if members>MAX_MEMBERS: raise ValueError('Слишком много файлов в зависимостях')
        if plan(source,project)!=current: raise ValueError('Lock или source изменились при подготовке')
        for folder,dirs,_ in os.walk(output,topdown=False): md._sync_dir(Path(folder))
        snapshot=take_snapshot(output,'delivery')
        records=md._path(work,work/'npm-deps-records',existing=False); records.mkdir(exist_ok=True)
        record={'version':1,'kind':'locked-npm-dependencies','project':current['project'],
                'source_snapshot':current['source_snapshot'],'lock_sha256':current['lock_sha256'],
                'dependency_snapshot':snapshot['digest'],'dependencies':str(output),'packages':current['packages'],
                'skipped':current['skipped'],'scripts_executed':False,'isolated':False,'publication_eligible':False}
        raw=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf8')
        path=records/(uuid.uuid4().hex+'.json'); md._write_new(path,raw); md._sync_dir(records); md._sync_dir(root)
        return {'operation':'applied','record':str(path),'sha256':md.sha(raw),'dependencies':str(output),
                'dependency_snapshot':snapshot['digest'],'source_snapshot':current['source_snapshot'],
                'packages':len(current['packages']),'skipped':len(current['skipped']),'scripts_executed':False,
                'publication_eligible':False,'limitations':current['limitations']}
    except Exception as exc:
        if started or cache_touched: raise DependenciesUncertain(f'Кэш, каталог зависимостей или запись могли измениться: {output}: {exc}') from exc
        raise


def inspect(source, file, expected_sha256):
    """Check relative integrity and drift; a caller-provided hash is not authenticity."""
    source=Path(source).absolute(); work=source/'.work'; path=md._path(work,file)
    if path.parent!=work/'npm-deps-records' or not isinstance(expected_sha256,str) or not md.HEX.fullmatch(expected_sha256):
        raise ValueError('Нужна запись npm-deps и её sha256')
    raw=md._safe_read(path,MAX_LOCK)
    if md.sha(raw)!=expected_sha256: raise ValueError('Запись зависимостей изменена')
    record=_json(raw,'запись зависимостей')
    if (type(record.get('version')) is not int or record['version']!=1 or record.get('kind')!='locked-npm-dependencies'
            or record.get('isolated') is not False or record.get('scripts_executed') is not False
            or record.get('publication_eligible') is not False):
        raise ValueError('Неизвестная запись зависимостей')
    value=record.get('dependencies')
    if not isinstance(value,str): raise ValueError('Путь зависимостей отсутствует')
    dep=md._path(work,value)
    if dep.parent!=work/'npm-deps' or not dep.is_dir(): raise ValueError('Недопустимый путь зависимостей')
    source_now=take_snapshot(source,'source')['digest']; dep_now=take_snapshot(dep,'delivery')['digest']
    changed=[]
    if source_now!=record.get('source_snapshot'): changed.append('source_snapshot')
    if dep_now!=record.get('dependency_snapshot'): changed.append('dependency_snapshot')
    if md._safe_read(path,MAX_LOCK)!=raw: raise ValueError('Запись зависимостей изменилась при проверке')
    return {'operation':'not_applied','path':str(path),'sha256':expected_sha256,'dependencies':str(dep),
            'freshness':'stale' if changed else 'current','changed':changed,'record':record,
            'isolated':False,'publication_eligible':False}
