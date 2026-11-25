// Генератор статичного сайта для vanilla-версии. Запуск из корня проекта: node build.mjs
// Пишет ./vanilla/index.html + ./vanilla/players/*.html, остальные файлы (css, js, img) не трогает.
import { mkdirSync, writeFileSync } from "node:fs"

// ── 1. Данные 1:1 из src/App.tsx ─────────────────────────────────────────────

const players = [
  {
    num: 88,
    name: "Лев Герасимов",
    pos: "Нападающий",
    g: 1,
    a: 0,
    gp: 0,
    img: "lev-gerasimov.png",
    page: true,
  },
  {
    num: 10,
    name: "Кирилл Форись",
    pos: "Нападающий",
    g: 1,
    a: 1,
    gp: 0,
    img: "player-10.png",
    page: true,
  },
  {
    num: 11,
    name: "Тимофей Константинов",
    pos: "Защитник",
    g: 1,
    a: 2,
    gp: 0,
    img: "player-11.png",
    page: true,
  },
  {
    num: 83,
    name: "Макар Федоров",
    pos: "Нападающий",
    g: 3,
    a: 0,
    gp: 0,
    img: "player-83.png",
    page: true,
  },
  {
    num: 5,
    name: "Олег Бабанев",
    pos: "Нападающий",
    g: 2,
    a: 0,
    gp: 0,
    img: "player-5.png",
    page: true,
  },
  {
    num: 85,
    name: "Андрей Хабаров",
    pos: "Вратарь",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-85.png",
    page: true,
  },
  {
    num: 23,
    name: "Михаил Воронин",
    pos: "Нападающий",
    g: 1,
    a: 1,
    gp: 0,
    img: "player-23.png",
    page: true,
  },
  {
    num: 29,
    name: "Егор Кузьмин",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-29.png",
    page: true,
  },
  {
    num: 19,
    name: "Арсений Михайлов",
    pos: "Нападающий",
    g: 2,
    a: 0,
    gp: 0,
    img: "player-19.png",
    page: true,
  },
  {
    num: 31,
    name: "Павел Колесов",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-31.png",
    page: true,
  },
  {
    num: 99,
    name: "Вадим Эверт",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-99.png",
    page: true,
  },
  {
    num: 22,
    name: "Ерофей Сенчук",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-22.png",
    page: true,
  },
  {
    num: 20,
    name: "Максим Ильин",
    pos: "Защитник",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-20.png",
    page: true,
  },
  {
    num: 16,
    name: "Дмитрий Круглов",
    pos: "Вратарь",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-16.png",
    page: false,
  },
  {
    num: 95,
    name: "Артем Мысоев",
    pos: "Нападающий",
    g: 0,
    a: 1,
    gp: 0,
    img: "player-95.png",
    page: false,
  },
  {
    num: 92,
    name: "Никита Яремчук",
    pos: "Нападающий",
    g: 0,
    a: 0,
    gp: 0,
    img: "player-92.png",
    page: false,
  },
]

const coaches = [
  {
    name: "Лобачев Илья Андреевич",
    role: "Главный тренер",
    email: "info@fbk-target.ru",
    photo: "head-coach-ilya-lobachev.png",
  },
  {
    name: "Исаков Ярослав Андреевич",
    role: "Старший тренер",
    email: "info@fbk-target.ru",
    photo: "senior-coach-yaroslav-isakov.png",
  },
  {
    name: "Петухов Василий Вячеславович",
    role: "Спортивный директор",
    email: "info@fbk-target.ru",
    photo: "sport-director-vasiliy-petukhov.png",
  },
  {
    name: "Воронин Роман Андреевич",
    role: "Генеральный директор",
    email: "info@fbk-target.ru",
    photo: "general-director-roman-voronin.png",
  },
  {
    name: "Сенчук Алексей Михайлович",
    role: "Начальник команды",
    email: "info@fbk-target.ru",
    photo: "team-manager-aleksey-senchuk.png",
  },
  {
    name: "Исакова Вероника Александровна",
    role: "Контентмейкер",
    phone: "+7 913 764 42 84",
    photo: null,
  },
  {
    name: "Асылова Надежда Павловна",
    role: "Администратор",
    phone: "+7 913 764 42 84",
    photo: "administrator-nadezhda-asylova.png",
  },
]

const partners = [
  { name: "Сталкер", cat: "Генеральный партнёр", main: true },
  { name: "TARGETZONE", cat: "Официальный партнёр", main: false },
  { name: "МАГИСТРАЛЬ", cat: "Официальный партнёр", main: false },
  { name: "АЗС TIME", cat: "Официальный партнёр", main: false },
  { name: "АТЗ", cat: "Официальный партнёр", main: false },
  { name: "М2", cat: "IT-партнёр", main: false },
]

const standings = [
  { team: "ФБК Таргет", isTarget: true },
  { team: "Варягъ", isTarget: false },
  { team: "Нижегородец", isTarget: false },
  { team: "Юность-НН", isTarget: false },
  { team: "Спартак", isTarget: false },
  { team: "Барракуда ", isTarget: false },
  { team: "Кольчуга-УМ", isTarget: false },
  { team: "Норд Сити", isTarget: false },
  { team: "Ирбис", isTarget: false },
  { team: "Невская дружина", isTarget: false },
]

// Порядок строк таблицы результатов и статистика — как в App.tsx
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

const matchResults = [
  { home: "Ирбис", homeScore: 3, awayScore: 4, away: "Спартак" },
  { home: "Нижегородец", homeScore: 1, awayScore: 6, away: "Норд Сити" },
  { home: "Варягъ", homeScore: 3, awayScore: 5, away: "ФБК Таргет" },
  { home: "Кольчуга-УМ", homeScore: 0, awayScore: 9, away: "Невская дружина" },
  { home: "Барракуда ", homeScore: 4, awayScore: 7, away: "Юность-НН" },
  { home: "Невская дружина", homeScore: 10, awayScore: 1, away: "ФБК Таргет" },
  { home: "Невская дружина", homeScore: 5, awayScore: 4, away: "Варягъ" },
  { home: "Спартак", homeScore: 5, awayScore: 1, away: "Юность-НН" },
  { home: "Спартак", homeScore: 1, awayScore: 0, away: "Барракуда " },
  { home: "Ирбис", homeScore: 6, awayScore: 1, away: "Норд Сити" },
  { home: "Ирбис", homeScore: 8, awayScore: 3, away: "Кольчуга-УМ" },
  { home: "Норд Сити", homeScore: 6, awayScore: 1, away: "Юность-НН" },
  { home: "ФБК Таргет", homeScore: 6, awayScore: 2, away: "Барракуда " },
  { home: "Кольчуга-УМ", homeScore: 3, awayScore: 0, away: "Нижегородец" },
  {
    home: "Нижегородец",
    homeScore: 3,
    awayScore: 4,
    away: "Варягъ",
    overtime: true,
  },
]

const navItems = [
  { id: "team", label: "Команда" },
  { id: "coaching", label: "Руководство" },
  { id: "standings", label: "Первенство России U19" },
  { id: "history", label: "История" },
  { id: "partners", label: "Партнёры" },
  { id: "contacts", label: "Контакты" },
]

// ── 2. Страницы игроков (текст 1:1 из компонентов *Profile в App.tsx) ────────

const profiles = [
  {
    num: 85,
    kicker: "Вратарь",
    title: "Живёт игрой",
    lead: "Вратарь, который живёт игрой",
    facts: [
      ["Дата рождения", "27.02.2009"],
      ["Амплуа", "Вратарь"],
      ["Игровой стаж", "9–10 лет"],
    ],
    quote: "Без поражений не бывает побед.",
    intro: "Во флорбол Андрей пришёл почти случайно, но очень вовремя.",
    before: [
      "В первом классе он увидел на стенде расписание кружков — и зацепился взглядом за слово «флорбол». Многие знакомые уже занимались, и он решил попробовать. Сразу понял: это его. Тогда он начинал полевым, но в итоге оказался в воротах и уже не представлял себя на другой позиции.",
      "Девять лет в спорте — серьёзный срок. Андрей любит флорбол за динамику, скорость и моторику. Говорит, что здесь нет «кто-то один» — играют все, и команда решает всё. Физика, мораль, резкость, принятие решений — вот что важно.",
    ],
    orient:
      "Как вратарь, он равняется на Влада Сманцева и старается расти. Для Андрея флорбол — не хобби и не просто образ жизни: он живёт этим, хочет стать сильнее и готов работать на результат.",
    after: [
      "Проект ФБК «Таргет» вызвал у него большое удивление — впервые он видит, чтобы юниорскую команду спонсировали на таком уровне. Это редкость, и Андрей ценит возможность, стараясь использовать её на максимум.",
      "Ожидания от сезона — работа и выход на новый уровень. Уже пора быть в юниорской лиге U19. Родители сначала не поверили, а потом очень обрадовались. Мама особенно удивлена тем, что такие возможности могут дать простым ребятам. Она рада, что Андрея пригласили и помогли оказаться здесь.",
    ],
  },
  {
    num: 88,
    kicker: "Нападающий",
    title: "С характером",
    lead: "Нападающий с характером",
    facts: [
      ["Дата рождения", "02.03.2011"],
      ["Амплуа", "Нападающий"],
      ["Хват", "Левый"],
      ["Игровой стаж", "7 лет"],
    ],
    quote: "Слабые ищут оправдания, сильные создают историю.",
    intro: "Во флорбол Лев пришёл благодаря старшему брату.",
    before: [
      "Сначала было непонятно — нравится или нет, чувства были смешанными. Но со временем игра затянула. Теперь он уже не представляет себя без площадки.",
      "Семь лет в спорте — срок серьёзный. Лев отмечает, что его держат скорость, динамика и командная работа. Финты, обводка, борьба до конца — это то, ради чего он выходит на площадку.",
    ],
    orient:
      "Нападающий с левым хватом, он равняется на Трофимова. Старается подмечать детали в игре кумира и переносить их в свою игру. Для Льва флорбол — не хобби. Он называет это профессиональным спортом и относится к нему соответственно.",
    after: [
      "О проекте ФБК «Таргет» Лев узнал и сразу заинтересовался. Его привлекли новый уровень, сильный тренерский штаб и возможность расти рядом с хорошими игроками. Ожидания от сезона — победы и возможность играть по-мужски, на равных с сильными соперниками.",
      "Родители, когда узнали, что Лев попал в «Таргет», обрадовались и поддержали сына в этом шаге.",
    ],
  },
  {
    num: 10,
    kicker: "Нападающий",
    title: "С характером",
    lead: "Нападающий с характером",
    facts: [
      ["Дата рождения", "08.07.2010"],
      ["Амплуа", "Нападающий"],
      ["Хват", "Левый"],
      ["Игровой стаж", "5 лет"],
    ],
    quote: "Всего одна ошибка — и ты ошибся.",
    intro: "Во флорбол Кирилл пришёл не случайно.",
    before: [
      "До этого он восемь лет занимался большим теннисом — с трёх лет. А потом пошёл с подругой на флорбол. Сначала совмещал, но в итоге выбрал командную игру. Говорит, что в теннисе ты один на один, а здесь — команда, движение и поддержка.",
      "Пять лет во флорболе не прошли даром. Кирилл ценит этот вид спорта за скорость, лёгкость и принятие решений. И особенно — за командный дух. В его жизни больше друзей из флорбола, чем вне его. И это говорит о многом.",
    ],
    orient:
      "Нападающий с левым хватом, он равняется на Егорова Егора. Старается перенимать лучшее у тех, кто уже на виду. Для Кирилла флорбол — профессиональный спорт. Он не просто играет, он хочет расти и заявлять о себе.",
    after: [
      "В проекте ФБК «Таргет» его привлекло новое: новые знакомства, новый уровень и шанс влиться в серьёзную команду. Ожидания от сезона — попасть в топ-5 и играть по-взрослому.",
      "Мама Кирилла очень рада его участию в проекте и очень хочет, чтобы он прошёл отбор.",
    ],
  },
  {
    num: 11,
    kicker: "Защитник",
    title: "Не сдаётся",
    lead: "Защитник, который не сдаётся",
    facts: [
      ["Дата рождения", "21.01.2010"],
      ["Амплуа", "Защитник"],
      ["Хват", "Левый"],
      ["Игровой стаж", "5 лет"],
    ],
    quote: "Никогда не сдавайтесь, идите к своей цели.",
    intro: "Во флорбол Тимофей пришёл через акробатику и футбол.",
    before: [
      "Всё случилось в нужный момент: вместе с другом, в школьной секции. И он сразу понял — это его игра.",
      "Пять лет в спорте он ценит флорбол за динамику и командный дух. В его жизни больше друзей из флорбола, чем вне него — потому что здесь общий язык, общие цели и взаимная поддержка.",
    ],
    orient:
      "Защитник с левым хватом, Тимофей равняется на Михаила Синицу. Смотрит, учится и старается перенимать лучшее. Для него флорбол — профессиональный спорт. Он не играет ради хобби, а хочет расти и достигать серьёзных результатов.",
    after: [
      "Ожидания от сезона — войти в тройку и делать для этого всё возможное.",
      "В проекте ФБК «Таргет» его привлекло то, что здесь много знакомых — а значит, есть с кем работать и с кем расти. Родители, когда узнали, очень обрадовались.",
    ],
  },
  {
    num: 83,
    kicker: "Нападающий",
    title: "Десять лет в игре",
    lead: "Нападающий с десятилетним стажем",
    facts: [
      ["Дата рождения", "12.09.2009"],
      ["Амплуа", "Нападающий"],
      ["Хват", "Левый"],
      ["Игровой стаж", "10 лет"],
    ],
    quote: "Верь в себя, и всё получится.",
    intro: "Во флорбол Макар пришёл через школьную секцию.",
    before: [
      "Родители записали его, и он сразу втянулся. С тех пор прошло десять лет, а игра так и осталась с ним.",
      "Макар ценит флорбол за скорость и командную работу. В его окружении больше друзей из флорбола — с ними проще, понятнее и интереснее.",
    ],
    orient:
      "Нападающий с левым хватом, он равняется на Трофимова и старается расти, глядя на сильных игроков. Для Макара вопрос о статусе флорбола пока открыт. Он ещё определяет, станет ли это профессией на всю жизнь, но уже сейчас готов пробовать новое и работать на результат.",
    after: [
      "Ожидания от сезона — попробовать себя в новом месте, выиграть и показать, на что способен. Проект ФБК «Таргет» даёт ему такую возможность.",
    ],
  },
  {
    num: 5,
    kicker: "Левый нападающий",
    title: "В удовольствие",
    lead: "Нападающий, который выматывает в удовольствие",
    facts: [
      ["Дата рождения", "26.08.2010"],
      ["Амплуа", "Левый нападающий"],
      ["Хват", "Левый"],
      ["Игровой стаж", "6 лет"],
    ],
    quote: "Айайай",
    intro: "Во флорбол Олег пришёл из каратэ.",
    before: [
      "Мама узнала о секции, привела, и уже на первой тренировке — бег, движение, всё быстро закрутилось. И затянуло.",
      "Идёт шестой год в спорте. Олегу нравится, что флорбол выматывает в удовольствие. Он говорит, что многому ещё учится, особенно командной работе в нападении. Важно найти того, с кем можно сыграться.",
    ],
    orient:
      "Нападающий с левым хватом, он равняется на Севу Иванова. Злость на поле переводит в бег — это его способ переключаться и работать дальше. Для Олега флорбол — профессиональный спорт. Он хочет расти, получать больше нагрузок и прокачивать навыки.",
    after: [
      "У Олега больше друзей из флорбольной жизни. Ожидания от сезона — увеличенные физические нагрузки, личный рост, готовность брать на себя больше заданий и целей и достигать их.",
      "Родители Олега, когда узнали, что он попал в проект, были в шоке и очень обрадовались. Мама была особенно рада. Олег говорит: что-то новое — это всегда круто, это опыт и возможность попробовать себя в другом месте.",
    ],
  },
  {
    num: 23,
    kicker: "Нападающий",
    title: "За голами",
    lead: "Нападающий, который ушёл в атаку за голами",
    facts: [
      ["Дата рождения", "23.08.2011"],
      ["Амплуа", "Нападающий"],
      ["Хват", "Левый"],
      ["Игровой стаж", "8 лет"],
    ],
    quote: "Лишь утратив всё до конца, мы обретаем свободу.",
    intro: "Во флорбол Михаил пришёл из хоккея.",
    before: [
      "Семь лет он стоял в воротах — всё это время был вратарём. Совмещал, пробовал, но в итоге сделал выбор. Хотелось забивать, хотелось быть в атаке. Говорит: «В рамке устал стоять» — и ушёл во флорбол.",
      "Восемь лет в спорте. Михаилу нравятся динамика, сплочённость, принятие решений и яркость побед. Флорбол даёт ему то, чего не хватало в хоккее, — движение вперёд.",
    ],
    orient:
      "Нападающий с левым хватом, он равняется на Вилли Ластика. Старается быть быстрым, точным и решать исход игры. Для Михаила флорбол — профессиональный спорт, хотя он не исключает совмещения с чем-то ещё.",
    after: [
      "У Михаила больше друзей из флорбола — здесь он нашёл свою команду и своё окружение. Ожидания от сезона — подержать в руках кубок первенства. Самая главная цель — победа.",
      "Родители поддерживают Михаила и стараются делать всё возможное, чтобы он мог расти и добиваться результатов. Он им за это очень благодарен.",
    ],
  },
  {
    num: 29,
    kicker: "Защитник",
    title: "Реалистичный взгляд",
    lead: "Защитник с реалистичным взглядом",
    facts: [
      ["Дата рождения", "17.02.2009"],
      ["Амплуа", "Защитник"],
      ["Хват", "Правый"],
      ["Игровой стаж", "С 2018 года"],
    ],
    quote: "Не мы такие, жизнь такая.",
    intro: "Во флорбол Егор пришёл из хоккея на траве.",
    before: [
      "Команда распалась, он ушёл в бассейн, а потом его команда перешла во флорбол. Решил попробовать. Сработало: знакомые рядом, игра пошла — и он остался.",
      "Егор не строит из себя суперзвезду, но и не недооценивает себя. Говорит, что быстро бегает, и это его сильная сторона. Друзей у него поровну — из флорбола и вне спорта.",
    ],
    orient:
      "Защитник с правым хватом, он называет Лобачева Илью в числе тех, на кого стоит равняться. К флорболу Егор относится как к хорошему хобби, но без фанатизма. При этом он готов работать и пробовать новое.",
    after: [
      "Ожидания от сезона — совместить подготовку с ЕГЭ, а ещё круто взять Р-Лигу и показать результат с «Таргет». Он понимает, что сезон будет непростым, но видит в этом возможность.",
      "Мама поддерживает: «Круто, поедешь повидать города».",
    ],
  },
  {
    num: 19,
    kicker: "Нападающий",
    title: "В крови",
    lead: "Нападающий с хоккейными генами и желанием",
    facts: [
      ["Дата рождения", "17.09.2009"],
      ["Амплуа", "Нападающий"],
      ["Хват", "Левый"],
      ["Игровой стаж", "10 лет"],
    ],
    quote: "Never give up.",
    intro: "Арсений пришёл во флорбол не случайно.",
    before: [
      "Отец, хоккеист, записал его в секцию — и Арсений сразу понял: это его игра. Говорит, что гены дали о себе знать: любовь к спорту, движению и борьбе у него в крови.",
      "Десять лет он в игре. За это время флорбол стал для него не просто увлечением, а серьёзным делом. Он любит этот вид спорта за то, что здесь нужно думать, принимать решения и работать в команде.",
    ],
    orient:
      "Нападающий с левым хватом, он равняется на Виллу Ластика — смотрит, учится и перенимает лучшее. Флорбол для Арсения — профессиональный уровень. Он не играет «для галочки», он хочет расти и побеждать.",
    after: [
      "Друзей у Арсения больше вне спорта, но на площадке он полностью свой. Ожидания от сезона максимальные: выиграть всё, что можно. И он настроен серьёзно.",
      "Родители полностью поддерживают. Говорят: «Молодец, двигайся дальше». Арсений чувствует, что за ним — надёжный тыл.",
    ],
  },
  {
    num: 31,
    kicker: "Защитник",
    title: "Вышел и делает",
    lead: "Защитник, который вышел и делает",
    facts: [
      ["Дата рождения", "31.12.2010"],
      ["Амплуа", "Защитник"],
      ["Хват", "Левый"],
      ["Игровой стаж", "10-й год"],
    ],
    quote: "Выхожу и делаю.",
    intro: "Во флорбол Павел пришёл из футбола.",
    before: [
      "Увидел секцию в школе, попробовал совмещать, но в итоге выбрал одно. Говорит, что устал от футбола, а здесь нашёл то, что искал: динамику, контакт и возможность проявить себя.",
      "Десять лет в спорте. Павел признаётся, что всегда хотел заниматься хоккеем, но флорбол дал ему не меньше: друзей, голы, финты и ту самую командную атмосферу, ради которой стоит выходить на площадку.",
    ],
    orient:
      "Защитник с левым хватом, он равняется на Егорова Егора. Вдохновляется игроками, которые умеют держать удар и вести за собой. Для Павла флорбол — не хобби и не просто спорт. Это жизнь.",
    after: [
      "У Павла больше друзей из флорбола — здесь он нашёл своих. Ожидания от сезона — первое место. Он настроен серьёзно и готов работать ради результата.",
      "Родители поддерживают: «Молодец». И Павел знает, что это не просто слова.",
    ],
  },
  {
    num: 99,
    kicker: "Защитник",
    title: "Нашёл своё",
    lead: "Защитник, который за компанию нашёл своё",
    facts: [
      ["Дата рождения", "08.07.2010"],
      ["Амплуа", "Защитник"],
      ["Хват", "Правый"],
      ["Игровой стаж", "6 лет"],
    ],
    quote: "Тише едешь — дальше будешь.",
    intro: "Во флорбол Вадим пришёл через несколько видов спорта.",
    before: [
      "Начинал с футбола, пробовал плавание. Футбол закончился, но спорт не отпускал. Потом он увидел объявление в школе и пошёл за компанию с другом. Так и остался. Говорит, что понравилось с первого раза — и до сих пор не отпускает.",
      "Вадиму нравятся во флорболе динамичность, контратаки, красота игры и командный дух. Всё то, что делает этот спорт живым и зрелищным.",
    ],
    orient:
      "Защитник с правым хватом. Среди тех, на кого равняется, Вадим называет Севу Иванова. Сам он пока не знает, станет ли флорбол профессией, но хотел бы попробовать.",
    after: [
      "Друзей у него больше вне флорбола, но на площадке он чувствует себя своим. Ожидания от сезона в ФБК «Таргет» — хорошо отыграть, занять призовые места и показать результат.",
      "Родители поддерживают: «Пробуй, мы надеемся и верим». Это придаёт сил двигаться дальше.",
    ],
  },
  {
    num: 22,
    kicker: "Защитник",
    title: "Выбирает флорбол",
    lead: "Защитник, который совмещает, но выбирает флорбол",
    facts: [
      ["Дата рождения", "29.07.2011"],
      ["Амплуа", "Защитник"],
      ["Хват", "Левый"],
      ["Игровой стаж", "7 лет"],
    ],
    quote: "Награда — это сам спорт, а не слава.",
    intro: "Во флорбол Ерофей пришёл через футбол.",
    before: [
      "До сих пор совмещает, но именно флорбол затянул по-настоящему. В школе тренер Василий Вячеславович рассказывал о флорболе, Ерофей решил попробовать — и сразу понял: это его игра.",
      "Сразу получилось. Скорость, динамичность и возможность играть в команде — вот что его держит.",
    ],
    orient:
      "Защитник с левым хватом. Чаще всего он наблюдает за Трофимовым: смотрит, учится и старается перенимать лучшее. Для Ерофея флорбол — не хобби, а профессиональный уровень. Он уже настроен серьёзно.",
    after: [
      "Друзья у Ерофея в основном из флорбола. Здесь он нашёл свою компанию и своих людей. Ожидания от сезона — попасть в топ-3.",
      "Родители рады его успехам и хотят, чтобы он добился ещё большего. Ерофей готов работать дальше.",
    ],
  },
  {
    num: 20,
    kicker: "Защитник",
    title: "Пришёл и остался",
    lead: "Защитник, который пришёл за другом и остался",
    facts: [
      ["Дата рождения", "18.03.2011"],
      ["Амплуа", "Защитник"],
      ["Хват", "Левый"],
      ["Игровой стаж", "Около 8 лет"],
    ],
    quote: "Ни пуха ни пера.",
    intro: "Во флорбол Максим пришёл ещё в детском саду.",
    before: [
      "Он пошёл за другом. С самого начала понравилось, и с тех пор Максим уже не представлял себя без этой игры.",
      "Ему нравятся во флорболе скорость и командная работа. В его окружении больше друзей из флорбола, чем вне него.",
    ],
    orient:
      "Защитник с левым хватом. Среди тех, на кого равняется, Максим называет Всеволода Иванова. Проект ФБК «Таргет» ему интересен — он видит в нём возможность расти и пробовать себя на новом уровне.",
    after: [
      "Родители отнеслись нейтрально, но с поддержкой: «Молодец». Максим чувствует, что они рядом, даже если не говорят об этом громко.",
    ],
  },
]

const playerByNum = new Map(players.map((p) => [p.num, p]))
for (const profile of profiles) {
  const p = playerByNum.get(profile.num)
  if (!p || !p.page)
    throw new Error(`профиль ${profile.num} не связан с карточкой-ссылкой`)
  profile.player = p
}

const siteUrlBase = "https://fbk-target.ru/"
const playerSlug = (p) => `players/${p.num}-${translit(p.name)}.html`

// ── 3. Утилиты ───────────────────────────────────────────────────────────────

function translit(str) {
  const map = {
    а: "a",
    б: "b",
    в: "v",
    г: "g",
    д: "d",
    е: "e",
    ё: "e",
    ж: "zh",
    з: "z",
    и: "i",
    й: "y",
    к: "k",
    л: "l",
    м: "m",
    н: "n",
    о: "o",
    п: "p",
    р: "r",
    с: "s",
    т: "t",
    у: "u",
    ф: "f",
    х: "h",
    ц: "ts",
    ч: "ch",
    ш: "sh",
    щ: "sch",
    ъ: "",
    ы: "y",
    ь: "",
    э: "e",
    ю: "yu",
    я: "ya",
  }
  return str
    .toLowerCase()
    .split("")
    .map((ch) => (map[ch] !== undefined ? map[ch] : ch))
    .join("")
    .replace(/\s+/g, "-")
}

const esc = (s) =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")

const posOrder = { Вратарь: 0, Нападающий: 1, Защитник: 2 } // сортировка как в App.tsx
const playersSorted = [...players].sort(
  (a, b) => posOrder[a.pos] - posOrder[b.pos],
)

// ── 4. Шаблоны секций главной ────────────────────────────────────────────────

const playerCards = playersSorted
  .map((p) => {
    const gk = p.pos === "Вратарь"
    const inner = `<div class="player-photo">
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
      <div class="card-accent"></div>`
    return p.page
      ? `<a class="player-card" href="./${playerSlug(p)}" aria-label="Открыть страницу ${esc(p.name)}">
      ${inner}
    </a>`
      : `<article>
      ${inner}
    </article>`
  })
  .join("\n")

const staffCards = coaches
  .map((c) => {
    const photo = c.photo
      ? `<div class="staff-photo"><img src="./img/${c.photo}" alt="${esc(c.name)}" width="1080" height="1080" loading="lazy" decoding="async"></div>`
      : '<div class="staff-icon" aria-hidden="true">🎯</div>'
    const contact = c.email
      ? `Email: <a href="mailto:${c.email}" class="gold-text u-fw-600 u-no-deco">${c.email}</a>`
      : `Тел.: <span class="gold-text u-fw-600">${c.phone}</span>`
    return `<article>
      ${photo}
      <p class="section-label staff-role">${esc(c.role)}</p>
      <p class="staff-name">${esc(c.name)}</p>
      <p class="staff-contact">${contact}</p>
      <div class="staff-corner"></div>
    </article>`
  })
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

const statValues = (team) => {
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
        p.main ? " is-main" : ""
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

const jsonLd = `{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SportsTeam",
      "@id": "${siteUrlBase}#team",
      "name": "ФБК Таргет",
      "sport": "Floorball",
      "url": "${siteUrlBase}",
      "logo": "${siteUrlBase}apple-touch-icon.png",
      "email": "info@fbk-target.ru",
      "telephone": "+7 913 764-42-84",
      "memberOf": { "@type": "SportsOrganization", "name": "Первенство России U19" }
    },
    {
      "@type": "WebSite",
      "@id": "${siteUrlBase}#website",
      "url": "${siteUrlBase}",
      "name": "ФБК Таргет",
      "inLanguage": "ru-RU",
      "publisher": { "@id": "${siteUrlBase}#team" }
    }
  ]
}`

// ── 5. Главная страница ──────────────────────────────────────────────────────

const indexTitle = "ФБК Таргет — флорбольный клуб | Состав, таблица U19"
const indexDescription =
  "Флорбольный клуб «Таргет»: состав команды, тренерский штаб, турнирная таблица Первенства России U19, история клуба, партнёры и контакты."

const indexHtml = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(indexTitle)}</title>
  <meta name="description" content="${esc(indexDescription)}">
  <link rel="canonical" href="${siteUrlBase}">
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
  <meta property="og:url" content="${siteUrlBase}">
  <meta property="og:image" content="${siteUrlBase}og-cover.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="ФБК Таргет — флорбольный клуб">
  <meta name="twitter:description" content="Состав команды, турнирная таблица Первенства России U19, история клуба, партнёры и контакты.">
  <meta name="twitter:image" content="${siteUrlBase}og-cover.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap">
  <link rel="stylesheet" href="./css/style.css">
  <script type="application/ld+json">
${jsonLd}
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

  <main id="main">
  <section class="hero" aria-label="Флорбольный клуб Таргет">
    <img src="./img/target-hero-texture.png" alt="" class="hero-bg" width="800" height="800" fetchpriority="high">
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

// ── 6. Страница игрока ──────────────────────────────────────────────────────

function profilePage(profile) {
  const p = profile.player
  const [first, ...rest] = p.name.split(" ")
  const last = rest.join(" ")
  const role = profile.kicker.toLowerCase()
  const canonical = siteUrlBase + playerSlug(p)
  const title = `${p.name} — игрок ФБК Таргет | № ${p.num}`
  const description = `${p.name}, ${role} ФБК «Таргет», № ${p.num}. ${profile.lead}. Дата рождения ${profile.facts[0][1]}.`
  const facts = profile.facts
    .map(
      ([label, value]) =>
        `<div class="profile-fact"><p>${esc(label)}</p><strong>${esc(value)}</strong></div>`,
    )
    .join("\n                  ")
  const paragraphsBefore = profile.before
    .map((t) => `<p>${esc(t)}</p>`)
    .join("\n                ")
  const paragraphsAfter = profile.after
    .map((t) => `<p>${esc(t)}</p>`)
    .join("\n                ")

  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  <link rel="canonical" href="${canonical}">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <meta name="theme-color" content="#080808">
  <link rel="icon" href="../favicon.svg" type="image/svg+xml">
  <link rel="icon" href="../favicon-32.png" sizes="32x32" type="image/png">
  <link rel="icon" href="../favicon-16.png" sizes="16x16" type="image/png">
  <link rel="apple-touch-icon" href="../apple-touch-icon.png" sizes="180x180">
  <meta property="og:type" content="profile">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="ФБК Таргет">
  <meta property="og:title" content="${esc(p.name)} — ФБК Таргет">
  <meta property="og:description" content="${esc(profile.lead)}">
  <meta property="og:url" content="${canonical}">
  <meta property="og:image" content="${siteUrlBase}og-cover.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(p.name)} — ФБК Таргет">
  <meta name="twitter:description" content="${esc(profile.lead)}">
  <meta name="twitter:image" content="${siteUrlBase}og-cover.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap">
  <link rel="stylesheet" href="../css/style.css">
  <script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Person",
  "name": "${esc(p.name)}",
  "jobTitle": "${esc(profile.kicker)}",
  "memberOf": { "@type": "SportsTeam", "name": "ФБК Таргет", "url": "${siteUrlBase}" },
  "image": "${siteUrlBase}img/${p.img}",
  "url": "${canonical}"
}
  </script>
</head>
<body>
<a class="skip-link" href="#main">Перейти к содержимому</a>
<div class="player-profile">

  <header class="player-profile-nav">
    <a href="../index.html#team" class="profile-back" aria-label="Вернуться к составу команды">
      <span class="profile-back-icon" aria-hidden="true">←</span>
      <span class="profile-back-text">Назад к команде</span>
    </a>
    <a href="../index.html" class="profile-brand">
      <img src="../img/target_avatar.jpg" alt="ФБК Таргет" width="1080" height="1080">
      <span class="profile-brand-text">
        <span class="font-display gold-text">ФБК</span>
        <span class="font-display">ТАРГЕТ</span>
      </span>
    </a>
  </header>

  <main id="main">
    <section class="player-profile-hero">
      <div class="profile-grid-pattern" aria-hidden="true"></div>

      <div class="profile-hero-grid">
        <div class="profile-portrait">
          <div class="profile-number-bg" aria-hidden="true">${p.num}</div>
          <div class="profile-photo-glow" aria-hidden="true"></div>
          <img src="../img/${p.img}" alt="${esc(p.name)}, ${role} ФБК Таргет" width="800" height="701" class="profile-photo">
          <div class="profile-photo-fade" aria-hidden="true"></div>
        </div>

        <p class="profile-kicker section-label">${esc(profile.kicker)} · № ${p.num}</p>

        <div class="profile-summary">
          <h1 class="profile-title">${esc(first)}<span>${esc(last)}</span></h1>
          <p class="profile-lead">${esc(profile.lead)}</p>

          <div class="profile-facts">
            ${facts}
          </div>
        </div>
      </div>
    </section>

    <section class="profile-body">
      <div class="profile-body-grid">
        <div>
          <p class="section-label profile-body-label">История игрока</p>
          <h2 class="section-title">${esc(profile.title)}</h2>
          <div class="gold-line"></div>

          <blockquote class="profile-quote">
            <span aria-hidden="true">“</span>
            <p>${esc(profile.quote)}</p>
            <footer>${esc(p.name)}</footer>
          </blockquote>
        </div>

        <article class="profile-story">
          <p class="profile-story-intro">${esc(profile.intro)}</p>
          ${paragraphsBefore}

          <div class="profile-highlight">
            <p class="section-label profile-highlight-label">Ориентир</p>
            <p>${esc(profile.orient)}</p>
          </div>

          ${paragraphsAfter}
        </article>
      </div>
    </section>

    <section class="profile-cta">
      <p class="section-label profile-cta-label">ФБК «Таргет» · Сезон 2026/27</p>
      <p class="font-display profile-cta-title">Команда решает всё</p>
      <a href="../index.html#team" class="btn-outline profile-cta-btn">Смотреть весь состав</a>
    </section>
  </main>

</div>
</body>
</html>
`
}

// ── 7. Запись ────────────────────────────────────────────────────────────────

mkdirSync(new URL("./vanilla", import.meta.url), { recursive: true })
mkdirSync(new URL("./vanilla/players", import.meta.url), { recursive: true })

writeFileSync(
  new URL("./vanilla/index.html", import.meta.url),
  indexHtml,
  "utf8",
)
let bytes = Buffer.byteLength(indexHtml)

for (const profile of profiles) {
  const page = profilePage(profile)
  writeFileSync(
    new URL(`./vanilla/${playerSlug(profile.player)}`, import.meta.url),
    page,
    "utf8",
  )
  bytes += Buffer.byteLength(page)
}

console.log(
  `vanilla/index.html + ${profiles.length} страниц игроков сгенерированы, байт: ${bytes}`,
)
