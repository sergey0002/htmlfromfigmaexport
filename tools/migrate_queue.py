"""Explicit, journaled v1 cutover; never classifies legacy ambiguities.

The lock coordinates current writers only. The caller must stop old processes and
external editors. POSIX advisory lock is required; Windows is intentionally blocked.
"""
from __future__ import annotations
import contextlib
import difflib
import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from . import queue_md as md
from .queue import validate as validate_legacy, render as render_legacy
from .snapshot import take_snapshot


class MigrationUncertain(OSError):
    pass


@contextlib.contextmanager
def migration_lock(work, clear_stale_lock=False):
    try:
        import fcntl
    except ImportError as exc:
        raise ValueError('Миграция требует POSIX flock; эта ОС пока не поддерживается') from exc
    path = md._path(work, work/'.queue-md-os.lock', existing=False)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os,'O_NOFOLLOW',0), 0o600)
    try:
        info=os.fstat(fd)
        if info.st_nlink != 1: raise ValueError('Недопустимый hardlink lock-файла')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc: raise ValueError('Миграция уже выполняется') from exc
        if clear_stale_lock:
            lock = md._path(work, work/'.queue.lock', existing=False)
            if lock.exists():
                md._safe_read(lock, 10000)
                lock.unlink()
        with md._lock(work):
            yield
    finally:
        try: os.close(fd)
        except OSError as exc: raise MigrationUncertain(f'Не удалось освободить OS-lock; проверьте journal: {exc}') from exc


def _work(source):
    source=Path(source).absolute(); work=source/'.work'
    if source.is_symlink() or not source.is_dir() or work.is_symlink() or not work.is_dir(): raise ValueError('Недопустимая рабочая область')
    return source,work


def prepare(source):
    source,work = _work(source)
    info=md.inspect_legacy(source)
    if not info['markdown_matches_render']:
        raise ValueError('Markdown отличается от v1 render; сохраните оба варианта и разберите diff')
    manifest_raw=md._safe_read(md._path(work,work/'manifest.json'))
    markdown_raw=md._safe_read(md._path(work,work/'PAGE-QUEUE.md'))
    if md.sha(manifest_raw)!=info['manifest_sha256'] or md.sha(markdown_raw)!=info['markdown_sha256']:
        raise ValueError('Очередь изменилась во время чтения')
    data=validate_legacy(json.loads(manifest_raw.decode('utf8')))
    source_snapshot=take_snapshot(source,'source')['digest']
    rows=md.parse(md.template(source))
    for meta in rows['meta']:
        if meta['key']=='discovery_status': meta['value']='review_required'
        if meta['key']=='legacy_review': meta['value']='unclassified'
    for p in data['pages']:
        evidence = '; '.join(p.get('evidence',[])) if isinstance(p.get('evidence',[]),list) and all(isinstance(x,str) for x in p.get('evidence',[])) else ''
        rows['pages'].append(dict(zip(md.TABLES['pages'], (p['id'],p['title'],p['reference_route'],p['output'],p['confirmation'],'true',p['work_status'],evidence or 'legacy-v1: требуется проверка',''))))
        for route in p.get('reference_aliases',[]):
            rows['aliases'].append(dict(zip(md.TABLES['aliases'], (p['id'],route,'legacy-unverified','legacy-v1: требуется проверка'))))
        for s in p.get('states',[]):
            rows['states'].append(dict(zip(md.TABLES['states'], (p['id'],s['id'],str(s['required']).lower(),'390x844,768x1024,1440x900',s.get('scenario') or ''))))
    proposal=md.render(rows)
    proposal += ('\nИсторическая v1-очередь сохранена в архиве миграции. Все страницы временно обязательны, '
                 'размеры состояний взяты из standard-v1 и требуют проверки агентом. '
                 'Неопределённости, проверки и неизвестные поля v1 остаются без классификации в архиве; '
                 'они не являются evidence v2.\n')
    # Abort instead of transforming values which the grammar cannot represent.
    compiled=md.compile_queue(proposal,source)
    if compiled['source_snapshot_current'] != source_snapshot: raise ValueError('Источник изменился при подготовке миграции')
    diff=''.join(difflib.unified_diff(markdown_raw.decode('utf8').splitlines(keepends=True), proposal.splitlines(keepends=True), fromfile='legacy-PAGE-QUEUE.md', tofile='proposed-PAGE-QUEUE.md'))
    return {'version':1,'manifest_sha256':md.sha(manifest_raw),'markdown_sha256':md.sha(markdown_raw),
            'source_snapshot':source_snapshot,'proposal_sha256':md.sha(proposal.encode('utf8')),
            'proposal':proposal,'proposal_diff':diff,'requirements_hash':compiled['requirements_hash'],'counts':info['counts'],'unknown_fields':info['unknown_fields'],
            'unclassified_discovery':data['discovery'].get('unresolved',[]),
            'unclassified_links':data['unresolved_links'],
            'warnings':['Все страницы временно обязательны; применимость viewport требует проверки.',
                        'Свободные заметки и неясные ссылки не классифицированы и сохранены в архиве.',
                        'Проверки v1 — исторические, не являются evidence v2.']}


def create_plan(source, output):
    source,work=_work(source); output=md._path(work,output,existing=False)
    if output.exists() or not output.parent.is_dir(): raise ValueError('План должен быть новым файлом внутри .work')
    plan=prepare(source)
    content=(json.dumps(plan,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    if len(content)>md.MAX_BYTES: raise ValueError('План миграции превышает лимит; требуется ручная оценка формата')
    try:
        md._write_new(output,content)
        md._sync_dir(output.parent)
    except Exception as exc:
        raise MigrationUncertain(f'План миграции мог быть записан частично: {output}; проверьте перед повтором: {exc}') from exc
    return {'operation':'applied','plan':str(output), **{k:v for k,v in plan.items() if k != 'proposal'},'proposal':plan['proposal']}


def _journal_write(directory, journal):
    data=(json.dumps(journal,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    fd,tmp=tempfile.mkstemp(prefix='.journal-',dir=directory)
    try:
        with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,directory/'journal.json'); tmp=None
        md._sync_dir(directory)
    finally:
        if tmp and os.path.exists(tmp): os.unlink(tmp)


def _replace_queue(work, proposal):
    fd,tmp=tempfile.mkstemp(prefix='.migration-',dir=work)
    try:
        with os.fdopen(fd,'wb') as f: f.write(proposal); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,work/'PAGE-QUEUE.md'); tmp=None
        md._sync_dir(work)
    finally:
        if tmp and os.path.exists(tmp): os.unlink(tmp)


def _verify_archive(work, directory):
    journal=json.loads(md._safe_read(md._path(work,directory/'journal.json')).decode('utf8'))
    if not isinstance(journal, dict) or journal.get('version') != 1 or journal.get('phase') not in ('prepared','marker_installed','complete'):
        raise ValueError('Неизвестный журнал миграции')
    for name,key in (('manifest.json','manifest_sha256'),('PAGE-QUEUE.md','markdown_sha256'),('proposal.md','proposal_sha256')):
        if md.sha(md._safe_read(md._path(work,directory/name))) != journal[key]: raise ValueError('Backup миграции не прошёл проверку: '+name)
    return journal


def apply(source, plan_path, manifest_hash, markdown_hash, offline_ack):
    if not offline_ack: raise ValueError('Нужно явно подтвердить остановку старых писателей и внешних редакторов')
    source,work=_work(source); plan_path=md._path(work,plan_path)
    supplied=json.loads(md._safe_read(plan_path).decode('utf8'))
    if not md.HEX.fullmatch(manifest_hash or '') or not md.HEX.fullmatch(markdown_hash or ''): raise ValueError('Нужны оба sha256 исходных файлов')
    if not isinstance(supplied, dict): raise ValueError('Некорректный план миграции')
    if supplied.get('manifest_sha256')!=manifest_hash or supplied.get('markdown_sha256')!=markdown_hash: raise ValueError('Hashes не совпадают с планом')
    with migration_lock(work):
        # Do not create another archive while an earlier one is unresolved,
        # including failures before the marker was installed.
        md._guard_incomplete_migrations(work)
        current=prepare(source)
        if current != supplied: raise ValueError('План устарел или изменён; повторите dry-run и проверьте diff')
        migrations=md._path(work,work/'migrations',existing=False)
        run=migrations/uuid.uuid4().hex
        started=False
        try:
            started=True
            migrations.mkdir(exist_ok=True)
            run.mkdir(mode=0o700)
            manifest=md._safe_read(md._path(work,work/'manifest.json'))
            markdown=md._safe_read(md._path(work,work/'PAGE-QUEUE.md'))
            proposal=current['proposal'].encode('utf8')
            if md.sha(manifest)!=manifest_hash or md.sha(markdown)!=markdown_hash: raise ValueError('Очередь изменилась до backup')
            for name,raw in (('manifest.json',manifest),('PAGE-QUEUE.md',markdown),('proposal.md',proposal)):
                md._write_new(run/name,raw)
            journal={k:current[k] for k in ('version','manifest_sha256','markdown_sha256','proposal_sha256','source_snapshot','requirements_hash')}
            journal['phase']='prepared'; _journal_write(run,journal); _verify_archive(work,run)
            md._sync_dir(migrations)
            if md.sha(md._safe_read(work/'manifest.json'))!=manifest_hash or md.sha(md._safe_read(work/'PAGE-QUEUE.md'))!=markdown_hash or take_snapshot(source,'source')['digest']!=current['source_snapshot']:
                raise ValueError('Источник или очередь изменились до cutover')
            started=True
            md._write_new(work/md.MARKER,b'queue-md-v1\n'); md._sync_dir(work)
            journal['phase']='marker_installed'; _journal_write(run,journal)
            _replace_queue(work,proposal)
            if md.sha(md._safe_read(work/'PAGE-QUEUE.md'))!=current['proposal_sha256']: raise OSError('Новая очередь изменилась после замены')
            md._write_head(work, proposal, current['requirements_hash'])
            journal['phase']='complete'; _journal_write(run,journal)
            return {'operation':'applied','migration_id':run.name,'journal':str(run/'journal.json'), 'queue_sha256':current['proposal_sha256'], 'status':'review_required'}
        except Exception as exc:
            if started: raise MigrationUncertain(f'Архив или исход миграции могли измениться: {run}; сначала проверьте файлы и journal, неполный архив требует ручного разбора: {exc}') from exc
            raise


def inspect(source, migration_id):
    source,work=_work(source)
    if not re.fullmatch('[0-9a-f]{32}',migration_id): raise ValueError('Некорректный ID миграции')
    directory=md._path(work,work/'migrations'/migration_id)
    journal=_verify_archive(work,directory)
    manifest=md._safe_read(md._path(work,work/'manifest.json'))
    queue=md._safe_read(md._path(work,work/'PAGE-QUEUE.md'))
    marker=md._path(work,work/md.MARKER,existing=False)
    marker_state = 'absent' if not marker.exists() else 'valid' if md._safe_read(marker)==b'queue-md-v1\n' else 'invalid'
    return {'journal':journal, 'manifest_matches':md.sha(manifest)==journal['manifest_sha256'],
            'queue_state':'legacy' if md.sha(queue)==journal['markdown_sha256'] else 'proposal' if md.sha(queue)==journal['proposal_sha256'] else 'unknown',
            'marker_state':marker_state,'source_matches':take_snapshot(source,'source')['digest']==journal['source_snapshot']}


def recover(source, migration_id, offline_ack, clear_stale_lock=False):
    if not offline_ack: raise ValueError('Нужно подтвердить остановку старых писателей')
    source,work=_work(source)
    with migration_lock(work, clear_stale_lock=clear_stale_lock):
        state=inspect(source,migration_id)
        if not state['manifest_matches'] or not state['source_matches'] or state['marker_state']=='invalid' or state['queue_state']=='unknown':
            raise ValueError('Данные расходятся с журналом; требуется ручной разбор')
        run=work/'migrations'/migration_id; journal=state['journal']
        if journal['phase']=='complete':
            if state['marker_state']!='valid' or state['queue_state']!='proposal': raise ValueError('Завершённый журнал не соответствует файлам')
            return {'operation':'not_applied','migration_id':migration_id,'status':'complete'}
        started=False
        try:
            if state['marker_state']=='absent':
                started=True; md._write_new(work/md.MARKER,b'queue-md-v1\n'); md._sync_dir(work)
            journal['phase']='marker_installed'; _journal_write(run,journal)
            if state['queue_state']=='legacy':
                started=True; _replace_queue(work,md._safe_read(run/'proposal.md'))
            md._write_head(work, md._safe_read(run/'proposal.md'), journal['requirements_hash'])
            journal['phase']='complete'; _journal_write(run,journal)
            return {'operation':'applied','migration_id':migration_id,'status':'complete'}
        except Exception as exc:
            if started or state['marker_state']=='valid': raise MigrationUncertain(f'Восстановление прервано; повторно inspect: {run}: {exc}') from exc
            raise
