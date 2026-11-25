# -*- coding: utf-8 -*-
"""Пиксельная сверка с опубликованным оригиналом (tuba-sticky-…figma.site):
секция team/coaching на 390 и 1440 + отдельные фрагменты card.html/staff.html.
Оригиналу подменяются только URL картинок (локальные копии из src/imports):
превью отдаёт их как target_avatar/GiGgd4V2.jpg и player-XX-XXXX.png.
"""
import os
import re
import sys
import pathlib
import urllib.request

from playwright.sync_api import sync_playwright
from browser_test import serve, free_port

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(".").resolve()
OUT = ROOT / "vanilla" / ".pixel"
OUT.mkdir(exist_ok=True)
ORIGIN = "https://tuba-sticky-11235261.figma.site/"
ONLINE = sys.argv[1:] and sys.argv[1] == "--online"
online = ONLINE

port = free_port()
server = serve("vanilla", port)
LOCAL = f"http://127.0.0.1:{port}/"

ASSET_MAP = {
    "GiGgd4V2": "target-avatar.jpg",
    "D128d2d9": "administrator-nadezhda-asylova.jpg",
    "fbtqSQbz": "general-director-roman-voronin.jpg",
    "a2zdmnLx": "head-coach-ilya-lobachev.jpg",
    "DCzr_LUm": "senior-coach-yaroslav-isakov.jpg",
    "DIXzLzqn": "sport-director-vasiliy-petukhov.jpg",
    "BI7NhT89": "team-manager-aleksey-senchuk.jpg",
}
for n in (85, 16, 10, 11, 83, 5, 23, 29, 19, 31, 99, 22, 20):
    ASSET_MAP[f"player-{n}"] = f"player-{n}.jpg"
ASSET_MAP["lev-gerasimov"] = "lev-gerasimov.jpg"
ASSET_MAP["target-hero-texture"] = "target-hero-texture.png"

ASSET_URL = re.compile(r"/assets/([a-z0-9-]+?)-[A-Za-z0-9_]+\.(?:png|jpg|webp|jpeg)")

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for w, h in ((390, 844), (1440, 900)):
        tag = str(w)
        vp = {"width": w, "height": h}

        def new_page(block_external=True):
            ctx = browser.new_context(viewport=vp, device_scale_factor=1)
            if block_external:
                ctx.route("**/*", lambda r: r.continue_()
                          if (r.request.url.startswith("http://127.0.0.1")
                              or r.request.url.startswith("data:"))
                          else r.abort())
            return ctx.new_page()

        local = new_page()
        local.goto(LOCAL, wait_until="load")
        local.wait_for_timeout(800)
        if online:
            orig = new_page(block_external=False)

            def rewrite(route):
                url = route.request.url
                m = ASSET_URL.search(url)
                if m and m.group(1) in ASSET_MAP:
                    route.fulfill(status=302, headers={"location": LOCAL + "img/" + ASSET_MAP[m.group(1)]})
                else:
                    route.continue_()
            orig.route(re.compile(r"https://tuba-sticky-11235261\.figma\.site/assets/.*"), rewrite)
            orig.goto(ORIGIN, wait_until="load")
            orig.wait_for_timeout(2500)
            for name, sel in (("team", "#team"), ("coaching", "#coaching"), ("standings", "#standings")):
                a, b = local.locator(sel).first, orig.locator(sel).first
                if not b.count():
                    print(f"[{tag}] {name}: нет секции в оригинале")
                    continue
                a_shot = OUT / f"cmp_{tag}_{name}_vanilla.png"
                b_shot = OUT / f"cmp_{tag}_{name}_orig.png"
                a.screenshot(path=str(a_shot), animations="disabled")
                b.screenshot(path=str(b_shot), animations="disabled")
                print(f"[{tag}] {name}: снимки {a_shot.name} / {b_shot.name}")
            orig.context.close()

        # фрагменты карточки/штаба с фиксированной шириной: 300 / 290 px (как в макете)
        for name, sel_html, width in (("card", "card.html", 300), ("staff", "staff.html", 1312)):
            html = (ROOT / ".doc" / "screenshots" / sel_html).read_text(encoding="utf-8")
            html = ASSET_URL.sub(lambda m: "/img/" + ASSET_MAP.get(m.group(1), m.group(0)), html)
            html = html.replace(ORIGIN.rstrip("/") + "/", LOCAL)
            page = browser.new_page(viewport={"width": width + 40, "height": 700})
            page.goto(LOCAL, wait_until="load")
            page.set_content(
                f"<!doctype html><html lang=ru><head><meta charset=utf-8>"
                f"<link rel=stylesheet href='{LOCAL}css/style.css'>"
                f"<style>body{{padding:20px;background:#080808}}</style></head>"
                f"<body>{html}</body></html>", wait_until="load")
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / f"cmp_{tag}_{name}_orig-fragment.png"), animations="disabled")
            page.close()
        local.close()
    browser.close()
server.shutdown()
print("готово:", OUT)
