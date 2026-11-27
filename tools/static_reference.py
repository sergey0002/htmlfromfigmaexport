"""Materialize a read-only static reference copy without executing project code.

The copy's file provenance is verifiable relative to a recorded source snapshot,
but this is not an OS sandbox, a browser run, or proof of visual equivalence.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path

from . import queue_md as md
from .snapshot import take_snapshot


class ReferenceUncertain(OSError):
    pass


def materialize(source, selection_file, output):
    source=Path(source).absolute(); work=source/'.work'
    selection=md._path(work,selection_file); raw=md._safe_read(selection)
    selected=json.loads(raw.decode('utf8'))
    if (not isinstance(selected,list) or not selected or len(selected)>200000
            or any(not isinstance(p,str) or not md._relpath(p) or any(part.startswith('.') for part in p.split('/')) for p in selected)
            or len(selected)!=len(set(selected))):
        raise ValueError('Нужен непустой список уникальных открытых относительных путей')
    references=md._path(work,work/'static-references',existing=False)
    output=md._path(work,output,existing=False)
    if output.parent!=references or output.exists() or output.name.startswith('.'):
        raise ValueError('Нужен новый каталог непосредственно в .work/static-references')
    snapshot=take_snapshot(source,'source'); index={e['path']:e for e in snapshot['entries']}
    if any(path not in index for path in selected): raise ValueError('Путь отсутствует в source snapshot или исключён политикой')
    include=set(selected)
    for name in selected:
        parent=Path(name).parent
        while parent!=Path('.'):
            include.add(parent.as_posix()); parent=parent.parent
    if not any(index[name]['type']=='file' and name.lower().endswith(('.html','.htm')) for name in include):
        raise ValueError('В статическом эталоне нужна хотя бы одна выбранная HTML-страница')
    started=False
    try:
        # Either mkdir can succeed and still report an error (e.g. an injected
        # failure after the syscall), so mark the attempt before mutation.
        started=True
        references.mkdir(exist_ok=True)
        output.mkdir(mode=0o700)
        for name in sorted(include,key=lambda p:(p.count('/'),p)):
            entry=index[name]; src=md._path(source,source/name); dst=output/name
            if entry['type']=='directory': dst.mkdir(mode=0o700,exist_ok=True); continue
            meta=src.lstat()
            if not stat.S_ISREG(meta.st_mode) or meta.st_nlink!=1: raise ValueError('Исходный файл изменил тип')
            fd=os.open(src,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)); out_fd=-1
            try:
                info=os.fstat(fd)
                if (info.st_dev,info.st_ino)!=(meta.st_dev,meta.st_ino) or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                    raise ValueError('Исходный файл изменился при открытии')
                out_fd=os.open(dst,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0),0o600)
                digest=hashlib.sha256(); size=0
                with os.fdopen(fd,'rb') as inp,os.fdopen(out_fd,'wb') as out:
                    fd=out_fd=-1
                    while True:
                        chunk=inp.read(1024*1024)
                        if not chunk: break
                        size+=len(chunk); digest.update(chunk); out.write(chunk)
                    out.flush(); os.fsync(out.fileno())
                if size!=entry['size'] or digest.hexdigest()!=entry['sha256']:
                    raise ValueError('Исходный файл изменился при копировании')
            finally:
                if fd!=-1: os.close(fd)
                if out_fd!=-1: os.close(out_fd)
        copied=take_snapshot(output,'delivery')
        if copied['entries'] != [e for e in snapshot['entries'] if e['path'] in include]:
            raise ValueError('Копия не соответствует выбранным файлам')
        if take_snapshot(source,'source')['digest']!=snapshot['digest'] or md._safe_read(selection)!=raw:
            raise ValueError('Источник или выбор изменился во время копирования')
        for name in sorted((n for n in include if index[n]['type']=='directory'),key=lambda n:n.count('/'),reverse=True):
            md._sync_dir(output/name)
        md._sync_dir(output)
        records=md._path(work,work/'static-reference-records',existing=False); records.mkdir(exist_ok=True)
        record={'version':1,'kind':'static-reference-copy','source_snapshot':snapshot['digest'],
                'reference_snapshot':copied['digest'],'selection_sha256':hashlib.sha256(raw).hexdigest(),
                'reference':str(output),'included':sorted(include),'excluded':sorted(set(index)-include),
                'executes_source':False,'isolated':False,'publication_eligible':False}
        encoded=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf8')
        record_path=records/(uuid.uuid4().hex+'.json'); md._write_new(record_path,encoded)
        md._sync_dir(records); md._sync_dir(references)
        return {'operation':'applied','record':str(record_path),'sha256':md.sha(encoded),'reference':str(output),
                'source_snapshot':snapshot['digest'],'reference_snapshot':copied['digest'],
                'included':record['included'],'excluded':record['excluded'], 'publication_eligible':False}
    except Exception as exc:
        if started: raise ReferenceUncertain(f'Копия/запись могла быть создана частично: {output}; проверьте перед повтором: {exc}') from exc
        raise


def inspect(source, file, expected_sha256):
    source=Path(source).absolute(); work=source/'.work'; path=md._path(work,file)
    if path.parent!=work/'static-reference-records' or not isinstance(expected_sha256,str) or not md.HEX.fullmatch(expected_sha256):
        raise ValueError('Нужна запись static-reference и её sha256')
    raw=md._safe_read(path,md.MAX_BYTES*8+10000)
    if md.sha(raw)!=expected_sha256: raise ValueError('Запись эталона изменена')
    record=json.loads(raw.decode('utf8'))
    if (not isinstance(record,dict) or record.get('kind')!='static-reference-copy' or record.get('version')!=1
            or record.get('isolated') is not False or record.get('publication_eligible') is not False):
        raise ValueError('Неизвестная запись статического эталона')
    ref=record.get('reference')
    if not isinstance(ref,str): raise ValueError('Путь эталона отсутствует')
    ref=md._path(work,ref)
    if ref.parent!=work/'static-references' or not ref.is_dir(): raise ValueError('Недопустимая копия эталона')
    source_now=take_snapshot(source,'source')['digest']; ref_now=take_snapshot(ref,'delivery')['digest']
    changed=[]
    if source_now!=record.get('source_snapshot'): changed.append('source_snapshot')
    if ref_now!=record.get('reference_snapshot'): changed.append('reference_snapshot')
    if md._safe_read(path,md.MAX_BYTES*8+10000)!=raw: raise ValueError('Запись эталона изменилась при проверке')
    return {'operation':'not_applied','path':str(path),'sha256':expected_sha256,'reference':str(ref),
            'freshness':'stale' if changed else 'current','changed':changed,'record':record,
            'isolated':False,'publication_eligible':False}


def audit(source,site,record,expected_sha256,acknowledge_browser_code,output=None):
    """Serve an exact static copy for diagnostics; this is NOT OS isolation."""
    if not acknowledge_browser_code:
        raise ValueError('Нужно явно подтвердить риск выполнения кода страниц в браузере; изоляция не предоставляется')
    from .audit_markdown import audit as browser_audit
    from .lifecycle import serve_site
    source=Path(source).absolute(); work=source/'.work'; site=Path(site).absolute()
    state=inspect(source,record,expected_sha256)
    if state['freshness']!='current': raise ValueError('Копия статического эталона устарела')
    reference=Path(state['reference'])
    if reference==site or reference.is_relative_to(site) or site.is_relative_to(reference):
        raise ValueError('Кандидат и копия эталона должны быть отдельными каталогами')
    result=None
    try:
        with serve_site(reference) as url:
            result=browser_audit(source,site,url,output)
        again=inspect(source,record,expected_sha256)
        if again['freshness']!='current': raise ValueError('Копия или source изменились во время аудита; отчёт не подтверждает происхождение')
        binding={'version':1,'kind':'static-reference-binding','record':str(Path(record).absolute()),
                 'record_sha256':expected_sha256,'reference_snapshot':state['record']['reference_snapshot'],
                 'source_snapshot':state['record']['source_snapshot'], 'isolated':False}
        directory=md._path(work,result['artifact_directory']); path=md._path(work,directory/'static-reference-binding.json',existing=False)
        encoded=(json.dumps(binding,ensure_ascii=False,indent=2)+'\n').encode('utf8')
        md._write_new(path,encoded); md._sync_dir(directory)
        result['static_reference_binding']=binding
        result['warnings'].append('Копия статического эталона связана со снимком source; ОС-изоляция и происхождение исполнения не подтверждены.')
        return result
    except Exception as exc:
        if result is not None:
            raise ReferenceUncertain(f'Артефакты созданы, но привязка статического эталона не завершена; проверьте {result.get("artifact_directory")}: {exc}') from exc
        raise
