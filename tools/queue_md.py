"""Agent-owned, limited Markdown queue. No page discovery or publishing decisions.

This module deliberately does not migrate legacy v1. The marker prevents the
cooperating v1 writer from writing after a new-format queue is activated.
The lock does not protect against older programs or arbitrary external editors.
"""
from __future__ import annotations

import contextlib
import difflib
import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, unquote

from .queue import ID, local_route, safe_output
from .snapshot import take_snapshot

BEGIN = '<!-- QUEUE:BEGIN v1 -->'
END = '<!-- QUEUE:END -->'
MARKER = '.queue-md-active'
MAX_BYTES = 2_000_000
MAX_ROWS = 10000
TABLES = {
    'meta': ('key', 'value'),
    'pages': ('id', 'title', 'reference_route', 'output', 'confirmation', 'required', 'work_status', 'evidence', 'optional_reason'),
    'aliases': ('page_id', 'reference_route', 'purpose', 'evidence'),
    'states': ('page_id', 'state_id', 'required', 'viewports', 'scenario'),
    'resources': ('id', 'scope', 'location', 'required', 'status', 'evidence'),
    'issues': ('id', 'context', 'kind', 'status', 'resolution', 'reason'),
}
META = ('schema_version', 'source_snapshot', 'source_policy', 'discovery_status', 'confirmation_reason', 'check_policy', 'legacy_review', 'legacy_review_reason')
HEX = re.compile(r'^[0-9a-f]{64}$')
VIEWPORT = re.compile(r'^([1-9][0-9]{1,4})x([1-9][0-9]{1,4})$')


class QueueError(ValueError):
    pass


class CommitUncertain(OSError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _escape(value):
    value = str(value)
    if '\n' in value or '\r' in value:
        raise QueueError('Многострочные ячейки не поддерживаются')
    return value.replace('\\', '\\\\').replace('|', '\\|')


def _cells(line, lineno):
    if not line.startswith('|') or not line.endswith('|'):
        raise QueueError(f'Строка {lineno}: строка таблицы должна начинаться и заканчиваться |')
    result, cell = [], []
    i = 1
    while i < len(line) - 1:
        c = line[i]
        if c == '\\':
            i += 1
            if i >= len(line)-1 or line[i] not in ('|', '\\'):
                raise QueueError(f'Строка {lineno}: допустимы только экранирования \\| и \\\\')
            cell.append(line[i])
        elif c == '|':
            result.append(''.join(cell).strip()); cell = []
        else:
            cell.append(c)
        i += 1
    result.append(''.join(cell).strip())
    for value in result:
        if len(value) > 4000 or any(ord(x) < 32 or ord(x) == 127 for x in value) or any(x in value for x in ('<', '>', '`')):
            raise QueueError(f'Строка {lineno}: управляющие символы, HTML и inline markup запрещены')
    return result


def _row(values):
    return '| ' + ' | '.join(_escape(v) for v in values) + ' |'


def render(data):
    out = ['# Очередь страниц', '', BEGIN]
    for name, columns in TABLES.items():
        out += [f'## {name}', _row(columns), _row(['---'] * len(columns))]
        for row in data[name]:
            out.append(_row([row[c] for c in columns]))
        out.append('')
    out += [END, '', '## Заметки агента', '', '']
    return '\n'.join(out)


def template(source):
    snapshot = take_snapshot(Path(source), 'source')
    vals = ('1', snapshot['digest'], snapshot['policy_id'], 'unconfirmed', '', 'standard-v1', 'not_applicable', '')
    data = {x: [] for x in TABLES}
    data['meta'] = [{'key': key, 'value': val} for key, val in zip(META, vals)]
    return render(data)


def _relpath(value):
    if not value or '\\' in value or '%' in value or any(ord(c) < 32 for c in value): return False
    parts = value.split('/')
    reserved = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
    return not PurePosixPath(value).is_absolute() and all(p not in ('', '.', '..') and not p.endswith(('.', ' ')) and not reserved.match(p) and not any(x in p for x in ':*?"<>|') for p in parts)


def parse(text):
    if len(text.encode('utf8')) > MAX_BYTES:
        raise QueueError('Очередь превышает лимит размера')
    lines = text.splitlines()
    if lines.count(BEGIN) != 1 or lines.count(END) != 1:
        raise QueueError('Нужна одна пара точных маркеров QUEUE версии v1')
    start, end = lines.index(BEGIN), lines.index(END)
    if start >= end or any('<!-- QUEUE:' in line for line in lines if line not in (BEGIN, END)):
        raise QueueError('Неизвестный или повторный маркер QUEUE')
    data = {name: [] for name in TABLES}
    pos, total, locations = start + 1, 0, {}
    for name, columns in TABLES.items():
        while pos < end and not lines[pos].strip(): pos += 1
        if pos >= end or lines[pos] != '## ' + name:
            raise QueueError(f'Строка {pos+1}: ожидалась секция ## {name}')
        locations[name] = pos + 1
        pos += 1
        if pos >= end or tuple(_cells(lines[pos], pos+1)) != columns:
            raise QueueError(f'Строка {pos+1}: неверные столбцы {name}')
        pos += 1
        if pos >= end or _cells(lines[pos], pos+1) != ['---'] * len(columns):
            raise QueueError(f'Строка {pos+1}: неверный разделитель {name}')
        pos += 1
        while pos < end and lines[pos].startswith('|'):
            row = _cells(lines[pos], pos+1)
            if len(row) != len(columns): raise QueueError(f'Строка {pos+1}: неверное число полей {name}')
            data[name].append(dict(zip(columns, row))); total += 1
            if total > MAX_ROWS: raise QueueError('Превышен лимит строк очереди')
            pos += 1
    while pos < end and not lines[pos].strip(): pos += 1
    if pos != end: raise QueueError(f'Строка {pos+1}: лишние данные в машинной области')
    try:
        _validate(data)
    except QueueError as exc:
        message = str(exc)
        section = next((name for name in TABLES if message.startswith(name)), 'meta')
        raise QueueError(f'Строка {locations[section]} ({section}): {message}') from exc
    return data


def _route_key(route):
    # Decode a single encoding layer and normalize Unicode, but preserve the
    # distinct query and fragment components; paths remain case-sensitive.
    u = urlsplit(route)
    return tuple(unicodedata.normalize('NFC', unquote(part)) for part in (u.path, u.query, u.fragment))


def _validate(data):
    meta_rows = data['meta']
    keys=tuple(r['key'] for r in meta_rows)
    if keys not in (META, META+('template_policy',)):
        raise QueueError('meta: обязательны фиксированные ключи и необязательный template_policy в заданном порядке')
    meta = {r['key']: r['value'] for r in meta_rows}
    if 'template_policy' in meta and not _relpath(meta['template_policy']):
        raise QueueError('meta.template_policy: нужен безопасный относительный путь внутри .work')
    if meta['schema_version'] != '1' or meta['source_policy'] != 'source-v2' or meta['check_policy'] != 'standard-v1':
        raise QueueError('meta: неизвестная версия или policy')
    if meta['source_snapshot'] and not HEX.fullmatch(meta['source_snapshot']): raise QueueError('meta.source_snapshot: ожидается sha256')
    if meta['discovery_status'] not in ('unconfirmed','confirmed','review_required'): raise QueueError('meta.discovery_status: недопустимый статус')
    if meta['legacy_review'] not in ('not_applicable','unclassified','classified') or (meta['legacy_review']=='classified' and not meta['legacy_review_reason']):
        raise QueueError('meta.legacy_review: некорректное состояние или отсутствует причина классификации')
    ids, outputs, routes = set(), set(), set()
    for p in data['pages']:
        if not ID.fullmatch(p['id']) or p['id'] in ids: raise QueueError('pages.id: неверный или повторный ID')
        ids.add(p['id'])
        if not p['title'] or not p['evidence'] or not local_route(p['reference_route']) or not safe_output(p['output']): raise QueueError(f"pages.{p['id']}: отсутствуют данные или неверный маршрут/выход")
        if p['confirmation'] not in ('candidate','confirmed') or p['required'] not in ('true','false') or p['work_status'] not in ('pending','in_progress','built','blocked'): raise QueueError(f"pages.{p['id']}: неверный статус")
        if p['required'] == 'false' and not p['optional_reason']: raise QueueError(f"pages.{p['id']}: необязательной странице нужна причина")
        norm = unicodedata.normalize('NFC', p['output']).casefold()
        if norm in outputs or any(norm.startswith(x+'/') or x.startswith(norm+'/') for x in outputs): raise QueueError('pages.output: конфликт путей')
        outputs.add(norm)
        route_key = _route_key(p['reference_route'])
        if route_key in routes: raise QueueError('pages.reference_route: повторный маршрут')
        routes.add(route_key)
    for a in data['aliases']:
        if a['page_id'] not in ids or not local_route(a['reference_route']) or _route_key(a['reference_route']) in routes or not a['purpose'] or not a['evidence']: raise QueueError('aliases: неверный page_id, маршрут или обоснование')
        routes.add(_route_key(a['reference_route']))
    states = set()
    for s in data['states']:
        key = (s['page_id'], s['state_id'])
        if s['page_id'] not in ids or not ID.fullmatch(s['state_id']) or s['state_id'] == 'initial' or key in states or s['required'] not in ('true','false'): raise QueueError('states: неверный ID, ссылка или обязательность')
        states.add(key)
        widths = s['viewports'].split(',')
        if not widths or len(set(widths)) != len(widths) or any(not VIEWPORT.fullmatch(v) or any(int(n) > 20000 for n in v.split('x')) for v in widths): raise QueueError('states.viewports: пары widthxheight через запятую')
        if s['scenario'] and not _relpath(s['scenario']): raise QueueError('states.scenario: недопустимый относительный путь')
    resources = set()
    for r in data['resources']:
        if not ID.fullmatch(r['id']) or r['id'] in resources or r['scope'] not in ids | {'global'} or r['required'] not in ('true','false') or r['status'] not in ('unknown','available','missing') or not r['evidence']: raise QueueError('resources: неверный ID, scope, статус или evidence')
        resources.add(r['id']); loc = r['location']
        if loc.startswith(('https://', 'http://')):
            u = urlsplit(loc)
            if not u.hostname or u.username or u.password: raise QueueError('resources.location: неверный внешний URL')
        elif not _relpath(loc): raise QueueError('resources.location: неверный локальный путь')
    issues = set()
    for q in data['issues']:
        if not ID.fullmatch(q['id']) or q['id'] in issues or not q['context'] or q['kind'] not in ('decision_required','limitation','info') or q['status'] not in ('open','resolved'): raise QueueError('issues: неверный ID, статус, тип или контекст')
        if q['status'] == 'resolved' and (not q['resolution'] or not q['reason']): raise QueueError('issues: решению нужны resolution и reason')
        if q['resolution'].startswith('duplicate:') and q['resolution'][10:] not in ids: raise QueueError('issues: неизвестная цель duplicate')
        issues.add(q['id'])
    if meta['discovery_status'] == 'confirmed':
        if meta['legacy_review'] == 'unclassified' or not meta['source_snapshot'] or not meta['confirmation_reason'] or not data['pages'] or any(p['confirmation'] != 'confirmed' for p in data['pages']) or any(q['kind'] == 'decision_required' and q['status'] == 'open' for q in data['issues']):
            raise QueueError('confirmed требует snapshot, основание, подтверждённые страницы и отсутствие открытых решений')


def _safe_read(path, limit=MAX_BYTES):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit: raise QueueError(f'Недопустимый файл: {path}')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        check = os.fstat(fd)
        if (info.st_dev, info.st_ino) != (check.st_dev, check.st_ino) or not stat.S_ISREG(check.st_mode) or check.st_nlink != 1: raise QueueError('Файл изменился при открытии')
        with os.fdopen(fd, 'rb') as f:
            fd = -1
            content = f.read(limit + 1)
            after = os.fstat(f.fileno())
        if len(content) > limit or (check.st_size, check.st_mtime_ns, check.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns): raise QueueError('Файл слишком большой или изменился при чтении')
        return content
    finally:
        if fd != -1: os.close(fd)


def _path(work, path, *, existing=True):
    work = Path(work).absolute(); path = Path(path).absolute()
    if any(p.is_symlink() for p in (work, *work.parents)) or not work.is_dir() or not path.is_relative_to(work) or path == work: raise QueueError('Путь должен быть внутри обычного каталога .work')
    cursor = work
    for part in path.relative_to(work).parts:
        if part in ('', '.', '..'): raise QueueError('Недопустимый путь')
        cursor = cursor / part
        if cursor.is_symlink(): raise QueueError('Symlink в рабочем пути запрещён')
        if cursor.exists():
            info = cursor.lstat()
            if getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0): raise QueueError('Reparse point запрещён')
    if existing and not path.exists(): raise QueueError(f'Файл не найден: {path}')
    return path


def _scenario_hash(work, name):
    if not name: return None
    p = _path(work, Path(work) / name, existing=False)
    if not p.exists(): return None
    return sha(_safe_read(p))


def compile_queue(text, source):
    data = parse(text)
    meta = {r['key']: r['value'] for r in data['meta']}
    work = Path(source).absolute()/'.work'
    semantic = {'schema': 'requirements-v1', 'meta': meta,
                'pages': sorted(({k:v for k,v in p.items() if k != 'work_status'} for p in data['pages']), key=lambda x:x['id']),
                'aliases': sorted(data['aliases'], key=lambda x:(x['page_id'], x['reference_route'])),
                'states': sorted(data['states'], key=lambda x:(x['page_id'], x['state_id'])),
                'resources': sorted(data['resources'], key=lambda x:x['id']),
                'issues': sorted(data['issues'], key=lambda x:x['id'])}
    for state in semantic['states']:
        state['scenario_sha256'] = _scenario_hash(work, state['scenario'])
    if 'template_policy' in meta:
        from .templates import parse_policy
        policy_bytes=_safe_read(_path(work,work/meta['template_policy']))
        parse_policy(policy_bytes,{p['output'] for p in data['pages']})
        semantic['template_policy_sha256']=sha(policy_bytes)
    raw = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')
    requirements = hashlib.sha256(b'htmlfromfigma.requirements.v1\0' + raw).hexdigest()
    snapshot = take_snapshot(Path(source), 'source')
    freshness = 'current' if meta['source_snapshot'] and snapshot['digest'] == meta['source_snapshot'] else 'stale' if meta['source_snapshot'] else 'unknown'
    warnings = []
    if freshness != 'current': warnings.append('Источник не совпадает с привязкой очереди; требуется пересмотр')
    for s in semantic['states']:
        if s['required'] == 'true' and not s['scenario_sha256']: warnings.append(f"Нет сценария обязательного состояния {s['page_id']}/{s['state_id']}")
    for r in semantic['resources']:
        if r['required'] == 'true' and r['status'] != 'available': warnings.append(f"Обязательный ресурс {r['id']} не подтверждён")
    return {'parser_version': 1, 'requirements_hash': requirements, 'semantic': semantic,
            'source_snapshot_current': snapshot['digest'], 'freshness': freshness, 'warnings': warnings,
            'eligible': False}


@contextlib.contextmanager
def _lock(work):
    lock = work / '.queue.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os,'O_NOFOLLOW',0), 0o600)
    try:
        os.close(fd)
        yield
    finally:
        try: lock.unlink(missing_ok=True)
        except OSError as exc:
            raise CommitUncertain(f'Не удалось освободить lock; проверьте состояние очереди: {exc}') from exc


def _sync_dir(path):
    if os.name == 'nt':
        return  # Directory fsync is not available via this interface on Windows.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)


def _write_new(path, content):
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0), 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(content); f.flush(); os.fsync(f.fileno())


def write_template(source, output):
    source = Path(source).absolute(); work = source/'.work'; output = Path(output).absolute()
    if any(p.is_symlink() for p in (source,*source.parents,work)) or not source.is_dir(): raise QueueError('Недопустимая рабочая область')
    if not output.is_relative_to(work) or output == work or any(p in ('', '.', '..') for p in output.relative_to(work).parts):
        raise QueueError('Путь должен быть внутри обычного каталога .work')
    if work.exists():
        output = _path(work, output, existing=False)
        if not output.parent.is_dir() or output.exists(): raise QueueError('Нужен новый файл предложения в существующем каталоге')
    elif output.parent != work:
        raise QueueError('Нужен новый файл предложения в существующем каталоге')
    if output in (work/'PAGE-QUEUE.md',work/'manifest.json',work/MARKER,work/'.queue-md-head.json'):
        raise QueueError('Шаблон не может занимать канонический или служебный путь')
    content = template(source).encode('utf8')
    try:
        work.mkdir(exist_ok=True); _sync_dir(source)
        output = _path(work, output, existing=False)
        _write_new(output, content); _sync_dir(output.parent)
    except Exception as exc:
        raise CommitUncertain(f'Шаблон или рабочий каталог могли быть созданы частично: {output}; проверьте перед повтором: {exc}') from exc
    return {'operation':'applied', 'proposal': str(output), 'sha256': sha(content)}


def _guard_incomplete_migrations(work):
    directory = _path(work, work/'migrations', existing=False)
    if not directory.exists(): return
    if not directory.is_dir(): raise QueueError('Каталог миграций повреждён')
    for run in directory.iterdir():
        if run.is_symlink() or not run.is_dir() or not re.fullmatch(r'[0-9a-f]{32}', run.name):
            raise QueueError('Неизвестное содержимое каталога миграций')
        journal_path = _path(work, run/'journal.json', existing=False)
        if not journal_path.exists(): raise QueueError('Не завершён архив миграции; требуется диагностика')
        try: journal = json.loads(_safe_read(journal_path).decode('utf8'))
        except (ValueError, OSError, UnicodeError) as exc: raise QueueError('Повреждён журнал миграции') from exc
        if not isinstance(journal, dict) or journal.get('version') != 1 or journal.get('phase') != 'complete':
            raise QueueError('Миграция не завершена; сначала inspect/recover')


def _write_head(work, content, requirements_hash):
    record = {'version':1, 'queue_sha256':sha(content), 'requirements_hash':requirements_hash}
    fd,tmp = tempfile.mkstemp(prefix='.queue-head-',dir=work)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write((json.dumps(record,sort_keys=True)+'\n').encode('utf8')); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,work/'.queue-md-head.json'); tmp=None
        _sync_dir(work)
    finally:
        if tmp and os.path.exists(tmp): os.unlink(tmp)


def _history_entries(work):
    """Reject incomplete or inconsistent history before relying on or extending it."""
    history = _path(work, work/'queue-history', existing=False)
    if not history.exists(): return
    if not history.is_dir(): raise QueueError('Каталог истории повреждён')
    for path in history.iterdir():
        try:
            entry=json.loads(_safe_read(_path(work,path), MAX_BYTES*8+10000).decode('utf8'))
            if (not isinstance(entry,dict) or not {'version','reason','before','before_sha256','after','after_sha256','requirements_hash','diff'} <= set(entry) or
                    type(entry.get('version')) is not int or entry['version'] != 1 or
                    not isinstance(entry.get('reason'),str) or not entry['reason'].strip() or
                    not isinstance(entry.get('diff'),str) or not isinstance(entry.get('after'),str) or
                    not isinstance(entry.get('after_sha256'),str) or not HEX.fullmatch(entry['after_sha256']) or
                    not isinstance(entry.get('requirements_hash'),str) or not HEX.fullmatch(entry['requirements_hash'])):
                raise QueueError('Повреждена история очереди')
            before=entry.get('before'); before_hash=entry.get('before_sha256')
            if ((before is not None and not isinstance(before,str)) or
                    (before is None and before_hash is not None) or
                    (before is not None and (not isinstance(before_hash,str) or sha(before.encode('utf8'))!=before_hash)) or
                    sha(entry['after'].encode('utf8'))!=entry['after_sha256']):
                raise QueueError('Повреждена история очереди')
        except (ValueError, OSError, UnicodeError) as exc:
            raise QueueError(f'Повреждена история очереди: {path}; требуется ручной разбор') from exc
        yield path,entry


def _recorded_requirements(work, queue_bytes):
    """Check HEAD plus an immutable history/journal entry for this revision."""
    target = sha(queue_bytes)
    head = json.loads(_safe_read(_path(work,work/'.queue-md-head.json')).decode('utf8'))
    if not isinstance(head, dict) or head.get('version') != 1 or head.get('queue_sha256') != target or not HEX.fullmatch(head.get('requirements_hash','')):
        raise QueueError('HEAD не соответствует очереди; требуется диагностика прерванной операции')
    wanted = head['requirements_hash']; found = False
    for _,entry in _history_entries(work):
        if entry['after_sha256'] == target and entry['requirements_hash'] == wanted:
            found = True
    migrations = _path(work, work/'migrations', existing=False)
    if migrations.exists():
        _guard_incomplete_migrations(work)
        for directory in migrations.iterdir():
            journal = json.loads(_safe_read(_path(work,directory/'journal.json')).decode('utf8'))
            if journal.get('proposal_sha256') == target and journal.get('requirements_hash') == wanted:
                found = True
    if not found:
        raise QueueError('Нет зафиксированной привязки требований; требуется пересмотр очереди')
    return wanted


def validate_file(source, path):
    work = Path(source).absolute()/'.work'; path = _path(work, path)
    if path == work/'PAGE-QUEUE.md' and (work/MARKER).exists(): _guard_incomplete_migrations(work)
    content = _safe_read(path)
    result = compile_queue(content.decode('utf8'), source)
    if path == work/'PAGE-QUEUE.md' and result['semantic']['meta']['discovery_status'] == 'confirmed':
        try: result['confirmation_current'] = _recorded_requirements(work, content) == result['requirements_hash'] and result['freshness'] == 'current'
        except QueueError: result['confirmation_current'] = False
        if not result['confirmation_current']:
            result['warnings'].append('Подтверждение не соответствует зафиксированным требованиям; нужен пересмотр')
    return {'file': str(path), 'sha256': sha(content), **result}


def commit(source, proposal, expected, reason):
    source = Path(source).absolute(); work = source/'.work'
    if source.is_symlink() or not source.is_dir(): raise QueueError('Недопустимый source')
    proposal = _path(work, proposal); canon = _path(work, work/'PAGE-QUEUE.md', existing=False)
    marker = _path(work, work/MARKER, existing=False)
    if proposal == canon: raise QueueError('Предложение не может совпадать с канонической очередью')
    candidate = _safe_read(proposal); compiled = compile_queue(candidate.decode('utf8'), source)
    if compiled['semantic']['meta']['discovery_status'] == 'confirmed' and compiled['freshness'] != 'current': raise QueueError('Подтверждённая очередь должна соответствовать текущему source snapshot')
    if not reason or not reason.strip(): raise QueueError('Для фиксации нужна причина')
    started = False
    with _lock(work):
        if _safe_read(proposal) != candidate: raise QueueError('Предложение изменилось параллельно')
        rechecked = compile_queue(candidate.decode('utf8'), source)
        if rechecked['source_snapshot_current'] != compiled['source_snapshot_current'] or rechecked['requirements_hash'] != compiled['requirements_hash']:
            raise QueueError('Источник или сценарий изменился до фиксации')
        legacy = work/'manifest.json'
        if not marker.exists() and (legacy.exists() or legacy.is_symlink()): raise QueueError('Обнаружена v1 очередь: сначала безопасная миграция; commit не заменяет её')
        if marker.exists(): _guard_incomplete_migrations(work)
        # Even the first commit must not proceed over an incomplete history.
        for _ in _history_entries(work): pass
        if marker.exists() and _safe_read(marker) != b'queue-md-v1\n': raise QueueError('Повреждён marker; требуется ручная диагностика')
        if marker.exists() and not canon.exists(): raise QueueError('Незавершённая операция: отсутствует каноническая очередь; требуется восстановление')
        before = _safe_read(canon) if canon.exists() else None
        if before is not None and not marker.exists(): raise QueueError('Существующая очередь без marker: не перезаписывать')
        if expected == 'absent':
            if before is not None: raise QueueError('Конфликт: очередь уже существует')
        elif not HEX.fullmatch(expected or '') or before is None or sha(before) != expected:
            raise QueueError('Конфликт sha256 очереди: перечитайте и объедините изменения')
        if before is not None:
            old_binding = _recorded_requirements(work, before)
            previous = parse(before.decode('utf8'))
            old_meta = {x['key']:x['value'] for x in previous['meta']}
            if old_meta['legacy_review'] != 'not_applicable' and compiled['semantic']['meta']['legacy_review'] == 'not_applicable':
                raise QueueError('Нельзя отменить факт миграции: классифицируйте исторические заметки')
            if old_meta['discovery_status'] == 'confirmed' and compiled['semantic']['meta']['discovery_status'] == 'confirmed':
                if old_binding != compiled['requirements_hash']:
                    raise QueueError('Требования или сценарии изменились: сначала зафиксируйте review_required и повторно подтвердите исследование')
        diff = ''.join(difflib.unified_diff((before or b'').decode('utf8').splitlines(keepends=True), candidate.decode('utf8').splitlines(keepends=True), fromfile='previous', tofile='proposal'))
        # History is itself a mutation: a partial record must be reported and
        # block further commits rather than silently poisoning the history.
        history = _path(work, work/'queue-history', existing=False)
        history_file=history/(uuid.uuid4().hex+'.json')
        entry = {'version':1, 'reason':reason.strip(), 'before_sha256':sha(before) if before is not None else None,
                 'after_sha256':sha(candidate), 'requirements_hash':compiled['requirements_hash'], 'before':before.decode('utf8') if before is not None else None,
                 'after':candidate.decode('utf8'), 'diff':diff}
        encoded=(json.dumps(entry, ensure_ascii=False, indent=2)+'\n').encode('utf8')
        temp = None
        try:
            started=True
            history.mkdir(exist_ok=True)
            if not history.is_dir(): raise QueueError('Недопустимый каталог истории')
            _write_new(history_file, encoded)
            _sync_dir(history); _sync_dir(work)
            fd, temp = tempfile.mkstemp(prefix='.queue-md-', dir=work)
            with os.fdopen(fd, 'wb') as f: f.write(candidate); f.flush(); os.fsync(f.fileno())
            if not marker.exists():
                started = True
                _write_new(marker, b'queue-md-v1\n')
                _sync_dir(work)
            started = True
            os.replace(temp, canon); temp = None
            _sync_dir(work)
            if _safe_read(canon) != candidate: raise OSError('Очередь изменена после установки')
            _write_head(work, candidate, compiled['requirements_hash'])
        except Exception as exc:
            if started: raise CommitUncertain(f'История или исход фиксации могли измениться; проверьте marker, очередь и запись {history_file}: {exc}') from exc
            raise
        finally:
            if temp and os.path.exists(temp):
                try: os.unlink(temp)
                except OSError as exc: raise CommitUncertain(f'Не удалось удалить временный файл {temp}; проверьте историю и очередь: {exc}') from exc
    return {'operation':'applied', 'sha256':sha(candidate), 'requirements_hash':compiled['requirements_hash'], 'diff':diff, 'warnings':compiled['warnings']}


def inspect_legacy(source):
    """Read both legacy files without making decisions or modifying them."""
    from .queue import validate, render as render_v1
    source = Path(source).absolute(); work = source/'.work'
    marker = _path(work, work/MARKER, existing=False)
    if marker.exists(): raise QueueError('Найден marker новой очереди; legacy inspect не является актуальной очередью')
    manifest_path = _path(work, work/'manifest.json')
    markdown_path = _path(work, work/'PAGE-QUEUE.md')
    manifest_raw, markdown_raw = _safe_read(manifest_path), _safe_read(markdown_path)
    data = validate(json.loads(manifest_raw.decode('utf8')))
    expected = render_v1(data)
    actual = markdown_raw.decode('utf8')
    diff = ''.join(difflib.unified_diff(expected.splitlines(keepends=True), actual.splitlines(keepends=True), fromfile='expected-v1-render', tofile='actual-markdown'))
    known = {'schema_version','source','discovery','pages','unresolved_links'}
    page_known = {'id','title','reference_route','reference_aliases','output','confirmation','work_status','states','checks','check_evidence','evidence','issues'}
    state_known = {'id','required','scenario'}
    unknown = {'top_level': sorted(set(data)-known),
               'source': sorted(set(data['source'])-{'root','fingerprint','fingerprint_version'}),
               'discovery': sorted(set(data['discovery'])-{'status','confirmation_reason','unresolved','hints'}),
               'unresolved_links': {str(i): sorted(set(link)-{'reference_route','reason','resolution','resolution_reason'}) for i,link in enumerate(data['unresolved_links']) if set(link)-{'reference_route','reason','resolution','resolution_reason'}},
               'pages': {p['id']: sorted(set(p)-page_known) for p in data['pages'] if set(p)-page_known},
               'states': {p['id']+'/'+s['id']: sorted(set(s)-state_known) for p in data['pages'] for s in p.get('states',[]) if set(s)-state_known}}
    return {'manifest_sha256':sha(manifest_raw), 'markdown_sha256':sha(markdown_raw),
            'markdown_matches_render':not bool(diff), 'markdown_diff':diff,
            'pages':data['pages'], 'unresolved_links':data['unresolved_links'],
            'discovery':data['discovery'], 'unknown_fields':unknown,
            'counts':{'pages':len(data['pages']), 'aliases':sum(len(p.get('reference_aliases',[])) for p in data['pages']),
                      'states':sum(len(p.get('states',[])) for p in data['pages']),
                      'unresolved_links':len(data['unresolved_links']), 'notes':len(data['discovery'].get('unresolved',[]))},
            'migration_ready':False}


def recover_commit(source, history_file, expected, offline_ack):
    """Finish one explicitly selected interrupted commit, without overwriting drift."""
    if not offline_ack: raise QueueError('Подтвердите остановку несовместимых писателей')
    source=Path(source).absolute(); work=source/'.work'
    history_file=_path(work,history_file)
    if history_file.parent!=work/'queue-history': raise QueueError('Нужна запись из queue-history')
    record=json.loads(_safe_read(history_file,MAX_BYTES*8+10000).decode('utf8'))
    if not isinstance(record,dict) or record.get('version')!=1 or not isinstance(record.get('after'),str): raise QueueError('История повреждена')
    before = record.get('before')
    if before is not None and not isinstance(before,str): raise QueueError('История повреждена')
    before = before.encode('utf8') if before is not None else None
    candidate=record['after'].encode('utf8')
    if (sha(before) if before is not None else None)!=record.get('before_sha256') or sha(candidate)!=record.get('after_sha256'):
        raise QueueError('Хеши истории не совпадают')
    compiled=compile_queue(candidate.decode('utf8'),source)
    if compiled['requirements_hash']!=record.get('requirements_hash') or (compiled['semantic']['meta']['discovery_status']=='confirmed' and compiled['freshness']!='current'):
        raise QueueError('Требования или источник изменились после прерывания')
    with _lock(work):
        selected=None
        for path,entry in _history_entries(work):
            if path==history_file: selected=entry
        if selected!=record: raise QueueError('История изменилась до восстановления')
        marker=_path(work,work/MARKER,existing=False); canon=_path(work,work/'PAGE-QUEUE.md',existing=False)
        if marker.exists():
            if _safe_read(marker)!=b'queue-md-v1\n': raise QueueError('Повреждён marker')
            _guard_incomplete_migrations(work)
        elif (work/'manifest.json').exists(): raise QueueError('Обнаружена legacy очередь; recovery commit невозможен')
        current=_safe_read(canon) if canon.exists() else None
        current_hash=sha(current) if current is not None else 'absent'
        if current_hash != expected: raise QueueError('Конфликт ожидаемого состояния очереди')
        if current not in (before,candidate): raise QueueError('Канон не совпадает с известной версией истории')
        if current == candidate and marker.exists():
            try:
                if _recorded_requirements(work,candidate)==compiled['requirements_hash']:
                    return {'operation':'not_applied','status':'already_complete','sha256':sha(candidate)}
            except (QueueError,OSError,ValueError): pass
        started=False; temp=None
        try:
            if not marker.exists():
                started=True; _write_new(marker,b'queue-md-v1\n'); _sync_dir(work)
            if current != candidate:
                fd,temp=tempfile.mkstemp(prefix='.queue-recover-',dir=work)
                with os.fdopen(fd,'wb') as f: f.write(candidate); f.flush(); os.fsync(f.fileno())
                started=True; os.replace(temp,canon); temp=None; _sync_dir(work)
            started=True; _write_head(work,candidate,compiled['requirements_hash'])
            return {'operation':'applied','status':'recovered','sha256':sha(candidate)}
        except Exception as exc:
            if started: raise CommitUncertain(f'Восстановление прервано; проверьте очередь и историю: {exc}') from exc
            raise
        finally:
            if temp and os.path.exists(temp): os.unlink(temp)
