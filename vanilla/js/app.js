/* Поведение страницы — 1:1 с source/src/App.tsx (без React).
   1) логотип: запасной текстовый вариант при ошибке загрузки;
   2) бургер-меню: aria-expanded, смена иконки и подписи, закрытие
      по пункту «Согласия» (как setMenuOpen(false) в React);
   3) кнопка скачивания: после клика иконка «галочка» и подпись
      «Скачать ещё раз» (как setDownloaded(true) в React). */
(function () {
  'use strict';

  var FILE_ICON =
    '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9Z" /><path d="M14 2v7h7M7 13h10M7 17h7" /></svg>';

  /* — Логотип: аналог React-состояния error в компоненте Logo — */
  function replaceLogo(img) {
    /* Событие error может прийти и после ручной проверки complete —
       повторная замена недопустима (в React второй вызов setError идемпотентен). */
    if (!img.parentNode) return;
    var span = document.createElement('span');
    span.className = 'brand-fallback';
    span.innerHTML =
      FILE_ICON +
      '<span class="brand-fallback-text">НОВОСИБИРСКАЯ ОБЛАСТНАЯ<br />ФЕДЕРАЦИЯ ФЛОРБОЛА</span>';
    img.parentNode.replaceChild(span, img);
  }

  Array.prototype.forEach.call(document.querySelectorAll('.brand-logo'), function (img) {
    img.addEventListener('error', function () {
      replaceLogo(img);
    });
    if (img.complete && img.naturalWidth === 0) {
      replaceLogo(img);
    }
  });

  /* У SVG нет свойства hidden — только атрибут (HTMLElement.hidden). */
  function setHidden(el, hidden) {
    if (hidden) {
      el.setAttribute('hidden', '');
    } else {
      el.removeAttribute('hidden');
    }
  }

  /* — Мобильное меню —
     В React меню рендерится условно и отсутствует в DOM при закрытии —
     воспроизводим это: узел создаётся при открытии и удаляется при закрытии. */
  var burger = document.querySelector('.burger');
  var header = document.querySelector('.site-header');
  var menu = null;
  var menuIcon = burger.querySelector('.icon-menu');
  var closeIcon = burger.querySelector('.icon-close');

  var MOBILE_MENU_HTML =
    '<nav class="mobile-menu" id="mobile-menu" aria-label="Мобильная навигация">' +
    '<a class="mobile-link" href="https://xn--m1acsa.xn--p1ai/about/">О федерации</a>' +
    '<a class="mobile-link" href="https://xn--m1acsa.xn--p1ai/tournaments/">Турниры</a>' +
    '<a class="mobile-link" href="https://xn--m1acsa.xn--p1ai/teams2/">Команды</a>' +
    '<a class="mobile-link" href="https://xn--m1acsa.xn--p1ai/events/">Медиа</a>' +
    '<a class="mobile-link" href="https://xn--m1acsa.xn--p1ai/contacts/">Контакты</a>' +
    '<a class="mobile-link" href="#documents">Согласия</a>' +
    '</nav>';

  function setMenuOpen(open) {
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    burger.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    setHidden(menuIcon, open);
    setHidden(closeIcon, !open);
    if (open && !menu) {
      header.insertAdjacentHTML('beforeend', MOBILE_MENU_HTML);
      menu = document.getElementById('mobile-menu');
      /* В React закрывается только пункт «Согласия» (setMenuOpen(false)). */
      menu.lastElementChild.addEventListener('click', function () {
        setMenuOpen(false);
      });
    } else if (!open && menu) {
      menu.parentNode.removeChild(menu);
      menu = null;
    }
  }

  burger.addEventListener('click', function () {
    setMenuOpen(burger.getAttribute('aria-expanded') !== 'true');
  });

  /* — Состояние «документ скачан» — */
  Array.prototype.forEach.call(document.querySelectorAll('.btn-download'), function (link) {
    link.addEventListener('click', function () {
      setHidden(link.querySelector('.icon-download'), true);
      setHidden(link.querySelector('.icon-check'), false);
      link.querySelector('.btn-download-label').textContent = 'Скачать ещё раз';
    });
  });
})();
