// Поведение статического сайта — один IIFE без зависимостей, подключение с defer.
// Связан с разметкой build.mjs: data-scroll/data-scrolltop, #burger/#mobileMenu,
// [data-tab] + *-panel, .desktop-nav .nav-link, секции из #team… #contacts.
;(function () {
  "use strict"

  // ── Плавный скролл к разделу ─────────────────────────────────────────────

  // ── Табы первенства: таблица / результаты / плейофф ──────────────────────

  // ── Подсветка активного раздела (как IntersectionObserver в React:
  //    раздел задевает полосу 40%–45% высоты вьюпорта, иначе — ничего) ─────
  // идём снизу вверх: последний задевший полосу раздел ближе к центру

  // ── Мобильное меню: плавное раскрытие (шторка + каскад пунктов) ──────────
  // даём браузеру отрисовать закрытое состояние, затем запускаем transition
  // тап по пустому месту меню тоже закрывает (пункты обрабатывает data-scroll)

  function scrollToId(id) {
    var el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" })
  }
  var tabButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-tab]"),
  )
  var panels = {
    standings: document.getElementById("standings-panel"),
    results: document.getElementById("results-panel"),
    playoffs: document.getElementById("playoffs-panel"),
  }

  tabButtons.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var id = tab.getAttribute("data-tab")
      tabButtons.forEach(function (t) {
        var on =
          t ===
          tab
        t.classList.toggle("is-active", on)
        t.setAttribute("aria-selected", on ? "true" : "false")
      })
      Object.keys(panels).forEach(function (key) {
        if (panels[key])
          panels[key].hidden =
            key !==
            id
      })
    })
  })
  var links = Array.prototype.slice.call(
    document.querySelectorAll(
      ".desktop-nav .nav-link, .mobile-menu button, .footer-link",
    ),
  )
  var ids = ["team", "coaching", "standings", "history", "partners", "contacts"]

  function setActive(id) {
    links.forEach(function (l) {
      l.classList.toggle(
        "active",
        !!id &&
          l.getAttribute("data-scroll") ===
            id,
      )
    })
  }

  function syncActive() {
    var bandTop =
      window.innerHeight *
      0.4
    var bandBottom =
      window.innerHeight *
      0.45
    var bestId = ""
    for (
      var i =
        ids.length -
        1;
      i >=
      0;
      i -= 1
    ) {
      var el = document.getElementById(ids[i])
      if (!el) continue
      var r = el.getBoundingClientRect()
      if (
        r.top <=
          bandBottom &&
        r.bottom >=
          bandTop
      ) {
        bestId = ids[i]
        break
      }
    }
    setActive(bestId)
  }

  var ticking = false
  window.addEventListener(
    "scroll",
    function () {
      if (ticking) return
      ticking = true
      requestAnimationFrame(function () {
        syncActive()
        ticking = false
      })
    },
    { passive: true },
  )
  window.addEventListener("resize", syncActive)
  syncActive()
  var burger = document.getElementById("burger")
  var menu = document.getElementById("mobileMenu")
  var menuTimer = null

  function openMenu() {
    if (!menu) return
    clearTimeout(menuTimer)
    menu.hidden = false
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        menu.classList.add("is-open")
        menu.classList.remove("closing")
      })
    })
    if (burger) {
      burger.classList.add("open")
      burger.setAttribute("aria-expanded", "true")
      burger.setAttribute("aria-label", "Закрыть меню")
    }
  }

  function closeMenu() {
    if (!menu || menu.hidden) return
    menu.classList.remove("is-open")
    menu.classList.add("closing")
    if (burger) {
      burger.classList.remove("open")
      burger.setAttribute("aria-expanded", "false")
      burger.setAttribute("aria-label", "Открыть меню")
    }
    clearTimeout(menuTimer)
    menuTimer = setTimeout(function () {
      menu.hidden = true
      menu.classList.remove("closing")
    }, 240)
  }

  if (burger && menu) {
    menu.hidden = true
    burger.addEventListener("click", function (e) {
      e.preventDefault()
      if (menu.hidden) openMenu()
      else closeMenu()
    })
    menu.addEventListener("click", function (e) {
      if (!e.target.closest("button, a")) closeMenu()
    })
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeMenu()
  })

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-scroll]")
    if (btn) {
      scrollToId(btn.getAttribute("data-scroll"))
      closeMenu()
      return
    }
    if (e.target.closest("[data-scrolltop]")) {
      window.scrollTo({ top: 0, behavior: "smooth" })
    }
  })
})()
