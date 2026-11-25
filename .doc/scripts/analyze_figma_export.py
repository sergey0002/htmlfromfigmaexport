#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор экспорта Figma Make (React или Vue) перед конвертацией в vanilla-HTML.

Что делает:
  1. Определяет стек (React / Vue / неизвестно) и точку входа.
  2. Читает .figma/make/site.json (title/description/robots/OG) и figma-слоты index.html.
  3. Собирает все изображения (src/imports, src/assets, public) с реальными размерами.
  4. Извлекает из компонентов: массивы данных (имя, число элементов, ключи первого
     элемента), переменные состояния, эффекты/наблюдатели, скролл-вызовы,
     импорты картинок, инлайн-цвета, адаптивные Tailwind-классы.
  5. Собирает CSS-переменные и кастомные классы из src/**/*.css и <style> в *.vue.

Результат: markdown-отчёт (stdout; с --write — в .doc/report.md).

Зависимости: только стандартная библиотека Python 3.8+.
Запуск:  python .doc/scripts/analyze_figma_export.py [корень_проекта] [--write]
"""
import argparse
import json
import os
import re
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKIP_DIRS = {"node_modules", ".git", "dist", "hosting", "vanilla", ".doc", ".figma", ".kilo"}


# ── размеры изображений (без Pillow) ────────────────────────────────────────
def img_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(64)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:3] == b"\xff\xd8\xff":
            with open(path, "rb") as f:
                b = f.read()
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", b[i + 5:i + 9])
                    return w, h
                if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                ln = struct.unpack(">H", b[i + 2:i + 4])[0]
                i += 2 + ln
            return None
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            if head[12:16] == b"VP8X":
                w = int.from_bytes(head[24:27], "little") + 1
                h = int.from_bytes(head[27:30], "little") + 1
                return w, h
            if head[12:16] == b"VP8 ":
                w, h = struct.unpack("<HH", head[26:30])
                return (w & 0x3FFF), (h & 0x3FFF)
            if head[12:16] == b"VP8L":
                bits = int.from_bytes(head[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if head[:4] == b"GIF8":
            return struct.unpack("<HH", head[6:10])
    except OSError:
        pass
    return None


# ── разбор JS/TS-массивов со скобочным балансом ────────────────────────────
def split_top(body):
    items, depth, cur, instr, esc = [], 0, [], None, False
    for c in body:
        if instr:
            cur.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == instr:
                instr = None
            continue
        if c in "\"'`":
            instr = c
            cur.append(c)
            continue
        if c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
        if c == "," and depth == 0:
            items.append("".join(cur).strip())
            cur = []
            continue
        cur.append(c)
    tail = "".join(cur).strip()
    if tail:
        items.append(tail)
    return items


def extract_arrays(text):
    out = {}
    for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\[]+?)?=\s*\[", text):
        name = m.group(1)
        start = m.end() - 1
        depth, i, instr, esc = 0, start, None, False
        while i < len(text):
            c = text[i]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == instr:
                    instr = None
            elif c in "\"'`":
                instr = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[start + 1:i]
        items = [x for x in split_top(body) if x]
        first_keys = []
        if items and items[0].lstrip().startswith("{"):
            first_keys = re.findall(r"[{,]\s*([A-Za-z_$][\w$]*)\s*:", items[0])
        out[name] = {"count": len(items), "keys": first_keys, "preview": items[0][:120] if items else ""}
    return out


def find_files(root, exts):
    res = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if os.path.splitext(f)[1].lower() in exts:
                res.append(os.path.join(dirpath, f))
    return res


def read(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser(description="Анализ экспорта Figma Make (React/Vue)")
    ap.add_argument("root", nargs="?", default=".", help="корень проекта (по умолчанию текущая папка)")
    ap.add_argument("--write", action="store_true", help="дополнительно записать отчёт в .doc/report.md")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    L = []

    def w(s=""):
        L.append(s)

    w("# Отчёт анализа исходника (Figma Make)")
    w("")
    w(f"- Корень: `{root}`")

    # 1. Стек
    src = os.path.join(root, "src")
    vue_files = find_files(root, {".vue"})
    tsx_files = [p for p in find_files(root, {".tsx", ".jsx"})]
    app_vue = os.path.join(src, "App.vue")
    stack = "неизвестно"
    entry = ""
    if os.path.isfile(app_vue) or vue_files:
        stack = "Vue"
        entry = next((v for v in vue_files if v.endswith(("App.vue", "app.vue"))), vue_files[0] if vue_files else "")
    elif tsx_files:
        stack = "React"
        entry = os.path.join(src, "App.tsx") if os.path.isfile(os.path.join(src, "App.tsx")) else tsx_files[0]
    w(f"- Стек: **{stack}**; корневой компонент: `{os.path.relpath(entry, root) if entry else '—'}`")
    main_ts = os.path.join(src, "main.tsx")
    main_js = os.path.join(src, "main.ts")
    for cand in (main_ts, main_js):
        if os.path.isfile(cand):
            w(f"- Точка входа: `{os.path.relpath(cand, root)}`")

    # 2. Figma-оболочка
    idx = read(os.path.join(root, "index.html"))
    slots = re.findall(r"<!--\s*(figma:[\w-]+)\s*-->", idx)
    if slots:
        w(f"- Figma-слоты в index.html: {', '.join(f'`{s}`' for s in slots)} (это шаблон, не страница)")
    site_json_path = os.path.join(root, ".figma", "make", "site.json")
    if os.path.isfile(site_json_path):
        try:
            sj = json.loads(read(site_json_path))
            w("- `.figma/make/site.json`: " + json.dumps(sj, ensure_ascii=False))
            if sj.get("robots", {}).get("index") is False:
                w("  - ⚠️ `robots.index=false` → на проде обязательно включить индексацию (см. 05-seo-modern.md, 06-deploy-checklist.md)")
        except ValueError:
            w("- `.figma/make/site.json`: (битый JSON)")

    # 3. Изображения
    img_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
    imgs = find_files(root, img_exts)
    w("")
    w("## Изображения")
    w("")
    w("| Файл | Размер | Вектор |")
    w("|---|---|---|")
    for p in sorted(imgs):
        rel = os.path.relpath(p, root)
        if p.lower().endswith(".svg"):
            w(f"| `{rel}` | — | да |")
            continue
        wh = img_size(p)
        dim = f"{wh[0]}×{wh[1]}" if wh else "?"
        w(f"| `{rel}` | {dim} | — |")
    if imgs:
        nonsvg = [p for p in imgs if not p.lower().endswith(".svg")]
        ratios = {}
        for p in nonsvg:
            wh = img_size(p)
            if wh and wh[1]:
                ratios.setdefault(round(wh[0] / wh[1], 2), []).append(os.path.basename(p))
        if ratios:
            w("")
            w("Пропорции (W/H → файлы): " + "; ".join(f"{k} → {len(v)} шт." for k, v in sorted(ratios.items())))
            w("→ Контейнерам фото задать `aspect-ratio` по этим пропорциям (см. 03-css-responsive.md §3.4).")

    # 4. Компоненты
    comp_text = read(entry) if entry else ""
    if comp_text:
        vue_style = re.findall(r"<style[^>]*>(.*?)</style>", comp_text, re.S)
        script_text = comp_text
        w("")
        w("## Данные (массивы) в корневом компоненте")
        w("")
        arrays = extract_arrays(script_text)
        if arrays:
            w("| Имя | Элементов | Ключи первого элемента |")
            w("|---|---|---|")
            for name, info in arrays.items():
                if info["count"] >= 2 or re.search(r"(player|team|coach|staff|partner|match|stand|item|card|product|post|service|slide|nav|menu|link|img|photo)", name, re.I):
                    w(f"| `{name}` | {info['count']} | {', '.join(info['keys'][:10])} |")
            w("")
            w("Перенести ВСЕ перечисленные массивы целиком в `build.mjs` (см. 02-vanilla-build.md §2.3).")
        else:
            w("Массивов не найдено — данные могут лежать в соседних модулях: " + ", ".join(os.path.basename(p) for p in tsx_files[:10] + vue_files[:10]))

        state = re.findall(r"useState\s*(?:<[^>]+>)?\s*\(\s*['\"]?([\w-]*)['\"]?\s*\)", script_text)
        state += ["ref:" + n for n in re.findall(r"ref\s*\(\s*['\"]?([^)'\"]{1,30})", script_text)]
        w("")
        w("## Состояние и эффекты")
        w("")
        for label, pat in (
            ("Состояние (useState/ref)", state and ", ".join(f"`{s}`" for s in state) or "—"),
            ("useEffect/onMounted", "да" if re.search(r"useEffect|onMounted", script_text) else "—"),
            ("IntersectionObserver", "да" if "IntersectionObserver" in script_text else "—"),
            ("scrollIntoView / scrollTo", "да" if re.search(r"scrollIntoView|scrollTo\(", script_text) else "—"),
            ("Слушатели событий", ", ".join(sorted(set(re.findall(r"on(?:Click|Change|Input|Submit|KeyDown|MouseEnter|MouseLeave|Scroll)", script_text)))) or "—"),
        ):
            w(f"- {label}: {label.split(' (')[0] in ('Состояние',) and '' or ''}{pat}")
        imports = re.findall(r"import\s+\w+\s+from\s+['\"]([^'\"]+)['\"]", script_text)
        img_imports = [i for i in imports if re.search(r"\.(png|jpe?g|webp|svg|avif|gif)$", i, re.I)]
        w(f"- Импортов изображений: {len(img_imports)}" + ("" if not img_imports else " — скопировать файлы в `vanilla/img/`"))
        colors = sorted(set(re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]+\)", script_text)))
        if colors:
            w(f"- Инлайн-цвета ({len(colors)}): {', '.join(colors[:15])}{' …' if len(colors) > 15 else ''}")
        tw = sorted(set(re.findall(r"\b(?:sm|md|lg|xl|2xl):[\w./[\]-]+", script_text)))
        if tw:
            w(f"- Адаптивные Tailwind-классы ({len(tw)}): {', '.join(f'`{c}`' for c in tw[:25])}{' …' if len(tw) > 25 else ''}")
            w("  → Перевести в media-запросы по карте 03-css-responsive.md §3.2 (грид-классы `grid-cols-N` → `repeat(N, minmax(0,1fr))`).")

    # 5. CSS
    css_texts = []
    for p in find_files(root, {".css"}):
        css_texts.append(read(p))
    for s in vue_style:
        css_texts.append(s)
    css_all = "\n".join(css_texts)
    if css_all:
        vars_ = sorted(set(re.findall(r"(--[\w-]+)\s*:", css_all)))
        classes = sorted(set(re.findall(r"\.([A-Za-z][\w-]+)\s*[,{]", css_all)))
        w("")
        w("## CSS")
        w("")
        w(f"- Переменные ({len(vars_)}): {', '.join(f'`{v}`' for v in vars_)}")
        w(f"- Кастомные классы ({len(classes)}): {', '.join(f'`.{c}`' for c in classes[:40])}{' …' if len(classes) > 40 else ''}")
        w("- Google Fonts в CSS: " + ("да — перенести в <link> с preconnect (05 §5.1)" if "fonts.googleapis" in css_all else "не найдено"))

    report = "\n".join(L)
    print(report)
    if args.write:
        doc_dir = os.path.join(root, ".doc")
        os.makedirs(doc_dir, exist_ok=True)
        out = os.path.join(doc_dir, "report.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\n→ Отчёт записан: {out}")


if __name__ == "__main__":
    main()
