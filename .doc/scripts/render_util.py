#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Открыть пару страниц (React-эталон и vanilla) в одном Chromium с одинаковыми
условиями: шрифты не блокируются, анимации выключены, lazy-картинки догружены,
DSF = 2. Общая инфраструктура для dom_diff.py и pixel_gate.py.

Запуск напрямую поставлять не нужно — модуль импортируется.
"""
import functools
import http.server
import os
import socket
import sys
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VIEWPORTS = [(390, 844), (768, 1024), (1024, 800), (1440, 900)]

# Ключевые блоки: сравнение идёт ПО БЛОКАМ, а не по секции целиком —
# одна сломанная карточка не «тонет» в среднем значении.
BLOCKS = [
    ("hero", "#root > div > section:nth-of-type(1)", ".hero"),
    ("header", "#root > div > header", ".site-header"),
    ("team", "#team", "#team"),
    ("coaching", "#coaching", "#coaching"),
    ("standings", "#standings", "#standings"),
    ("history", "#history", "#history"),
    ("partners", "#partners", "#partners"),
    ("contacts", "#contacts", "#contacts"),
    ("footer", "#root > div > footer", ".site-footer"),
]

# Карточки внутри секции: отдельный дифф по каждой (п. 3 идеи pixel-gate).
BLOCK_CARDS = {
    # эталон / vanilla: карточка игрока, персонала, партнёра
    "team": ("#team .card", "#team .player-card"),
    "coaching": ("#coaching .grid > .card", "#coaching .staff-card"),
    "partners": ("#partners .grid > div", "#partners .partner-card"),
}

FREEZE_CSS = """
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}
"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve(folder, port=None):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *a):
            pass

    port = port or free_port()
    handler = functools.partial(Quiet, directory=folder)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    httpd.port = port
    return httpd


def is_local(url):
    return ("127.0.0.1" in url) or ("localhost" in url)


def make_context(browser, width, height, dsf=2, block_external=False):
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=dsf,
    )
    if block_external:
        ctx.route("**/*", lambda r: r.continue_() if is_local(r.request.url) else r.abort())
    return ctx


def settle(page, timeout=25000, step=350):
    """Дождаться шрифтов, сети и всех lazy-изображений, затем вернуться наверх."""
    page.wait_for_load_state("load")
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    # Каждый шаг изолирован: страница могла перезагрузиться (Vite HMR и т.п.),
    # и падение одного evaluate не должно ронять весь гейт.
    steps = [
        lambda: page.add_style_tag(content=FREEZE_CSS),
        lambda: page.evaluate("""async () => {
            if (document.fonts && document.fonts.ready) { try { await document.fonts.ready } catch (e) {} }
        }"""),
        lambda: page.evaluate("""async () => {
            const h = Math.min(document.documentElement.scrollHeight, 60000);
            for (let y = 0; y < h; y += Math.max(300, innerHeight * 0.8)) {
                window.scrollTo(0, y);
                await new Promise(r => setTimeout(r, 40));
            }
            window.scrollTo(0, 0);
            await new Promise(r => setTimeout(r, 150));
        }"""),
        lambda: page.evaluate("""async () => {
            await Promise.race([
                Promise.all([...document.images].map(i => i.decode ? i.decode().catch(() => {}) : null)),
                new Promise(r => setTimeout(r, 5000)),
            ]);
            window.scrollTo(0, 0);
        }"""),
    ]
    for stepfn in steps:
        try:
            stepfn()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] settle: {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr)
    page.wait_for_timeout(step)


def both_pages(browser, ref_url, van_url, width, height, dsf=2):
    """Открыть эталон и vanilla: одинаковые viewport/DSF, шрифты разрешены."""
    ref_ctx = make_context(browser, width, height, dsf)
    ref = ref_ctx.new_page()
    ref.goto(ref_url, wait_until="load")
    settle(ref)

    van_ctx = make_context(browser, width, height, dsf)
    van = van_ctx.new_page()
    van.goto(van_url, wait_until="load")
    settle(van)
    return (ref_ctx, ref), (van_ctx, van)


def ensure_ref_url(url):
    """Нормализовать локальный эталон: playwright блокирует localhost-route,
    поэтому внутри роутинга используем 127.0.0.1."""
    if url.startswith("http://localhost:"):
        return url.replace("http://localhost:", "http://127.0.0.1:", 1)
    return url


def folder_abspath(folder):
    return os.path.abspath(folder)
