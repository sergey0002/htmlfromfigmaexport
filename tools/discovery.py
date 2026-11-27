"""Conservative, non-executing JSX/TSX route discovery.

Every result is a candidate, never evidence that the export has no other pages.
Tree-sitter parses input; it does not evaluate imports, plugins or project code.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote, urljoin
from .core import files
from .queue import local_route, safe_output


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _string(node, src):
    if node is None or node.type != 'string': return None
    text = src[node.start_byte:node.end_byte].decode('utf8', errors='replace')
    if len(text) < 2 or '\\' in text: return None
    return text[1:-1]


def _slug(route):
    text = route.split('#',1)[-1].strip('/') if '#' in route else urlsplit(route).path.strip('/')
    text = re.sub(r'\.html?$', '', text)
    stem = re.sub(r'[^a-z0-9]+','-',text.lower()).strip('-')[:48]
    return stem or ('home' if route in ('/', '/#home') else 'page-'+hashlib.sha256(route.encode()).hexdigest()[:10])


def _output(route):
    u = urlsplit(route)
    path = unquote(u.fragment if u.fragment and u.path in ('','/') else u.path).strip('/')
    if not path or path == 'home': return 'index.html'
    if ':' in path or '*' in path or '?' in path or '#' in path: return None
    out = path if path.endswith('.html') else path.rstrip('/') + '.html'
    return out if safe_output(out) else None


def _candidate(route, evidence, title=None):
    output = _output(route)
    if not local_route(route) or not output: return None
    return {'id':_slug(route), 'title':title or (_slug(route).replace('-',' ').title()),
            'reference_route':route,'reference_aliases':[],'output':output,'evidence':[evidence],
            'confirmation':'candidate','work_status':'pending','states':[],
            'checks':{'static':'not_run','browser':'not_run','manual':'not_run'},'issues':[]}


class _Links(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href')
            if href: self.links.append((href,self.getpos()[0]))


def scan(source: Path):
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts
        import tree_sitter_javascript as js
    except ImportError:
        return [], [], ['AST-анализ недоступен: установите tree-sitter из tools/requirements.txt.'], []
    project=source.resolve(); found={}; unresolved=[]; notes=[]; hints=[]
    def add(route,evidence,title=None):
        c=_candidate(route,evidence,title)
        if c:
            if route in found: found[route]['evidence'].append(evidence)
            else: found[route]=c
        else: unresolved.append({'reference_route':route,'reason':'Параметризованный или небезопасный маршрут: '+evidence})
    add('/', 'Точка входа проекта; проверить, что существует главная страница', 'Главная')
    parsed=[]
    for path in files(project):
        if path.suffix.lower() not in ('.js','.jsx','.ts','.tsx','.html'): continue
        if path.stat().st_size > 5_000_000:
            notes.append(f'Слишком большой файл для AST: {path.relative_to(project)}'); continue
        try: src=path.read_bytes(); src.decode('utf8')
        except (OSError,UnicodeError): notes.append(f'Файл не прочитан как UTF-8: {path.relative_to(project)}'); continue
        rel=path.relative_to(project).as_posix()
        if path.suffix.lower()=='.html':
            if rel != 'index.html': add('/'+rel, f'{rel}: самостоятельный HTML-файл')
            doc=_Links(); doc.feed(src.decode('utf8'))
            for href,line in doc.links:
                if href.startswith('/') and not href.startswith('//'): add(href,f'{rel}:{line}: HTML href')
                elif href.endswith('.html') and not urlsplit(href).scheme: add(urljoin('/'+rel,href),f'{rel}:{line}: HTML href')
            continue
        try:
            lang=Language(ts.language_tsx() if path.suffix.lower() in ('.tsx','.jsx') else ts.language_typescript() if path.suffix.lower()=='.ts' else js.language())
            root=Parser(lang).parse(src).root_node
        except Exception as e:
            notes.append(f'Ошибка AST {rel}: {e}'); continue
        if root.has_error: notes.append(f'AST содержит ошибки в {rel}; проверить вручную')
        nodes=list(_walk(root)); parsed.append((src,rel,nodes))
    # Hash routing mode is inferred per project and is never a guarantee.
    is_hash=any(b'location.hash' in src or b'HashRouter' in src for src,_,_ in parsed)
    branches=set()
    for src,rel,nodes in parsed:
        for n in nodes:
            if n.type=='binary_expression':
                left=n.child_by_field_name('left'); right=n.child_by_field_name('right'); lit=_string(right,src)
                left_text=src[left.start_byte:left.end_byte].decode('utf8') if left else ''
                raw=src[n.start_byte:n.end_byte].decode('utf8')
                if is_hash and lit and left_text in ('page','route','pathname') and re.search(r'===?',raw): branches.add(lit)
    for src,rel,nodes in parsed:
        arrays={}
        for n in nodes:
            if n.type!='variable_declarator': continue
            name=n.child_by_field_name('name'); val=n.child_by_field_name('value')
            if not name or not val or val.type!='array': continue
            name_text=src[name.start_byte:name.end_byte].decode('utf8'); items=[]
            for obj in val.named_children:
                if obj.type!='object': continue
                fields={}
                for pair in obj.named_children:
                    if pair.type!='pair': continue
                    key=pair.child_by_field_name('key'); value=pair.child_by_field_name('value'); lit=_string(value,src)
                    if key and lit: fields[src[key.start_byte:key.end_byte].decode('utf8')]=lit
                if fields: items.append(fields)
            arrays[name_text]=items
        for n in nodes:
            line=n.start_point.row+1; where=f'{rel}:{line}'
            if n.type=='pair':
                key=n.child_by_field_name('key'); val=n.child_by_field_name('value')
                name=src[key.start_byte:key.end_byte].decode('utf8') if key else ''
                lit=_string(val,src)
                if name=='path' and lit and lit.startswith('/'):
                    if ':' in lit or '*' in lit: unresolved.append({'reference_route':lit,'reason':where+': параметры конфигурации маршрута'})
                    else: add(lit,where+': объект path (требует проверки)')
                continue
            if n.type=='jsx_attribute':
                children=n.named_children
                if len(children)<2: continue
                key=src[children[0].start_byte:children[0].end_byte].decode('utf8')
                lit=_string(children[1],src)
                if not lit or key not in ('href','to','path'): continue
                if key=='path' and (':' in lit or '*' in lit): unresolved.append({'reference_route':lit,'reason':where+': параметры маршрута требуют списка значений'}); continue
                if key=='path' and not lit.startswith('/'):
                    unresolved.append({'reference_route':lit,'reason':where+': относительный вложенный маршрут требует анализа родителя'}); continue
                if lit.startswith('#'):
                    if is_hash and len(lit)>1: add('/'+lit,where+': JSX '+key)
                elif lit.startswith('/') and not lit.startswith('//'): add(lit,where+': JSX '+key)
                continue
            if n.type!='call_expression': continue
            fn=n.child_by_field_name('function'); args=n.child_by_field_name('arguments')
            if not fn or not args or not args.named_children: continue
            func=src[fn.start_byte:fn.end_byte].decode('utf8')
            if func not in ('go','navigate','router.push','router.replace','history.push'): continue
            arg=args.named_children[0]; literal=_string(arg,src)
            if literal:
                r=('/#'+literal if is_hash and not literal.startswith('/') else literal)
                if literal in ('home','/'): r='/'
                if not r.startswith('/'): unresolved.append({'reference_route':literal,'reason':where+': относительная навигация требует анализа'}); continue
                if is_hash and '/' in literal and not literal.startswith('/'):
                    unresolved.append({'reference_route':r,'reason':where+': вложенный маршрут требует проверки обработчика и содержимого'}); continue
                add(r,where+': '+func)
            elif arg.type=='template_string':
                raw=src[arg.start_byte:arg.end_byte].decode('utf8')
                match=re.fullmatch(r'`([^`$]+)\$\{([a-zA-Z_$][\w$]*)\.([a-zA-Z_$][\w$]*)\}`',raw)
                if not match: unresolved.append({'reference_route':raw,'reason':where+': вычисляемый маршрут'}); continue
                prefix,variable,prop=match.groups(); parent=n.parent; array_name=None
                while parent:
                    if parent.type=='call_expression':
                        function=parent.child_by_field_name('function')
                        text=src[function.start_byte:function.end_byte].decode('utf8') if function else ''
                        args2=parent.child_by_field_name('arguments')
                        body=src[args2.start_byte:args2.end_byte].decode('utf8') if args2 else ''
                        if text.endswith('.map') and re.match(r'\(\s*(?:\(\s*)?'+re.escape(variable)+r'\b',body): array_name=text[:-4].split('.')[-1]; break
                    parent=parent.parent
                items=arrays.get(array_name,[])
                if not items or any(prop not in x for x in items): unresolved.append({'reference_route':raw,'reason':where+': не найден конечный набор параметров'}); continue
                for item in items:
                    value=prefix+item[prop]; r='/#'+value if is_hash else '/'+value.lstrip('/')
                    add(r,where+': шаблон и конечный массив '+array_name,item.get('title'))
            else:
                hints.append({'file':rel,'line':line,'expression':src[arg.start_byte:arg.end_byte].decode('utf8')[:200]})
    for branch in sorted(branches):
        if branch=='home': continue
        add('/#'+branch, 'Условие выбора страницы по hash: '+branch)
    # An index alias and duplicate output paths are not separate pages.
    outputs={}; unique=[]
    for route,p in found.items():
        key=p['output'].casefold()
        if key in outputs:
            unresolved.append({'reference_route':route,'reason':'Конфликт выходного пути с '+outputs[key]['reference_route']+'; проверить алиас или отдельную страницу'})
            continue
        ids={x['id'] for x in unique}
        if p['id'] in ids: p['id']=p['id'][:50]+'-'+hashlib.sha256(route.encode()).hexdigest()[:8]
        outputs[key]=p; unique.append(p)
    notes.append('AST обнаруживает только поддерживаемые конструкции; агент обязан проверить маршруты, состояния, алиасы и неподтверждённые ссылки.')
    return unique, unresolved, notes, hints
