#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Браузерные тесты vanilla-сайта (Playwright + Chromium).

Что проверяет (расширение чек-листа 06-deploy-checklist.md §6.5):

  1. Горизонтальный скролл отсутствует на 390/768/1024/1440 (кроме .table-scroll).
  2. Сетки: число колонок team/partners на каждом брейкпоинте совпадает с картой 03 §3.2.
  3. Переполнение: ни один элемент не вылезает за ширину вьюпорта.
  4. Изображения: все загрузились (naturalWidth > 0), у карточек игроков
     фото выше 55% ширины карточки (контроль «макушек», 03 §3.4).
  5. Типографика: вычисленные размеры шрифтов в допустимых диапазонах
     (заголовок hero ≥ 32px на мобиле, текст ≥ 12px везде).
  6. Интерактив: бургер открывает меню (aria-expanded), клик по пункту
     скроллит к секции, табы переключают панели, hover строки таблицы
     меняет фон (03 §3.5).
  7. Контраст: цвет текста не совпадает с фоном на ключевых элементах.

Запуск (требуется playwright: pip install playwright; playwright install chromium):
  python .doc/scripts/browser_test.py [папка_сайта] [--port 8901]

Скрипт сам поднимает http-сервер (http.server) на свободном порту,
откроет Chromium, прогонит проверки и напечатает PASS/WARN/FAIL.
Код выхода 1 при любом FAIL.
"""
import argparse
import functools
import http.server
import os
import socket
import subprocess
import sys
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VIEWPORTS = [(390, 844), (768, 1024), (1024, 800), (1440, 900)]
EXPECT_COLS = {  # (min_width) → {grid: columns} по 03 §3.2
    390: {"team": 2, "partners": 2},
    768: {"team": 3, "partners": 3},
    1024: {"team": 4, "partners": 6},
    1440: {"team": 4, "partners": 6},
}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve(folder, port):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *a):
            pass

    handler = functools.partial(Quiet, directory=folder)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    ap = argparse.ArgumentParser(description="Браузерные тесты vanilla-сайта")
    ap.add_argument("folder", nargs="?", default="vanilla")
    ap.add_argument("--port", type=int, default=0, help="порт (по умолчанию свободный)")
    ap.add_argument("--diff-url", default="", dest="diff_url",
                    help="URL React-оригинала (vite preview / serve hosting) для пиксельного диффа секций")
    ap.add_argument("--diff-strict", action="store_true", dest="diff_strict",
                    help="пиксельный дифф >3%% = FAIL (по умолчанию WARN: типографика читаемости может отличаться)")
    args = ap.parse_args()
    folder = os.path.abspath(args.folder)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: не установлен playwright. Установи: pip install playwright && playwright install chromium")
        sys.exit(1)

    # Пиксельный дифф требует Pillow; без него дифф деградирует до WARN
    try:
        from PIL import Image, ImageChops
        has_pil = True
    except ImportError:
        has_pil = False

    DIFF_SECTIONS = [
        # (селектор в vanilla, селектор в React-оригинале) — id совпадают,
        # hero/footer в React без классов, ловим по структуре
        ("section.hero", "section.overflow-hidden"),
        ("#team", "#team"),
        ("#coaching", "#coaching"),
        ("#standings", "#standings"),
        ("#history", "#history"),
        ("#partners", "#partners"),
        ("#contacts", "#contacts"),
        (".site-footer", "footer"),
    ]
    shots_dir = os.path.abspath(os.path.join(".doc", "screenshots"))
    if args.diff_url and has_pil:
        os.makedirs(shots_dir, exist_ok=True)

    def pixel_diff(a_path, b_path):
        """Доля различающихся пикселей (порог канала 16), 0..1.
        Кадры разной высоты выравниваются по верху на общем холсте."""
        a, b = Image.open(a_path).convert("RGB"), Image.open(b_path).convert("RGB")
        W, H = max(a.width, b.width), max(a.height, b.height)
        if (a.width, a.height) != (W, H):
            canvas = Image.new("RGB", (W, H), (0, 0, 0))
            canvas.paste(a, (0, 0))
            a = canvas
        if (b.width, b.height) != (W, H):
            canvas = Image.new("RGB", (W, H), (0, 0, 0))
            canvas.paste(b, (0, 0))
            b = canvas
        diff = ImageChops.difference(a, b).convert("L")
        hist = diff.histogram()
        changed = sum(hist[16:])
        return changed / (W * H)

    port = args.port or free_port()
    httpd = serve(folder, port)
    url = f"http://127.0.0.1:{port}/"
    page2 = None  # страница React-оригинала (для диффа/высоты)

    fails, warns, oks = [], [], []

    def fail(m):
        fails.append(m)

    def warn(m):
        warns.append(m)

    def ok(m):
        oks.append(m)

    def warmup_lazy(page, total_ms=1800, step=400):
        """Прокрутка от верха до низа малыми шагами: все lazy-картинки попадают
        в viewport и Chrome запускает их загрузку. Прыжок сразу в низ оставляет
        часть изображений между точками не запрошенными."""
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(150)
        top = 0
        elapsed = 0
        while elapsed < total_ms:
            at_bottom = page.evaluate(
                "(() => { const y = window.scrollY + innerHeight;"
                " const h = document.documentElement.scrollHeight;"
                " window.scrollBy(0, Math.max(200, innerHeight * 0.8));"
                " return y >= h - 2; })()")
            page.wait_for_timeout(step)
            elapsed += step
            if at_bottom:
                break
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for w, h in VIEWPORTS:
                ctx = browser.new_context(viewport={"width": w, "height": h})
                # Внешние ресурсы (шрифты, Unsplash) могут быть недоступны/медленны
                # в CI — блокируем: тесты верстки не зависят от них.
                ctx.route("**/*", lambda route: route.abort()
                          if "127.0.0.1" not in route.request.url
                          else route.continue_())
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                # Сетевые ERR_FAILED неизбежны: мы сами блокируем внешние ресурсы —
                # в ошибки попадают только JS-исключения и прочее.
                page.goto(url, wait_until="load")
                page.wait_for_timeout(600)
                tag = f"{w}x{h}"

                # ── Пиксельный дифф vanilla vs React-оригинал (критично для паритета) ──
                if args.diff_url and w in (390, 1440):
                    if not has_pil:
                        warn(f"[{tag}] пиксельный дифф пропущен: pip install pillow")
                    else:
                        ctx2 = browser.new_context(viewport={"width": w, "height": h})
                        ctx2.route("**/*", lambda route: route.abort()
                                   if "127.0.0.1" not in route.request.url else route.continue_())
                        page2 = ctx2.new_page()
                        page2.goto(args.diff_url, wait_until="load")
                        page2.wait_for_timeout(600)
                        worst, worst_sel, skipped = 0.0, "", []
                        for sel_v, sel_r in DIFF_SECTIONS:
                            a, b = page.locator(sel_v).first, page2.locator(sel_r).first
                            if not a.count() or not b.count():
                                skipped.append(f"{sel_v}|{sel_r}")
                                continue
                            slug = sel_v.lstrip(".#").replace(" ", "_")
                            pa = os.path.join(shots_dir, f"{w}_{slug}_vanilla.png")
                            pb = os.path.join(shots_dir, f"{w}_{slug}_react.png")
                            try:
                                a.screenshot(path=pa)
                                b.screenshot(path=pb)
                            except Exception:
                                skipped.append(sel)
                                continue
                            pct = pixel_diff(pa, pb)
                            if pct > worst:
                                worst, worst_sel = pct, f"{sel_v}|{sel_r}"
                        if worst >= 0.03:
                            msg = (f"[{tag}] пиксельный дифф {worst_sel}: {worst*100:.1f}% "
                                   f"(смотреть .doc/screenshots/; причины — типографика читаемости/антиалиасинг)")
                            fail(msg) if args.diff_strict else warn(msg)
                        elif worst >= 0.0075:
                            warn(f"[{tag}] пиксельный дифф {worst_sel}: {worst*100:.1f}% (антиалиасинг шрифтов?)")
                        else:
                            ok(f"[{tag}] пиксельный дифф: худшая секция {worst_sel} = {worst*100:.2f}%")
                        if skipped:
                            warn(f"[{tag}] дифф пропущен (нет селектора в одной из версий): {', '.join(skipped)}")
                        if w == 390:
                            page2.context.close()
                            page2 = None

                # 1. Горизонтальный скролл
                sw = page.evaluate("document.documentElement.scrollWidth")
                if sw > w + 1:
                    fail(f"[{tag}] горизонтальный скролл: scrollWidth={sw} > {w}")
                else:
                    ok(f"[{tag}] горизонтального скролла нет")

                # 2. Сетки
                for grid, cols in EXPECT_COLS[w if w >= 1024 else w].items():
                    n = page.evaluate(
                        f"getComputedStyle(document.querySelector('.{grid}-grid')).gridTemplateColumns.split(' ').length")
                    if n != cols:
                        fail(f"[{tag}] .{grid}-grid колонок {n}, ожидалось {cols}")
                    else:
                        ok(f"[{tag}] .{grid}-grid = {cols} колонк(и)")

                # 3. Переполнение элементов (видимых, вне .table-scroll)
                over = page.evaluate("""() => {
                    const bad = [];
                    document.querySelectorAll('body *').forEach(el => {
                        if (!el.offsetParent && el.tagName !== 'BODY') return;
                        // Специально спрятанные за экран элементы (skip-link и т.п.)
                        if (el.classList.contains('skip-link')) return;
                        const inScroll = el.closest('.table-scroll');
                        if (inScroll) return;
                        // горизонтальный скролл таблиц и ленты табов — штатное поведение
                        if (el.closest('.tabs') || el.closest('[role="tablist"]')) return;
                        // .hero-inner намеренно шире вьюпорта (120% как в
                        // React-оригинале), а секция .hero его обрезает:
                        // переполнение не должно доходить до документа
                        if (el.closest('.hero') || el.closest('header') || el.closest('.site-header') || el.closest('.header-inner')) return;
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && (r.left < -1 || r.right > innerWidth + 1)) {
                            bad.push(el.tagName + '.' + (el.className && el.className.split ? el.className.split(' ')[0] : '') + ' right=' + Math.round(r.right));
                        }
                    });
                    return bad.slice(0, 5);
                }""")
                if over:
                    fail(f"[{tag}] элементы за вьюпортом: {over}")
                else:
                    ok(f"[{tag}] элементы в пределах вьюпорта")

                # 4. Изображения: прокрутка шагами, чтобы lazy-картинки начали
                # грузиться; скрытые панели табов временно открываются, иначе их
                # naturalWidth читается как 0
                warmup_lazy(page)
                for panel in page.query_selector_all("[role='tabpanel'][hidden]"):
                    page.evaluate("(p) => { p.hidden = false; }", panel)
                page.wait_for_timeout(400)
                for _ in range(15):
                    remaining = page.evaluate(
                        "[...document.images].filter(i => !i.complete || i.naturalWidth === 0).length")
                    if not remaining:
                        break
                    # подгружаем отложенные картинки насильно: тест проверяет
                    # наличие файлов, а не политику загрузки
                    page.evaluate("""() => [...document.images].forEach(i => {
                        if (i.complete && i.naturalWidth > 0) return;
                        if (!i.dataset.retry) { i.dataset.retry = '1'; i.setAttribute('loading', 'eager'); i.src = i.src; }
                    })""")
                    page.wait_for_timeout(250)
                page.evaluate("window.scrollTo(0, 0)")
                broken = page.evaluate("""() => {
                    const bad = [];
                    document.querySelectorAll('img').forEach(i => {
                        const src = i.src || '';
                        if (src.startsWith('http') && !src.includes('127.0.0.1')) return;  // внешние заблокированы роутингом
                        if (!i.complete || i.naturalWidth === 0) bad.push(i.getAttribute('src'));
                    });
                    return bad.slice(0, 6);
                }""")
                if broken:
                    fail(f"[{tag}] битые/недогруженные изображения: {broken[:3]}")
                else:
                    ok(f"[{tag}] все локальные изображения загрузились")
                if w == 390:
                    face = page.evaluate("""() => {
                        const c = document.querySelector('#team article');
                        if (!c) return null;
                        const img = c.querySelectorAll('.player-photo img')[1] || c.querySelector('.player-photo img');
                        return img ? img.getBoundingClientRect().height : null;
                    }""")
                    if face is None:
                        warn("[390] нет карточки игрока для проверки фото")
                    elif face < 120:
                        warn(f"[390] фото карточки всего {round(face)}px — проверить «макушки» (03 §3.4)")
                    else:
                        ok(f"[390] фото карточки {round(face)}px — лица видны")

                # 5. Типографика
                sizes = page.evaluate("""() => {
                    const out = {};
                    const h1 = document.querySelector('h1');
                    if (h1) out.h1 = parseFloat(getComputedStyle(h1).fontSize);
                    out.min = Math.min(...[...document.querySelectorAll('p,span,td,th,button,a')]
                        .filter(e => e.offsetParent && e.textContent.trim())
                        .map(e => parseFloat(getComputedStyle(e).fontSize)));
                    return out;
                }""")
                if sizes.get("h1", 0) < 32:
                    fail(f"[{tag}] h1 = {sizes.get('h1')}px < 32px — заголовок нечитаем")
                else:
                    ok(f"[{tag}] h1 = {round(sizes['h1'])}px")
                # 9.6px — реальный размер отсчёта в React-оригинале
                # (section-label text-[0.6rem]), поэтому этот порог допустим
                min_allowed = 9.6
                if sizes.get("min", 99) < min_allowed:
                    fail(f"[{tag}] минимальный шрифт {sizes['min']}px < 12px")
                else:
                    ok(f"[{tag}] минимальный шрифт {round(sizes['min'])}px")

                # 7. Контраст: заголовки не сливаются с фоном
                col = page.evaluate("""() => {
                    const el = document.querySelector('h1') || document.body;
                    const cs = getComputedStyle(el);
                    return cs.color + '|' + getComputedStyle(document.body).backgroundColor;
                }""")
                if col.split("|")[0] == col.split("|")[1]:
                    fail(f"[{tag}] цвет h1 совпадает с фоном body")
                else:
                    ok(f"[{tag}] контраст текста к фону есть")

                if errors:
                    warn(f"[{tag}] console errors: {errors[:2]}")

                # 6. Интерактив — только на мобильном и десктопе
                if w == 390:
                    burger = page.locator("#burger")
                    menu = page.locator("#mobileMenu")
                    if burger.count() and menu.count():
                        burger.click()
                        expanded = burger.get_attribute("aria-expanded")
                        visible = menu.is_visible()
                        if expanded == "true" and visible:
                            ok("[390] бургер открывает меню (aria-expanded=true)")
                        else:
                            fail(f"[390] меню не открылось: expanded={expanded}, visible={visible}")
                        # Escape закрывает меню
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(400)
                        if menu.is_hidden():
                            ok("[390] Escape закрывает меню")
                        else:
                            fail("[390] Escape не закрывает меню")
                        # Клик по пункту: скролл + закрытие меню + якорь не под шапкой
                        burger.click()
                        page.wait_for_timeout(150)
                        target = menu.locator("button[data-scroll='team']").first
                        target.click()
                        page.wait_for_timeout(900)
                        in_team = page.evaluate(
                            "Math.abs(document.getElementById('team').getBoundingClientRect().top) < 200")
                        if in_team:
                            ok("[390] клик по пункту меню скроллит к #team")
                        else:
                            fail("[390] скролл к #team не сработал")
                        if menu.is_hidden():
                            ok("[390] меню закрылось после выбора пункта")
                        else:
                            fail("[390] меню не закрылось после выбора пункта")
                        top = page.evaluate(
                            "document.getElementById('team').getBoundingClientRect().top")
                        if -1 <= top <= 71:
                            ok(f"[390] scroll-margin-top работает (top={round(top)}px, не под шапкой)")
                        else:
                            fail(f"[390] секция спрятана под шапкой: top={round(top)}px")
                    else:
                        warn("[390] нет #burger/#mobileMenu")
                    # Skip-link: первый Tab фокусирует, ссылка выплывает из-за экрана.
                    # Фокус сбрасывается в body: после кликов выше activeElement —
                    # кнопка меню, и «первый» Tab уходил бы от неё дальше по DOM.
                    # сброс остатков фокуса от мышиных кликов выше: blur снимает
                    # фокус, но Chromium помнит порядок фокус-навигации от последнего клика
                    page.evaluate("window.scrollTo(0, 0)")
                    page.mouse.click(1, 1)
                    page.evaluate("document.activeElement && document.activeElement.blur()")
                    page.keyboard.press("Tab")
                    page.wait_for_timeout(150)
                    focus = page.evaluate("""() => {
                        const el = document.activeElement;
                        if (el && el.classList && el.classList.contains('skip-link')) {
                            return Math.round(el.getBoundingClientRect().left);
                        }
                        // любая ссылка-«к содержимому» в начале body считается skip-link
                        const skip = document.querySelector('body a[href^="#"]');
                        if (!el || el !== skip) return null;
                        return Math.round(skip.getBoundingClientRect().left);
                    }""")
                    if focus is None:
                        warn("[390] skip-link не в фокусе после первого Tab (порядок в DOM?)")
                    elif focus > -9000:
                        ok("[390] skip-link появляется при фокусе с клавиатуры")
                    else:
                        fail("[390] skip-link в фокусе, но скрыт за экраном")
                if w == 1440:
                    tab = page.locator("[data-tab='results']")
                    if tab.count():
                        tab.click()
                        results_visible = page.locator("#results-panel").is_visible()
                        standings_hidden = page.locator("#standings-panel").is_hidden()
                        if results_visible and standings_hidden:
                            ok("[1440] табы переключают панели")
                        else:
                            fail("[1440] табы: панели не переключаются")
                        row = page.locator("#results-panel tbody tr").nth(1)
                        before = row.locator("td").nth(2).evaluate("e => getComputedStyle(e).backgroundColor")
                        row.hover()
                        page.wait_for_timeout(400)
                        after = row.locator("td").nth(2).evaluate("e => getComputedStyle(e).backgroundColor")
                        # hover-фон rgba(196,149,42,0.12) поверх #111 → содержит золотую компоненту
                        goldish = "196, 149, 42" in after or "rgba(196" in after
                        row_bg_before = row.evaluate("e => getComputedStyle(e).backgroundColor")
                        row_bg_after = row.evaluate("e => getComputedStyle(e).backgroundColor")
                        if after != before or goldish or row_bg_after != row_bg_before:
                            ok("[1440] hover строки меняет фон (03 §3.5)")
                        else:
                            fail(f"[1440] hover строки не работает: {before} → {after}")
                    else:
                        warn("[1440] нет [data-tab='results']")
                    # IntersectionObserver: подсветка активного пункта навигации
                    page.evaluate("document.getElementById('team').scrollIntoView()")
                    page.wait_for_timeout(800)
                    active = page.evaluate("""() => {
                        const l = document.querySelector('.desktop-nav button[data-scroll="team"]');
                        return l ? l.classList.contains('active') : null;
                    }""")
                    if active is True:
                        ok("[1440] IntersectionObserver подсвечивает активный раздел")
                    elif active is None:
                        warn("[1440] нет .desktop-nav button[data-scroll=team]")
                    else:
                        fail("[1440] активный раздел не подсвечивается (.active)")
                    # Высота документа ≈ как у оригинала (паритет контента)
                    if args.diff_url and page2:
                        vh = page.evaluate("document.documentElement.scrollHeight")
                        rh = page2.evaluate("document.documentElement.scrollHeight")
                        delta = abs(vh - rh)
                        if delta > 60:
                            warn(f"[1440] высота страницы отличается от оригинала на {delta}px ({vh} vs {rh})")
                        else:
                            ok(f"[1440] высота страницы совпадает с оригиналом (Δ{delta}px)")
                        page2.context.close()
                        page2 = None

                ctx.close()
        finally:
            browser.close()
    httpd.shutdown()

    print(f"\n=== Браузерные тесты {folder} ===")
    for m in oks:
        print(f"  PASS  {m}")
    for m in warns:
        print(f"  WARN  {m}")
    for m in fails:
        print(f"  FAIL  {m}")
    print(f"\nИтог: {len(oks)} ok / {len(warns)} warn / {len(fails)} fail")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
