"""Persistent page inventory; discovery is intentionally conservative, never a converter."""
from __future__ import annotations
import json
import hashlib
import os
import re
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from html.parser import HTMLParser
from .core import analyze, check_site, files, Page, resolve_ref

ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
STATUSES = {'pending', 'in_progress', 'built', 'blocked'}
CHECKS = {'not_run', 'incomplete', 'fail', 'blocked', 'review', 'checked', 'stale'}


def local_route(route):
    if not isinstance(route, str) or not route.startswith('/') or route.startswith('//') or '\\' in route or any(ord(c)<32 for c in route):
        return False
    u = urlsplit(route)
    if u.scheme or u.netloc: return False
    decoded = unquote(u.path)
    return not any(ord(c)<32 or ord(c)==127 for c in decoded) and '\\' not in decoded and not decoded.startswith('//') and not re.search(r'%[0-9a-fA-F]{2}', decoded) and all(p not in ('.', '..') for p in decoded.split('/'))


def safe_output(value):
    if not isinstance(value, str) or not value or unquote(value) != value or '\\' in value or any(ord(c)<32 for c in value): return False
    p = PurePosixPath(value)
    parts=value.split('/')
    reserved=re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
    return (not p.is_absolute() and all(x not in ('', '.', '..') and not x.endswith(('.', ' ')) and not reserved.match(x) for x in parts)
            and p.suffix.lower() == '.html' and not any(x in value for x in ('?', '#', ':', '*', '"', '<', '>', '|')))


def validate(data):
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('source'), dict): raise ValueError('Некорректная версия или source манифеста')
    if not isinstance(data.get('pages'), list) or not isinstance(data.get('discovery'), dict) or not isinstance(data.get('unresolved_links'), list): raise ValueError('Некорректная структура манифеста')
    if data['discovery'].get('status') not in ('unconfirmed', 'confirmed'): raise ValueError('Некорректный статус инвентаризации')
    ids, outputs, routes = set(), set(), set()
    for p in data['pages']:
        if not isinstance(p, dict) or not isinstance(p.get('id'), str) or not ID.fullmatch(p['id']) or p['id'] in ids: raise ValueError('Некорректный или повторный ID страницы')
        ids.add(p['id'])
        if not isinstance(p.get('title'), str) or not p['title']: raise ValueError('Страница без названия')
        if not safe_output(p.get('output')): raise ValueError('Недопустимый output')
        norm = unicodedata.normalize('NFC', p['output']).casefold()
        if norm in outputs or any(norm.startswith(x+'/') or x.startswith(norm+'/') for x in outputs): raise ValueError('Конфликт выходных путей')
        outputs.add(norm)
        aliases = p.get('reference_aliases', [])
        if not isinstance(aliases, list): raise ValueError('Некорректные алиасы')
        for r in [p.get('reference_route'), *aliases]:
            if not local_route(r) or r in routes: raise ValueError('Недопустимый или повторный маршрут')
            routes.add(r)
        if p.get('confirmation') not in ('candidate', 'confirmed') or p.get('work_status') not in STATUSES: raise ValueError('Некорректный статус страницы')
        if not isinstance(p.get('states', []), list) or not isinstance(p.get('checks', {}), dict) or any(x not in CHECKS for x in p.get('checks', {}).values()): raise ValueError('Некорректные проверки')
        state_ids = set()
        for state in p.get('states', []):
            if not isinstance(state, dict) or not isinstance(state.get('id'), str) or not ID.fullmatch(state['id']) or state['id'] in state_ids or type(state.get('required')) is not bool: raise ValueError('Некорректное состояние')
            state_ids.add(state['id'])
            scenario = state.get('scenario')
            if scenario is not None and (not isinstance(scenario, str) or PurePosixPath(scenario).is_absolute() or any(x in ('', '.', '..') for x in scenario.split('/')) or '\\' in scenario): raise ValueError('Недопустимый путь сценария')
    if any(not isinstance(x, dict) or not isinstance(x.get('reference_route'), str) or (x.get('resolution') is not None and x.get('resolution') not in ('missing','duplicate','not-a-page')) for x in data['unresolved_links']): raise ValueError('Некорректная неясная ссылка')
    if data['discovery']['status'] == 'confirmed' and (not data['pages'] or not data['discovery'].get('confirmation_reason') or any(p['confirmation'] != 'confirmed' for p in data['pages']) or any(not x.get('resolution') or not x.get('resolution_reason') for x in data['unresolved_links'])):
        raise ValueError('Нельзя подтвердить пустую или неподтверждённую очередь')
    return data


def load(path):
    path = Path(path)
    if path.name == 'manifest.json' and path.parent.name == '.work' and ((path.parent / '.queue-md-active').exists() or (path.parent / '.queue-md-active').is_symlink()):
        raise ValueError('Новая очередь активна или переключение не завершено; v1 не является актуальной очередью')
    return validate(json.loads(path.read_text(encoding='utf8')))


def render(data):
    def cell(v): return str(v).replace('|', '\\|').replace('\n', ' ')
    pages = data['pages']; confirmed = sum(p['confirmation']=='confirmed' for p in pages)
    lines = ['# Очередь страниц', '', '> Создано из manifest.json. Не редактируйте статусы здесь.', '',
             f"Инвентаризация: **{data['discovery']['status']}**. Страниц: {len(pages)}, подтверждено: {confirmed}.", '',
             '| № | Страница | Эталон | Файл | Подтверждение | Работа | Проверки |', '|---:|---|---|---|---|---|---|']
    for i,p in enumerate(pages,1):
        checks = ', '.join(f'{k}: {v}' for k,v in p.get('checks',{}).items())
        lines.append(f"| {i} | {cell(p['title'])} | `{cell(p['reference_route'])}` | `{cell(p['output'])}` | {cell(p['confirmation'])} | {cell(p['work_status'])} | {cell(checks)} |")
    lines += ['', '## Неясные ссылки и ограничения', '']
    for x in data.get('unresolved_links',[]):
        lines.append(f"- `{cell(x.get('reference_route',''))}`: {cell(x.get('reason',''))}" + (f" — {cell(x.get('resolution'))}: {cell(x.get('resolution_reason',''))}" if x.get('resolution') else ' — требуется решение'))
    for x in data['discovery'].get('unresolved',[]): lines.append(f'- {cell(x)}')
    if len(lines) and lines[-1] == '': lines.append('- Нет записей.')
    lines += ['', '## Состояния', '']
    for p in pages:
        if p.get('states'): lines.append(f"- **{cell(p['title'])}**: " + ', '.join(cell(s.get('id','')) for s in p['states']))
    return '\n'.join(lines)+'\n'


def save(path, data, create=False, expected_hash=None):
    path = Path(path)
    validate(data)
    if path.name != 'manifest.json' or path.parent.name != '.work': raise ValueError('Манифест должен находиться в <source>/.work/manifest.json')
    if path.is_symlink() or path.parent.is_symlink(): raise ValueError('Symlink рабочей области запрещён')
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent/'.queue.lock'
    fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        if (path.parent / '.queue-md-active').exists() or (path.parent / '.queue-md-active').is_symlink(): raise ValueError('Новая очередь активна или переключение не завершено; запись v1 запрещена')
        if create and path.exists(): raise ValueError('Манифест уже существует; повторный скан не перезаписывает решения')
        if expected_hash is not None and (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash):
            raise ValueError('Очередь изменилась параллельно; повторите операцию')
        if (path.parent/'PAGE-QUEUE.md').is_symlink(): raise ValueError('Symlink файла очереди запрещён')
        for target, text in [(path,json.dumps(data,ensure_ascii=False,indent=2)+'\n'), (path.parent/'PAGE-QUEUE.md',render(data))]:
            if target.is_symlink(): raise ValueError('Symlink файла очереди запрещён')
            tmp_fd, tmp_name = tempfile.mkstemp(prefix='.queue-',dir=path.parent)
            try:
                with os.fdopen(tmp_fd,'w',encoding='utf8') as f: f.write(text); f.flush(); os.fsync(f.fileno())
                os.replace(tmp_name,target)
            finally:
                if os.path.exists(tmp_name): os.unlink(tmp_name)
    finally:
        lock.unlink(missing_ok=True)


def discover(source):
    source = Path(source)
    preflight = analyze(source)
    if preflight['status']=='BLOCKED': return preflight, None
    from .discovery import scan
    pages, unresolved, notes, hints = scan(source)
    data = {'schema_version':1,'source':{'root':'.','fingerprint':preflight['fingerprint'],'fingerprint_version':1},
            'discovery':{'status':'unconfirmed','unresolved':notes, 'hints':hints},
            'pages':pages,'unresolved_links':unresolved}
    return preflight, validate(data)


def merge_discovery(old, new):
    """Keep human decisions and progress. Source changes invalidate all evidence."""
    validate(old); validate(new)
    merged = json.loads(json.dumps(old, ensure_ascii=False))
    changed = old['source'].get('fingerprint') != new['source'].get('fingerprint')
    existing = {p['reference_route']:p for p in merged['pages']}
    used_ids = {p['id'] for p in merged['pages']}
    used_outputs = {unicodedata.normalize('NFC',p['output']).casefold() for p in merged['pages']}
    for fresh in new['pages']:
        current = existing.get(fresh['reference_route'])
        if current:
            current['evidence'] = list(dict.fromkeys(current.get('evidence',[])+fresh.get('evidence',[])))
        elif unicodedata.normalize('NFC',fresh['output']).casefold() not in used_outputs:
            if fresh['id'] in used_ids: fresh['id'] = fresh['id'][:50]+'-'+hashlib.sha256(fresh['reference_route'].encode()).hexdigest()[:8]
            merged['pages'].append(fresh); used_ids.add(fresh['id']); used_outputs.add(unicodedata.normalize('NFC',fresh['output']).casefold())
            merged['discovery']['status']='unconfirmed'
        else:
            new['unresolved_links'].append({'reference_route':fresh['reference_route'], 'reason':'Обнаруженный маршрут конфликтует с существующим output; сопоставить вручную'})
    seen = {(x.get('reference_route'),x.get('reason')) for x in merged['unresolved_links']}
    for item in new['unresolved_links']:
        key=(item.get('reference_route'),item.get('reason'))
        if key not in seen:
            merged['unresolved_links'].append(item); seen.add(key); merged['discovery']['status']='unconfirmed'
    merged['discovery']['unresolved']=list(dict.fromkeys(merged['discovery'].get('unresolved',[])+new['discovery'].get('unresolved',[])))
    merged['discovery']['hints']=new['discovery'].get('hints',[])
    if changed:
        merged['source']=new['source']; merged['discovery']['status']='unconfirmed'; merged['discovery'].pop('confirmation_reason',None)
        for p in merged['pages']:
            p['checks']={k:'not_run' for k in p.get('checks',{})}
            if p.get('work_status')=='built': p['work_status']='in_progress'
            p.setdefault('issues',[]).append('Исходник изменился: результаты проверок устарели')
    return validate(merged)


class Markers(HTMLParser):
    def __init__(self): super().__init__(); self.marks=[]
    def handle_comment(self, text):
        if text.strip() in ('HEADER:START','HEADER:END','FOOTER:START','FOOTER:END'): self.marks.append(text.strip())


class StaticPHPReferences(HTMLParser):
    """Conservative literal-URL check; not a JavaScript or server analysis."""
    def __init__(self): super().__init__(convert_charrefs=True); self.refs=[]
    def handle_starttag(self,tag,attrs):
        for name,value in attrs:
            if value and name in ('href','xlink:href','src','action','formaction','poster','data'):
                self.refs.append(value)
            elif value and name=='srcset':
                self.refs.extend(item.strip().split()[0] for item in value.split(',') if item.strip())
    handle_startendtag=handle_starttag


def _looks_like_php_url(ref):
    # Decode the URL once, matching ordinary URL resolution; catch path-info
    # and semicolon path parameters as well as the usual direct extension.
    path=unquote(urlsplit(ref).path)
    return any(re.search(r'\.(?:php[0-9]?|phtml|phar)$',part.split(';',1)[0],re.I) for part in path.split('/'))


def check_manifest(site, data, template_policy=None, *, snapshot_access=None):
    result = check_site(site, snapshot_access=snapshot_access)
    site = Path(site).resolve()
    if result['status'] == 'BLOCKED': return result
    issues, warnings = result['issues'], result['warnings']
    expected = [p for p in data['pages'] if p['confirmation']=='confirmed']
    if not expected or data['discovery']['status'] != 'confirmed': warnings.append('Инвентаризация не подтверждена; полнота сайта неизвестна')
    missing=[]; present=0
    is_file=snapshot_access.is_file if snapshot_access else lambda p: p.is_file()
    read_text=snapshot_access.text if snapshot_access else lambda p: p.read_text(encoding='utf8')
    for p in expected:
        path=site/p['output']
        if not path.resolve().is_relative_to(site) or any(q.is_symlink() for q in [path,*path.parents] if q != site and q.is_relative_to(site)): issues.append(f"{p['output']}: symlink или путь вне сайта"); continue
        if not is_file(path): missing.append(p['output']); continue
        present += 1
        parser=Markers()
        try:
            text=read_text(path); parser.feed(text)
            if parser.marks != ['HEADER:START','HEADER:END','FOOTER:START','FOOTER:END']: issues.append(f"{p['output']}: некорректные маркеры header/footer")
            if '<?' in text: issues.append(f"{p['output']}: HTML содержит PHP-подобный открывающий тег или processing instruction")
            php_refs=StaticPHPReferences(); php_refs.feed(text); php_refs.close()
            for ref in php_refs.refs:
                if _looks_like_php_url(ref): issues.append(f"{p['output']}: ссылка на PHP в статическом HTML: {ref}")
            doc=Page(); doc.feed(text)
            for tag, attr, ref in doc.refs:
                if tag != 'a' or attr != 'href': continue
                if ref == '#': warnings.append(f"{p['output']}: ссылка-заглушка #"); continue
                target, err = resolve_ref(site,path,ref)
                if target is not None and (target.suffix.lower() in ('.html','.htm') or not target.suffix) and not is_file(target): issues.append(f"{p['output']}: отсутствует HTML-ссылка {ref}")
        except (OSError, UnicodeError, ValueError) as e: issues.append(f"{p['output']}: {e}")
    from .templates import compare_template
    template_issues, template_warnings = compare_template(site, [site/p['output'] for p in expected if is_file(site/p['output']) and (site/p['output']).resolve().is_relative_to(site)], template_policy, snapshot_access=snapshot_access)
    issues.extend(template_issues); warnings.extend(template_warnings)
    result['coverage']={'pages_expected':len(expected),'pages_present':present,'pages_missing':missing}
    result['status']='FAIL' if issues else 'INCOMPLETE'
    return result
