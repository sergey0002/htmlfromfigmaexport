"""Non-executing source inventory and static checks for generated sites.

The HTMLParser-based checks adapt the ideas of .doc/scripts/check_vanilla.py,
without its old site's paths and SEO policy. They are not an HTML5 validator.
"""
from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

IGNORED = {"node_modules", ".git", "dist", "build", ".vite", "__pycache__"}
LFS = b"version https://git-lfs.github.com/spec/v1\n"


def files(root: Path):
    for p in sorted(root.rglob('*')):
        if any(part in IGNORED for part in p.relative_to(root).parts) or p.is_symlink():
            continue
        if p.is_file():
            yield p


def fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    for p in files(root):
        name = p.relative_to(root).as_posix()
        h.update(name.encode('utf8') + b'\0')
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        h.update(b'\0')
    return h.hexdigest()


def analyze(root: Path) -> dict:
    root = root.resolve()
    issues, warnings = [], []
    if not root.is_dir():
        return {'status': 'BLOCKED', 'issues': [f'Каталог не найден: {root}']}
    manifests = [p for p in files(root) if p.name == 'package.json']
    if len(manifests) != 1:
        return {'status': 'BLOCKED', 'issues': [f'Найдено package.json: {len(manifests)}; нужен один однозначный корень']}
    project = manifests[0].parent
    try:
        package = json.loads(manifests[0].read_text(encoding='utf8'))
    except (OSError, ValueError) as exc:
        return {'status': 'BLOCKED', 'issues': [f'Некорректный package.json: {exc}']}
    locks = [name for name in ('pnpm-lock.yaml', 'package-lock.json', 'yarn.lock', 'bun.lock', 'bun.lockb') if (project / name).is_file()]
    if len(locks) != 1:
        issues.append(f'Lock-файлов: {len(locks)}; определить пакетный менеджер вручную')
    lfs, zones, symlinks = [], [], []
    for p in project.rglob('*'):
        if any(part in IGNORED for part in p.relative_to(project).parts):
            continue
        if p.is_symlink():
            symlinks.append(p.relative_to(project).as_posix())
        elif p.is_file():
            rel = p.relative_to(project).as_posix()
            if 'Zone.Identifier' in p.name:
                zones.append(rel)
            with p.open('rb') as f:
                if f.read(len(LFS)) == LFS:
                    lfs.append(rel)
    if lfs:
        warnings.append(f'Git LFS: {len(lfs)} указателей вместо файлов: {", ".join(lfs)}')
    if symlinks:
        issues.append(f'Symlink требуют ручной проверки: {len(symlinks)}')
    if not (project / 'index.html').is_file():
        issues.append('Нет index.html; точку входа необходимо определить вручную')
    # Only literal root-relative src references are statically provable here;
    # computed paths and dynamic imports still require a browser/network audit.
    missing = set()
    for p in files(project):
        if p.suffix.lower() not in ('.jsx', '.tsx', '.js', '.ts'): continue
        try: content = p.read_text(encoding='utf8')
        except (OSError, UnicodeError): continue
        for ref in re.findall(r'\bsrc\s*=\s*[\"\'](/[^\"\']+)[\"\']', content):
            target = (project / 'public' / ref.lstrip('/')).resolve()
            if target.is_relative_to((project / 'public').resolve()) and not target.is_file():
                missing.add(ref)
    if missing: warnings.append('Возможные отсутствующие public-ресурсы: ' + ', '.join(sorted(missing)))
    if not isinstance(package, dict):
        return {'status': 'BLOCKED', 'issues': ['package.json должен быть объектом']}
    deps = {}
    for field in ('dependencies', 'devDependencies'):
        part = package.get(field, {})
        if isinstance(part, dict): deps.update(part)
        else: issues.append(f'Некорректное поле {field} в package.json')
    scripts = package.get('scripts', {})
    if not isinstance(scripts, dict):
        scripts = {}
        issues.append('Некорректные scripts в package.json')
    return {'status': 'BLOCKED' if symlinks else 'INCOMPLETE',
            'root': str(project), 'fingerprint': fingerprint(project), 'locks': locks,
            'engines': package.get('engines', {}), 'dependencies': {k: deps[k] for k in ('react', 'react-dom', 'vite', 'tailwindcss', '@tailwindcss/vite') if k in deps},
            'scripts': scripts, 'lfs_pointers': lfs, 'symlinks': symlinks,
            'zone_identifiers': zones, 'missing_literal_assets': sorted(missing), 'issues': issues, 'warnings': warnings,
            'next': 'Проверить зависимости, конфиги, ресурсы и безопасность до запуска; затем сравнить все необходимые состояния в браузере.'}


class Page(HTMLParser):
    """Generic subset of the original Doc parser; no website-specific assumptions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs, self.ids, self.anchors, self.problems = [], set(), [], []
        self.lang = False
        self.title = False
        self.viewport = False
        self.doctype = False

    def handle_decl(self, decl):
        if decl.lower().strip() == 'doctype html': self.doctype = True

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            if a['id'] in self.ids: self.problems.append(f'повтор id: {a["id"]}')
            self.ids.add(a['id'])
        if tag == 'html': self.lang = bool(a.get('lang'))
        if tag == 'title': self.title = True
        if tag == 'meta' and (a.get('name') or '').lower() == 'viewport': self.viewport = True
        if tag == 'img' and 'alt' not in a: self.problems.append('img без alt')
        for attr in ('src', 'href', 'poster'):
            if a.get(attr): self.refs.append((tag, attr, a[attr]))
        if a.get('data-image-src'):
            self.refs.append((tag, 'data-image-src', a['data-image-src']))
        if a.get('srcset'):
            for item in a['srcset'].split(','):
                if item.strip(): self.refs.append((tag, 'srcset', item.strip().split()[0]))


def resolve_ref(root: Path, origin: Path, value: str):
    u = urlsplit(value.strip())
    if u.scheme or u.netloc or value.startswith('//'): return None, None
    path = unquote(u.path)
    if '\x00' in path or '\\' in path: return None, 'недопустимый путь'
    target = (root / path.lstrip('/') if path.startswith('/') else origin.parent / path).resolve()
    if not target.is_relative_to(root): return None, 'путь вне сайта'
    if not path: target = origin
    if target.is_dir(): target = target / 'index.html'
    return target, unquote(u.fragment)


def check_site(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir(): return {'status': 'BLOCKED', 'issues': [f'Каталог не найден: {root}']}
    pages = [p for p in files(root) if p.suffix.lower() in ('.html', '.htm')]
    if not pages: return {'status': 'BLOCKED', 'issues': ['HTML-страницы не найдены']}
    docs, issues, warnings = {}, [], []
    checked_svg = set()
    for p in pages:
        try:
            parser = Page(); parser.feed(p.read_text(encoding='utf8')); parser.close(); docs[p] = parser
        except (OSError, UnicodeError, ValueError) as e:
            issues.append(f'{p.relative_to(root)}: ошибка чтения: {e}')
            continue
        rel = p.relative_to(root)
        issues += [f'{rel}: {x}' for x in parser.problems]
        for prop, name in ((parser.doctype, 'doctype'), (parser.lang, 'html lang'), (parser.title, 'title'), (parser.viewport, 'viewport')):
            if not prop: issues.append(f'{rel}: отсутствует {name}')
    for p, doc in docs.items():
        for tag, attr, ref in doc.refs:
            try: target, fragment = resolve_ref(root, p, ref)
            except ValueError: issues.append(f'{p.relative_to(root)}: некорректный URL {ref}'); continue
            if target is None:
                if fragment: issues.append(f'{p.relative_to(root)}: {fragment}: {ref}')
                continue
            if not target.is_file(): warnings.append(f'{p.relative_to(root)}: отсутствует файл {ref}'); continue
            with target.open('rb') as f:
                is_pointer = f.read(len(LFS)) == LFS
            if is_pointer:
                warnings.append(f'{p.relative_to(root)}: LFS pointer вместо ресурса: {ref}')
            elif target.suffix.lower() == '.svg' and target not in checked_svg:
                checked_svg.add(target)
                try:
                    ET.parse(target)
                except (ET.ParseError, OSError) as exc:
                    warnings.append(f'{p.relative_to(root)}: повреждённый SVG {ref}: {exc}')
            if fragment and target in docs and fragment not in docs[target].ids:
                issues.append(f'{p.relative_to(root)}: отсутствует якорь {ref}')
            if ref.startswith('/') and not ref.startswith('//'):
                warnings.append(f'{p.relative_to(root)}: корневой путь не работает в подпапке: {ref}')
    for p in files(root):
        if p.suffix.lower() != '.css': continue
        try: text = p.read_text(encoding='utf8')
        except (OSError, UnicodeError) as e:
            issues.append(f'{p.relative_to(root)}: ошибка чтения CSS: {e}'); continue
        refs = re.findall(r'url\(\s*[\'"]?([^\'"\)]+)', text, re.I)
        refs += re.findall(r'@import\s+[\'"]([^\'"]+)[\'"]', text, re.I)
        for ref in refs:
            ref = ref.strip()
            try: target, error = resolve_ref(root, p, ref)
            except ValueError: issues.append(f'{p.relative_to(root)}: некорректный URL {ref}'); continue
            if target is None:
                if error: issues.append(f'{p.relative_to(root)}: {error}: {ref}')
                continue
            if not target.is_file(): warnings.append(f'{p.relative_to(root)}: отсутствует CSS ресурс {ref}')
            elif target.read_bytes().startswith(LFS): warnings.append(f'{p.relative_to(root)}: LFS pointer: {ref}')
            if ref.startswith('/'): warnings.append(f'{p.relative_to(root)}: корневой CSS путь: {ref}')
    # Static checks never certify visual, functional, or HTML5 correctness.
    return {'status': 'FAIL' if issues else 'INCOMPLETE', 'pages': [str(p.relative_to(root)) for p in pages],
            'fingerprint': fingerprint(root), 'issues': issues, 'warnings': warnings,
            'next': 'Проверить HTML5, поведение и визуальное соответствие в браузере; статическая проверка не является приёмкой.'}
