"""Publication planning and gated transaction/recovery primitives.

The public apply gate always rejects: trustworthy evidence is not yet available.
The journal and restore code are experimental and tested only with fixtures.
"""
from __future__ import annotations
import json
from pathlib import Path

from . import queue_md as md
from .coverage import diagnostic
from .readiness import evaluate as evaluate_readiness
from .snapshot import take_snapshot
from . import posix_metadata


def _metadata_hint(path):
    path=Path(path)
    if not path.exists() and not path.is_symlink(): return None
    try:
        item=posix_metadata.inventory(path)
        return {'status':'supported','policy':item['policy'],'sha256':item['sha256']}
    except (OSError,ValueError,NotImplementedError) as exc:
        return {'status':'unsupported','reason':str(exc)}


def plan(source, delivery_record, target, run_record=None, run_sha256=None, manual_record=None, manual_sha256=None):
    source=Path(source).absolute(); work=source/'.work'
    record_path=md._path(work,delivery_record)
    if record_path.parent != work/'delivery-records': raise ValueError('Нужна запись из .work/delivery-records')
    record=json.loads(md._safe_read(record_path).decode('utf8'))
    if not isinstance(record, dict) or type(record.get('version')) is not int or record['version'] not in (1,2) or record.get('status')!='unverified':
        raise ValueError('Неизвестная запись delivery')
    site=md._path(work,Path(record['delivery']))
    if site.parent != work/'deliveries' or not site.is_dir(): raise ValueError('Недопустимый путь delivery')
    delivery=take_snapshot(site,'delivery')
    if delivery['digest']!=record.get('delivery_snapshot'): raise ValueError('Delivery изменился после создания')
    target=Path(target).absolute()
    if target != Path.cwd().absolute()/'vanilla' or target.is_symlink(): raise ValueError('Целью может быть только vanilla в корне рабочей папки')
    if target.exists() and not target.is_dir(): raise ValueError('Цель не является каталогом')
    old=take_snapshot(target,'delivery') if target.exists() else None
    delivery_metadata=_metadata_hint(site); target_metadata=_metadata_hint(target)
    if record['version']==2:
        expected=record.get('delivery_metadata')
        if (record.get('permission_profile')!='web-readable-v1' or not isinstance(expected,dict) or
                set(expected)!={'policy','sha256'} or expected.get('policy')!=posix_metadata.POLICY or
                not isinstance(expected.get('sha256'),str) or not md.HEX.fullmatch(expected['sha256']) or
                delivery_metadata!={'status':'supported',**expected}):
            raise ValueError('Метаданные delivery не совпадают с записью или не поддерживаются')
        inventory=posix_metadata.inventory(site,delivery)
        if inventory['sha256']!=expected['sha256'] or any(row['mode']!=(0o644 if row['type']=='file' else 0o755) for row in inventory['entries']):
            raise ValueError('Профиль прав delivery не совпадает с записью')
    old_index={x['path']:x for x in old['entries']} if old else {}
    new_index={x['path']:x for x in delivery['entries']}
    new_paths=set(new_index); old_paths=set(old_index)
    diff={'added':sorted(new_paths-old_paths), 'removed':sorted(old_paths-new_paths),
          'changed':sorted(p for p in new_paths&old_paths if new_index[p]!=old_index[p])}
    result=evaluate_readiness(source,site,run_record,run_sha256,manual_record,manual_sha256)
    if (take_snapshot(site,'delivery')['digest']!=delivery['digest'] or _target_snapshot(target)!=(old['digest'] if old else None)
            or _metadata_hint(site)!=delivery_metadata or _metadata_hint(target)!=target_metadata):
        raise ValueError('Delivery, цель или их метаданные изменились при планировании')
    inputs={'run_record':str(Path(run_record).absolute()) if run_record else None, 'run_sha256':run_sha256,
            'manual_record':str(Path(manual_record).absolute()) if manual_record else None, 'manual_sha256':manual_sha256}
    import os
    permissions={'work_writable_hint':os.access(work,os.W_OK|os.X_OK),
                 'target_parent_writable_hint':os.access(target.parent,os.W_OK|os.X_OK),
                 'target_readable_hint':os.access(target,os.R_OK|os.X_OK) if old else None,
                 'same_filesystem':os.stat(work).st_dev==os.stat(target.parent).st_dev,
                 'note':'Эти проверки не гарантируют будущие права, место на диске или отсутствие гонок.'}
    approvals=['Остановить внешних писателей и явно подтвердить это перед apply.',
               'Проверить diff и сделать независимый внешний backup при риске потери данных.']
    return {'operation':'not_applied','delivery_record':str(record_path),'delivery_snapshot':delivery['digest'],
            'delivery_metadata':delivery_metadata, 'target_metadata':target_metadata,
            'target':str(target),'target_snapshot':old['digest'] if old else None,'diff':diff,
            'permissions':permissions,'required_approvals':approvals,
            'readiness_inputs':inputs, 'queue_sha256':result['queue_sha256'],'requirements_hash':result['requirements_hash'],
            'source_snapshot':result['source_snapshot'],'coverage':result['coverage'],'resources':result['resources'],
            'static_status':'FAIL' if result['issues'] else 'INCOMPLETE', 'static_issues':result['issues'],
            'run':result['run'], 'manual':result['manual'], 'apply_allowed':False,
            'blockers':result['blockers']+['Apply намеренно закрыт; browser/manual post-publication приёмка и полная fault matrix не реализованы.',
                                           'Экспериментальная политика метаданных не является полноценным backup.'],
            'warnings':result['warnings']+[METADATA_LIMITATION]}


# The transaction implementation is intentionally gated even for direct Python
# calls. A future eligibility implementation must prove all plan prerequisites;
# supplying a caller-created plan or a matching hash cannot enable apply.
class PublicationUncertain(OSError):
    pass


METADATA_LIMITATION = ('POSIX-профиль экспериментален: проверяются только mode, числовые uid/gid и mtime; '
                       'видимые xattrs/ACL и специальные биты отклоняются, atime, ctime, birth time и атрибуты ОС не сохраняются. '
                       'Права delivery зависят от профиля; доступ web-сервера и безопасность содержимого не подтверждены. '
                       'Оригинальный локальный backup не заменяет внешний.')


def _copy_snapshot(source, destination, snapshot):
    """Copy bytes and the supported metadata subset; never overwrite a tree."""
    metadata=posix_metadata.inventory(source,snapshot)
    posix_metadata.copy_checked(source,destination,snapshot,metadata)


def _target_snapshot(target):
    target = Path(target)
    if target.is_symlink(): raise ValueError('Symlink цели запрещён')
    if not target.exists(): return None
    if not target.is_dir(): raise ValueError('Цель должна быть каталогом')
    return take_snapshot(target, 'delivery')['digest']


def _publication_directory(source, run_id):
    import re
    source=Path(source).absolute(); work=source/'.work'
    if not re.fullmatch(r'[0-9a-f]{32}', run_id): raise ValueError('Некорректный ID публикации')
    run=md._path(work,work/'publications'/run_id)
    if not run.is_dir(): raise ValueError('Журнал публикации не найден')
    return work,run


def _journal(run, value):
    from .migrate_queue import _journal_write
    _journal_write(run, value)


def _guard_previous_publications(source, work):
    """Never start another transaction over an unresolved local journal."""
    import re
    root=md._path(work,work/'publications',existing=False)
    if not root.exists(): return
    if not root.is_dir(): raise ValueError('Каталог публикаций повреждён')
    for run in root.iterdir():
        if run.is_symlink() or not run.is_dir() or not re.fullmatch(r'[0-9a-f]{32}',run.name):
            raise ValueError('Неизвестное содержимое каталога публикаций; нужен ручной разбор')
        try: state=inspect(source,run.name)
        except (OSError,ValueError,UnicodeError,KeyError,TypeError) as exc:
            raise ValueError(f'Неполный или повреждённый журнал публикации {run}; нужен ручной разбор') from exc
        # published_unverified is deliberately not considered accepted.
        if state['journal']['phase']!='restored' or not state['metadata_policy_recorded'] or not state['backup_valid']:
            raise ValueError(f'Предыдущая публикация не завершена безопасным восстановлением: {run}; сначала inspect/разбор')


def apply(source, report, report_sha256, offline_ack):
    """Apply only a fresh, internally eligible plan; currently always blocked."""
    import os
    import uuid
    from .migrate_queue import migration_lock
    if not offline_ack: raise ValueError('Нужно остановить внешние редакторы и подтвердить это')
    source=Path(source).absolute(); work=source/'.work'
    report=md._path(work,report)
    raw=md._safe_read(report, md.MAX_BYTES*8+10000)
    if not md.HEX.fullmatch(report_sha256 or '') or md.sha(raw)!=report_sha256: raise ValueError('Хеш отчёта плана не совпадает')
    envelope=json.loads(raw.decode('utf8'))
    if not isinstance(envelope,dict) or not isinstance(envelope.get('plan'),dict): raise ValueError('Недопустимый отчёт плана')
    requested=envelope['plan']
    record=requested.get('delivery_record'); target=requested.get('target')
    inputs=requested.get('readiness_inputs')
    expected_keys={'run_record','run_sha256','manual_record','manual_sha256'}
    if (not isinstance(record,str) or not isinstance(target,str) or not isinstance(inputs,dict)
            or set(inputs)!=expected_keys or any(value is not None and not isinstance(value,str) for value in inputs.values())):
        raise ValueError('План неполон')
    with migration_lock(work):
        if md._safe_read(report,md.MAX_BYTES*8+10000)!=raw: raise ValueError('План изменился')
        actual=plan(source,record,target,**inputs)
        if actual != requested: raise ValueError('План устарел или изменён; повторите планирование')
        if not actual.get('apply_allowed'):
            raise ValueError('Публикация заблокирована: нет полной проверяемой цепочки evidence и допустимого provenance')
        site=md._path(work,Path(json.loads(md._safe_read(md._path(work,record)).decode('utf8'))['delivery']))
        target=Path(target).absolute()
        if target != Path.cwd().absolute()/'vanilla': raise ValueError('Недопустимая цель')
        if os.stat(work).st_dev != os.stat(Path.cwd()).st_dev: raise ValueError('Публикация требует одну файловую систему')
        source_snapshot=take_snapshot(site,'delivery')
        if (actual.get('delivery_metadata',{}).get('status')!='supported' or
                (actual.get('target_metadata') is not None and actual['target_metadata'].get('status')!='supported')):
            raise ValueError('Неподдерживаемые метаданные требуют ручного разбора')
        if (source_snapshot['digest']!=actual['delivery_snapshot'] or _target_snapshot(target)!=actual['target_snapshot']
                or _metadata_hint(site)!=actual['delivery_metadata'] or _metadata_hint(target)!=actual['target_metadata']):
            raise ValueError('Delivery, цель или метаданные изменились после планирования')
        _guard_previous_publications(source,work)
        publications=md._path(work,work/'publications',existing=False)
        run=publications/uuid.uuid4().hex
        journal={'version':2,'phase':'preparing','target':str(target), 'old_snapshot':actual['target_snapshot'],
                 'new_snapshot':actual['delivery_snapshot'], 'old_metadata':actual['target_metadata'],
                 'new_metadata':actual['delivery_metadata'], 'plan_sha256':report_sha256}
        started=False
        try:
            started=True
            publications.mkdir(exist_ok=True)
            run.mkdir(mode=0o700)
            _journal(run,journal)
            _copy_snapshot(site,run/'next',source_snapshot)
            journal['phase']='prepared'; _journal(run,journal); md._sync_dir(publications)
            # Copying can be slow: re-evaluate all eligibility inputs again,
            # not just the delivery and destination, before the first rename.
            if plan(source,record,target,**inputs)!=actual:
                raise ValueError('Источник, очередь, требования или план изменились перед заменой')
            if (_target_snapshot(target)!=journal['old_snapshot'] or take_snapshot(site,'delivery')['digest']!=journal['new_snapshot']
                    or _metadata_hint(target)!=journal['old_metadata'] or _metadata_hint(site)!=journal['new_metadata']
                    or _metadata_hint(run/'next')!=journal['new_metadata']):
                raise ValueError('Цель, delivery или метаданные изменились перед заменой')
            if target.exists():
                started=True
                os.rename(target,run/'previous'); md._sync_dir(Path.cwd()); md._sync_dir(run)
                journal['phase']='backup_moved'; _journal(run,journal)
            started=True
            os.rename(run/'next',target); md._sync_dir(Path.cwd()); md._sync_dir(run)
            journal['phase']='installed'; _journal(run,journal)
            if _target_snapshot(target)!=journal['new_snapshot'] or _metadata_hint(target)!=journal['new_metadata']:
                raise OSError('После переноса состав или метаданные цели не совпадают')
            journal['phase']='postcheck_started'; _journal(run,journal)
            post=diagnostic(source,target)
            if (not isinstance(post,dict) or post.get('status') not in ('INCOMPLETE','FAIL','BLOCKED') or
                    any(not isinstance(post.get(k),list) or any(not isinstance(x,str) for x in post[k])
                        for k in ('issues','warnings')) or
                    (post.get('status')=='INCOMPLETE' and post.get('issues'))):
                raise ValueError('Некорректный или противоречивый результат статической постпроверки')
            if (post['delivery_snapshot']!=journal['new_snapshot'] or
                    any(post[key]!=actual[key] for key in ('source_snapshot','queue_sha256','requirements_hash'))):
                raise ValueError('После переноса источник, очередь или цель изменились')
            journal['postcheck']={'status':post['status'],'issues':post['issues'],'warnings':post['warnings'],
                                  'delivery_snapshot':post['delivery_snapshot'],
                                  'source_snapshot':post['source_snapshot'],'queue_sha256':post['queue_sha256'],
                                  'requirements_hash':post['requirements_hash']}
            if post['status'] in ('FAIL','BLOCKED'):
                journal['phase']='postcheck_failed'; _journal(run,journal)
                raise ValueError('Статическая постпроверка обнаружила ошибки или заблокирована; требуется разбор и при необходимости restore')
            # Do not trust a single stale postcheck result if inputs changed
            # while it was computed. This narrows, but cannot remove, races.
            again=diagnostic(source,target)
            if (not isinstance(again,dict) or any(again.get(k)!=post.get(k) for k in
                    ('status','issues','warnings','source_snapshot','queue_sha256','requirements_hash','delivery_snapshot')) or
                    _target_snapshot(target)!=journal['new_snapshot'] or _metadata_hint(target)!=journal['new_metadata']):
                raise ValueError('Данные или метаданные изменились во время постпроверки')
            # Static checks and matching hashes are not browser/manual acceptance.
            journal['phase']='published_unverified'; _journal(run,journal)
            return {'operation':'applied','publication_id':run.name,'journal':str(run/'journal.json'),
                    'status':'published_unverified','target_snapshot':journal['new_snapshot'],
                    'postcheck':journal['postcheck']}
        except Exception as exc:
            if started: raise PublicationUncertain(f'Каталог, журнал или состояние публикации могли измениться: {run}; inspect и разбор перед повтором, неполный журнал требует ручной диагностики: {exc}') from exc
            raise


def inspect(source, run_id):
    work,run=_publication_directory(source,run_id)
    journal=json.loads(md._safe_read(md._path(work,run/'journal.json')).decode('utf8'))
    phases={'preparing','prepared','backup_moved','installed','postcheck_started','postcheck_failed','published_unverified','recovery_saved','restored'}
    if not isinstance(journal,dict) or journal.get('version') not in (1,2) or journal.get('phase') not in phases:
        raise ValueError('Неизвестный журнал публикации')
    target=Path(journal.get('target','')).absolute()
    if target!=Path.cwd().absolute()/'vanilla': raise ValueError('Цель журнала не совпадает с рабочим каталогом')
    old,new=journal.get('old_snapshot'),journal.get('new_snapshot')
    if (old is not None and (not isinstance(old,str) or not md.HEX.fullmatch(old))) or not isinstance(new,str) or not md.HEX.fullmatch(new):
        raise ValueError('Некорректные хеши журнала')
    previous=md._path(work,run/'previous',existing=False)
    next_dir=md._path(work,run/'next',existing=False)
    preserved=md._path(work,run/'recovery-preserved',existing=False)
    restore_copy=md._path(work,run/'restore-copy',existing=False)
    current=_target_snapshot(target); backup=_target_snapshot(previous)
    staged=_target_snapshot(next_dir); saved=_target_snapshot(preserved)
    restore_snapshot=_target_snapshot(restore_copy)
    if journal['version']==2:
        old_meta,new_meta=journal.get('old_metadata'),journal.get('new_metadata')
        def valid_meta(value):
            return (isinstance(value,dict) and set(value)=={'status','policy','sha256'} and value['status']=='supported'
                    and value['policy']==posix_metadata.POLICY and isinstance(value['sha256'],str) and bool(md.HEX.fullmatch(value['sha256'])))
        if not valid_meta(new_meta) or (old is None and old_meta is not None) or (old is not None and not valid_meta(old_meta)):
            raise ValueError('Некорректные метаданные журнала')
        current_meta=_metadata_hint(target); backup_meta=_metadata_hint(previous)
        staged_meta=_metadata_hint(next_dir); saved_meta=_metadata_hint(preserved); restore_meta=_metadata_hint(restore_copy)
        state=('absent' if current is None else 'new' if current==new and current_meta==new_meta else
               'old' if current==old and current_meta==old_meta else 'unknown')
        backup_valid=(backup==old and backup_meta==old_meta) if old is not None else backup is None and backup_meta is None
        limitations=[METADATA_LIMITATION]
    else:
        current_meta=backup_meta=staged_meta=saved_meta=restore_meta=None
        state='absent' if current is None else 'new' if current==new else 'old' if current==old else 'unknown'
        backup_valid=False
        limitations=[METADATA_LIMITATION,'Журнал v1 не содержит контрольной суммы метаданных; автоматический restore заблокирован.']
    return {'publication_id':run_id,'journal':journal,'target_snapshot':current,'backup_snapshot':backup,
            'staged_snapshot':staged,'preserved_snapshot':saved, 'target_metadata':current_meta,
            'backup_metadata':backup_meta,'staged_metadata':staged_meta,'preserved_metadata':saved_meta,
            'restore_copy_snapshot':restore_snapshot,'restore_copy_metadata':restore_meta,
            'restore_copy_valid':None if restore_snapshot is None else (journal['version']==2 and old is not None and restore_snapshot==old and restore_meta==old_meta),
            'target_state':state,'backup_valid':backup_valid,'metadata_policy_recorded':journal['version']==2,
            'limitations':limitations, 'operation':'not_applied'}


def restore(source, run_id, expected_target, offline_ack, clear_stale_lock=False):
    """Restore the old tree without deleting the new tree; requires explicit CAS."""
    import os
    from .migrate_queue import migration_lock
    if not offline_ack: raise ValueError('Нужно остановить внешние редакторы и подтвердить это')
    work,run=_publication_directory(source,run_id)
    with migration_lock(work,clear_stale_lock=clear_stale_lock):
        state=inspect(source,run_id); journal=state['journal']; target=Path(journal['target'])
        if not state['metadata_policy_recorded']:
            raise ValueError('Журнал v1 не подтверждает метаданные; требуется ручное восстановление')
        actual=state['target_snapshot'] or 'absent'
        if actual!=expected_target: raise ValueError('Цель изменилась; восстановление заблокировано')
        if state['target_state']=='unknown' or not state['backup_valid']:
            raise ValueError('Неизвестная цель или backup; требуется ручной разбор')
        if journal['phase']=='restored':
            if state['target_snapshot']!=journal['old_snapshot']: raise ValueError('Восстановленная цель изменилась')
            return {'operation':'not_applied','status':'restored','publication_id':run_id,'limitations':[METADATA_LIMITATION]}
        if state['target_state']=='old' and state['backup_snapshot'] is None:
            raise ValueError('Backup отсутствует; ничего не перезаписывается')
        if state['preserved_snapshot'] is not None and (state['preserved_snapshot']!=journal['new_snapshot'] or
                                                        state['preserved_metadata']!=journal['new_metadata']):
            raise ValueError('Сохранённая новая версия или её метаданные изменились')
        restore_dir=md._path(work,run/'restore-copy',existing=False)
        started=False
        try:
            if restore_dir.exists():
                if _target_snapshot(restore_dir)!=journal['old_snapshot'] or _metadata_hint(restore_dir)!=journal['old_metadata']:
                    raise ValueError('Существующая копия восстановления отличается')
            elif journal['old_snapshot'] is not None:
                backup=md._path(work,run/'previous'); backup_snapshot=take_snapshot(backup,'delivery')
                started=True
                _copy_snapshot(backup,restore_dir,backup_snapshot)
            # Recheck after the potentially slow copy. Offline writers remain
            # mandatory; this reduces but does not eliminate filesystem races.
            now=inspect(source,run_id)
            copy_fields={'restore_copy_snapshot','restore_copy_metadata','restore_copy_valid'}
            if {k:v for k,v in now.items() if k not in copy_fields}!={k:v for k,v in state.items() if k not in copy_fields}:
                raise ValueError('Цель, журнал или сохранённые деревья изменились при подготовке восстановления')
            if _target_snapshot(restore_dir)!=journal['old_snapshot'] or _metadata_hint(restore_dir)!=journal['old_metadata']:
                raise ValueError('Подготовленная копия восстановления отличается от backup')
            if state['target_state']=='new':
                if state['preserved_snapshot'] is not None: raise ValueError('Новая версия уже сохранена; нужен ручной разбор')
                started=True; os.rename(target,run/'recovery-preserved'); md._sync_dir(Path.cwd()); md._sync_dir(run)
                journal['phase']='recovery_saved'; _journal(run,journal)
            if journal['old_snapshot'] is not None and not target.exists():
                started=True; os.rename(restore_dir,target); md._sync_dir(Path.cwd()); md._sync_dir(run)
            if _target_snapshot(target)!=journal['old_snapshot'] or _metadata_hint(target)!=journal['old_metadata']:
                raise OSError('Восстановленная цель или метаданные не совпадают с backup')
            started=True; journal['phase']='restored'; _journal(run,journal)
            return {'operation':'applied','status':'restored','publication_id':run_id,'limitations':[METADATA_LIMITATION]}
        except Exception as exc:
            if started: raise PublicationUncertain(f'Копия или состояние восстановления могли измениться; inspect и ручной разбор перед повтором: {run}: {exc}') from exc
            raise
