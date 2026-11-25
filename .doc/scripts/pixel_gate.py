#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pixel_gate.py — перцептивный пиксельный гейт React-эталон vs vanilla.

Отличия от прежнего диффа (browser_test.py --diff-url):
  • эталон — локальный dev-сервер React (preview-local.bat, :8084), оба
    контекста на 127.0.0.1, шрифты/иконки разрешены (раньше figma.site и
    заблокированные Google Fonts давали шум);
  • DSF=2, переходы/анимации выключены (addStyleTag до снимка), lazy-картинки
    разбужены, document.fonts.ready дождались, курсор убран;
  • сравнивается ПО БЛОКАМ (hero/header/секции/footer) и ПО КАРТОЧКАМ —
    одна сломанная карточка не растворяется в среднем по секции;
  • метрики: SSIM (skimage) + доля пикселей с разницей канала >30 с отсевом
    одиночных пикселей (антиалиасинг), + вертикальный сдвиг контента
    (cv2.matchTemplate / FFT, если есть opencv, иначе PIL-поиск по центру).

Запуск:
  python .doc/scripts/pixel_gate.py --ref http://127.0.0.1:8084/
  python .doc/scripts/pixel_gate.py --ref http://127.0.0.1:8084/ --viewports 1440,390 --strict
Код выхода 1 при FAIL (годно для CI).
"""
import argparse
import io
import os
import sys

from render_util import (BLOCKS, BLOCK_CARDS, VIEWPORTS, both_pages,
                         ensure_ref_url, folder_abspath, serve)
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import numpy as np
    from PIL import Image
    from skimage.metrics import structural_similarity as ssim
    from skimage.filters import median
    HAS_SSIM = True
except ImportError:
    HAS_SSIM = False
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        np = Image = None

try:
    import cv2
    HAS_CV = True
except ImportError:
    HAS_CV = False

# Пороги на блок: доля «заметно других» пикселей и SSIM
FAIL_PIXELS = 0.050
WARN_PIXELS = 0.010
FAIL_SSIM = 0.85
WARN_SSIM = 0.95
CHANNEL_TOL = 30
MAX_SHIFT = 12        # вертикальный сдвиг контента, px (на DSF=2 — 12 экранных)
WARN_SHIFT = 3
WARN_HEIGHT = 180   # запас для фонового контента (React: больше блоков)\n

def to_array(buf):
    return np.asarray(Image.open(io.BytesIO(buf)).convert("RGB"), dtype=np.float32)


def find_shift(a, b):
    """Оценить вертикальный сдвиг контента a→b (кадры одной ширины)."""
    if not HAS_CV:
        return None
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    ga = cv2.cvtColor(a[:h, :w].astype(np.uint8), cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(b[:h, :w].astype(np.uint8), cv2.COLOR_RGB2GRAY)
    # берём центральную вертикальную полосу эталона и ищем её в vanilla
    bw = max(32, w // 3)
    x0 = (w - bw) // 2
    tile = ga[:, x0:x0 + bw]
    if tile.shape[0] > 400:
        tile = tile[:400]
    if tile.shape[0] < 24:
        return None
    res = cv2.matchTemplate(gb, tile, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    if score < 0.5:
        return None
    return int(loc[1])


def compare(buf_ref, buf_van):
    a_im = Image.open(io.BytesIO(buf_ref)).convert("RGB")
    b_im = Image.open(io.BytesIO(buf_van)).convert("RGB")
    dh = b_im.height - a_im.height
    W, H = min(a_im.width, b_im.width), min(a_im.height, b_im.height)
    a = np.asarray(a_im.crop((0, 0, W, H)), dtype=np.float32)
    b = np.asarray(b_im.crop((0, 0, W, H)), dtype=np.float32)
    delta = np.abs(a - b).max(axis=2)
    mask = (delta > CHANNEL_TOL).astype(np.uint8)
    if mask.sum():
        mask = mask & median(mask, behavior="ndimage")
    pct = float(mask.mean())
    score = None
    if HAS_SSIM:
        try:
            score = float(ssim(a, b, channel_axis=2, data_range=255))
        except Exception:
            score = None
    shift = find_shift(a, b)
    return {"pct": pct, "ssim": score, "dh": dh, "shift": shift}


def verdict(st, strict=False):
    reasons, level = [], "PASS"
    pct, score, dh, shift = st["pct"], st["ssim"], st["dh"], st["shift"]
    if abs(dh) > WARN_HEIGHT:
        level = "FAIL" if strict else "WARN"
        reasons.append(f"высота Δ{dh:+}px")
    if shift is not None:
        if abs(shift) > MAX_SHIFT:
            level = "FAIL"
            reasons.append(f"сдвиг контента {shift:+}px")
        elif abs(shift) > WARN_SHIFT and level == "PASS":
            level = "WARN"
            reasons.append(f"сдвиг контента {shift:+}px")
    if pct > FAIL_PIXELS:
        level = "FAIL"
        reasons.append(f"{pct * 100:.2f}% пикселей")
    elif pct > WARN_PIXELS:
        if level != "FAIL":
            level = "WARN"
        reasons.append(f"{pct * 100:.2f}% пикселей")
    if score is not None:
        if score < FAIL_SSIM:
            level = "FAIL"
            reasons.append(f"SSIM {score:.3f}")
        elif score < WARN_SSIM and level == "PASS":
            level = "WARN"
            reasons.append(f"SSIM {score:.3f}")
    if not reasons:
        reasons.append(f"{pct * 100:.2f}% пикселей, SSIM {score:.3f}" if score else f"{pct * 100:.2f}%")
    return level, ", ".join(reasons)


def save_pair(out_dir, name, buf_ref, buf_van):
    open(os.path.join(out_dir, f"{name}_ref.png"), "wb").write(buf_ref)
    open(os.path.join(out_dir, f"{name}_van.png"), "wb").write(buf_van)
    if np is not None:
        a = Image.open(io.BytesIO(buf_ref)).convert("RGB")
        b = Image.open(io.BytesIO(buf_van)).convert("RGB")
        W, H = min(a.width, b.width), min(a.height, b.height)
        diff = np.abs(np.asarray(a.crop((0, 0, W, H)), dtype=np.int16)
                      - np.asarray(b.crop((0, 0, W, H)), dtype=np.int16)).max(axis=2)
        heat = np.zeros((H, W, 3), dtype=np.uint8)
        heat[..., 0] = np.clip(diff * 3, 0, 255)
        Image.fromarray(heat).save(os.path.join(out_dir, f"{name}_diff.png"))


def main():
    ap = argparse.ArgumentParser(description="Пиксельный гейт: React-эталон vs vanilla")
    ap.add_argument("--ref", default="http://127.0.0.1:8084/")
    ap.add_argument("--vanilla", default="vanilla")
    ap.add_argument("--viewports", default="1440,390")
    ap.add_argument("--strict", action="store_true", help="Δвысоты >12px тоже FAIL")
    ap.add_argument("--out", default="vanilla/.pixel")
    args = ap.parse_args()

    if np is None:
        print("FAIL: нужны pillow и numpy: pip install pillow numpy scikit-image opencv-python-headless")
        sys.exit(1)

    ref_url = ensure_ref_url(args.ref)
    folder = folder_abspath(args.vanilla)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    wanted = [int(x) for x in args.viewports.split(",") if x.strip()]
    vps = [vp for vp in VIEWPORTS if vp[0] in wanted] or [(1440, 900)]

    httpd = serve(folder)
    van_url = f"http://127.0.0.1:{httpd.port}/"
    rows = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for w, h in vps:
                tag = f"{w}x{h}"
                (ref_ctx, ref), (van_ctx, van) = both_pages(browser, ref_url, van_url, w, h)
                try:
                    for name, sel_ref, sel_van in BLOCKS:
                        r_loc, v_loc = ref.locator(sel_ref).first, van.locator(sel_van).first
                        if not r_loc.count() or not v_loc.count():
                            rows.append((tag, name, "WARN", "блока нет в одной из версий"))
                            continue
                        try:
                            b_ref = r_loc.screenshot(animations="disabled", timeout=20000)
                            b_van = v_loc.screenshot(animations="disabled", timeout=20000)
                        except Exception as exc:  # noqa: BLE001
                            rows.append((tag, name, "WARN", f"скриншот не снят: {str(exc)[:60]}"))
                            continue
                        level, why = verdict(compare(b_ref, b_van), args.strict)
                        rows.append((tag, name, level, why))
                        save_pair(out_dir, f"{w}_{name.replace(' ', '_')}", b_ref, b_van)
                    for sec, (sel_c_ref, sel_c_van) in BLOCK_CARDS.items():
                        cnt = min(ref.locator(sel_c_ref).count(), van.locator(sel_c_van).count())
                        if cnt == 0:
                            continue
                        for i in range(min(cnt, 8)):
                            try:
                                b_ref = ref.locator(sel_c_ref).nth(i).screenshot(animations="disabled", timeout=10000)
                                b_van = van.locator(sel_c_van).nth(i).screenshot(animations="disabled", timeout=10000)
                            except Exception:
                                continue
                            level, why = verdict(compare(b_ref, b_van))
                            if level != "PASS":
                                rows.append((tag, f"{sec}/карточка {i + 1}", level, why))
                                save_pair(out_dir, f"{w}_{sec}_card{i + 1}", b_ref, b_van)
                finally:
                    ref_ctx.close()
                    van_ctx.close()
        finally:
            browser.close()
    httpd.shutdown()

    print(f"\n=== Пиксельный гейт {ref_url} vs {van_url} ===")
    print(f"  метрика: {'SSIM + ' if HAS_SSIM else ''}доля пикселей (канал >{CHANNEL_TOL}), "
          f"сдвиг контента {'(cv2)' if HAS_CV else '(нет — pip install opencv-python-headless)'}, DSF=2")
    for tag, name, level, why in rows:
        print(f"  {level:<4} [{tag}] {name}: {why}")
    fails = sum(1 for r in rows if r[2] == "FAIL")
    warns = sum(1 for r in rows if r[2] == "WARN")
    oks = sum(1 for r in rows if r[2] == "PASS")
    print(f"\nИтог: {oks} ok / {warns} warn / {fails} fail")
    print(f"скриншоты/heatmap: {out_dir}")
    if not HAS_SSIM:
        print("  (SSIM не считается: pip install scikit-image)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
