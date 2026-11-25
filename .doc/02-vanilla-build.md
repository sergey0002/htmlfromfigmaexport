# 02 — Vanilla-сборка: структура и генератор

> **Исторический материал:** документ относится преимущественно к примеру ФБК «Таргет» и может не соответствовать текущему исходнику. Актуальное состояние и ограничения — в [обзоре проекта](project-review.md). Команды проверяйте перед запуском.

## 2.1. Структура результата

**В `vanilla/` — только готовый сайт, ничего лишнего** (генераторы и служебное
живут в `.doc/`, см. 00-overview):

```text
vanilla/                  ← ЧИСТАЯ ПОСТАВКА
  index.html             ← сгенерирован шаблоном (руками НЕ править)
  css/style.css           ← весь дизайн (03)
  js/app.js              ← всё поведение (04)
  img/*                   ← копии из src/imports (или src/assets для Vue)
  favicon.svg             ← + favicon-16/32.png, apple-touch-icon.png, og-cover.png
                            (генерирует make_seo_pack.py, см. 07)
```

Рабочая копия генератора — `build.mjs` (скопирован из `.doc/templates/build.mjs`)
в корень проекта или временную папку; после `node build.mjs` результат кладётся
в `vanilla/`, а генератор остаётся вне поставки.

Запрещено в поставке: `build.mjs`, `seo-head.html`, отчёты, `node_modules`,
Tailwind CDN, React/Vue-рантайм, инлайн `<style>`, `onclick` в HTML,
абсолютные пути `/assets/...`, `file://`-несовместимые конструкции,
выдуманные файлы (robots/sitemap/манифест/PDF — только если были в макете или
по явной просьбе заказчика).

## 2.2. Скелет генератора (шаблон: `.doc/templates/build.mjs`)

```js
// Генератор index.html. Запуск: node build.mjs (Node 18+, зависимостей нет)
// Рабочая копия шаблона .doc/templates/build.mjs — ВНЕ vanilla/
import { writeFileSync } from 'node:fs';

// ── 1. Данные 1:1 из исходника ─────────────────────────────
const players = [ { num: 88, name: '...', pos: 'Нападающий', g: 0, a: 0, gp: 0, img: 'lev-gerasimov.png' }, /* ... */ ];
const coaches = [ { name: '...', role: '...', email: '...' }, /* ... */ ];
const standings = [ { pos: 1, team: 'ФБК Таргет', gp: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0, isTarget: true }, /* ... */ ];
const matchResults = [ { round: 1, date: '', home: 'ФБК Таргет', homeScore: 0, awayScore: 0, away: 'Варягъ' } ];
const partners = [ { name: '...', cat: '...', color: '#C4952A' }, /* ... */ ];
const navItems = [ { id: 'team', label: 'Команда' }, /* ... */ ];

// ── 2. Эскейп ──────────────────────────────────────────────
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// ── 3. SEO-блок (полный шаблон — см. 05 §2, подставить значения) ──
const SITE = {
  url: 'https://example.ru/', title: '...', description: '...',
  locale: 'ru_RU', themeColor: '#080808', ogImage: './img/og-cover.jpg',
};

// ── 4. Шаблоны секций (по одному на сущность) ──────────────
const playerCards = players.map((p) => `...`).join('\n');
// ... staffCards, standingsRows, matrixHead/Rows, partnerCards, navLinks ...

// ── 5. Документ ────────────────────────────────────────────
const html = `<!doctype html>\n<html lang="ru">\n<head>...${...}...</head>\n<body>...${playerCards}...</body>\n</html>\n`;
writeFileSync(new URL('./index.html', import.meta.url), html, 'utf8');
console.log('vanilla/index.html generated, bytes:', Buffer.byteLength(html));
```

Правила шаблонов:

- Все тексты из данных — через `esc()`.
- Декоративные `<img>` — `alt=""`; контентные — осмысленный `alt` (имя игрока).
- Ниже-сгибные `<img>` — `loading="lazy"` (+ `decoding="async"`); hero/LCP — `fetchpriority="high"`.
- У каждого `<img>` — `width`/`height` (защита от CLS), см. `05 §6`.
- Табы: `role="tablist/tab/tabpanel"`, `aria-selected`, `aria-controls`, `hidden` у скрытой панели.
- Матрица результатов: `cellScore(rowTeam, colTeam)` ищет матч в обе стороны,
  диагональ пустая, «—» при отсутствии матча (см. эталон `build.mjs:113-143`).

## 2.3. Перенос данных: React → build.mjs / Vue → build.mjs

| Сущность | React-источник | Vue-источник | Поле в build.mjs |
|---|---|---|---|
| Игроки | `players` в `App.tsx` + `playerPortraits[num]` | `players` в `<script setup>` + импорты `@/assets` | `{num,name,pos,g,a,gp,img}` |
| Персонал | `coaches` | `coaches` / `staff` | `{name,role,email?,phone?,icon?}` |
| Таблица | `standings` (`isTarget`) | то же | `{pos,team,gp,w,d,l,gf,ga,pts,isTarget}` |
| Матчи | `matchResults` | `matches` / `results` | `{round,date,home,homeScore,awayScore,away}` |
| Партнёры | `partners` (`name/cat/color`) | то же | `{name,cat,color}` |
| Навигация | `navItems` (`id/label`) | `navLinks` / роуты | `{id,label}` |

Имена файлов в `img` привести к `kebab-case.png`, связать `img:` с реальным файлом,
проверить отсутствие битых ссылок скриптом:

```powershell
node -e "$h=Get-Content vanilla/index.html -Raw; $m=[regex]::Matches($h,'img/[\w.-]+') | ForEach-Object{$_.Value} | Sort-Object -Unique; $m | ForEach-Object{if(-not (Test-Path \"vanilla/$_\")){Write-Host \"MISSING $_\"}}"
```

## 2.4. Запрет инлайн-стилей (правило style=0)

В сгенерированном HTML **не должно быть ни одного атрибута `style="…"`** —
весь дизайн живёт только в `css/style.css` через классы. Причины:

1. **Специфичность**: инлайн перебивает любые CSS-правила (даже hover через
   `!important` — см. историю с подсветкой строк в 03 §3.5). Стили
   концентрируются в одном месте и правятся в одном месте.
2. **Кэш**: одинаковый `style.css` кэшируется браузером; инлайны грузятся
   с каждой страницей заново (здесь: 65 инлайнов ≈ 23 КБ, HTML похудел
   с 70 КБ до 47 КБ после выноса).
3. **Проверяемость**: `check_vanilla.py` ставит FAIL за любой найденный
   `style=` — правило автоматизировано, а не «на совести».

Как переносить React-инлайны (`style={{...}}` / Vue `:style`) в классы:

| React-инлайн | Решение в vanilla |
|---|---|
| Условный фон/рамка (`row.isTarget ? …`) | Блок `.is-target` (модификатор): `tr.is-target`, `td.mteam.is-target`, `td.mnum-cell.is-target`, `th.mnum.is-target` |
| Диагональные/золотые ячейки матрицы | `.mcell.is-same`, `.mcell.is-dim`, `.score` / `.score.is-hot`, `.dash` |
| Стат-колонки с золотой рамкой | `.mstat` + `.has-left`, `.is-gold-col` |
| Позиция/цвет команде | `.team-name` / `.team-name.is-target`, `.pos-cell` / `.pos-cell.is-top` |
| Бейдж вратаря | `.pos-badge` / `.pos-badge.is-gk` |
| Разовые отступы/типографика | Семантические классы (`.sec-head`, `.footer-head`, `.contact-label`) или утилиты `.u-*` |

Утилиты `.u-*` (в начале `style.css`, слой 3) — для повторяющихся односложных
свойств без семантики: `.u-fs-75`, `.u-fw-600/.u-fw-700`,
`.u-no-deco`, `.u-block`, `.u-shrink-0`, `.u-flex-col/.u-gap-2`,
`.u-team-logo/.u-photo-mini`. Утилита живёт, только пока используется
в HTML минимум дважды (одиночные случаи — в семантический класс);
мёртвые утилиты запрещены (WARN валидатора).

Алгоритм при новой конвертации: посчитать `style=` в шаблоне, каждый уникальный
инлайн превратить в класс/модификатор, добиться `style=0` и убедиться, что
`check_vanilla.py` подтверждает «инлайн-стилей нет».

Одинаковые элементы внутри одной секции не получают одинаковый класс на
каждый тег. Стиль вешается на родителя:

- `table.comp tbody td` — числовые ячейки без класса;
- `.partners-grid > div`, `.staff-grid > article`, `.contact-grid > div` —
  карточки без `class="card"` на каждой;
- `.pillar > div:first-child` и `.pillar p:first-child` — номер и заголовок
  принципа без классов `n`/`t`/`d`.

Класс остаётся только у элемента, который от общего вида отличается
(`is-target`, `is-main`, `is-gk`, `is-gold-col`). Пустой `class=""` не
писать: если модификатора нет, атрибут `class` опускается.

Дополнительную обёртку вокруг детей грида не создавать. Родитель уже есть —
сама сетка. Стиль вешается на неё: `.team-grid > article`,
`.desktop-nav button`, `.footer-nav-grid button`. Обёртка оправдана только
если без неё нельзя описать раскладку (фото поверх градиента, иконка рядом
с текстом). Класс, который JS ставит в рантайме (`.active`, `.open`),
остаётся в CSS-селекторе, но в статическом HTML его нет.

Шаблон HTML тоже оптимизируется: повторяющиеся SVG/разметка выносятся
в JS-функции генератора (как `cellScore` для счёта матчей), семантические
повторы (`<div class="sec-head">` + `gold-line`) — в единую строку шаблона,
а не копипастой. Правило: любой фрагмент, встречающийся 3+ раза, —
кандидат в функцию/класс.

Структура `style.css` — слои 1→10 с русскими комментариями (см. 03 §3.6):
токены → база → утилиты → типографика → каркас → блоки → таблицы →
прочие секции → адаптив → reduced-motion. Для любого макета блоки
меняются, слои и порядок — нет: результат предсказуем.

## 2.5. Эталонные размеры «ФБК Таргет» (ориентиры)

- `index.html` ≈ 614 строк / ~66 КБ; `style.css` ≈ 270 строк; `app.js` ≈ 87 строк.
- Карточек: 16 `.player-card`, 7 `.staff-card`, 6 `.partner-card`.
- Таблица: 10 строк; матрица: 10×10 + 6 стат-колонок (`matrixCols = 18`).
- `img/`: 17 файлов (16 PNG 800×701 + `target_avatar.jpg`).

### 2.x. Перенос изображений и таблиц «один в один»

- **Картинки** берём из `src/imports` исходными файлами (PNG с прозрачностью —
  тоже PNG). JPEG-remux меняет crop, шум и края портретов: `pixel_gate.py`
  сразу видит 15–30% расхождения в карточках.
- **Фоновый логотип карточки** — не `object-fit: cover` «на глаз», а кадр,
  посчитанный по React: ширина золотого щита в эталоне (449 CSS px) / ширина
  щита в файле (618 px) = scale 0.727; смещения — по левому краю и вершине.
  Файл-подложка `target-card-bg.jpg` кладётся с `object-fit: cover`.
- **Матрица результатов** строится ровно как в React: заголовки — класс
  `table-header` (0.75rem, letter-spacing 0.15em), ячейки — 1rem; ширины
  колонок `# 3rem`, `Команда min-w-14rem`, соперники `5rem`, статистика `4rem`;
  `min-width` таблицы = 1584px (как у React `sm:min-w-[1400px]` + контент).
  Строки 51px: `padding: 0.75rem` + `line-height` 1.5 у ячеек.
- **Активный пункт меню** появляется только после прокрутки к разделу
  (как у IntersectionObserver в React), на первом экране — ни одного
  `.nav-link.active`.
- **Шапка**: «ФБК»/«ТАРГЕТ» — `tracking-widest` только на «ТАРГЕТ»
  (tracking-widest: 0.28px у 14px / 0.36px у 18px), «ФБК» — 0.28px; сезон —
  `СЕЗОН` 0.65rem + `2026/27` text-sm/leading-5 шириной 51px.
- **Hero** (первый экран): `h1` clamp(5.5rem, 11.25vw, 8rem) / line-height 0.9,
  `.hero-inner` 120% ширины с `box-sizing: border-box` (как в React),
  кнопки `btn-primary`/`btn-outline` — 1rem/1.5 (213x50), вертикальная цепочка
  отступов `hero-sub -> лого -> h1 -> hero-desc -> hero-actions` снята
  по замеру `dom_diff.py`.
- **Скрипты проверки**: `check_vanilla.py` (код/файлы), `browser_test.py`
  (скролл/контраст/интерактив, горизонтальный скролл `table-scroll` и `.tabs` —
  штатный, не FAIL), `dom_diff.py` + `pixel_gate.py` (сверка с локальным
  React на :8084, см. 07 §7.6–7.7).

- **Шрифты self-host**: `vanilla/fonts/*.woff2` + `vanilla/css/fonts.css`
  (Oswald/Inter, latin/latin-ext/cyrillic), preload `oswald-700/600-cyrillic`
  и `inter-400-cyrillic`, fallback-семейства с `size-adjust` (78.5% / 104.3%)
  и инлайн-guard `html{background:#080808;font-family:'Oswald Fallback',…}` —
  без Google Fonts и без «прыжка» начертаний при загрузке (07 §7.10).
- **Фото карточек не lazy**: `photo-main` — `fetchpriority="high"`,
  `card-bg` — без `loading`, иначе карточка меняет высоту после загрузки.

### 2.y. Ховеры, скроллбар и таблица (правки после приёмки)

- **Общий эффект карточек.** Игрок и сотрудник штаба используют одну
  «поверхность» `.card`-семейства: фон `--bg-card-hover`, рамка
  `--gold-border`, зум фото 1.04 (`transition: transform .35s`) и золотой
  акцент `.card-accent` (scaleX 0→1, `transform-origin: left`).
  У штаба акцент больше не `is-visible` — только на `:hover/:focus-within`;
  фото штаба без `loading="lazy"` (как портреты игроков), чтобы карточки не
  прыгали. Поведение покрывает `.player-card` и `.staff-card` одинаковыми
  селекторами — один источник истины в CSS.
- **Курсор.** Все кликабельные — `cursor: pointer`: `a`, `.staff-contact`,
  `mailto:`, бренд, нав, бургер, вкладки, кнопки.
- **Скроллбар.** Вместо `scrollbar-width: none` — видимый в цветах сайта:
  `scrollbar-color: rgba(196,149,42,.55) #101010`, `::-webkit-scrollbar`
  12px, золотой ползунок с радиусом 6px; у `.table-scroll` — тонкий скролл
  с `padding-bottom: 0.5rem`.
- **Таблица результатов на десктопе без горизонтального скролла**:
  `min-width: 100%`, ячейки `0.625rem 0.5rem`, колонка команды `min-w 10.5rem`,
  соперники `3.25rem`, статистика `2.5rem`, высота строки 46px.
  Проверено: 1440 → 1312/1312 (скролла нет), 1280 → 1152/1152 (нет),
  1024 → 896/1056, ниже — скролл со скроллбаром в цветах сайта.
- **История**: `.history-lead` — `text-wrap: balance`, белый,
  `letter-spacing: .02em`; `.history-text` 0.95rem/1.8 с `margin-bottom`
  (как React `mb-5`); `.pillar-num` — `flex-shrink: 0` + `pt-0.5`.

### 2.z. Навигация, меню, логотип и анти-FOUT

- **Активный пункт меню** вычисляется в `app.js` по полосе вьюпорта
  40%–45% (как `rootMargin: '-40% 0px -55% 0px'` в React): выше блока
  «Команда» активных пунктов нет, при возврате наверх подсветка снимается.
  IntersectionObserver в vanilla больше не используется — один источник
  истины (skrollr-обработчик с `requestAnimationFrame`).
- **Мобильное меню** анимировано: `.mobile-menu` (opacity + translateY 10px,
  240ms) и каскад пунктов через `transition-delay` 0.05–0.3s; закрытие —
  класс `.closing`, затем `hidden`. Бургер анимируется в крестик,
  `z-index: 61` (выше меню), пункты — три `<span>`.
- **Логотип** в шапке — квадрат 40×40 (`w-10 h-10 object-cover`), рядом
  текстовый блок `ФБК / ТАРГЕТ`; добавлен правосторонний пробел в
  `.brand-text`, чтобы блок был ровно 54px (как в React) и «ФБК» стоял по
  центру относительно «ТАРГЕТ».
- **Анти-FOUT/CLS**: self-host шрифтов, preload, `@font-face` fallback с
  `size-adjust` (78.5% / 104.3%), critical-CSS hero (`.hero`, `.hero-inner`,
  `.hero-sub/.hero-title/.hero-logo/.hero-desc`, `.site-header`) инлайном в
  `<head>`. Замер: при перезагрузке `.hero-title` держит top=499/height=115
  с первого кадра (до правок: 610→623 и ширина 812→645).

- **Логотип «ФБК / ТАРГЕТ»**: .brand-text { width: 54px; text-align: center } — «ФБК» центрируется относительно «ТАРГЕТ» (замер: текст 105..133 против 92..146, как в React).
- **Таблица первенства**: .team-cell — min-width: 15rem; white-space: nowrap, .team-name — display: inline-block; white-space: nowrap (название команды не переносится ни на 390, ни на 1440); 	able.comp без зебры (	r:nth-child(odd)), как в React.

- **Закрытие мобильного меню**: шторка .mobile-menu живёт под шапкой (	op: var(--header-h); z-index: 55), бургер-крестик — z-index: 70 и всегда виден (44×44, hover-подложка, белый крестик как в React). Три способа закрыть: тап по крестику, тап по пустой области меню, Escape; выбор пункта закрывает автоматически.
