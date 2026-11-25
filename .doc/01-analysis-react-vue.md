# 01 — Разбор нового исходника: React, Vue, Figma-специфика

> **Исторический материал / план:** факты, примеры и будущие предложения ниже могут устареть и не означают реализованную функциональность. Актуальные процессы и возможности: [README](README.md), [tools](tools.md), [agent workflow](agent-workflow.md). Для текущего `vanilla/` см. [отчёт о конвертации](vanilla-verification.md).

> **Исторический материал:** документ относится преимущественно к примеру ФБК «Таргет» и может не соответствовать текущему исходнику. Актуальное состояние и ограничения — в [обзоре проекта](project-review.md). Команды проверяйте перед запуском.

## 1.1. Определить стек

| Признак | React (как текущий проект) | Vue |
|---|---|---|
| Точка входа | `src/main.tsx` → `createRoot(...).render(<App/>)` | `src/main.ts` → `createApp(App).mount('#app')` |
| Корневой компонент | `src/App.tsx` | `src/App.vue` (`<template>` + `<script setup>` + `<style>`) |
| Состояние | `useState`, `useEffect`, `useRef` | `ref`, `computed`, `onMounted`, `watch` |
| Списки | `array.map(x => <... key={...}>)` | `v-for="x in array" :key="..."` |
| Условия | `{cond && <...>}`, тернарники | `v-if / v-else`, `v-show` |
| Стили | `src/index.css` + Tailwind-классы + инлайн `style={{...}}` | `<style>` в SFC + Tailwind + `:style="{...}"` |

Оба варианта разбираются одинаково: **данные → разметка → стили → поведение**.
Разница только в синтаксисе чтения (таблица выше) и сборке (обе — Vite).

## 1.2. Figma Make: что обязательно проверить

1. `index.html` в корне — это **шаблон**, а не страница:
   `<!-- figma:lang -->`, `<!-- figma:title -->`, `<!-- figma:head-start -->` и т.д.
   Реальные `lang/title/meta` подставляются плагином `figmaSiteConfiguration`
   из `.figma/make/site.json`. Открытие этого файла через `file://` даёт пустой экран —
   это нормально, нужен Vite dev-сервер.
2. `.figma/make/site.json` — забрать `title`, `description`, `robots.index`,
   `icons.icon`, `openGraph.image`, `analytics.googleAnalyticsId`.
3. `vite.config.ts` — забрать алиас `@ → src`, `base`, список плагинов.
   Для ваниллы важно: `base` должен стать `./` (см. `06`).
4. `src/imports/` — все картинки, которые Figma экспортировала.
   Скопировать как есть в `vanilla/img/`, имена — в нижнем регистре, без пробелов.
5. `src/index.css` — CSS-переменные (`--gold`, `--bg`, `--bg-card`, ...),
   шрифты (`Oswald` + `Inter` через Google Fonts), кастомные классы
   (`.font-display`, `.gold-text`, `.section-label`, `.card`, `.table-header`, ...).
   Tailwind-классы (`grid-cols-2`, `md:grid-cols-3`, `px-6`...) — это спецификация
   адаптива, переписать вручную (см. `03`).

## 1.3. Инвентаризация (чек-лист чтения)

Выписать в рабочий файл перед генерацией:

- [ ] Секции и их `id` (напр. `team, coaching, standings, history, partners, contacts`).
- [ ] Навигация: десктоп, мобильная, футер — тексты и якоря.
- [ ] Каждый массив данных целиком: игроки (номер/имя/позиция/статы/портрет),
      персонал (имя/роль/контакт), таблицы (команды/очки), матчи, партнёры,
      история/статы, контакты/соцсети/документы.
- [ ] Особые состояния: `isTarget` (выделенная строка), `pos <= 3` (золото),
      бейдж вратаря, активная секция, активный таб.
- [ ] Интерактив: `useState` (React) / `ref` (Vue) — меню, табы, фильтры, слайдеры,
      `useEffect`/`onMounted` — скролл, IntersectionObserver, анимации.
- [ ] Инлайн-стили с цветами/фонами — перенести в CSS-переменные, не плодить копии.
- [ ] Внешние URL (Unsplash-фон hero, соцсети, PDF-документы) — сохранить как есть
      или заменить локальными по указанию заказчика.

## 1.4. Референс: как это выглядело в «ФБК Таргет» (React)

- `src/App.tsx:22-100` — массивы `players[16]`, `coaches[7]`, `standings[10]`,
  `matchResults`, `partners[6]`, `navItems[6]`.
- `src/App.tsx:109-133` — `activeSection` (IntersectionObserver) + `menuOpen` + таб.
- `src/App.tsx:199-227` — бургер + мобильное меню (`menuOpen && ...`).
- `src/App.tsx:300-369` — секция команды: сетка `grid-cols-2 md:3 lg:4`,
  фото `aspect-ratio 1/1` (было `h-48` — резало макушки, см. `03 §4`).
- `src/App.tsx:447-630` — табы + турнирная таблица + матрица результатов 10×10.
- `src/index.css` — токены, `.card:hover`, hover строк таблиц, анимация меню.

## 1.5. Референс: соответствие для Vue-исходника

| React-паттерн | Где искать в Vue | Что забрать в build.mjs |
|---|---|---|
| `const players = [...]` | `const players = ref([...])` / `const players = [...]` в `<script setup>` | массив как есть |
| `players.map(p => ...)` | `<article v-for="p in players" :key="p.num">` | шаблон карточки |
| `{menuOpen && <div>}` | `<div v-if="menuOpen">` | факт условного рендера → JS-рендер/тоггл |
| `activeSection` + `useEffect` + `IntersectionObserver` | `onMounted(() => new IntersectionObserver(...))` | `rootMargin`, список id |
| `style={{ background: row.isTarget ? ... }}` | `:style="{ background: row.isTarget ? ... }"` | правило выделения |
| `import img from '@/imports/x.png'` | `import img from '@/assets/x.png'` / `/src/assets` | файл в `vanilla/img/` |

Если Vue-проект использует Vue Router / Pinia — роуты превращаются в якоря
одностраничника (или отдельные `page.html`, каждый со своим SEO-блоком),
сторы — в константы `build.mjs`.
