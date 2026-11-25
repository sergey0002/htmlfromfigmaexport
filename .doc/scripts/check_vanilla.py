#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Валидатор готового vanilla-сайта перед отдачей/заливкой.

  Проверяет (stdin-версия чек-листа 06-deploy-checklist.md):
  SEO:     title/description длины, ровно один h1, canonical, robots без noindex,
           OG/Twitter-разметка, JSON-LD валиден.
  Файлы:   все локальные href/src существуют (img/css/js/pdf/фавиконы).
  A11y:    alt у всех img, width/height у img, loading=lazy ниже первого экрана,
           script подключён с defer.
  Чистота: НУЛЬ атрибутов style="..." (FAIL); мёртвые CSS-классы (WARN) —
           учитываются и классы из JS (classList + querySelector/closest).
  Контракт JS: все id из getElementById существуют в HTML (FAIL);
           data-атрибуты обработчиков (data-scroll/tab) не осиротели.
  Sanity:  doctype, html lang, meta charset, viewport (FAIL при отсутствии).
  CSS:     опасные `repeat(N, 1fr)` без minmax(0,1fr) (риск overflow на мобильных),
           наличие aspect-ratio для фото-контейнеров, prefers-reduced-motion.

Зависимости: только стандартная библиотека. Выход: PASS/WARN/FAIL, код выхода 1 при FAIL.
Запуск:  python .doc/scripts/check_vanilla.py [папка_vanilla] [--url https://site.ru/]
"""
import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.h1 = 0
        self.metas = []          # (name|property, content)
        self.links = []          # (rel, href)
        self.scripts = []        # dict(src, defer, type)
        self.jsonld = []
        self._in_ld = False
        self.imgs = []           # dict(src, alt, width, height, loading, style)
        self.local_refs = []     # (kind, url)
        self.anchors = set()
        self.inline_styles = []  # (tag, snippet) — запрет style= (02 §2.4)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "style" in a:
            self.inline_styles.append((tag, str(a.get("style", ""))[:60]))
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "meta":
            key = a.get("name") or a.get("property") or ""
            if key and a.get("content") is not None:
                self.metas.append((key.lower(), a.get("content", "")))
            if a.get("charset"):
                pass
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            href = a.get("href") or ""
            self.links.append((rel, href))
            if href and not _external(href):
                self.local_refs.append(("link:" + rel, href))
        elif tag == "script":
            if a.get("type") == "application/ld+json":
                self._in_ld = True
            else:
                self.scripts.append(a)
                src = a.get("src") or ""
                if src and not _external(src):
                    self.local_refs.append(("script", src))
        elif tag == "img":
            self.imgs.append(a)
            src = a.get("src") or ""
            if src and not _external(src):
                self.local_refs.append(("img", src))
        elif tag == "a":
            href = a.get("href") or ""
            if href == "#":
                self.local_refs.append(("a-placeholder", href))
            elif href.startswith("#"):
                self.anchors.add(href[1:])
            elif href and not _external(href):
                self.local_refs.append(("a", href))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title or self._in_ld:
            if self._in_title:
                self.title += data
        # jsonld копим отдельно:
        if self._in_ld:
            self.jsonld.append(data)


def _external(url):
    u = url.strip().lower()
    return (u.startswith(("http://", "https://", "//", "mailto:", "tel:", "data:", "#"))
            or u == "")


def main():
    ap = argparse.ArgumentParser(description="Валидация vanilla-сайта")
    ap.add_argument("folder", nargs="?", default="vanilla", help="папка сайта (по умолчанию ./vanilla)")
    ap.add_argument("--url", default="", help="канонический URL для напоминаний (https://site.ru/)")
    args = ap.parse_args()
    folder = os.path.abspath(args.folder)
    idx = os.path.join(folder, "index.html")

    fails, warns, oks = [], [], []

    def fail(msg):
        fails.append(msg)

    def warn(msg):
        warns.append(msg)

    def ok(msg):
        oks.append(msg)

    if not os.path.isfile(idx):
        print(f"FAIL: не найден {idx}")
        sys.exit(1)

    with open(idx, "r", encoding="utf-8") as f:
        html = f.read()
    d = Doc()
    d.feed(html)

    # ── Sanity базового HTML-документа ──
    low = html[:600].lower()
    if low.startswith("<!doctype html"):
        ok("doctype присутствует")
    else:
        fail("нет <!doctype html> в начале документа")
    if re.search(r"<html\s+lang=", html):
        ok("html lang указан")
    else:
        fail("нет lang у <html> — скринридеры и поиск не поймут язык")
    if "charset" in low:
        ok("meta charset есть")
    else:
        fail("нет meta charset (кириллица побьётся)")
    if "viewport" in low:
        ok("meta viewport есть")
    else:
        fail("нет meta viewport — мобильные отрисуют 980px")

    # ── SEO ──
    t = d.title.strip()
    if not t:
        fail("нет <title>")
    else:
        ok(f"title: «{t}» ({len(t)} симв.)")
        if len(t) < 30 or len(t) > 65:
            warn(f"title вне диапазона 30–65 символов ({len(t)})")
    desc = next((c for k, c in d.metas if k == "description"), "")
    if not desc:
        fail("нет meta description")
    else:
        ok(f"description: {len(desc)} симв.")
        if len(desc) < 120 or len(desc) > 170:
            warn(f"description вне диапазона ~120–170 символов ({len(desc)})")
    if d.h1 == 1:
        ok("ровно один h1")
    else:
        fail(f"h1 встречается {d.h1} раз (должен быть 1)")
    robots = next((c for k, c in d.metas if k == "robots"), "")
    if "noindex" in robots.lower():
        fail("meta robots содержит noindex — сайт не попадёт в поиск!")
    if any(k == "canonical" for k, _ in d.links):
        ok("canonical присутствует")
    else:
        warn("нет <link rel=canonical>" + (" (укажи " + args.url + ")" if args.url else ""))
    need = ["og:title", "og:description", "og:image", "og:url", "twitter:card"]
    have = {k for k, _ in d.metas}
    miss = [n for n in need if n not in have]
    if miss:
        warn("не хватает meta: " + ", ".join(miss))
    else:
        ok("OG/Twitter-разметка полная")
    ld_raw = "".join(d.jsonld).strip()
    if ld_raw:
        try:
            json.loads(ld_raw)
            ok("JSON-LD валиден")
        except ValueError as e:
            fail(f"JSON-LD битый: {e}")
    else:
        warn("нет JSON-LD (schema.org)")
    if not args.url:
        warn("укажи --url https://… — canonical/OG/sitemap должны быть абсолютными")

    # ── файлы ──
    missing = []
    for kind, ref in d.local_refs:
        if kind == "a-placeholder":
            continue
        p = os.path.normpath(os.path.join(folder, ref))
        if not os.path.isfile(p):
            missing.append(f"{kind} → {ref}")
    if missing:
        hard = [m for m in missing if not m.endswith(".pdf")]
        if hard:
            fail("битые локальные ссылки: " + "; ".join(sorted(set(hard))))
        for m in missing:
            if m.endswith(".pdf"):
                warn(f"PDF не найден: {m} — положить реальный файл или убрать ссылку")
    else:
        ok(f"все локальные ссылки существуют ({len(d.local_refs)} шт.)")
    fav = any(rel for rel, href in d.links if "icon" in rel)
    if fav:
        ok("фавиконы подключены")
    else:
        warn("не подключены фавиконы (05 §5.4, scripts/make_seo_pack.py)")
    for aid in sorted(d.anchors):
        if not re.search(r"id=[\"']" + re.escape(aid) + r"[\"']", html):
            fail(f"якорь #{aid} не имеет цели (id)")

    # ── a11y / производительность ──
    no_alt = [i.get("src", "?") for i in d.imgs if "alt" not in i]
    if no_alt:
        fail("img без alt: " + ", ".join(no_alt[:5]))
    else:
        ok(f"alt у всех img ({len(d.imgs)} шт.)")
    no_dims = [i.get("src", "?") for i in d.imgs if not i.get("width") or not i.get("height")]
    if no_dims:
        warn("img без width/height (риск CLS): " + ", ".join(no_dims[:5]))
    # портреты и фон карточек грузятся сразу (иначе карточка «прыгает» при
    # подгрузке lazy), поэтому этот класс картинок из проверки исключён
    eager_ok = ("card-bg", "photo-main", "staff-photo-main", "hero-logo", "brand-logo")
    no_lazy = [i.get("src", "?") for n, i in enumerate(d.imgs)
               if n >= 2 and not i.get("loading") and not i.get("fetchpriority")
               and not any(c in (i.get("class") or "") for c in eager_ok)]
    if no_lazy:
        warn("img ниже первого экрана без loading=lazy: " + ", ".join(no_lazy[:5]))
    placeholder_links = [ref for kind, ref in d.local_refs if kind == "a-placeholder"]
    if placeholder_links:
        warn(f"ссылки-заглушки href=\"#\" ({len(placeholder_links)} шт.) — заменить на реальные URL")
    app_js = [s for s in d.scripts if (s.get("src") or "").endswith(".js")]
    if app_js and all("defer" in s or "async" in s for s in app_js):
        ok("js подключён с defer/async")
    elif app_js:
        warn("js без defer — блокирует разбор")

    # ── чистота: запрет инлайн-стилей + мёртвые классы ──
    if d.inline_styles:
        fail(f"найдено {len(d.inline_styles)} атрибутов style=… — вынести в классы style.css (02 §2.4): "
             + "; ".join(f"<{t}> {s}" for t, s in d.inline_styles[:3]))
    else:
        ok("инлайн-стилей нет — весь дизайн через классы")

    # ── CSS-грабли ──
    css_path = os.path.join(folder, "css", "style.css")
    if os.path.isfile(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        bad_grid = re.findall(r"repeat\(\s*\d+\s*,\s*1fr\s*\)", css)
        if bad_grid:
            fail("CSS: найдено " + ", ".join(bad_grid[:3]) + " — заменить на minmax(0,1fr) (03 §3.3)")
        else:
            ok("CSS: опасных repeat(N,1fr) нет")
        if "aspect-ratio" in css:
            ok("CSS: aspect-ratio используется (03 §3.4)")
        else:
            warn("CSS: нет aspect-ratio — проверить контейнеры фото на «макушки»")
        if "prefers-reduced-motion" in css:
            ok("CSS: prefers-reduced-motion учтён")
        else:
            warn("CSS: нет prefers-reduced-motion (05 §5.7)")
        # Мёртвые классы: определены в CSS, но не встречаются ни в HTML, ни в JS.
        # JS тоже использует классы: classList.add/remove/toggle('x') и
        # селекторы querySelector/closest('.a .b') — всё это «использование».
        used = set(re.findall(r'class="([^"]+)"', html))
        with open(os.path.join(folder, "js", "app.js"), "r", encoding="utf-8") as jf:
            js_text = jf.read()
        for pat in (r"classList\.(?:add|remove|toggle)\('([^']+)'",
                    r'classList\.(?:add|remove|toggle)\("([^"]+)"',
                    r"querySelector(?:All)?\('([^']+)'",
                    r'querySelector(?:All)?\("([^"]+)"',
                    r"closest\('([^']+)'",
                    r'closest\("([^"]+)"'):
            for sel in re.findall(pat, js_text):
                used.update(re.findall(r"[\w-]+", sel))
        used_atoms = set()
        for cl in used:
            used_atoms.update(cl.split())
        defined = set()
        css_nocomments = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for m in re.finditer(r"(?:^|[{}])\s*([^{}@]+?)\s*\{", css_nocomments):
            for sel in m.group(1).split(","):
                defined.update(re.findall(r"\.([A-Za-z][\w-]*)", sel))
        dead = sorted(defined - used_atoms - {"com", "googleapis"})
        if dead:
            warn("мёртвые CSS-классы (удалить или обосновать в CSS): " + ", ".join(dead[:8]))
        else:
            ok("мёртвых CSS-классов нет (HTML+JS учтены)")

        # ── Контракт JS ↔ HTML: id из getElementById обязаны существовать ──
        js_ids = set(re.findall(r"getElementById\([\"']([^\"']+)[\"']\)", js_text))
        html_ids = set(re.findall(r'id="([^"]+)"', html))
        lost = sorted(js_ids - html_ids)
        if lost:
            fail("JS ссылается на несуществующие id: " + ", ".join(lost) + " — переименовали в шаблоне?")
        elif js_ids:
            ok(f"все {len(js_ids)} id из app.js существуют в HTML")
        # осиротевшие data-атрибуты: есть обработчик, нет элементов
        # (булевы атрибуты пишутся без "=", поэтому ищем вхождение целиком)
        for attr in ("data-scroll", "data-scrolltop", "data-tab"):
            if attr in js_text and not re.search(attr + r"[ =>]", html):
                fail(f"JS обрабатывает {attr}, но в HTML нет ни одного элемента с ним")
    else:
        warn("не найден css/style.css")

    # ── итог ──
    print(f"\n=== Проверка {folder} ===")
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
