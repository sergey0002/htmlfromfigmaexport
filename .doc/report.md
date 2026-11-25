# Отчёт анализа исходника (Figma Make)

- Корень: `C:\Users\NewUser\Desktop\Новая папка (3)`
- Стек: **React**; корневой компонент: `src\App.tsx`
- Точка входа: `src\main.tsx`
- Figma-слоты в index.html: `figma:lang`, `figma:head-start`, `figma:title`, `figma:head-end`, `figma:body-start`, `figma:body-end` (это шаблон, не страница)
- `.figma/make/site.json`: {"title": "ФБК Таргет", "description": "Provides floorball team players and fans with up-to-date news, match schedules, stats, roster info, and club history in a sleek sports design.", "robots": {"index": false}, "accessibility": {"addBypassLinks": false, "ignoreReducedMotion": false}}
  - ⚠️ `robots.index=false` → на проде обязательно включить индексацию (см. 05-seo-modern.md, 06-deploy-checklist.md)

## Изображения

| Файл | Размер | Вектор |
|---|---|---|
| `public\favicon.png` | 96×96 | — |
| `public\images\partners\akcept.svg` | — | да |
| `public\images\partners\alfa.svg` | — | да |
| `public\images\partners\bspb.png` | 800×305 | — |
| `public\images\partners\domrf.svg` | — | да |
| `public\images\partners\levoberezhny.svg` | — | да |
| `public\images\partners\psb.svg` | — | да |
| `public\images\partners\sber.svg` | — | да |
| `public\images\partners\vtb.svg` | — | да |
| `public\images\site\burger.svg` | — | да |
| `public\images\site\m2.svg` | — | да |
| `public\images\site\max.svg` | — | да |
| `public\images\site\mlogo.png` | 40×40 | — |
| `public\images\site\ok.svg` | — | да |
| `public\images\site\stalker.svg` | — | да |
| `public\images\site\tg-2.svg` | — | да |
| `public\images\site\tg.svg` | — | да |
| `public\images\site\vk.svg` | — | да |
| `src\imports\administrator-nadezhda-asylova.png` | 800×701 | — |
| `src\imports\general-director-roman-voronin.png` | 800×701 | — |
| `src\imports\head-coach-ilya-lobachev.png` | 800×701 | — |
| `src\imports\lev-gerasimov.png` | 800×701 | — |
| `src\imports\player-10.png` | 800×701 | — |
| `src\imports\player-11.png` | 800×701 | — |
| `src\imports\player-16.png` | 800×701 | — |
| `src\imports\player-19.png` | 800×701 | — |
| `src\imports\player-20.png` | 800×701 | — |
| `src\imports\player-22.png` | 800×701 | — |
| `src\imports\player-23.png` | 800×701 | — |
| `src\imports\player-29.png` | 800×701 | — |
| `src\imports\player-31.png` | 800×701 | — |
| `src\imports\player-5.png` | 800×701 | — |
| `src\imports\player-83.png` | 800×701 | — |
| `src\imports\player-85.png` | 800×701 | — |
| `src\imports\player-92.png` | 800×701 | — |
| `src\imports\player-95.png` | 800×701 | — |
| `src\imports\player-99.png` | 800×701 | — |
| `src\imports\senior-coach-yaroslav-isakov.png` | 800×701 | — |
| `src\imports\sport-director-vasiliy-petukhov.png` | 800×701 | — |
| `src\imports\target-hero-texture.png` | 600×600 | — |
| `src\imports\target_avatar.jpg` | 1080×1080 | — |
| `src\imports\team-manager-aleksey-senchuk.png` | 800×701 | — |

Пропорции (W/H → файлы): 1.0 → 4 шт.; 1.14 → 22 шт.; 2.62 → 1 шт.
→ Контейнерам фото задать `aspect-ratio` по этим пропорциям (см. 03-css-responsive.md §3.4).

## Данные (массивы) в корневом компоненте

| Имя | Элементов | Ключи первого элемента |
|---|---|---|
| `banks` | 8 |  |
| `options` | 5 | id, label |
| `companyLinks` | 9 |  |
| `propertyLinks` | 5 |  |
| `topLinks` | 5 |  |
| `pressLinks` | 3 |  |

Перенести ВСЕ перечисленные массивы целиком в `build.mjs` (см. 02-vanilla-build.md §2.3).

## Состояние и эффекты

- Состояние (useState/ref): `false`, `false`, `false`, `false`, ``
- useEffect/onMounted: да
- IntersectionObserver: —
- scrollIntoView / scrollTo: —
- Слушатели событий: onClick, onScroll
- Импортов изображений: 0
- Инлайн-цвета (4): #050505, #102e27, #26b99a, rgba(0,0,0,0.3)
- Адаптивные Tailwind-классы (64): `lg:border-0`, `lg:col-span-1`, `lg:col-span-2`, `lg:col-start-1`, `lg:col-start-2`, `lg:flex`, `lg:flex-row`, `lg:gap-3`, `lg:gap-6`, `lg:gap-8`, `lg:grid-cols-3`, `lg:grid-cols-[1.2fr_1fr]`, `lg:hidden`, `lg:items-end`, `lg:justify-between`, `lg:mb-0`, `lg:mt-5`, `lg:p-11`, `lg:p-8`, `lg:pb-0`, `lg:pb-7`, `lg:pb-[30px]`, `lg:pt-14`, `lg:px-10`, `lg:px-2.5` …
  → Перевести в media-запросы по карте 03-css-responsive.md §3.2 (грид-классы `grid-cols-N` → `repeat(N, minmax(0,1fr))`).

## CSS

- Переменные (14): `--color-bg`, `--color-bg-card`, `--color-bg-card-hover`, `--color-border`, `--color-gold`, `--color-gold-border`, `--color-gold-dark`, `--color-gold-dim`, `--color-gold-light`, `--color-text`, `--color-text-muted`, `--font-body`, `--font-display`, `--header-h`
- Кастомные классы (17): `.btn-outline`, `.btn-primary`, `.divider-top`, `.font-display`, `.gold-border`, `.gold-line`, `.gold-text`, `.is-muted`, `.mb-12`, `.mb-3`, `.mt-4`, `.section-label`, `.section-title`, `.skip-link`, `.u-fw-700`, `.u-team-logo`, `.u-tracking`
- Google Fonts в CSS: не найдено
