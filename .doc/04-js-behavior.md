# 04 — JS: поведение 1:1 (`js/app.js`)

> **Исторический материал / план:** факты, примеры и будущие предложения ниже могут устареть и не означают реализованную функциональность. Актуальные процессы и возможности: [README](README.md), [tools](tools.md), [agent workflow](agent-workflow.md). [Отчёт о конвертации](vanilla-verification.md) относится к другому экспорту и не подтверждает текущий `vanilla/`.

> **Исторический материал:** документ относится преимущественно к примеру ФБК «Таргет» и может не соответствовать текущему исходнику. Актуальное состояние и ограничения — в [обзоре проекта](project-review.md). Команды проверяйте перед запуском.

Файл — один IIFE, `'use strict'`, ноль зависимостей, подключение с `defer`.
Эталон — 87 строк. Ниже — полный контракт поведения.

## 4.1. Плавный скролл по якорям

```js
function scrollToId(id) {
  var el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-scroll]');
  if (btn) { scrollToId(btn.getAttribute('data-scroll')); closeMenu(); return; }
  var top = e.target.closest('[data-scrolltop]');
  if (top) window.scrollTo({ top: 0, behavior: 'smooth' });
});
```

- Все кнопки навигации (десктоп, мобилка, футер, hero-кнопки) — `<button data-scroll="team">`.
- Логотип/бренд — `data-scrolltop`. Делегирование на `document` переживает регенерацию.
- В React это `scrollTo(id)` + `getElementById`, во Vue — метод с тем же телом.

## 4.2. Мобильное меню (бургер)

Разметка: `<button class="burger" id="burger" aria-expanded="false" aria-controls="mobileMenu">`
+ `<div class="mobile-menu" id="mobileMenu" hidden>`.

```js
var burger = document.getElementById('burger');
var menu = document.getElementById('mobileMenu');
function closeMenu() {
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  burger.classList.remove('open');
  burger.setAttribute('aria-expanded', 'false');
  burger.setAttribute('aria-label', 'Открыть меню');
}
burger.addEventListener('click', function () {
  var willOpen = menu.hidden;
  menu.hidden = !willOpen;
  burger.classList.toggle('open', willOpen);
  burger.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  burger.setAttribute('aria-label', willOpen ? 'Закрыть меню' : 'Открыть меню');
});
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); });
```

Закрытие при клике на пункт — через `closeMenu()` в обработчике `data-scroll` (§4.1).
Анимация открытия — чистый CSS (см. `03 §3.6`), JS только тогглит `hidden`.

## 4.3. Табы (турнирная таблица / матрица)

```js
var tabButtons = Array.prototype.slice.call(document.querySelectorAll('[data-tab]'));
var panels = { standings: document.getElementById('standings-panel'), results: document.getElementById('results-panel') };
tabButtons.forEach(function (btn) {
  btn.addEventListener('click', function () {
    var id = btn.getAttribute('data-tab');
    tabButtons.forEach(function (b) { b.setAttribute('aria-selected', b === btn ? 'true' : 'false'); });
    Object.keys(panels).forEach(function (key) { if (panels[key]) panels[key].hidden = key !== id; });
  });
});
```

В React это `useState<'standings'|'results'>`, во Vue — `ref('standings')`.
Разметка обязана содержать `role="tablist/tab/tabpanel"`, `aria-controls`,
`aria-labelledby`, `tab-line`-индикатор активного таба.

## 4.4. Подсветка активного раздела

```js
var links = Array.prototype.slice.call(document.querySelectorAll('.desktop-nav .nav-link, .mobile-menu button'));
var ids = ['team', 'coaching', 'standings', 'history', 'partners', 'contacts']; // = navItems
function setActive(id) {
  links.forEach(function (l) { l.classList.toggle('active', l.getAttribute('data-scroll') === id); });
}
if ('IntersectionObserver' in window) {
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) { if (entry.isIntersecting) setActive(entry.target.id); });
  }, { rootMargin: '-40% 0px -55% 0px' });
  ids.forEach(function (id) { var el = document.getElementById(id); if (el) observer.observe(el); });
}
```

`rootMargin: '-40% 0px -55% 0px'` — активна секция, занимающая среднюю полосу экрана.
Массив `ids` генерируется из `navItems`, руками не дублировать.
`.nav-link.active` → золотой цвет (CSS).

## 4.5. Контракт JS ↔ HTML ↔ CSS (проверяется автоматически)

`app.js` связан с разметкой тремя видами ссылок — все проверяет
`check_vanilla.py` (FAIL при разрыве), а мёртвые CSS-классы ищутся с учётом
**всех** использований в JS:

| Ссылка | Пример | Проверка |
|---|---|---|
| id | `getElementById('burger')` | id обязан существовать в HTML |
| data-атрибут | `[data-scroll]`, `[data-tab]` | обработчик без элементов = FAIL |
| класс | `classList.toggle('open')`, `querySelector('.desktop-nav .nav-link')` | входит в «используемые» классы CSS (не мёртвый) |

Правила при правках:

- Переименовал id/класс в шаблоне → переименуй в `app.js` (валидатор поймает).
- JS-классы считаются используемыми даже если их нет в статическом HTML —
  они появляются в рантайме (`open`, `active`).
- Удалил интерактив (табы/меню) → удали и обработчик, иначе FAIL по data-атрибуту.

## 4.6. Что НЕ переносить

- React StrictMode / Vue devtools-хуки, HMR-код, Figma-плагины (`figmaSiteConfiguration`,
  `figmaErrorOverlayReplay`, `figmaMakeKitPlugin`) — только dev-обвязка Vite.
- Состояние, существующее только ради анимаций фреймворка — заменяется CSS.
- Если в исходнике есть слайдер/фильтр/модалка — реализовать минимальным ванильным
  эквивалентом и задокументировать отличие в `00-overview.md` нового проекта.
