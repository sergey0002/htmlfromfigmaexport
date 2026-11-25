#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOM-diff: геометрия и вычисленные стили листовых (текстовых) элементов
React-эталона против vanilla. Даёт точечный отчёт вида
«text-shift «Вратарь» x 521→677 (Δ+156)» — раскладку, а не антиалиасинг.

Почему листья: React и vanilla структурно разные (div-карточки вместо ссылок,
доп. обёртки, плейсхолдеры), поэтому сравнение деревьев даёт шум. Текст —
единственный якорь, который обязан совпасть 1:1.

Проверяется (для каждого текстового узла, найденного в обеих версиях):
  • x/y (Δ > 2px — FAIL), w/h (Δ > 2px — FAIL);
  • color / backgroundColor / borderRadius / fontWeight (любое отличие — FAIL);
  • доля «текстов, найденных в vanilla» (< 97% — FAIL);
  • количество карточек в секциях team/coaching/partners.

Запуск (эталон — dev-сервер React, см. preview-local.bat):
  python .doc/scripts/dom_diff.py --ref http://127.0.0.1:8084/
  python .doc/scripts/dom_diff.py --ref http://127.0.0.1:8084/ --viewports 1440,390 --json .doc/dom-diff.json
Код выхода 1 при любом FAIL (годно для CI).
"""
import argparse
import json
import os
import sys

from render_util import (BLOCKS, BLOCK_CARDS, VIEWPORTS, both_pages,
                         ensure_ref_url, folder_abspath, serve)
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SNAPSHOT_JS = r"""
(sel) => {
  const root = document.querySelector(sel);
  if (!root) return null;
  const norm = (s) => (s || '').replace(/[\s\u00a0\u202f\u200b]+/g, ' ').trim().slice(0, 60);
  const clsOf = (el) => (el.className && el.className.baseVal !== undefined
    ? el.className.baseVal : el.className) || '';
  const out = [];
  const walk = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const visible = r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
    if (visible) {
      const text = el.children.length === 0 ? norm(el.innerText || el.textContent) : '';
      out.push({
        key: el.tagName.toLowerCase() + '|' + text,
        tag: el.tagName.toLowerCase(),
        text,
        leaf: text !== '',
        cls: clsOf(el),
        x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY),
        w: Math.round(r.width), h: Math.round(r.height),
        props: {
          color: cs.color, backgroundColor: cs.backgroundColor,
          borderRadius: cs.borderTopLeftRadius, fontWeight: cs.fontWeight,
        },
      });
    }
    for (const c of el.children) walk(c);
  };
  walk(root);
  return out;
}
"""

TEXT_TOL = 2.0  # Δ геометрии текстового листа, px
STRICT_PROPS = ["color", "backgroundColor", "borderRadius", "fontWeight"]
COUNTS = {}  # текст → [cn, вхождений]: отладка дублей в vanilla


def rgba_noise(css):
    """rgba(0,0,0,0) и transparent — одно; rgb(255,255,255,0.55) → rgba-нормализация."""
    s = (css or "").replace(" ", "")
    if s in ("rgba(0,0,0,0)", "transparent"):
        return "transparent"
    if s.startswith("rgba(") and s.endswith(",1)"):
        return "rgb(" + s[5:-3] + ")"
    return s


def _match_leaves(ref_nodes, van_nodes):
    by_key = {}
    for n in van_nodes:
        if n["leaf"]:
            by_key.setdefault(n["key"], []).append(n)
    pairs, missing = [], []
    # 1) точные совпадения (тэг + текст), уникальные — однозначная пара;
    #    дубли (счёт «1», подписи в карточках) откладываем на шаг 2
    for r in ref_nodes:
        if r["leaf"] and len(by_key.get(r["key"], [])) == 1:
            pairs.append((r, by_key[r["key"]].pop()))
    # 2) остальное — по близости координат; тэг не важен: <span> и <b>
    #    в счётчиках выводят одну и ту же цифру
    extra = [n for b in by_key.values() for n in b]
    for r in ref_nodes:
        if not r["leaf"] or any(p[0] is r for p in pairs):
            continue
        cand = [v for v in extra if v["text"] == r["text"]]
        if not cand:
            missing.append(r)
            continue
        v = min(cand, key=lambda n: abs(n["x"] - r["x"]) + abs(n["y"] - r["y"]))
        extra.remove(v)
        pairs.append((r, v))
    return pairs, missing, extra


def compare_block(ref_nodes, van_nodes, limit=12):
    """Сопоставить текстовые листья и вернуть список расхождений."""
    if ref_nodes is None:
        return [{"kind": "missing-block", "detail": "блока нет в эталоне"}]
    if van_nodes is None:
        return [{"kind": "missing-block", "detail": "блока нет в vanilla"}]

    issues = []
    pairs, missing, extra = _match_leaves(ref_nodes, van_nodes)
    for r, v in pairs:
        dx, dy = v["x"] - r["x"], v["y"] - r["y"]
        dw, dh = v["w"] - r["w"], v["h"] - r["h"]
        if abs(dx) > TEXT_TOL or abs(dy) > TEXT_TOL:
            issues.append({"kind": "text-shift", "el": r["text"][:40], "cls": r["cls"][:60],
                           "detail": f"«{r['text'][:30]}» x {r['x']}→{v['x']} (Δ{dx:+}), "
                                     f"y {r['y']}→{v['y']} (Δ{dy:+})"})
        elif abs(dw) > TEXT_TOL or abs(dh) > TEXT_TOL:
            issues.append({"kind": "text-size", "el": r["text"][:40], "cls": r["cls"][:60],
                           "detail": f"«{r['text'][:30]}» w {r['w']}→{v['w']} (Δ{dw:+}), "
                                     f"h {r['h']}→{v['h']} (Δ{dh:+})"})
        for p in STRICT_PROPS:
            a, b = rgba_noise(r["props"].get(p)), rgba_noise(v["props"].get(p))
            if a != b:
                issues.append({"kind": "text-style", "prop": p, "el": r["text"][:40], "cls": r["cls"][:60],
                               "detail": f"«{r['text'][:30]}» {p}: {a} → {b}"})

    total = max(1, sum(1 for n in ref_nodes if n["leaf"]))
    if len(missing) > max(2, total * 0.03):
        issues.append({"kind": "text-missing", "el": "(нет в vanilla)", "cls": "",
                       "detail": f"{len(missing)}/{total} текстов не найдено: "
                                 + ", ".join(f"«{m['text'][:20]}»" for m in missing[:5])})
    if len(extra) > max(2, total * 0.03):
        issues.append({"kind": "text-extra", "el": "(лишние в vanilla)", "cls": "",
                       "detail": f"{len(extra)} лишних текстов: "
                                 + ", ".join(f"«{e['text'][:20]}»" for e in extra[:5])})
    return issues[:limit]


def report_extra_counts(clear=True):
    """Отладка: какие тексты в vanilla встречаются больше раз, чем в эталоне."""
    rows = [(t, c, n) for t, (c, n) in COUNTS.items() if n > 1]
    if clear:
        COUNTS.clear()
    return sorted(rows, key=lambda r: -r[2])[:10]


def main():
    ap = argparse.ArgumentParser(description="DOM-diff: React-эталон vs vanilla")
    ap.add_argument("--ref", default="http://127.0.0.1:8084/", help="URL React-эталона")
    ap.add_argument("--vanilla", default="vanilla", help="папка vanilla-сайта")
    ap.add_argument("--viewports", default="1440,390", help="ширины через запятую")
    ap.add_argument("--json", default="", help="куда сохранить полный отчёт (json)")
    ap.add_argument("--max-issues", type=int, default=40, help="сколько строк печатать")
    args = ap.parse_args()

    ref_url = ensure_ref_url(args.ref)
    folder = folder_abspath(args.vanilla)
    if not os.path.isdir(folder):
        print(f"FAIL: нет папки {folder}")
        sys.exit(1)

    wanted = [int(x) for x in args.viewports.split(",") if x.strip()]
    vps = [vp for vp in VIEWPORTS if vp[0] in wanted] or [(1440, 900)]

    httpd = serve(folder)
    van_url = f"http://127.0.0.1:{httpd.port}/"
    report = {"ref": ref_url, "vanilla": van_url, "viewports": {}}
    fails, warns, oks = [], [], []

    def fail(m):
        fails.append(m)

    def warn(m):
        warns.append(m)

    def ok(m):
        oks.append(m)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for w, h in vps:
                tag = f"{w}x{h}"
                (ref_ctx, ref), (van_ctx, van) = both_pages(browser, ref_url, van_url, w, h)
                vp_issues = {}
                try:
                    for name, sel_ref, sel_van in BLOCKS:
                        ref_nodes = ref.evaluate(SNAPSHOT_JS, sel_ref)
                        van_nodes = van.evaluate(SNAPSHOT_JS, sel_van)
                        issues = compare_block(ref_nodes, van_nodes)
                        for n in van_nodes or []:
                            if n["leaf"]:
                                COUNTS.setdefault(n["text"], [n["cls"][:60], 0])
                                COUNTS[n["text"]][1] += 1
                        vp_issues[name] = issues
                        n_leaf_ref = sum(1 for n in (ref_nodes or []) if n["leaf"])
                        if not issues:
                            ok(f"[{tag}] {name}: {n_leaf_ref} текстов — позиции и стили совпадают")
                        else:
                            first = issues[0]
                            fail(f"[{tag}] {name}: {len(issues)} расхождени(й), напр. "
                                 f"{first['kind']} «{first.get('el', '')}» — {first['detail']}")
                        if name in BLOCK_CARDS:
                            sel_c_ref, sel_c_van = BLOCK_CARDS[name]
                            rc = ref.locator(sel_c_ref).count()
                            vc = van.locator(sel_c_van).count()
                            if rc != vc:
                                fail(f"[{tag}] {name}: карточек {vc}, в эталоне {rc}")
                            else:
                                ok(f"[{tag}] {name}: карточек {rc} — как в эталоне")
                    sh_r = ref.evaluate("document.documentElement.scrollHeight")
                    sh_v = van.evaluate("document.documentElement.scrollHeight")
                    if abs(sh_r - sh_v) > 40:
                        warn(f"[{tag}] высота страницы {sh_v} vs эталон {sh_r} (Δ{sh_v - sh_r:+}px)")
                    else:
                        ok(f"[{tag}] высота страницы ≈ эталон (Δ{sh_v - sh_r:+}px)")
                    report["viewports"][tag] = vp_issues
                finally:
                    ref_ctx.close()
                    van_ctx.close()
        finally:
            browser.close()
    httpd.shutdown()

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)

    print(f"\n=== DOM-diff {ref_url} vs {van_url} ===")
    for m in oks:
        print(f"  PASS  {m}")
    for m in warns:
        print(f"  WARN  {m}")
    for m in fails[: args.max_issues]:
        print(f"  FAIL  {m}")
    if len(fails) > args.max_issues:
        print(f"  ... ещё {len(fails) - args.max_issues} FAIL (полный отчёт в --json)")
    print(f"\nИтог: {len(oks)} ok / {len(warns)} warn / {len(fails)} fail")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
