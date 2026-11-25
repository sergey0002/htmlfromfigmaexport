#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор SEO-пакета для vanilla-сайта: то, что скучно делать руками (05-seo-modern.md).

Создаёт в папке сайта (по умолчанию ./vanilla) — только on-page:
  favicon.svg + favicon-16/32.png, apple-touch-icon.png, android-chrome-192/512.png
  og-cover.png (1200×630)
  seo-head.html — готовый <head>-блок для вставки в build.mjs

Серверные файлы (robots.txt, sitemap.xml, манифест) НЕ создаются —
область ограничена on-page SEO.

PNG-иконки рисуются чистым Python (мишень: тёмный фон + золотые кольца),
Pillow не требуется. Свой логотип-картинку можно подставить флагом --logo
(тогда нужны Pillow; pip install pillow).

Запуск:
  python .doc/scripts/make_seo_pack.py --url https://fbk-target.ru/ --name "ФБК Таргет"
  python .doc/scripts/make_seo_pack.py ... --logo src/imports/target_avatar.jpg
"""
import argparse
import json
import os
import struct
import sys
import zlib

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ── чистый Python: PNG с мишенью (без зависимостей) ─────────────────────────
def _png_chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def target_png(size, bg=(8, 8, 8), gold=(196, 149, 42)):
    cx = cy = (size - 1) / 2
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter: None
        for x in range(size):
            dx, dy = x - cx, y - cy
            d = (dx * dx + dy * dy) ** 0.5
            r = d / (size / 2)
            if r > 0.92:
                c = bg
            elif r <= 0.18 or 0.42 <= r <= 0.58 or r >= 0.82:
                c = gold
            else:
                c = bg
            row += bytes(c)
        rows.append(bytes(row))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + _png_chunk(b"IEND", b""))


def og_cover_png(w=1200, h=630, bg=(8, 8, 8), gold=(196, 149, 42)):
    # тёмный фон + диагональная золотая полоса + мишень справа
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            c = bg
            diag = (x + y) / (w + h)
            if 0.605 <= diag <= 0.625 or 0.645 <= diag <= 0.66:
                c = gold
            dx, dy = x - w * 0.78, y - h / 2
            d = (dx * dx + dy * dy) ** 0.5 / (h * 0.30)
            if d <= 0.16 or 0.40 <= d <= 0.56 or d >= 0.80:
                c = gold
            row += bytes(c)
        rows.append(bytes(row))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + _png_chunk(b"IEND", b""))


def try_logo_png(src, sizes):
    try:
        from PIL import Image
    except ImportError:
        return None
    outs = {}
    im = Image.open(src).convert("RGBA")
    for name, s in sizes.items():
        sq = Image.new("RGBA", (max(im.size),) * 2, (8, 8, 8, 255))
        sq.paste(im, ((max(im.size) - im.width) // 2, (max(im.size) - im.height) // 2), im)
        outs[name] = sq.resize((s, s), Image.LANCZOS)
    return outs


def main():
    ap = argparse.ArgumentParser(description="SEO-пакет: favicons, og-cover, head-блок (on-page only)")
    ap.add_argument("--dir", default="vanilla", help="папка сайта (по умолчанию ./vanilla)")
    ap.add_argument("--url", required=True, help="канонический URL, https://site.ru/")
    ap.add_argument("--name", required=True, help="название сайта (для manifest/OG)")
    ap.add_argument("--desc", default="", help="описание для OG (по умолчанию — короткая форма)")
    ap.add_argument("--email", default="", help="email для JSON-LD")
    ap.add_argument("--logo", default="", help="PNG/JPG логотип: иконки из него (нужен Pillow)")
    ap.add_argument("--theme", default="#080808", help="theme color")
    args = ap.parse_args()

    d = os.path.abspath(args.dir)
    os.makedirs(d, exist_ok=True)
    url = args.url.rstrip("/") + "/"
    desc = args.desc or (args.name + " — официальный сайт.")

    # фавиконы
    sizes = {"favicon-16.png": 16, "favicon-32.png": 32,
             "apple-touch-icon.png": 180, "android-chrome-192.png": 192, "android-chrome-512.png": 512}
    made = []
    if args.logo and os.path.isfile(args.logo):
        imgs = try_logo_png(args.logo, sizes)
        if imgs:
            for name, im in imgs.items():
                im.save(os.path.join(d, name))
                made.append(name)
    if not made:
        for name, s in sizes.items():
            with open(os.path.join(d, name), "wb") as f:
                f.write(target_png(s))
            made.append(name)
        print("Иконки: сгенерирована мишень (--logo + Pillow = из логотипа).")

    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" fill="#080808"/>'
           '<circle cx="32" cy="32" r="26" fill="none" stroke="#C4952A" stroke-width="5"/>'
           '<circle cx="32" cy="32" r="14" fill="none" stroke="#C4952A" stroke-width="5"/>'
           '<circle cx="32" cy="32" r="4.5" fill="#C4952A"/></svg>')
    with open(os.path.join(d, "favicon.svg"), "w", encoding="utf-8") as f:
        f.write(svg)

    with open(os.path.join(d, "og-cover.png"), "wb") as f:
        f.write(og_cover_png())

    # head-блок для build.mjs
    sport = json.dumps(args.name, ensure_ascii=False)
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "SportsTeam", "@id": url + "#team", "name": args.name, "url": url,
         "logo": url + "android-chrome-512.png"},
        {"@type": "WebSite", "@id": url + "#website", "url": url, "name": args.name,
         "inLanguage": "ru-RU"}]}
    if args.email:
        ld["@graph"][0]["email"] = args.email
    head = f"""<!-- SEO-HEAD: вставить в build.mjs (шаблон <head>) -->
<title>{args.name} — официальный сайт</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="{args.theme}">
<link rel="icon" href="./favicon.svg" type="image/svg+xml">
<link rel="icon" href="./favicon-32.png" sizes="32x32" type="image/png">
<link rel="icon" href="./favicon-16.png" sizes="16x16" type="image/png">
<link rel="apple-touch-icon" href="./apple-touch-icon.png" sizes="180x180">
<meta property="og:type" content="website">
<meta property="og:locale" content="ru_RU">
<meta property="og:site_name" content={sport}>
<meta property="og:title" content="{args.name}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{url}og-cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{args.name}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{url}og-cover.png">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=2)}
</script>
"""
    with open(os.path.join(d, "seo-head.html"), "w", encoding="utf-8") as f:
        f.write(head)

    print(f"OK: {d}")
    print("  иконки:", ", ".join(made))
    print("  + favicon.svg, og-cover.png, seo-head.html")


if __name__ == "__main__":
    main()
