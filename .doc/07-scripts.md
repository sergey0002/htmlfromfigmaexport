# 07 — Скрипты автоматизации (Python 3.14)

Все скрипты лежат в `.doc/scripts/`, запускаются из корня проекта:

```powershell
python .doc/scripts/analyze_figma_export.py .          # 1: разбор нового исходника
python .doc/scripts/make_seo_pack.py --url https://site.ru/ --name "Название"   # 2: SEO-пакет
python .doc/scripts/check_vanilla.py vanilla --url https://site.ru/              # 3: приёмка (код/файлы)
python .doc/scripts/browser_test.py vanilla                                     # 4: приёмка (браузер)
python .doc/scripts/dom_diff.py --ref http://127.0.0.1:8084/                    # 5: геометрия/стили vs React
python .doc/scripts/pixel_gate.py --ref http://127.0.0.1:8084/                   # 6: пиксельный гейт vs React
```

Эталон для 5–6 — **живой React-исходник** из `preview-local.bat`
(`http://localhost:8084`, поднимается из `src/App.tsx`). Папку создавать не
нужно: скрипты сами поднимают локальный сервер для `vanilla`.

Зависимости: 1–3 — только стандартная библиотека (Pillow опционально);
4–6 — `pip install playwright pillow numpy scikit-image opencv-python-headless`
и `playwright install chromium`.

## 7.1. `analyze_figma_export.py` — анализ исходника (шаг 1)

**Что делает** (писать отчёт: stdout; `--write` → `.doc/report.md`):

- Определяет стек (React по `App.tsx`/`App.jsx`, Vue по `App.vue`) и точку входа.
- Читает `.figma/make/site.json` (title/description/robots) и перечисляет
  figma-слоты — с предупреждением про noindex.
- **Размеры всех изображений** (PNG/JPEG/WebP/GIF — парсинг заголовков без Pillow)
  и группировка по пропорциям W/H → готовые значения для `aspect-ratio` (03 §3.4).
- **Массивы данных** корневого компонента: имя, число элементов, ключи первого
  элемента — чек-лист переноса в build.mjs (02 §2.3).
- Состояние (useState/ref), эффекты, IntersectionObserver, scroll-вызовы,
  обработчики событий — карта поведения для app.js (04).
- Импорты изображений, инлайн-цвета (кандидаты в CSS-классы по 02 §2.4),
  адаптивные Tailwind-классы (`md:grid-cols-3` и т.п.) — спецификация
  медиазапросов (03 §3.2).
- CSS-переменные и кастомные классы из `src/**/*.css` и `<style>` в `.vue`.

**Вывод** — готовый markdown-отчёт, с него начинать конвертацию нового проекта.

## 7.2. `make_seo_pack.py` — SEO-пакет (шаг 2)

**Аргументы**: `--dir` (по умолчанию `vanilla`), `--url` (обязательный),
`--name`, `--desc`, `--email`, `--logo` (файл логотипа), `--theme` (#hex).

**Создаёт** (только on-page, серверные файлы не трогаем):

- `favicon.svg`, `favicon-16/32.png`, `apple-touch-icon.png` (180) — мишень
  «золото на тёмном», рисуется чистым Python (zlib/PNG вручную);
  с `--logo` и Pillow — иконки из реального логотипа (квадрат с паддингом).
- `og-cover.png` 1200×630 — тёмный фон, золотая диагональ, мишень.
- `seo-head.html` — полный `<head>-блок` (title/description/canonical/robots/
  фавиконы/OG/Twitter/JSON-LD SportsTeam+WebSite) для вставки в шаблон build.mjs.

## 7.3. `check_vanilla.py` — валидатор приёмки (шаг 3)

**Аргументы**: папка сайта (по умолчанию `vanilla`), `--url`.

**Проверяет** (exit code 1 при любом FAIL — пригоден для CI):

- SEO: title 30–65 симв., description ~120–170, **ровно один h1**, canonical,
  `noindex` = FAIL, OG/Twitter-набор, JSON-LD парсится.
- Файлы: битые локальные href/src (PDF — WARN, а не FAIL: файл даёт заказчик);
  `href="#"` — WARN-список; якоря без `id` — FAIL.
- A11y/perf: `alt` у всех img (FAIL при отсутствии), `width/height` (WARN — CLS),
  `loading=lazy` ниже первого экрана (WARN), `defer` у js (WARN).
- Чистота: любой `style=` в HTML — FAIL (правило style=0, см. 02 §2.4).
- Контракт JS: id из `getElementById` и data-атрибуты обработчиков обязаны
  существовать в HTML; классы из `classList` и `querySelector` считаются
  используемыми (04 §4.5).
- Sanity: doctype, `lang`, charset, viewport — FAIL при отсутствии.
- CSS-грабли: `repeat(N,1fr)` без minmax — FAIL (03 §3.3); отсутствие
  `aspect-ratio` и `prefers-reduced-motion` — WARN.
- Мёртвые CSS-классы (определены, но не используются в HTML/JS) — WARN
  с именами: удаляй или обосновывай комментарием в CSS.

Формат: `PASS/WARN/FAIL` + итог; 0 FAIL — сайт готов к отдаче.

## 7.4. `browser_test.py` — браузерные тесты (шаг 4)

**Аргументы**: папка сайта (по умолчанию `vanilla`), `--port`,
`--diff-url` (React-оригинал для пиксельного диффа), `--diff-strict`.

Сам поднимает локальный http-сервер, открывает Chromium и на вьюпортах
**390×844 / 768×1024 / 1024×800 / 1440×900** проверяет:

- отсутствие горизонтального скролла документа;
- число колонок ключевых сеток (карта значений `EXPECT_COLS` — правь под свой
  проект по 03 §3.2);
- вылет видимых элементов за вьюпорт (кроме намеренного `.table-scroll`);
- загрузку всех локальных изображений — со скроллом до низа, чтобы сработал
  `loading="lazy"`; внешние (Google Fonts, Unsplash) блокируются роутингом и
  ошибкой не считаются;
- высоту фото первой карточки игрока на 390px (≥120px — контроль «макушек», 03 §3.4);
- типографику (03 §3.7): h1 ≥ 32px, минимальный шрифт ≥ 12px;
- базовый контраст (цвет h1 ≠ фон body);
- интерактив: бургер (`aria-expanded`), Escape, закрытие меню по пункту,
  scroll-margin якоря, табы, hover строки, подсветка активного раздела
  через IntersectionObserver;
- JS-исключения на странице (pageerror);
- с `--diff-url`: грубый пиксельный дифф секций (WARN >3%, FAIL с `--diff-strict`).

Выход: `PASS/WARN/FAIL` + итог, код выхода 1 при FAIL. Для точной сверки
с React используй `dom_diff.py` и `pixel_gate.py` (7.7–7.8): они не блокируют
шрифты, ставят DSF=2 и считают метрики по блокам и карточкам.

## 7.5. `render_util.py` — общее ядро DOM/pixel-проверок

Не запускается напрямую, импортируется `dom_diff.py` и `pixel_gate.py`:

- `serve(folder)` — локальный http-сервер на свободном порту (127.0.0.1);
- `both_pages(...)` — открывает эталон и vanilla в одном Chromium с одинаковыми
  viewport/DSF=2 и **одинаковыми разрешёнными шрифтами** (Google Fonts не
  блокируются — иначе Oswald подменяется системным и дифф шумит);
- `settle(page)` — ждёт `load` → `networkidle` → `document.fonts.ready`,
  прогоняет страницу до низа (lazy-картинки), ждёт `decode()`, выключает
  анимации/переходы через `add_style_tag` и возвращает скролл наверх. Каждый
  шаг в try/except: HMR-перезагрузка не роняет гейт;
- `BLOCKS` — карта «секция → селектор эталона → селектор vanilla»;
  `BLOCK_CARDS` — «секция → селектор карточек», чтобы ловить сломанную одну
  карточку, а не среднее по секции;
- `ensure_ref_url` — `localhost` → `127.0.0.1` (у playwright блокируется
  роутинг на localhost).

## 7.6. `dom_diff.py` — геометрия и стили vs React (шаг 5)

```powershell
python .doc/scripts/dom_diff.py --ref http://127.0.0.1:8084/
python .doc/scripts/dom_diff.py --ref http://127.0.0.1:8084/ --viewports 1440,390 --json .doc/dom-diff.json
```

Что сравнивает (`SNAPSHOT_JS` снимает видимое дерево блока):

- **текстовые листья** — узлы без детей, с текстом. Это единственный надёжный
  якорь: React и vanilla структурно разные (div-карточки вместо ссылок, другие
  обёртки), а текст обязан совпасть 1:1;
- сопоставление: сначала точное `(тег, текст)` с уникальным ключом, затем
  дубли (счёт «1», подписи в карточках, `<span>` vs `<b>`) — по ближайшим
  координатам, поэтому число не «уезжает» в чужую карточку;
- `x/y` (Δ>2px — FAIL, x — только при равной ширине узла), `w/h` (Δ>2px),
  `color/backgroundColor/borderRadius/fontWeight` (любое отличие);
- доля найденных текстов (<97% — FAIL) и лишние тексты;
- количество карточек в `team`/`coaching`/`partners`.

`--json` пишет полный отчёт по блокам. Код выхода 1 при FAIL (для CI).

## 7.7. `pixel_gate.py` — пиксельный гейт vs React (шаг 6)

```powershell
python .doc/scripts/pixel_gate.py --ref http://127.0.0.1:8084/
python .doc/scripts/pixel_gate.py --ref http://127.0.0.1:8084/ --viewports 1440,390 --strict
```

Как считается:

- скриншоты **каждого блока** и **каждой карточки** первых 8 штук, DSF=2,
  анимации выключены (`animations="disabled"`);
- `SSIM` (skimage) + доля пикселей с разницей канала >30 с медианным отсевом
  одиночных пикселей (антиалиасинг), + **вертикальный сдвиг контента**
  (`cv2.matchTemplate` по центральной полосе);
- пороги: SSIM <0.90 / пиксели >1% / сдвиг >12px — FAIL; 0.96 / 0.2% / 3px — WARN;
  Δвысоты >12px — WARN (FAIL с `--strict`);
- в `vanilla/.pixel/` складываются `*_ref.png`, `*_van.png` и `*_diff.png`
  (heatmap) — удобно открыть и глазами увидеть, что именно сломалось.

Почему это точнее прежнего `--diff-url`: эталон локальный, шрифты в обоих
контекстах загружены, снимок по блоку (а не по секции целиком), есть сдвиг
контента и перцептивная метрика.

## 7.8. Конвейер конвертации нового исходника (полный путь)

```text
1. python .doc/scripts/analyze_figma_export.py <корень> --write
   → .doc/report.md: стек, данные, размеры фото, Tailwind-адаптив, цвета, шрифты.
2. vanilla/: скопировать css/js/img по образцу 02/03/04 (report.md — источник).
3. Шаблон: cp .doc/templates/build.mjs → build.mjs в корень проекта, подставить
   данные из report.md, head-блок из make_seo_pack.py; node build.mjs.
4. python .doc/scripts/make_seo_pack.py --url … --name … [--logo …]
5. node build.mjs → index.html.
6. preview-local.bat → React-эталон на http://localhost:8084 (не закрывать).
7. python .doc/scripts/dom_diff.py  --ref http://127.0.0.1:8084/ --viewports 1440,390
   → точечный список «что не совпало» (x/y, размеры, цвета, шрифты).
8. python .doc/scripts/pixel_gate.py --ref http://127.0.0.1:8084/ --viewports 1440,390
   → SSIM/пиксели/сдвиг по блокам и карточкам, heatmap в vanilla/.pixel/.
9. python .doc/scripts/check_vanilla.py vanilla --url … → 0 FAIL.
10. python .doc/scripts/browser_test.py vanilla → 0 FAIL (скролл, контраст, JS).
11. Убрать из проекта всё служебное (build.mjs, seo-head.html, отчёты,
    vanilla/.pixel) — в поставке только готовый сайт (06 §6.1).
12. Картинки переносить исходными PNG из `src/imports` (не JPEG-remux):
    React отдаёт PNG с прозрачностью, а JPEG-версии дают другой crop/шум.
```

## 7.9. Ограничения

- Анализатор не исполняет JS: если данные появляются после запросов/API —
  искать их вручную в исходнике (fetch/axios) и занести в шаблон как константы.
- Vue с `<script setup>` и JSX-в-TSX покрываются regex-ами; экзотика
  (render-функции, styled-components вне CSS-файлов) — ручной разбор.
- Иконки-«мишень» — заглушка эстетики: для продакшена лучше `--logo` с Pillow
  или ручные иконки дизайнера.
- `dom_diff.py` сверяет только текстовые листья: чисто декоративные блоки
  (градиенты, фоновые картинки) ловит `pixel_gate.py`.
- `pixel_gate.py` чувствителен к `object-fit`/`object-position` фоновых
  картинок: если в CSS неверный crop, diff по карточкам подскочит мгновенно.
- `check_vanilla.py` не проверяет визуал (скриншоты) — только код и файлы.

## 7.10. Шрифты и «прыжки» при загрузке (FOUT/CLS)

Проблема: при подключении `fonts.googleapis.com` браузер сначала рисует
системный шрифт (Oswald → Arial/Times), затем перерисовывает — начертания
и отступы «прыгают». Что сделано в vanilla:

1. **Self-host.** Все woff2 (Oswald/Inter, подмножества latin/latin-ext/
   cyrillic/cyrillic-ext) лежат в `vanilla/fonts/`, CSS — `vanilla/css/fonts.css`
   (36 `@font-face`). Подключение — `<link rel="stylesheet" href="./css/fonts.css">`
   вместо Google; на страницах игроков путь `../css/fonts.css`. Скрипт
   генерации — тот же приём, что `make_seo_pack.py` (urllib + UA Chrome).
2. **Preload** трёх критичных начертаний: `oswald-700-cyrillic`,
   `oswald-600-cyrillic`, `inter-400-cyrillic` (`as="font"`, `crossorigin`).
3. **Fallback-метрики.** `@font-face { font-family: 'Oswald Fallback';
   src: local('Arial Narrow')…; size-adjust: 78.5% }` и `'Inter Fallback'`
   с `size-adjust: 104.3%` — системный шрифт до загрузки занимает ту же
   ширину, поэтому вёрстка не сдвигается. Стек: `--font-display:
   'Oswald', 'Oswald Fallback', sans-serif`.
4. **Инлайн FOUC-guard** в `<head>` до внешних CSS:
   `<style>html{background:#080808;font-family:'Oswald Fallback',…}</style>` —
   первый пиксель уже тёмный и с нужными пропорциями строк.
5. **Портреты и фон карточек без `loading="lazy"`** (`fetchpriority="high"`
   для `photo-main`): lazy-фото подгружалось после первой отрисовки, карточка
   сначала была низкой и «прыгала» вниз. `check_vanilla.py` для этих классов
   (`card-bg`, `photo-main`, `staff-photo-main`, `hero-logo`, `brand-logo`)
   lazy не требует.

Проверка стабильности: `playwright` с `Network.emulateNetworkConditions`
(slow 3G) — `.hero-title` не меняет `top/height` между кадрами
(до правок: top 881/height 37 → 515/115 после загрузки).
