// Генератор статичного index.html для vanilla-версии. Запуск из корня проекта: node build.mjs
// Пишет ./vanilla/index.html, папку создаёт сам. Меняй данные и шаблоны ниже.
import { mkdirSync, writeFileSync } from "node:fs"

const players = [
  {
    num: 88,
    name: "Лев Герасимов",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "lev-gerasimov.png",
  },
  {
    num: 10,
    name: "Кирилл Форись",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-10.png",
  },
  {
    num: 11,
    name: "Тимофей Константинов",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-11.png",
  },
  {
    num: 83,
    name: "Макар Федоров",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-83.png",
  },
  {
    num: 5,
    name: "Олег Бабанев",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-5.png",
  },
  {
    num: 85,
    name: "Андрей Хабаров",
    pos: "Вратарь",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-85.png",
  },
  {
    num: 23,
    name: "Михаил Воронин",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-23.png",
  },
  {
    num: 29,
    name: "Егор Кузьмин",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-29.png",
  },
  {
    num: 19,
    name: "Арсений Михайлов",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-19.png",
  },
  {
    num: 31,
    name: "Павел Колесов",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-31.png",
  },
  {
    num: 99,
    name: "Вадим Эверт",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-99.png",
  },
  {
    num: 22,
    name: "Ерофей Сенчук",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-22.png",
  },
  {
    num: 20,
    name: "Максим Ильин",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-20.png",
  },
  {
    num: 16,
    name: "Дмитрий Круглов",
    pos: "Вратарь",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-16.png",
  },
  {
    num: 95,
    name: "Артем Мысоев",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-95.png",
  },
  {
    num: 92,
    name: "Никита Яремчук",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-92.png",
  },
]

const coaches = [
  {
    name: "Лобачев Илья Андреевич",
    role: "Главный тренер",
    email: "info@fbk-target.ru",
  },
  {
    name: "Исаков Ярослав Андреевич",
    role: "Старший тренер",
    email: "info@fbk-target.ru",
  },
  {
    name: "Петухов Василий Вячеславович",
    role: "Спортивный директор",
    email: "info@fbk-target.ru",
  },
  {
    name: "Воронин Роман Андреевич",
    role: "Генеральный директор",
    email: "info@fbk-target.ru",
  },
  {
    name: "Сенчук Алексей Михайлович",
    role: "Начальник команды",
    email: "info@fbk-target.ru",
  },
  {
    name: "Ткачева Вероника Александровна",
    role: "Контентмейкер",
    phone: "+7 913 764 42 84",
  },
  {
    name: "Асылова Надежда Павловна",
    role: "Администратор",
    phone: "+7 913 764 42 84",
  },
]

const partners = [
  { name: "Сталкер", cat: "Генеральный партнёр", color: "#C4952A" },
  { name: "TARGETZONE", cat: "Официальный партнёр", color: "#888" },
  { name: "МАГИСТРАЛЬ", cat: "Официальный партнёр", color: "#888" },
  { name: "АЗС TIME", cat: "Официальный партнёр", color: "#888" },
  { name: "АТЗ", cat: "Официальный партнёр", color: "#888" },
  { name: "М2", cat: "IT-партнёр", color: "#888" },
]

const standings = [
  {
    pos: 1,
    team: "ФБК Таргет",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: true,
  },
  {
    pos: 2,
    team: "Варягъ",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 3,
    team: "Нижегородец",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 4,
    team: "Юность-НН",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 5,
    team: "Спартак",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 6,
    team: "Барракуда ",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 7,
    team: "Кольчуга-УМ",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 8,
    team: "Норд Сити",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 9,
    team: "Ирбис",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
  {
    pos: 10,
    team: "Невская дружина",
    gp: 0,
    w: 0,
    d: 0,
    l: 0,
    gf: 0,
    ga: 0,
    pts: 0,
    isTarget: false,
  },
]

const matchResults = [
  {
    round: 1,
    date: "",
    home: "Ирбис",
    homeScore: 3,
    awayScore: 4,
    away: "Спартак",
  },
  {
    round: 1,
    date: "",
    home: "Нижегородец",
    homeScore: 1,
    awayScore: 6,
    away: "Норд Сити",
  },
  {
    round: 1,
    date: "",
    home: "Варягъ",
    homeScore: 3,
    awayScore: 5,
    away: "ФБК Таргет",
  },
  {
    round: 1,
    date: "",
    home: "Кольчуга-УМ",
    homeScore: 0,
    awayScore: 9,
    away: "Невская дружина",
  },
  {
    round: 1,
    date: "",
    home: "Барракуда ",
    homeScore: 4,
    awayScore: 7,
    away: "Юность-НН",
  },
  {
    round: 2,
    date: "",
    home: "Невская дружина",
    homeScore: 10,
    awayScore: 1,
    away: "ФБК Таргет",
  },
  {
    round: 2,
    date: "",
    home: "Невская дружина",
    homeScore: 5,
    awayScore: 4,
    away: "Варягъ",
  },
  {
    round: 2,
    date: "",
    home: "Спартак",
    homeScore: 5,
    awayScore: 1,
    away: "Юность-НН",
  },
  {
    round: 2,
    date: "",
    home: "Спартак",
    homeScore: 1,
    awayScore: 0,
    away: "Барракуда ",
  },
  {
    round: 2,
    date: "",
    home: "Ирбис",
    homeScore: 6,
    awayScore: 1,
    away: "Норд Сити",
  },
  {
    round: 2,
    date: "",
    home: "Ирбис",
    homeScore: 8,
    awayScore: 3,
    away: "Кольчуга-УМ",
  },
  {
    round: 2,
    date: "",
    home: "Норд Сити",
    homeScore: 6,
    awayScore: 1,
    away: "Юность-НН",
  },
  {
    round: 2,
    date: "",
    home: "ФБК Таргет",
    homeScore: 6,
    awayScore: 2,
    away: "Барракуда ",
  },
  {
    round: 2,
    date: "",
    home: "Кольчуга-УМ",
    homeScore: 3,
    awayScore: 0,
    away: "Нижегородец",
  },
  {
    round: 2,
    date: "",
    home: "Нижегородец",
    homeScore: 3,
    awayScore: 4,
    away: "Варягъ",
    overtime: true,
  },
]

// Порядок строк турнирной таблицы и статистика — как в App.tsx
const standingsOrder = [
  "Невская дружина",
  "Спартак",
  "Ирбис",
  "Норд Сити",
  "ФБК Таргет",
  "Юность-НН",
  "Кольчуга-УМ",
  "Нижегородец",
  "Варягъ",
  "Барракуда ",
]
const teamStats = {
  "Невская дружина": {
    gp: 3,
    w: 3,
    otw: 0,
    d: 0,
    otl: 0,
    l: 0,
    gf: 24,
    ga: 5,
    pts: 9,
  },
  Спартак: { gp: 3, w: 3, otw: 0, d: 0, otl: 0, l: 0, gf: 10, ga: 4, pts: 9 },
  Ирбис: { gp: 3, w: 2, otw: 0, d: 0, otl: 0, l: 1, gf: 17, ga: 8, pts: 6 },
  "Норд Сити": {
    gp: 3,
    w: 2,
    otw: 0,
    d: 0,
    otl: 0,
    l: 1,
    gf: 13,
    ga: 8,
    pts: 6,
  },
  "ФБК Таргет": {
    gp: 3,
    w: 2,
    otw: 0,
    d: 0,
    otl: 0,
    l: 1,
    gf: 12,
    ga: 15,
    pts: 6,
  },
  "Юность-НН": {
    gp: 3,
    w: 1,
    otw: 0,
    d: 0,
    otl: 0,
    l: 2,
    gf: 9,
    ga: 15,
    pts: 3,
  },
  "Кольчуга-УМ": {
    gp: 3,
    w: 1,
    otw: 0,
    d: 0,
    otl: 0,
    l: 2,
    gf: 6,
    ga: 17,
    pts: 3,
  },
  Нижегородец: {
    gp: 3,
    w: 0,
    otw: 1,
    d: 0,
    otl: 0,
    l: 2,
    gf: 5,
    ga: 12,
    pts: 2,
  },
  Варягъ: { gp: 3, w: 0, otw: 0, d: 0, otl: 1, l: 2, gf: 10, ga: 14, pts: 1 },
  "Барракуда ": {
    gp: 3,
    w: 0,
    otw: 0,
    d: 0,
    otl: 0,
    l: 3,
    gf: 6,
    ga: 14,
    pts: 0,
  },
}
const statLabels = ["И", "В", "ВО", "Н", "ПО", "П", "+/-", "О"]

const navItems = [
  { id: "team", label: "Команда" },
  { id: "coaching", label: "Руководство" },
  { id: "standings", label: "Первенство России U19" },
  { id: "history", label: "История" },
  { id: "partners", label: "Партнёры" },
  { id: "contacts", label: "Контакты" },
]

const esc = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")

const posOrder = { Вратарь: 0, Нападающий: 1, Защитник: 2 } // сортировка как в App.tsx
const playersSorted = [...players].sort(
  (a, b) => posOrder[a.pos] - posOrder[b.pos],
)

const playerCards = playersSorted
  .map((p) => {
    const gk = p.pos === "Вратарь"
    return `<article>
      <div class="player-photo">
        <img src="./img/target_avatar.jpg" alt="" width="1080" height="1080" loading="lazy">
        <img src="./img/${p.img}" alt="${esc(p.name)}" width="800" height="701" loading="lazy" decoding="async" class="photo-main">
        <div class="shade"></div>
        <div class="player-pos"><span class="pos-badge${
          gk ? " is-gk" : ""
        }">${esc(p.pos.toUpperCase())}</span></div>
      </div>
      <div class="player-info">
        <div>
          <p class="pname">${esc(p.name)}</p>
          <div class="player-stats"><span><span class="gold-text u-fw-700">${p.g}</span> Г</span><span><span class="gold-text u-fw-700">${p.a}</span> П</span><span><span>${p.gp}</span> И</span></div>
        </div>
        <div class="player-num" aria-label="Игровой номер ${p.num}">${p.num}</div>
      </div>
      <div class="card-accent"></div>
    </article>`
  })
  .join("\n")

const staffCards = coaches
  .map(
    (c) => `<article>
      <div class="staff-icon" aria-hidden="true">🎯</div>
      <p class="section-label staff-role">${esc(c.role)}</p>
      <p class="staff-name">${esc(c.name)}</p>
      <p class="staff-contact">${
        c.email
          ? `Email: <a href="mailto:${c.email}" class="gold-text u-fw-600 u-no-deco">${c.email}</a>`
          : `Тел.: <span class="gold-text u-fw-600">${c.phone}</span>`
      }</p>
      <div class="staff-corner"></div>
    </article>`,
  )
  .join("\n")

const standingsRows = standingsOrder
  .map((team, rowIndex) => {
    const row = standings.find((r) => r.team === team)
    const s = teamStats[team]
    const top = rowIndex < 3 ? " is-top" : ""
    const target = row.isTarget ? " is-target" : ""
    const cells = [s.gp, s.w, s.otw, s.d, s.otl, s.l, s.gf, s.ga]
      .map((v) => `<td>${v}</td>`)
      .join("")
    return `<tr${row.isTarget ? ' class="is-target"' : ""}>
      <td class="pl pos-cell${top}">${rowIndex + 1}</td>
      <td class="team-cell">${
        row.isTarget
          ? '<img src="./img/target_avatar.jpg" alt="" width="1080" height="1080" loading="lazy" class="u-team-logo">'
          : ""
      }<span class="team-name${target}">${esc(team)}</span></td>
      ${cells}
      <td class="pts-cell">${s.pts}</td>
    </tr>`
  })
  .join("\n")

function cellScore(rowTeam, colTeam) {
  if (rowTeam === colTeam) return ""
  const found = matchResults.filter(
    (m) =>
      (m.home === rowTeam && m.away === colTeam) ||
      (m.home === colTeam && m.away === rowTeam),
  )
  if (!found.length) return '<span class="dash">—</span>'
  const m = found[0]
  const score =
    m.home === rowTeam
      ? `${m.homeScore}:${m.awayScore}`
      : `${m.awayScore}:${m.homeScore}`
  const ot = m.overtime ? " (ОТ)" : ""
  const hot = rowTeam === "ФБК Таргет"
  return `<span class="score${hot ? " is-hot" : ""}">${score}${ot}</span>`
}

function statValues(team) {
  const s = teamStats[team]
  return [s.gp, s.w, s.otw, s.d, s.otl, s.l, s.gf - s.ga, s.pts]
}

const matrixHead =
  standings.map((_, i) => `<th class="table-header">${i + 1}</th>`).join("") +
  statLabels
    .map(
      (label, i) =>
        `<th class="table-header mstat-h${
          i === 0 ? " has-left" : ""
        }">${label}</th>`,
    )
    .join("")

const matrixRows = standings
  .map((row, ri) => {
    const cells =
      standings
        .map((col) => {
          const same = row.team === col.team
          return `<td${same ? ' class="is-same"' : ""}>${
            same ? "" : cellScore(row.team, col.team)
          }</td>`
        })
        .join("") +
      statValues(row.team)
        .map((v, i) => `<td${i === 0 ? ' class="has-left"' : ""}>${v}</td>`)
        .join("")
    return `<tr>
      <td class="mnum-cell">${ri + 1}</td>
      <td class="mteam">${esc(row.team)}</td>
      ${cells}
    </tr>`
  })
  .join("\n")

const partnerCards = partners
  .map(
    (p) =>
      `<div><div class="partner-name${
        p.color === "#C4952A" ? " is-main" : ""
      }">${esc(p.name)}</div><p class="section-label partner-cat">${esc(p.cat)}</p></div>`,
  )
  .join("\n")

const navLabel = (n, where) =>
  n.id === "standings" && where !== "mobile"
    ? "TargetZone Первенство России U19"
    : n.label
const navLinks = navItems
  .map(
    (n) =>
      `<button type="button" data-scroll="${n.id}">${esc(navLabel(n, "desktop"))}</button>`,
  )
  .join("\n")
const mobileLinks = navItems
  .map(
    (n) =>
      `<button type="button" data-scroll="${n.id}">${esc(navLabel(n, "mobile"))}</button>`,
  )
  .join("\n")
const footerLinks = navItems
  .map(
    (n) =>
      `<button type="button" data-scroll="${n.id}">${esc(navLabel(n, "footer"))}</button>`,
  )
  .join("\n")

const html = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ФБК Таргет — флорбольный клуб | Состав, таблица U19</title>
  <meta name="description" content="Флорбольный клуб «Таргет»: состав команды, тренерский штаб, турнирная таблица Первенства России U19, история клуба, партнёры и контакты.">
  <link rel="canonical" href="https://fbk-target.ru/">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <meta name="theme-color" content="#080808">
  <link rel="icon" href="./favicon.svg" type="image/svg+xml">
  <link rel="icon" href="./favicon-32.png" sizes="32x32" type="image/png">
  <link rel="icon" href="./favicon-16.png" sizes="16x16" type="image/png">
  <link rel="apple-touch-icon" href="./apple-touch-icon.png" sizes="180x180">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="ФБК Таргет">
  <meta property="og:title" content="ФБК Таргет — флорбольный клуб">
  <meta property="og:description" content="Состав команды, турнирная таблица Первенства России U19, история клуба, партнёры и контакты.">
  <meta property="og:url" content="https://fbk-target.ru/">
  <meta property="og:image" content="https://fbk-target.ru/og-cover.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="ФБК Таргет — флорбольный клуб">
  <meta name="twitter:description" content="Состав команды, турнирная таблица Первенства России U19, история клуба, партнёры и контакты.">
  <meta name="twitter:image" content="https://fbk-target.ru/og-cover.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="./css/style.css">
  <script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SportsTeam",
      "@id": "https://fbk-target.ru/#team",
      "name": "ФБК Таргет",
      "sport": "Floorball",
      "url": "https://fbk-target.ru/",
      "logo": "https://fbk-target.ru/apple-touch-icon.png",
      "email": "info@fbk-target.ru",
      "telephone": "+7 913 764-42-84",
      "memberOf": { "@type": "SportsOrganization", "name": "Первенство России U19" }
    },
    {
      "@type": "WebSite",
      "@id": "https://fbk-target.ru/#website",
      "url": "https://fbk-target.ru/",
      "name": "ФБК Таргет",
      "inLanguage": "ru-RU",
      "publisher": { "@id": "https://fbk-target.ru/#team" }
    }
  ]
}
  </script>
</head>
<body>
<a class="skip-link" href="#team">Перейти к содержимому</a>
<div class="page">

  <header class="site-header">
    <button type="button" class="brand" data-scrolltop aria-label="ФБК Таргет — наверх">
      <img src="./img/target_avatar.jpg" alt="ФБК Таргет" width="1080" height="1080" class="u-photo-mini">
      <span><span class="font-display gold-text brand-fbk">ФБК</span><span class="font-display brand-name">ТАРГЕТ</span></span>
    </button>
    <nav class="desktop-nav" aria-label="Основная навигация">
      ${navLinks}
    </nav>
    <div class="season-badge">
      <div class="section-label u-fs-75">Сезон</div>
      <div class="font-display">2026/27</div>
    </div>
    <button type="button" class="burger" id="burger" aria-label="Открыть меню" aria-expanded="false" aria-controls="mobileMenu">
      <span></span><span></span><span></span>
    </button>
  </header>

  <div class="mobile-menu" id="mobileMenu" hidden>
    ${mobileLinks}
  </div>

  <main>
  <section class="hero" aria-label="Флорбольный клуб Таргет">
    <img src="https://images.unsplash.com/photo-1547347298-4074fc3086f0?w=1600&amp;h=900&amp;fit=crop&amp;auto=format" alt="Флорбол — игровой момент" class="hero-bg" width="1600" height="900" fetchpriority="high">
    <div class="hero-shade"></div>
    <div class="hero-gold"></div>
    <div class="hero-inner wide">
      <p class="hero-sub">Флорбольный клуб</p>
      <img src="./img/target_avatar.jpg" alt="Логотип клуба «Таргет»" class="hero-logo" width="1080" height="1080" fetchpriority="high">
      <h1 class="hero-title"><span class="gold-text">ФБК</span> ТАРГЕТ</h1>
      <p class="hero-desc">Профессиональный флорбольный клуб. Страсть, командный дух и стремление к победе.</p>
      <div class="hero-actions">
        <button type="button" class="btn-primary" data-scroll="team">Состав команды</button>
        <button type="button" class="btn-outline" data-scroll="standings">Таблица</button>
      </div>
    </div>
    <div class="scroll-cue"><div class="line"></div><span class="section-label u-fs-75">Листать вниз</span></div>
  </section>

  <section id="team" class="wrap section-pad">
    <div class="sec-head"><p class="section-label">Состав</p><h2 class="section-title">Команда</h2><div class="gold-line"></div></div>
    <div class="team-grid">
${playerCards}
    </div>
  </section>

  <section id="coaching" class="wrap section-pad divider-top">
    <div class="sec-head"><p class="section-label">Руководство</p><h2 class="section-title">Тренерский штаб</h2><div class="gold-line"></div></div>
    <div class="staff-grid">
${staffCards}
    </div>
  </section>

  <section id="standings" class="wrap section-pad divider-top">
    <div class="sec-head"><p class="section-label">Сезон 2026/27</p><h2 class="section-title">Первенство России U19</h2><div class="gold-line"></div></div>
    <div role="tablist" aria-label="Таблицы первенства" class="tabs">
      <button type="button" role="tab" id="standings-tab" aria-selected="true" aria-controls="standings-panel" data-tab="standings">Турнирная таблица<span class="tab-line"></span></button>
      <button type="button" role="tab" id="results-tab" aria-selected="false" aria-controls="results-panel" data-tab="results">Таблица результатов<span class="tab-line"></span></button>
    </div>
    <div id="standings-panel" role="tabpanel" aria-labelledby="standings-tab" class="table-scroll">
      <table class="comp">
        <thead><tr><th class="table-header th-num">#</th><th class="table-header th-team">Команда</th><th class="table-header c">И</th><th class="table-header c">В</th><th class="table-header c">ВО</th><th class="table-header c">Н</th><th class="table-header c">ПО</th><th class="table-header c">П</th><th class="table-header c">ГЗ</th><th class="table-header c">ГП</th><th class="table-header c">О</th></tr></thead>
        <tbody>
${standingsRows}
        </tbody>
      </table>
    </div>
    <div id="results-panel" role="tabpanel" aria-labelledby="results-tab" class="table-scroll" hidden>
      <table class="matrix">
        <thead><tr><th class="table-header c mnum-h">#</th><th class="table-header mteam-h">Команда</th>${matrixHead}</tr></thead>
        <tbody>
${matrixRows}
        </tbody>
      </table>
    </div>
  </section>

  <section id="history" class="wrap section-pad divider-top">
    <div class="sec-head"><p class="section-label">Путь клуба</p><h2 class="section-title">История создания</h2><div class="gold-line"></div></div>
    <div class="history-grid">
      <div>
        <p class="history-lead">Мы за спорт — и вкладываем силы в <span class="gold-text">детский и юношеский флорбол</span></p>
        <p class="history-text">ФБК «Таргет» основан в&nbsp;&nbsp;2026 году людьми, которые хотят растить новое поколение флорбола. У нас есть место для каждого, кто готов выйти на площадку и играть.</p>
        <p class="history-text u-mb-0">Сегодня мы выступаем в Targetzone Первенстве России U19 и набираемся опыта у сильных соперников. Главный результат для нас — игроки, которые приходят всерьёз и надолго.</p>
      </div>
      <div class="pillars">
        <div class="pillar"><div>01</div><div><p>Спорт для детей</p><p>Мы вкладываем силы в детский и юношеский спорт: доступные тренировки, честная игра и поддержка каждого, кто выходит на площадку.</p></div></div>
        <div class="pillar"><div>02</div><div><p>Профессиональный подход</p><p>Структурированные тренировки, разборы игры и аналитика матчей — стандарты большого спорта, доступные юным игрокам, а не только взрослым.</p></div></div>
        <div class="pillar"><div>03</div><div><p>Воспитание характера</p><p>Мы растим не только спортсменов, но и личностей: командность, дисциплина и уважение к сопернику для нас важны не меньше побед.</p></div></div>
      </div>
    </div>
  </section>

  <section id="partners" class="wrap section-pad divider-top">
    <div class="sec-head"><p class="section-label">Поддержка</p><h2 class="section-title">Партнёры</h2><div class="gold-line"></div></div>
    <div class="partners-grid">
${partnerCards}
    </div>
  </section>

  <section id="contacts" class="wrap section-pad divider-top">
    <div class="sec-head"><p class="section-label">Свяжитесь с нами</p><h2 class="section-title">Контакты</h2><div class="gold-line"></div></div>
    <div class="contact-grid">
      <div>
        <div class="contact-icon" aria-hidden="true">✉</div>
        <div><p class="section-label contact-label">Email</p><p class="contact-val">info@fbk-target.ru</p><p class="contact-sub">Пишите нам по любым вопросам</p></div>
      </div>
      <div>
        <div class="contact-icon" aria-hidden="true">☎</div>
        <div><p class="section-label contact-label">Телефон</p><p class="contact-val">+7 913 764 42 84</p><p class="contact-sub">Пн–Пт, с 9:00 до 15:00 МСК</p></div>
      </div>
    </div>
    <div>
      <p class="section-label footer-head">Социальные сети</p>
      <div class="social-row">
        <a href="#" class="btn-outline">ВКонтакте</a>
        <a href="#" class="btn-outline">Telegram</a>
        <a href="#" class="btn-outline">TikTok</a>
      </div>
    </div>
  </section>
  </main>

  <footer class="site-footer">
    <div class="footer-grid">
      <div>
        <div class="footer-brand">
          <img src="./img/target_avatar.jpg" alt="ФБК Таргет" width="1080" height="1080" loading="lazy" class="u-photo-mini">
          <span><span class="font-display gold-text footer-brand-fbk">ФБК</span><span class="font-display footer-brand-name">ТАРГЕТ</span></span>
        </div>
        <p class="footer-about">Профессиональный флорбольный клуб. Основан в 2026 году.</p>
      </div>
      <nav aria-label="Навигация в подвале">
        <p class="section-label footer-head">Навигация</p>
        <div class="footer-nav-grid">
          ${footerLinks}
        </div>
      </nav>
      <div>
        <p class="section-label footer-head">Документы</p>
        <div class="footer-links">
          <a href="./otchetnost-ano-2026.pdf" download class="doc-link"><svg width="14" height="16" viewBox="0 0 14 16" fill="none" class="u-shrink-0" aria-hidden="true"><rect x="1" y="1" width="9" height="14" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M4 6h6M4 9h6M4 12h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M10 1v3.5H13" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>Отчётность АНО за 2026 год</a>
          <a href="./ustav-ano.pdf" download class="doc-link"><svg width="14" height="16" viewBox="0 0 14 16" fill="none" class="u-shrink-0" aria-hidden="true"><rect x="1" y="1" width="9" height="14" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M4 6h6M4 9h6M4 12h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M10 1v3.5H13" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>Устав АНО</a>
        </div>
      </div>
      <div>
        <p class="section-label footer-head">Контакты</p>
        <div class="footer-col">
          <div><p class="section-label contact-label">Email</p><p class="contact-row">info@fbk-target.ru</p></div>
          <div><p class="section-label contact-label">Телефон</p><p class="contact-row">+7 913 764 42 84</p></div>
        </div>
      </div>
    </div>
    <div class="footer-bottom">
      <p>© 2026 ФБК «Таргет». Все права защищены.</p>
      <div class="footer-soc">
        <button type="button" data-scrolltop>ВКонтакте</button>
        <button type="button" data-scrolltop>Telegram</button>
        <a href="#">TikTok</a>
      </div>
    </div>
  </footer>

</div>
<script src="./js/app.js" defer></script>
</body>
</html>
`

mkdirSync(new URL("./vanilla", import.meta.url), { recursive: true })
writeFileSync(new URL("./vanilla/index.html", import.meta.url), html, "utf8")
console.log("vanilla/index.html сгенерирован, байт:", Buffer.byteLength(html))
