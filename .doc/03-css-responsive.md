# 03 — CSS: токены, сетки, адаптив, грабли

## 3.1. Токены и база (переписать из `src/index.css`)

```css
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap');
:root {
  --gold: #c4952a; --gold-light: #d9a83c; --gold-dark: #9a7520;
  --gold-dim: rgba(196, 149, 42, 0.12); --gold-border: rgba(196, 149, 42, 0.3);
  --bg: #080808; --bg-card: #111111; --bg-card-hover: #161616;
  --text: #ffffff; --text-muted: rgba(255, 255, 255, 0.55);
  --border: rgba(255, 255, 255, 0.08);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body { background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
img { display: block; max-width: 100%; }
button { font: inherit; background: none; border: none; color: inherit; }
section { scroll-margin-top: 70px; } /* якоря не прячутся под fixed-шапку */
```

Шрифты только через `<link>` с `preconnect` (см. `05 §6`), `@import` в CSS —
запасной вариант. Запасные семейства обязательны (`'Oswald','Arial Narrow',sans-serif`).

## 3.2. Сетки: точная карта брейкпоинтов

Базовая таблица (мобайл-фёрст, значения эталона):

| Сетка | 390px | ≥768px | ≥1024px |
|---|---|---|---|
| `.team-grid` | `repeat(2, minmax(0,1fr))`, gap 1rem | `repeat(3, 1fr)` | `repeat(4, 1fr)` |
| `.staff-grid` | `1fr` | `repeat(2, 1fr)` | `repeat(auto-fill, minmax(220px, 1fr))` |
| `.partners-grid` | `repeat(2, minmax(0,1fr))` | `repeat(3, 1fr)` | `repeat(6, 1fr)` |
| `.stats-strip` | `repeat(3, minmax(0,1fr))`, gap 1px | — | — |
| `.history-grid` | `1fr` | — | `repeat(2, 1fr)` |
| `.contact-grid` / `.footer-grid` | `1fr` | `repeat(2, 1fr)` | `3 / 4` колонки |

Отступы: `.wrap` 1.5rem → 2.5rem (768) → 4rem (1024); `.section-pad` 6rem;
шапка `70px`. Десктоп-навигация `display:none → flex` на 1024, бургер наоборот.

## 3.3. Грабля №1 — `1fr` vs `minmax(0,1fr)` (КРИТИЧНО)

Tailwind-классы `grid-cols-2` раскрываются в `repeat(2, minmax(0, 1fr))`.
Голый `repeat(2, 1fr)` эквивалентен `minmax(auto, 1fr)` — минимум равен
контентной ширине: длинные слова («Тимофей Константинов», «TARGETZONE»,
«СЕТЬ АЗС TIME») распирают колонку, сетка вылезает за вьюпорт на 390px.

Фикс (везде, где есть текстовый контент в ячейках):

```css
.team-grid, .partners-grid, .stats-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.player-card, .partner-card { min-width: 0; }
.pname, .partner-name, .partner-cat { overflow-wrap: anywhere; }
```

Проверка: на 390px `document.documentElement.scrollWidth <= 390`
(кроме `.table-scroll` — там горизонтальный скролл разрешён и локализован).

## 3.4. Грабля №2 — фото игроков: «одни макушки» (КРИТИЧНО)

Симптом на широком экране: в карточках видны только макушки.
Причина: фото квадратные (800×701), контейнер `h-48` (192px) → широкая низкая
полоса, `object-fit: cover` + `object-position: top` режут всё ниже лба.

Фикс — пропорция вместо фиксированной высоты:

```css
/* БЫЛО: .player-photo { height: 12rem; ... } */
.player-photo { aspect-ratio: 1 / 1; position: relative; display: flex; align-items: flex-end; ... }
.player-photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: top; }
```

В React-исходнике аналогично: `className="h-48 ..."` → `style={{ aspectRatio: '1/1' }}`.
Правило на будущее: **для любого фото узнать реальные пропорции** (PNG: байты 16-23 —
ширина/высота; JPG — через просмотрщик) и задать контейнеру `aspect-ratio`,
близкий к исходнику. Фиксированный `height` + `cover` допустим только для
декоративных фонов (hero), но не для лиц.

## 3.5. Hover строк таблиц

Строка «своего» клуба выделена всегда (класс `.is-target`, раньше был
инлайн-фон `rgba(196,149,42,0.1)`), любая строка подсвечивается при наведении.
Hover перебивает классы строк, поэтому в правилах `:hover` оставлен
`!important` — это единственное допустимое его применение (см. 02 §2.4):

```css
table.comp tbody tr { transition: background 0.2s; }
table.comp tbody tr:hover { background: rgba(196, 149, 42, 0.12) !important; }
table.matrix tbody tr td { transition: background 0.2s; }
table.matrix tbody tr:hover td { background: rgba(196, 149, 42, 0.12) !important; }
```

Матрица `min-width: 1400px` внутри `.table-scroll { overflow-x: auto; }`,
липкие колонки встроены в классы `td.mnum-cell` (`left: 0`) /
`td.mteam`, `th.mteam-h` (`left: 3rem`) с `z-index`.
Динамические фоны ячеек — классы `.mcell.is-same/.is-dim`, `.score/.is-hot`,
`.mstat/.has-left/.is-gold-col` (правило style=0, см. 02 §2.4).

## 3.6. Ноль инлайнов + структура CSS (КРИТИЧНО)

Весь дизайн — только классы `style.css`; в HTML/шаблоне ноль `style=`.
Условные состояния из React (`isTarget`, `is-gk`, `hasWin`) → модификаторы
`.is-target/.is-gk/.is-hot`; утилиты `.u-*` — для односложных повторов.
Полная карта: 02 §2.4. Контроль: `check_vanilla.py` → FAIL при любом `style=`.

Структура `style.css` для любого макета (слои сверху вниз, каждый со своим
русским комментарием-разделителем):

1. **Дизайн-токены** (`:root`) — вся палитра/типографика проекта одним блоком.
2. **База** — сброс, `html/body`, `:focus-visible`, `skip-link`,
   `text-wrap`, назначение якорей (`scroll-margin-top`).
3. **Утилиты `.u-*`** — односложные повторы без семантики; мёртвых утилит
   быть не должно (валидатор предупреждает).
4. **Типографика проекта** — шрифтовые классы, заголовки через `clamp`.
5. **Каркас** — контейнер, секции, шапка, меню, футер.
6. **Блоки макета** — hero, карточки, таблицы, прочие секции (каждый со своим
   подразделом и русским комментарием: что это, ключевые инварианты).
7. **Адаптив** — только наращивающие `@media (min-width)`, мобайл-фёрст;
   узкие исключения — `@media (max-width)` с комментарием «почему».

Правила чистоты (проверяются автоматически + аудитом классов HTML↔CSS):

- ноль `style=`; ноль мёртвых классов (WARN валидатора);
- одинаковые тела правил — сливать в групповые селекторы
  (`.stat-label, .footer-bottom p { … }`), если это один визуальный вид;
- осмысленные различия (сетки брейкпоинтов, transition'ы, sticky-позиции)
  дублированием не считаются — у каждого свой комментарий «почему так».

## 3.6. Анимация мобильного меню (улучшение сверх оригинала)

В оригинале меню появлялось мгновенно (`menuOpen && ...` / `v-if`).
Эталонное улучшение — fade фона + stagger-подъём пунктов:

```css
@keyframes menu-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes menu-link { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
.mobile-menu:not([hidden]) { animation: menu-fade 0.25s ease; }
.mobile-menu:not([hidden]) button { animation: menu-link 0.32s ease backwards; }
.mobile-menu:not([hidden]) button:nth-child(1) { animation-delay: 0.04s; }
/* ... +0.04s на каждый следующий пункт ... */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  html { scroll-behavior: auto; }
}
```

## 3.7. Типографика: читаемость на любых экранах (КРИТИЧНО)

Правила, проверяемые браузерным тестом (`07-scripts.md`, `browser_test.py`):

1. **Минимальный размер шрифта — 12px (0.75rem)**. Микро-подписи
   (`section-label`, категории партнёров, подписи в футере) — не ниже
   `0.75rem`. Инлайны вида `font-size:0.6rem`/`0.65rem`/`0.7rem` — заменить
   на `0.75rem`.
2. **Заголовок h1 ≥ 32px на мобильном** — обеспечить `clamp(2.5rem, 10.5vw, …)`
   для hero-заголовка (мин 2.5rem, не 3.5rem — иначе на 320px не влезает).
3. **Fluid-масштаб**: заголовки — `clamp(min, Nvw, max)`; мелкие тексты —
   фиксированный rem без vw (предсказуемость).
4. **`text-size-adjust: 100%`** на html — iOS Safari не должен сам «раздувать»
   шрифты в альбомной ориентации.
5. **`text-wrap: balance`** для заголовков, **`text-wrap: pretty`** для абзацев —
   запрет сиротских слов (прогрессивное улучшение).
6. **`:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px }`** —
   видимый фокус с клавиатуры.
7. **Skip-link** первым элементом `body`: ссылка «К содержимому» на `#main`,
   скрытая за экраном до `:focus` (разметка — в шаблоне `templates/build.mjs`).
8. **Контейнер фото — `aspect-ratio`** по реальной пропорции изображений
   (отчёт `analyze_figma_export.py` показывает пропорции); на 390px фото
   карточки игрока должно быть ≥ 120px высоты — «лица, не макушки».

Эталонные значения ФБК Таргет: h1 = 41px (390) / 128px (1440);
минимальный шрифт 12px на всех брейкпоинтах; фото карточки 160px на 390px.
