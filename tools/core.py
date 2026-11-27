"""Non-executing source inventory and static checks for generated sites.

The HTMLParser-based checks adapt the ideas of .doc/scripts/check_vanilla.py,
without its old site's paths and SEO policy. They are not an HTML5 validator.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

IGNORED = {"node_modules", ".git", "dist", "build", ".vite", "__pycache__"}
LFS = b"version https://git-lfs.github.com/spec/v1\n"


def _walk(root: Path):
    """Prune large generated trees rather than descending into ignored folders."""
    found = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        allowed = []
        for name in dirs:
            path = base / name
            relative = path.relative_to(root)
            if name in IGNORED or (len(relative.parts) == 1 and name == '.work'):
                continue
            found.append(path)
            # Preserve the legacy refusal while never descending into ambiguous
            # secret or workspace names before the guard has run.
            if not path.is_symlink() and not name.casefold().startswith('.env') and name.casefold() != '.work':
                allowed.append(name)
        dirs[:] = allowed
        for name in names:
            if name not in IGNORED: found.append(base / name)
    return sorted(found)


def files(root: Path):
    for p in _walk(root):
        if not p.is_symlink() and p.is_file():
            yield p


def fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    paths = _walk(root)
    # Do not silently redefine the legacy v1 identity by excluding .env.
    # Refuse it instead; use the explicit v2 source policy for inventory.
    if any(p.name.casefold().startswith('.env') or p.name.casefold() == '.work' for p in paths):
        raise ValueError('Legacy fingerprint не поддерживает .env* и вложенные .work: используйте snapshot source v2; содержимое не читалось')
    for p in paths:
        if p.is_symlink() or not p.is_file():
            continue
        name = p.relative_to(root).as_posix()
        h.update(name.encode('utf8') + b'\0')
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        h.update(b'\0')
    return h.hexdigest()


def analyze(root: Path, *, include_source_text: bool = False) -> dict:
    root = root.resolve()
    issues, warnings = [], []
    if not root.is_dir():
        return {'status': 'BLOCKED', 'issues': [f'Каталог не найден: {root}']}
    if any(p.name.casefold().startswith('.env') or p.name.casefold() == '.work' for p in _walk(root)):
        return {'status': 'BLOCKED', 'issues': ['Legacy analyze/fingerprint не поддерживает .env* и вложенные .work: используйте snapshot source v2; содержимое не читалось']}
    manifests = [p for p in files(root) if p.name == 'package.json']
    if not manifests:
        html = [p.relative_to(root).as_posix() for p in files(root) if p.suffix.lower() in ('.html', '.htm')]
        if not html:
            return {'status': 'BLOCKED', 'issues': ['Нет package.json или статических HTML-файлов; требуется ручной выбор входа']}
        symlinks = [p.relative_to(root).as_posix() for p in _walk(root) if p.is_symlink()]
        if symlinks:
            return {'status': 'BLOCKED', 'issues': ['Symlink требуют ручной проверки'], 'symlinks': symlinks}
        return {'status': 'INCOMPLETE', 'format': 'static-html', 'root': str(root),
                'fingerprint': fingerprint(root), 'html_files': html, 'issues': [],
                'warnings': ['HTML-файлы — факты инвентаря, а не подтверждённый список страниц'],
                'next': 'Исследовать маршруты и состояния; файлы в исключённых каталогах не анализируются.'}
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
    for p in _walk(project):
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
    if missing:
        warnings.append('Возможные отсутствующие public-ресурсы: ' + (', '.join(sorted(missing)) if include_source_text else f'{len(missing)}; значения скрыты'))
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
    if include_source_text: warnings.append('Содержимое scripts, версий и путей может содержать чувствительные данные.')
    recognized = {k: deps[k] for k in ('react', 'react-dom', 'vite', 'tailwindcss', '@tailwindcss/vite') if k in deps}
    return {'status': 'BLOCKED' if symlinks else 'INCOMPLETE',
            'format': 'npm', 'root': str(project), 'fingerprint': fingerprint(project), 'locks': locks,
            'engines': package.get('engines', {}) if include_source_text else None,
            'dependencies': recognized if include_source_text else {k: None for k in recognized},
            'scripts': scripts if include_source_text else None, 'script_count': len(scripts),
            'lfs_pointers': lfs, 'symlinks': symlinks, 'source_text_included': include_source_text,
            'zone_identifiers': zones, 'missing_literal_assets': sorted(missing) if include_source_text else None, 'missing_literal_assets_count': len(missing), 'issues': issues, 'warnings': warnings,
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


def check_site(root: Path, *, snapshot_access=None) -> dict:
    root = root.resolve()
    if not root.is_dir(): return {'status': 'BLOCKED', 'issues': [f'Каталог не найден: {root}']}
    if snapshot_access is not None and snapshot_access.root!=root:
        raise ValueError('Snapshot не соответствует корню сайта')
    candidates=list(snapshot_access.legacy_files()) if snapshot_access else list(files(root))
    read_text=snapshot_access.text if snapshot_access else lambda p: p.read_text(encoding='utf8')
    is_file=snapshot_access.is_file if snapshot_access else lambda p: p.is_file()
    def prefix(path):
        if snapshot_access: return snapshot_access.prefix(path,len(LFS))
        with path.open('rb') as file: return file.read(len(LFS))
    pages = [p for p in candidates if p.suffix.lower() in ('.html', '.htm')]
    if not pages: return {'status': 'BLOCKED', 'issues': ['HTML-страницы не найдены']}
    docs, issues, warnings = {}, [], []
    checked_svg = set()
    for p in pages:
        try:
            parser = Page(); parser.feed(read_text(p)); parser.close(); docs[p] = parser
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
            if not is_file(target): warnings.append(f'{p.relative_to(root)}: отсутствует файл {ref}'); continue
            is_pointer = prefix(target) == LFS
            if is_pointer:
                warnings.append(f'{p.relative_to(root)}: LFS pointer вместо ресурса: {ref}')
            elif target.suffix.lower() == '.svg' and target not in checked_svg:
                checked_svg.add(target)
                try:
                    if snapshot_access: ET.fromstring(snapshot_access.bytes(target))
                    else: ET.parse(target)
                except (ET.ParseError, OSError) as exc:
                    warnings.append(f'{p.relative_to(root)}: повреждённый SVG {ref}: {exc}')
            if fragment and target in docs and fragment not in docs[target].ids:
                issues.append(f'{p.relative_to(root)}: отсутствует якорь {ref}')
            if ref.startswith('/') and not ref.startswith('//'):
                warnings.append(f'{p.relative_to(root)}: корневой путь не работает в подпапке: {ref}')
    for p in candidates:
        if p.suffix.lower() != '.css': continue
        try: text = read_text(p)
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
            if not is_file(target): warnings.append(f'{p.relative_to(root)}: отсутствует CSS ресурс {ref}')
            else:
                # Snapshot mode verifies all bytes but retains only the prefix;
                # legacy mode retains the old unbound prefix-only behaviour.
                is_pointer=prefix(target) == LFS
                if is_pointer: warnings.append(f'{p.relative_to(root)}: LFS pointer: {ref}')
            if ref.startswith('/'): warnings.append(f'{p.relative_to(root)}: корневой CSS путь: {ref}')
    # Static checks never certify visual, functional, or HTML5 correctness.
    return {'status': 'FAIL' if issues else 'INCOMPLETE', 'pages': [str(p.relative_to(root)) for p in pages],
            # Do not silently substitute a v2 digest for the legacy v1 fingerprint.
            'fingerprint': None if snapshot_access else fingerprint(root), 'issues': issues, 'warnings': warnings,
            'next': 'Проверить HTML5, поведение и визуальное соответствие в браузере; статическая проверка не является приёмкой.'}
