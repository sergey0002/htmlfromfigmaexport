"""Pairwise browser inspection, adapted from the project's render_util.py.

Requires Python Playwright, Pillow and a local Chromium installation. Only loopback
HTTP endpoints are accepted. External network requests are blocked and reported.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from urllib.parse import urlsplit

FREEZE_CSS = """*, *::before, *::after { animation-duration: 0s !important;
 animation-delay: 0s !important; transition-duration: 0s !important;
 transition-delay: 0s !important; caret-color: transparent !important;
 scroll-behavior: auto !important; }"""


def loopback_url(url: str) -> bool:
    try:
        u = urlsplit(url)
        return (u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1', '::1')
                and u.username is None and u.password is None and u.port is not None)
    except ValueError:
        return False


def compare(reference: str, candidate: str, width: int, height: int, output, threshold: float = 0.01, actions=None, work_dir=None):
    if actions is None: actions = []
    if not isinstance(actions, list) or len(actions) > 30:
        return {'status': 'BLOCKED', 'issues': ['Сценарий должен содержать не более 30 действий']}
    if not all(loopback_url(u) for u in (reference, candidate)):
        return {'status': 'BLOCKED', 'issues': ['Допустимы только HTTP URL на localhost/127.0.0.1/::1 с портом']}
    if not 200 <= width <= 4096 or not 200 <= height <= 4096 or not 0 <= threshold <= 1:
        return {'status': 'BLOCKED', 'issues': ['Некорректный размер viewport или порог']}
    raw_work = Path(work_dir or '.work').absolute(); raw_output = Path(output).absolute()
    if raw_work.is_symlink() or any(p.is_symlink() for p in (raw_output, *raw_output.parents) if p == raw_work or p.is_relative_to(raw_work)):
        return {'status':'BLOCKED', 'issues':['Символические ссылки рабочей области запрещены']}
    work = raw_work.resolve()
    output = raw_output.resolve()
    if not output.is_relative_to(work) or output == work or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        return {'status': 'BLOCKED', 'issues': ['Каталог снимков должен быть новым или пустым внутри .work/']}
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image, ImageChops
    except ImportError as e:
        return {'status': 'BLOCKED', 'issues': [f'Установите зависимости и Chromium: {e}']}
    issues, warnings, observed, screenshots = [], [], [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
            try:
                for name, url in [('reference', reference), ('candidate', candidate)]:
                    ctx = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1, locale='ru-RU', reduced_motion='reduce', service_workers='block')
                    ctx.route_web_socket('**/*', lambda ws: ws.close())
                    allowed = (urlsplit(url).scheme, urlsplit(url).hostname, urlsplit(url).port)
                    def route_handler(route):
                        u = urlsplit(route.request.url)
                        if (u.scheme, u.hostname, u.port) == allowed and route.request.method in ('GET', 'HEAD'):
                            route.continue_()
                        else:
                            message = f'{name}: заблокирован сетевой запрос {u.scheme}://{u.netloc}{u.path}'
                            (issues if route.request.is_navigation_request() or route.request.method not in ('GET', 'HEAD') else warnings).append(message)
                            route.abort()
                    ctx.route('**/*', route_handler)
                    page = ctx.new_page()
                    page.on('pageerror', lambda e: issues.append(f'{name}: ошибка JS: {e}'))
                    def response_handler(response):
                        if response.status >= 400:
                            msg = f'{name}: HTTP {response.status}: {response.url}'
                            (issues if response.request.is_navigation_request() else warnings).append(msg)
                    def request_failed(req):
                        msg = f'{name}: запрос не выполнен: {req.url} ({req.failure})'
                        (issues if req.is_navigation_request() else warnings).append(msg)
                    page.on('response', response_handler)
                    page.on('requestfailed', request_failed)
                    response = page.goto(url, wait_until='load', timeout=30000)
                    if not response or response.status >= 400:
                        issues.append(f'{name}: страница недоступна')
                    page.add_style_tag(content=FREEZE_CSS)
                    page.evaluate('document.fonts.ready')
                    for action in actions:
                        if not isinstance(action, dict): raise ValueError('Действие должно быть объектом')
                        kind = action.get('type')
                        if kind == 'click':
                            selector = action.get('selector')
                            if not isinstance(selector, str) or not selector or len(selector) > 500: raise ValueError('Некорректный selector')
                            element = page.locator(selector)
                            if element.count() != 1: raise ValueError(f'Селектор должен находить один элемент: {selector}')
                            safe = element.evaluate("e => e.tagName === 'BUTTON' && !(e.closest('form') && e.type === 'submit')")
                            if not safe: raise ValueError('Клик допустим только по кнопкам вне отправки форм')
                            element.click(timeout=5000)
                        elif kind == 'press' and action.get('key') in ('Tab', 'Escape', 'Enter', 'Space'):
                            if action['key'] in ('Enter', 'Space'): raise ValueError('Enter/Space могут запустить небезопасное действие')
                            page.keyboard.press(action['key'])
                        elif kind == 'scroll' and isinstance(action.get('y'), int) and 0 <= action['y'] <= 60000:
                            page.evaluate('(y) => window.scrollTo(0, y)', action['y'])
                        else: raise ValueError(f'Недопустимое действие: {action}')
                        if (urlsplit(page.url).scheme, urlsplit(page.url).hostname, urlsplit(page.url).port) != allowed:
                            raise ValueError('Навигация сценария за пределы исходного origin запрещена')
                    page.evaluate("""async () => {
                        const initialY = scrollY;
                        for (let y=0; y<Math.min(document.documentElement.scrollHeight, 60000); y+=Math.max(300,innerHeight)) {
                            scrollTo(0,y); await new Promise(r=>setTimeout(r,30));
                        }
                        scrollTo(0,initialY);
                        // Let scroll handlers and React state updates settle before measuring.
                        await new Promise(requestAnimationFrame);
                        await new Promise(requestAnimationFrame);
                    }""")
                    broken = page.locator('img').evaluate_all('(els) => els.filter(i => !i.complete || !i.naturalWidth).map(i => i.currentSrc || i.src)')
                    if broken: warnings.append(f'{name}: не загружены изображения: {broken}')
                    data = page.evaluate("""() => ({text: document.body.innerText.trim(),
                        size: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
                        counts: Object.fromEntries(['h1','h2','button','a','img','input','section','article'].map(t => [t, document.querySelectorAll(t).length]))})""")
                    observed.append(data)
                    if data['size'][1] > 60000 or data['size'][0] > 10000 or data['size'][0] * data['size'][1] > 40_000_000:
                        raise ValueError('Страница превышает безопасные размеры снимка')
                    screenshots.append(page.screenshot(full_page=True, animations='disabled'))
                    ctx.close()
            finally:
                browser.close()
        output.mkdir(parents=True, exist_ok=True)
        (output / 'reference.png').write_bytes(screenshots[0]); (output / 'candidate.png').write_bytes(screenshots[1])
        a, b = [Image.open(io.BytesIO(s)).convert('RGB') for s in screenshots]
        mismatches = []
        if a.size != b.size:
            (warnings if warnings else mismatches).append(f'Размеры изображений отличаются: {a.size} vs {b.size}' + ('; неполные ресурсы могут влиять на снимок' if warnings else ''))
            ratio = None
        else:
            diff = ImageChops.difference(a, b)
            diff.save(output / 'diff.png')
            channel_max = ImageChops.lighter(ImageChops.lighter(*diff.split()[:2]), diff.split()[2])
            hist = channel_max.point(lambda x: 255 if x > 12 else 0).histogram()
            ratio = hist[255] / (a.width * a.height)
            if ratio > threshold:
                (warnings if warnings else mismatches).append(f'Различается {ratio:.2%} пикселей, порог {threshold:.2%}' + ('; неполные ресурсы могут влиять на снимок' if warnings else ''))
        if observed[0]['text'] != observed[1]['text']: mismatches.append('Видимый текст отличается')
        if observed[0]['counts'] != observed[1]['counts']: mismatches.append('Количество элементов отличается')
        if any(x['size'][0] > width for x in observed): mismatches.append('Горизонтальный overflow')
        return {'status': 'BLOCKED' if issues else ('FAIL' if mismatches else 'INCOMPLETE'),
                'issues': issues, 'warnings': warnings, 'mismatches': mismatches, 'difference_ratio': ratio,
                'viewport': [width, height], 'observed': observed, 'artifacts': str(output),
                'next': 'Проверить все остальные размеры, маршруты, интерактив и доступность; один снимок не является приёмкой.'}
    except Exception as e:
        return {'status': 'BLOCKED', 'issues': issues + [f'Ошибка браузерной проверки: {type(e).__name__}: {e}'], 'warnings': warnings}
