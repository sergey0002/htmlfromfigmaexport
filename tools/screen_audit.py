"""Viewport-by-viewport comparison. No site-specific selectors or automatic edits."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from .browser import FREEZE_CSS, loopback_url
from .visual_diff import save_comparison

VIEWPORTS = [(390, 844), (768, 1024), (1440, 900)]
MAX_SCREENS = 100


def load_scenarios(path: Path | None):
    if not path:
        return []
    data = json.loads(path.read_text(encoding='utf8'))
    if not isinstance(data, list) or len(data) > 30:
        raise ValueError('Сценарии должны быть массивом не более 30 состояний')
    names = set()
    for item in data:
        if not isinstance(item, dict) or set(item) - {'name', 'reference', 'candidate', 'viewports'}:
            raise ValueError('Некорректная структура сценария')
        name = item.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', name) or name == 'initial' or name in names:
            raise ValueError('Имя состояния должно быть уникальным ASCII id, не initial')
        names.add(name)
        if 'viewports' in item:
            sizes = item['viewports']
            if not isinstance(sizes, list) or not sizes or any(type(x) is not int or x not in [w for w, _ in VIEWPORTS] for x in sizes) or len(sizes) != len(set(sizes)):
                raise ValueError('viewports: непустой массив ширин из 390, 768, 1440')
        for side in ('reference', 'candidate'):
            actions = item.get(side)
            if not isinstance(actions, list) or len(actions) > 30:
                raise ValueError('Каждая сторона должна содержать массив до 30 действий')
            for action in actions:
                if not isinstance(action, dict) or action.get('type') not in ('click', 'press', 'scroll', 'focus', 'fill', 'check', 'select'):
                    raise ValueError('Недопустимый тип действия')
                kind = action['type']
                if kind in ('click', 'focus', 'fill', 'check', 'select'):
                    selector = action.get('selector')
                    if not isinstance(selector, str) or not 0 < len(selector) <= 500:
                        raise ValueError(f'{kind} требует selector')
                    allowed_keys = {'type', 'selector'} | ({'value'} if kind in ('fill', 'check', 'select') else set())
                    if set(action) != allowed_keys: raise ValueError(f'Некорректные поля {kind}')
                    if kind in ('fill', 'select') and (not isinstance(action['value'], str) or len(action['value']) > 200):
                        raise ValueError(f'{kind} требует строку не длиннее 200 символов')
                    if kind == 'check' and type(action['value']) is not bool:
                        raise ValueError('check требует логическое value')
                elif kind == 'press':
                    if set(action) != {'type', 'key'} or action['key'] not in ('Tab', 'Escape', 'Enter', 'Space'):
                        raise ValueError('press допускает Tab, Escape, Enter или Space')
                elif set(action) != {'type', 'y'} or type(action.get('y')) is not int or not 0 <= action['y'] <= 60000:
                    raise ValueError('scroll требует y от 0 до 60000')
    return data


def inline_font_css(path: Path):
    """Embed only local WOFF/WOFF2 files referenced by CSS, never arbitrary paths."""
    path = path.resolve()
    text = path.read_text(encoding='utf8')
    root = path.parent.parent.resolve()
    embedded = []
    def replace(match):
        ref = match.group(2)
        if ':' in ref or ref.startswith('/') or '?' in ref or '#' in ref:
            raise ValueError('CSS шрифта должен ссылаться только на локальные файлы')
        file = (path.parent / ref).resolve()
        if not file.is_relative_to(root) or file.suffix.lower() not in ('.woff', '.woff2') or not file.is_file():
            raise ValueError(f'Недопустимый файл шрифта: {ref}')
        data = file.read_bytes()
        if len(data) > 3_000_000:
            raise ValueError('Слишком большой файл шрифта')
        embedded.append({'path': str(file), 'sha256': hashlib.sha256(data).hexdigest()})
        kind = 'font/woff2' if file.suffix == '.woff2' else 'font/woff'
        return f'url(data:{kind};base64,{base64.b64encode(data).decode()})'
    result = re.sub(r'url\(\s*([\'"]?)([^\'"\)]+)\1\s*\)', replace, text, flags=re.I)
    if '@import' in result.lower() or not embedded:
        raise ValueError('CSS шрифта должен содержать локальные файлы и не содержать @import')
    return result, embedded


def _actions(page, actions, allowed):
    safe_activation = """e => e && ((e.tagName === 'BUTTON' && !(e.closest('form') && e.type === 'submit')) ||
      (e.tagName === 'A' && (e.getAttribute('href') || '').startsWith('#')) || e.tagName === 'SUMMARY')"""
    for action in actions:
        kind = action['type']
        if kind in ('click', 'focus', 'fill', 'check', 'select'):
            element = page.locator(action['selector'])
            if element.count() != 1:
                raise ValueError(f"Селектор должен находить один элемент: {action['selector']}")
            if kind == 'click':
                if not element.evaluate(safe_activation):
                    raise ValueError('Клик допустим для кнопок без отправки форм, summary и локальных якорей')
                element.click(timeout=5000)
            elif kind == 'focus':
                if not element.evaluate("e => e.matches('button,a[href],summary,input:not([type=password]):not([type=file]),select,textarea')"):
                    raise ValueError('Недопустимый элемент для focus')
                element.focus(timeout=5000)
            elif kind == 'fill':
                if not element.evaluate("e => e.tagName === 'TEXTAREA' || (e.tagName === 'INPUT' && ['text','search','email','tel','url','number'].includes(e.type))"):
                    raise ValueError('fill допускает только обычные текстовые поля без паролей и файлов')
                element.fill(action['value'], timeout=5000)
            elif kind == 'check':
                if not element.evaluate("e => e.tagName === 'INPUT' && ['checkbox','radio'].includes(e.type)"):
                    raise ValueError('check допускает checkbox/radio')
                element.set_checked(action['value'], timeout=5000)
            else:
                if not element.evaluate("e => e.tagName === 'SELECT'"):
                    raise ValueError('select допускает только SELECT')
                element.select_option(action['value'], timeout=5000)
        elif kind == 'press':
            if action['key'] in ('Enter', 'Space') and not page.evaluate(f'() => ({safe_activation})(document.activeElement)'):
                raise ValueError('Enter/Space допустимы только на безопасном элементе управления')
            page.keyboard.press(action['key'])
        else:
            page.evaluate('(y) => window.scrollTo(0, y)', action['y'])
        parts = urlsplit(page.url)
        if (parts.scheme, parts.hostname, parts.port) != allowed:
            raise ValueError('Сценарий покинул исходный origin')
        page.wait_for_timeout(100)


def _measure(page):
    return page.evaluate("""() => ({text: document.body.innerText.trim(),
      width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,
      controls: [...document.querySelectorAll('button, input, select, textarea, [role="button"]')]
        .filter(e => e.getClientRects().length)
        .slice(0,100).map(e => ({tag:e.tagName.toLowerCase(), text:(e.innerText || (e.tagName === 'BUTTON' ? e.value : '') || '').trim().slice(0,100),
          id:e.id, label:e.getAttribute('aria-label'), expanded:e.getAttribute('aria-expanded'),
          disabled:!!e.disabled, checked:('checked' in e) ? !!e.checked : null,
          value_length:('value' in e && e.tagName !== 'BUTTON') ? String(e.value).length : null}))})""")


def audit_urls(reference, candidate, output: Path, scenarios=None, route='/', threshold=0.001, font_css=None, channel_tolerance=12):
    """Capture each viewport-height segment; report coverage even on failure."""
    scenarios = scenarios or []
    result = {'schema_version': 1, 'status': 'INCOMPLETE', 'issues': [], 'warnings': [],
              'viewports': [], 'coverage': {'states_planned': len(VIEWPORTS) + sum(len(s.get('viewports', VIEWPORTS)) for s in scenarios), 'states_checked': 0, 'screens_compared': 0, 'action_screens_compared': 0},
              'behavior': 'scenarios' if scenarios else 'not_checked', 'route': route, 'scenarios': scenarios,
              'pixel_threshold': threshold, 'channel_tolerance': channel_tolerance,
              'next': 'Проверить интерактив, все маршруты и вручную изучить несовпадения; автоматическая сверка не является полной приёмкой.'}
    if not all(loopback_url(url) for url in (reference, candidate)):
        result['status'] = 'BLOCKED'; result['issues'].append('Разрешены только локальные HTTP URL с портом'); return result
    if not route.startswith('/') or route.startswith('//') or urlsplit(route).netloc or urlsplit(route).scheme:
        result['status'] = 'BLOCKED'; result['issues'].append('Маршрут должен быть относительным путём внутри сайта'); return result
    if not 0 <= threshold <= 1 or type(channel_tolerance) is not int or not 0 <= channel_tolerance <= 255:
        result['status'] = 'BLOCKED'; result['issues'].append('Некорректный порог'); return result
    try:
        from playwright.sync_api import sync_playwright
        import PIL
    except ImportError as e:
        result['status'] = 'BLOCKED'; result['issues'].append(f'Установите Playwright, Pillow и Chromium: {e}'); return result
    try:
        font_content, font_files = inline_font_css(font_css) if font_css else (None, [])
        result['reference_font_override'] = {'css': str(font_css), 'files': font_files} if font_content else None
        if font_content:
            result['warnings'].append('Для исходника использована явно заданная локальная замена шрифта; оригинальный CDN не подтверждён.')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
            try:
                for width, height in VIEWPORTS:
                    vp = {'width': width, 'height': height, 'states': []}
                    result['viewports'].append(vp)
                    for state in [{'name':'initial', 'reference':[], 'candidate':[]}, *scenarios]:
                        if state.get('viewports') and width not in state['viewports']: continue
                        contexts, pages, state_warnings, action_screens, action_offsets = [], [], [], [], []
                        entry = {'name': state['name'], 'status': 'INCOMPLETE', 'screens': []}
                        vp['states'].append(entry)
                        try:
                            for name, base in [('reference', reference), ('candidate', candidate)]:
                                url = base.rstrip('/') + route
                                origin = urlsplit(base); allowed = (origin.scheme, origin.hostname, origin.port)
                                context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1, locale='ru-RU', reduced_motion='reduce')
                                contexts.append(context)
                                def make_handler(origin, side):
                                    def handler(r):
                                        u = urlsplit(r.request.url)
                                        if (u.scheme, u.hostname, u.port) == origin and r.request.method in ('GET', 'HEAD'):
                                            r.continue_()
                                        else:
                                            msg = f'{side}: заблокирован запрос {u.scheme}://{u.netloc}{u.path}'
                                            (result['issues'] if r.request.is_navigation_request() or r.request.method not in ('GET','HEAD') else state_warnings).append(msg)
                                            r.abort()
                                    return handler
                                context.route('**/*', make_handler(allowed, name))
                                page = context.new_page()
                                page.on('pageerror', lambda err, name=name: result['issues'].append(f'{name}: JS: {err}'))
                                def response_handler(r, name=name):
                                    if r.status >= 400:
                                        (result['issues'] if r.request.is_navigation_request() else state_warnings).append(f'{name}: HTTP {r.status}: {r.url}')
                                page.on('response', response_handler)
                                page.on('requestfailed', lambda req, name=name: state_warnings.append(f'{name}: запрос не выполнен: {req.url} ({req.failure})') if not req.is_navigation_request() else None)
                                response = page.goto(url, wait_until='load', timeout=30000)
                                if not response or response.status >= 400:
                                    raise ValueError(f'{name}: страница недоступна: {url}')
                                page.add_style_tag(content=FREEZE_CSS)
                                if name == 'reference' and font_content:
                                    page.add_style_tag(content=font_content)
                                page.evaluate('document.fonts.ready')
                                _actions(page, state[name], allowed)
                                if state['name'] != 'initial':
                                    page.wait_for_timeout(100)
                                    action_offsets.append(page.evaluate('window.scrollY'))
                                    action_screens.append(page.screenshot(animations='disabled'))
                                # Lazy resources and sticky headers are brought to a deterministic state.
                                page.evaluate('''async () => {let h=Math.min(document.documentElement.scrollHeight,60000);
                                  for(let y=0;y<h;y+=Math.max(300,innerHeight)){scrollTo(0,y);await new Promise(r=>setTimeout(r,30));}
                                  scrollTo(0,0);await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);}''')
                                page.wait_for_timeout(100)
                                broken = page.locator('img').evaluate_all('(els) => els.filter(i => !i.complete || !i.naturalWidth).map(i => i.currentSrc || i.src)')
                                if broken: state_warnings.append(f'{name}: не загружены изображения: {broken}')
                                pages.append(page)
                            data = [_measure(p) for p in pages]
                            entry['sizes'] = [[d['width'],d['height']] for d in data]
                            entry['controls'] = {side: d['controls'] for side,d in zip(('reference','candidate'),data)}
                            if data[0]['text'] != data[1]['text']:
                                entry.setdefault('mismatches', []).append('Видимый текст отличается')
                            comparable_controls = [[{k:v for k,v in control.items() if k != 'id'} for control in d['controls']] for d in data]
                            if comparable_controls[0] != comparable_controls[1]:
                                entry.setdefault('mismatches', []).append('Доступные элементы управления или их состояние отличаются')
                            if any(d['width'] > width for d in data):
                                entry.setdefault('mismatches', []).append('Горизонтальный overflow')
                            if data[0]['height'] != data[1]['height']:
                                entry.setdefault('mismatches', []).append(f"Высота страницы: {data[0]['height']} vs {data[1]['height']}")
                            count = math.ceil(max(d['height'] for d in data) / height)
                            if count < 1 or count > MAX_SCREENS:
                                raise ValueError(f'Число экранов {count} вне допустимого диапазона 1–{MAX_SCREENS}')
                            folder = output / f'{width}x{height}' / state['name']; folder.mkdir(parents=True, exist_ok=True)
                            if action_screens:
                                action_result = save_comparison(action_screens[0], action_screens[1], folder, 'action', channel_tolerance)
                                for key in ('reference','candidate','diff','overlay','heatmap'):
                                    action_result[key] = str((folder/action_result[key]).relative_to(output))
                                action_result['actual_y'] = action_offsets
                                action_result['status'] = ('REVIEW' if state_warnings else 'FAIL') if action_result['difference_ratio'] > threshold else 'OK'
                                entry['action'] = action_result
                                result['coverage']['action_screens_compared'] += 1
                            for index in range(count):
                                y = index * height
                                for page in pages:
                                    page.evaluate('''async y=>{scrollTo(0,y);await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame)}''', y)
                                    page.wait_for_timeout(80)
                                offsets = [p.evaluate('window.scrollY') for p in pages]
                                screenshots = [p.screenshot(animations='disabled') for p in pages]
                                prefix = f'{index+1:03d}'
                                comparison = save_comparison(screenshots[0], screenshots[1], folder, prefix, channel_tolerance)
                                for key in ('reference','candidate','diff','overlay','heatmap'):
                                    comparison[key] = str((folder/comparison[key]).relative_to(output))
                                comparison.update({'index': index+1, 'requested_y':y, 'actual_y':offsets, 'offsets_match': offsets[0] == offsets[1],
                                    'status':('REVIEW' if state_warnings else 'FAIL') if comparison['difference_ratio'] > threshold else 'OK'})
                                entry['screens'].append(comparison)
                                result['coverage']['screens_compared'] += 1
                            # Long captures complement viewport images; fixed/sticky elements can render
                            # differently, so never substitute this for scrolling screen-by-screen.
                            try:
                                for page in pages:
                                    page.evaluate('async () => { scrollTo(0,0); await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame); }')
                                    page.wait_for_timeout(100)
                                full_sizes = [_measure(p) for p in pages]
                                if max(d['width'] for d in full_sizes) * max(d['height'] for d in full_sizes) > 12_000_000:
                                    raise ValueError('Длинная страница превышает лимит 12 млн пикселей')
                                full = [page.screenshot(full_page=True, animations='disabled') for page in pages]
                                full_result = save_comparison(full[0], full[1], folder, 'full', channel_tolerance)
                                for key in ('reference','candidate','diff','overlay','heatmap'):
                                    full_result[key] = str((folder/full_result[key]).relative_to(output))
                                entry['fullpage'] = full_result
                            except Exception as exc:
                                entry['fullpage'] = None
                                state_warnings.append(f'Не удалось снять/сравнить длинную страницу: {exc}; поэкранные снимки сохранены')
                            entry['warnings'] = list(dict.fromkeys(state_warnings))
                            if entry.get('mismatches') or entry.get('action', {}).get('status') == 'FAIL' or any(x['status']=='FAIL' for x in entry['screens']): entry['status'] = 'FAIL'
                            elif entry.get('action', {}).get('status') == 'REVIEW' or any(x['status']=='REVIEW' for x in entry['screens']): entry['status'] = 'REVIEW'
                            else: entry['status'] = 'OK'
                            result['coverage']['states_checked'] += 1
                            result['warnings'].extend(entry['warnings'])
                        except Exception as e:
                            entry['status'] = 'BLOCKED'; entry['issue'] = f'{type(e).__name__}: {e}'
                            result['issues'].append(f'{width}x{height}/{state["name"]}: {entry["issue"]}')
                            result['warnings'].extend(state_warnings)
                        finally:
                            for ctx in contexts: ctx.close()
            finally:
                browser.close()
        statuses = [s['status'] for v in result['viewports'] for s in v['states']]
        result['warnings'] = list(dict.fromkeys(result['warnings']))
        if result['issues'] or 'BLOCKED' in statuses: result['status'] = 'BLOCKED'
        elif 'FAIL' in statuses: result['status'] = 'FAIL'
        # Never claim overall PASS: agent still needs to inspect scenarios and coverage.
        return result
    except Exception as e:
        result['status'] = 'BLOCKED'; result['issues'].append(f'Ошибка браузера: {type(e).__name__}: {e}'); return result
