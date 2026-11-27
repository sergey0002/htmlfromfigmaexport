# 05 — Современный SEO, соцсети, фавиконы, доступность, скорость

> **Исторический материал / план:** факты, примеры и будущие предложения ниже могут устареть и не означают реализованную функциональность. Актуальные процессы и возможности: [README](README.md), [tools](tools.md), [agent workflow](agent-workflow.md). [Отчёт о конвертации](vanilla-verification.md) относится к другому экспорту и не подтверждает текущий `vanilla/`.

> **Исторический материал:** документ относится преимущественно к примеру ФБК «Таргет» и может не соответствовать текущему исходнику. Актуальное состояние и ограничения — в [обзоре проекта](project-review.md). Команды проверяйте перед запуском.

Требование: сайт без JS обязан отдавать весь контент (SSR-эквивалент достигается
генерацией), Lighthouse SEO/Accessibility/Best-Practices = 100, Performance ≥ 90.

## 5.1. `<head>`: полный эталонный шаблон

Подставить значения `SITE` из `build.mjs`. Все URL — абсолютные (`https://...`).

```html
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ФБК Таргет — флорбольный клуб | Состав, таблица U19, история</title>
  <!-- title: 50–60 символов, главный запрос + бренд; ОДИН h1 на странице должен ему соответствовать -->
  <meta name="description" content="Флорбольный клуб «Таргет»: состав команды, тренерский штаб, турнирная таблица Первенства России U19, история клуба, партнёры и контакты.">
  <!-- description: 150–160 символов, 1–2 запроса, без переспама -->
  <link rel="canonical" href="https://example.ru/">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <meta name="theme-color" content="#080808">
  <meta name="author" content="ФБК Таргет">
  <meta name="geo.region" content="RU">
  <!-- Фавиконы (файлы — см. §5.4) -->
  <link rel="icon" href="./favicon.svg" type="image/svg+xml">
  <link rel="icon" href="./favicon-32.png" sizes="32x32" type="image/png">
  <link rel="icon" href="./favicon-16.png" sizes="16x16" type="image/png">
  <link rel="apple-touch-icon" href="./apple-touch-icon.png" sizes="180x180">
  <!-- Open Graph -->
  <meta property="og:type" content="website">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="ФБК Таргет">
  <meta property="og:title" content="ФБК Таргет — флорбольный клуб">
  <meta property="og:description" content="Состав, таблица Первенства России U19, история и партнёры клуба.">
  <meta property="og:url" content="https://example.ru/">
  <meta property="og:image" content="https://example.ru/img/og-cover.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="ФБК Таргет — флорбольный клуб">
  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="ФБК Таргет — флорбольный клуб">
  <meta name="twitter:description" content="Состав, таблица Первенства России U19, история и партнёры клуба.">
  <meta name="twitter:image" content="https://example.ru/img/og-cover.jpg">
  <meta name="twitter:image:alt" content="ФБК Таргет — флорбольный клуб">
  <!-- Шрифты: preconnect + display=swap, без @import в критическом пути -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap">
  <link rel="stylesheet" href="./css/style.css">
  <!-- JSON-LD (см. §5.3) -->
  <script type="application/ld+json">...</script>
  <script src="./js/app.js" defer></script>
</head>
```

Устаревшее/запрещённое: `keywords`, `revisit-after`, дубли `og:`+`twitter:` без нужды,
`http://` в canonical/OG, `noindex` на проде (в Figma-исходнике `robots.index=false` —
на проде заменить на `index, follow`).

## 5.2. Семантика тела

```text
header.site-header (бренд + nav.desktop-nav + бейдж) → div.mobile-menu →
main → section#team → section#coaching → section#standings → section#history →
section#partners → section#contacts → footer.site-footer
```

- `h1` — один, в hero. Секции — `h2`, карточки/имена — `p` + классы (не `h3` без нужды;
  если нужен `h3` — строго внутри своей `h2`-секции).
- Навигация — `<nav aria-label>`, табы — `tablist/tab/tabpanel`, таблицы — `<table>`
  с `<thead>`/`<tbody>`, `<th scope>` там, где заголовки строк/столбцов.
- Email — `mailto:`, телефон — `tel:+79137644284`, соцсети — именованные ссылки.
- Не использовать кнопки-пустышки `<a href="#">` для действий — `<button type="button">`.

## 5.3. JSON-LD (минимум: SportsTeam + WebSite + BreadcrumbList)

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SportsTeam", "@id": "https://example.ru/#team",
      "name": "ФБК Таргет", "sport": "Floorball",
      "url": "https://example.ru/", "logo": "https://example.ru/img/target_avatar.jpg",
      "email": "info@example.ru", "telephone": "+7 000 000-00-00",
      "memberOf": { "@type": "SportsOrganization", "name": "Первенство России U19" }
    },
    {
      "@type": "WebSite", "@id": "https://example.ru/#website",
      "url": "https://example.ru/", "name": "ФБК Таргет",
      "inLanguage": "ru-RU",
      "publisher": { "@id": "https://example.ru/#team" }
    }
  ]
}
</script>
```

Валидировать на `validator.schema.org`. Для других тематик заменить `SportsTeam`
на `Organization`/`LocalBusiness`/`Person` с соответствующими полями, структура
`@graph` сохраняется. Таблицу результатов дополнительно размечать `SportsEvent`
только при реальных датах/счетах.

## 5.4. Фавиконы и манифест (все файлы — в корень `vanilla/`)

| Файл | Размер | Назначение |
|---|---|---|
| `favicon.svg` | вектор | современные браузеры |
| `favicon-16.png` / `favicon-32.png` | 16 / 32 | вкладки, ретина |
| `apple-touch-icon.png` | 180×180 | iOS, JSON-LD logo |
| `img/og-cover.jpg` | 1200×630, <300 КБ | OG/Twitter-превью |

Манифест/иконки 192/512 для PWA — только по явной просьбе (не on-page, лишние файлы).
Все иконки генерирует `make_seo_pack.py` (см. 07-scripts.md).

SVG-фавикон — упрощённый логотип (золото `#C4952A` на `#080808`), без мелкого текста.
Проверить: вкладка, iOS-закладка, шаринг в TG/VK (дебаггеры соцсетей).

## 5.5. robots.txt / sitemap.xml (серверные, НЕ создаются скриптами)

По умолчанию **не генерируются** — только on-page SEO. Если у проекта появится
несколько страниц, добавить вручную:

`robots.txt` (корень хостинга):

```text
User-agent: *
Allow: /
Sitemap: https://example.ru/sitemap.xml
```

`sitemap.xml` — один `<url>` на страницу (`loc` абсолютный, `lastmod` = дата релиза,
`changefreq="weekly"`, `priority="1.0"` для главной). Для многостраничника —
по `<url>` на каждую страницу из генератора.

## 5.6. Производительность (Core Web Vitals)

- LCP-изображение (hero): `fetchpriority="high"`, без `lazy`; остальные — `loading="lazy" decoding="async"`.
- Все `<img>` с `width`/`height` (CLS < 0.1). Для `aspect-ratio`-контейнеров (§3.4) —
  размеры = пропорции исходника.
- Один CSS, один JS (`defer`), ноль блокирующих скриптов; Tailwind CDN запрещён.
- Шрифты: `display=swap` + системный фолбэк; `preconnect` до `fonts.gstatic.com`.
- Изображения: фото — WebP/AVIF при наличии конвертера (фолбэк PNG/JPG через `<picture>`);
  без конвертера — сжать исходники, OG — JPG q80, <300 КБ.
- Цели: LCP < 2.5s, INP < 200ms, CLS < 0.1 на Moto G4 / 4G.

## 5.7. Доступность (Accessibility = 100)

- Контраст золота `#C4952A` на `#080808` ≥ 4.5:1 для текста (проверить в DevTools).
- `aria-expanded/controls/label` у бургера, `aria-selected` у табов,
  `aria-label` у номеров игроков, `alt` у контентных фото, `alt=""` у декора.
- Фокус видим (`:focus-visible { outline: 2px solid var(--gold); }`), порядок табуляции = визуальному.
- `prefers-reduced-motion` — гасить анимации (см. `03 §3.6`).
- `lang="ru"`, `skip-link` «Перейти к содержимому» первым в `body`.
