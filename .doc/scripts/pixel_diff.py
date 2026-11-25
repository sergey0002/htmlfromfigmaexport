# -*- coding: utf-8 -*-
"""Пиксельная дифф-карта: оригинал vs vanilla по секциям, с картой различий."""
import sys
import json
import pathlib
import re
from io import BytesIO

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from browser_test import serve, free_port

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(".").resolve()
OUT = ROOT / "vanilla" / ".pixel"
OUT.mkdir(exist_ok=True)
ORIGIN = "https://tuba-sticky-11235261.figma.site/"

port = free_port()
server = serve("vanilla", port)
LOCAL = f"http://127.0.0.1:{port}/"

ASSET_MAP = {"GiGgd4V2": "target-avatar.jpg", "D128d2d9": "administrator-nadezhda-asylova.jpg",
             "fbtqSQbz": "general-director-roman-voronin.jpg", "a2zdmnLx": "head-coach-ilya-lobachev.jpg",
             "DCzr_LUm": "senior-coach-yaroslav-isakov.jpg", "DIXzLzqn": "sport-director-vasiliy-petukhov.jpg",
             "BI7NhT89": "team-manager-aleksey-senchuk.jpg"}
for n in (85, 16, 10, 11, 83, 5, 23, 29, 19, 31, 99, 22, 20):
    ASSET_MAP[f"player-{n}"] = f"player-{n}.jpg"
ASSET_MAP["lev-gerasimov"] = "lev-gerasimov.jpg"
ASSET_MAP["target-hero-texture"] = "target-hero-texture.png"
ASSET_URL = re.compile(r"/assets/([a-z0-9-]+?)-[A-Za-z0-9_]+\.(?:png|jpg|webp|jpeg)")

SECTIONS = ("team", "coaching", "standings", "history", "partners", "contacts")


def diff_stats(a_bytes, b_bytes, name):
    a = Image.open(BytesIO(a_bytes)).convert("RGB")
    b = Image.open(BytesIO(b_bytes)).convert("RGB")
    w = min(a.width, b.width)
    h = min(a.height, b.height)
    a = a.crop((0, 0, w, h))
    b = b.crop((0, 0, w, h))
    diff = ImageChops.difference(a, b).convert("L")
    px = diff.load()
    bad = 0
    rows = {}
    cols_max = 0
    for y in range(h):
        row_bad = 0
        for x in range(w):
            if px[x, y] > 24:
                bad += 1
                row_bad += 1
        if row_bad:
            rows[y] = row_bad
    pct = 100.0 * bad / (w * h)
    # сводка по полосам по 100px: где различия
    bands = []
    for start in range(0, h, 100):
        s = sum(1 for y in range(start, min(start + 100, h)) if y in rows)
        if s:
            bands.append(f"{start}-{min(start+100,h)}")
    out = OUT / f"diff_{name}.png"
    Image.merge("RGB", (diff, Image.new("L", diff.size, 0), Image.new("L", diff.size, 0))).save(out)
    return {"section": name, "size_orig": [a.width, a.height], "size_van": [b.width, b.height],
            "diff_pct": round(pct, 2), "diff_rows": len(rows), "rows_total": h, "bands": bands[:12]}


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    report = []
    for w, hgt in ((1440, 900), (390, 844)):
        ctx_v = browser.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
        ctx_v.route("**/*", lambda r: r.continue_() if "127.0.0.1" in r.request.url else r.abort())
        van = ctx_v.new_page()
        van.goto(LOCAL, wait_until="load")
        van.wait_for_timeout(1200)

        ctx_o = browser.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)

        def rewrite(route):
            u = route.request.url
            if u.startswith("https://fonts.") or "fonts.gstatic" in u:
                return route.abort()
            m = ASSET_URL.search(u)
            if m and m.group(1) in ASSET_MAP:
                return route.fulfill(status=302, headers={"location": LOCAL + "img/" + ASSET_MAP[m.group(1)]})
            return route.continue_()

        ctx_o.route(re.compile(r"https://tuba-sticky-11235261\.figma\.site/assets/.*"), rewrite)
        orig = ctx_o.new_page()
        orig.goto(ORIGIN, wait_until="load")
        orig.wait_for_timeout(3000)
        # одинаковые шрифты с обеих сторон: загружаем Google Fonts только в контексте оригинала
        for sel in SECTIONS:
            o = orig.locator("#" + sel).first
            v = van.locator("#" + sel).first
            ob = o.screenshot(animations="disabled")
            vb = v.screenshot(animations="disabled")
            report.append(diff_stats(ob, vb, f"{w}_{sel}"))
        ctx_o.close()
        ctx_v.close()
    browser.close()
server.shutdown()
print(json.dumps(report, ensure_ascii=False, indent=1))
