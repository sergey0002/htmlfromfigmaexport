import { FormEvent, useEffect, useMemo, useState } from "react";

const heroImage =
  "https://images.unsplash.com/photo-1684762257859-8890f883b3a9?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixlib=rb-4.1.0&q=85&w=1800";
const coastImage =
  "https://images.unsplash.com/photo-1670168476312-50278e456129?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixlib=rb-4.1.0&q=82&w=1200";
const mountainImage =
  "https://images.unsplash.com/photo-1668846488612-7dcac5776df7?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixlib=rb-4.1.0&q=82&w=1200";

type IconName =
  | "arrow"
  | "chevron"
  | "menu"
  | "close"
  | "play"
  | "calendar"
  | "pin"
  | "phone"
  | "mail"
  | "download"
  | "quote"
  | "search"
  | "check"
  | "users";

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    arrow: (
      <>
        <path d="M5 12h14" />
        <path d="m14 7 5 5-5 5" />
      </>
    ),
    chevron: <path d="m9 18 6-6-6-6" />,
    menu: (
      <>
        <path d="M4 7h16M4 12h16M4 17h16" />
      </>
    ),
    close: (
      <>
        <path d="m6 6 12 12M18 6 6 18" />
      </>
    ),
    play: <path d="m9 7 8 5-8 5Z" />,
    calendar: (
      <>
        <path d="M6 3v3m12-3v3M4 9h16" />
        <rect x="4" y="5" width="16" height="16" rx="2" />
      </>
    ),
    pin: (
      <>
        <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
        <circle cx="12" cy="10" r="2.5" />
      </>
    ),
    phone: (
      <path d="M8 3H5a2 2 0 0 0-2 2c0 8.8 7.2 16 16 16a2 2 0 0 0 2-2v-3l-4-1-2 3c-4-1.7-7.3-5-9-9l3-2-1-4Z" />
    ),
    mail: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 7 9 6 9-6" />
      </>
    ),
    download: (
      <>
        <path d="M12 3v12m-5-5 5 5 5-5M4 21h16" />
      </>
    ),
    quote: (
      <path d="M7 10H4a5 5 0 0 1 5-5v2a3 3 0 0 0-3 3h3v7H4v-7m11 0h-3a5 5 0 0 1 5-5v2a3 3 0 0 0-3 3h3v7h-5v-7" />
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    users: (
      <>
        <circle cx="9" cy="8" r="4" />
        <path d="M2 21c0-4 3-7 7-7s7 3 7 7M16 4a4 4 0 0 1 0 8m2 3c2.4.8 4 3 4 6" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

const nav = [
  ["Главная", "home"],
  ["О партии", "about"],
  ["Программа", "program"],
  ["Люди", "people"],
  ["Деятельность", "activity"],
  ["Регионы", "regions"],
  ["Медиа", "media"],
  ["Приемная", "reception"],
  ["Контакты", "contacts"],
];

const programItems = [
  {
    id: "economy",
    number: "01",
    title: "Экономика",
    text: "Новые рабочие места, поддержка предпринимателей и прозрачные правила для инвестиций.",
    stat: "+4 500",
    statLabel: "новых рабочих мест",
  },
  {
    id: "education",
    number: "02",
    title: "Образование",
    text: "Современные школы, достойный труд учителя и возможности для молодежи.",
    stat: "32",
    statLabel: "школы нового формата",
  },
  {
    id: "health",
    number: "03",
    title: "Здравоохранение",
    text: "Доступная помощь в каждом районе и обновление ключевых медицинских центров.",
    stat: "7/7",
    statLabel: "районов с диагностикой",
  },
  {
    id: "culture",
    number: "04",
    title: "Культура и язык",
    text: "Сохранение абхазского языка, наследия и поддержка современной культуры.",
    stat: "100+",
    statLabel: "культурных инициатив",
  },
  {
    id: "security",
    number: "05",
    title: "Безопасность",
    text: "Защита граждан, устойчивость государства и современная гражданская оборона.",
    stat: "24/7",
    statLabel: "единый центр реагирования",
  },
  {
    id: "world",
    number: "06",
    title: "Внешняя политика",
    text: "Прагматичный диалог, новые связи и защита интересов Абхазии в мире.",
    stat: "12",
    statLabel: "новых партнерств",
  },
];

const news = [
  {
    tag: "Экономика",
    date: "18 июня 2025",
    title: "Представили пакет мер поддержки малого бизнеса",
    image: coastImage,
  },
  {
    tag: "Регионы",
    date: "14 июня 2025",
    title: "В Очамчыре открылась новая общественная приемная",
    image: mountainImage,
  },
  {
    tag: "Общество",
    date: "10 июня 2025",
    title: "Волонтеры восстановили школьную библиотеку в Ткуарчале",
    image: heroImage,
  },
];

const people = [
  {
    initials: "АБ",
    name: "Аслан Бжания",
    role: "Депутат, экономист",
    story: "Помог создать программу грантов для молодых предпринимателей.",
  },
  {
    initials: "МГ",
    name: "Мадина Гунба",
    role: "Волонтер, врач",
    story: "Организует выездные приемы в отдаленных селах.",
  },
  {
    initials: "ДА",
    name: "Денис Ардзинба",
    role: "Координатор молодежи",
    story: "Объединил 400 волонтеров по всей Абхазии.",
  },
];

function go(page: string) {
  window.location.hash = page === "home" ? "" : page;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function Button({
  children,
  onClick,
  variant = "green",
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "green" | "gold" | "outline" | "white";
  type?: "button" | "submit";
}) {
  return (
    <button type={type} onClick={onClick} className={`btn btn-${variant}`}>
      {children}
    </button>
  );
}

function Header({ page, openForm }: { page: string; openForm: (type: string) => void }) {
  const [menu, setMenu] = useState(false);
  return (
    <>
      <div className="topline">
        <div className="shell top-inner">
          <span>Политическая партия «Новая Абхазия»</span>
          <div>
            <a href="tel:+79409280022">+7 940 928-00-22</a>
            <span className="top-social">TG · VK · YT</span>
            <b>RU</b>
            <span>АБ</span>
          </div>
        </div>
      </div>
      <header>
        <div className="shell header-inner">
          <button className="logo" onClick={() => go("home")} aria-label="На главную">
            <img
              src="/assets/logo_short.png"
              alt="Новая Абхазия"
              style={{ width: 70, height: 70 }}
            />
          </button>
          <nav className="desktop-nav">
            {nav.map(([label, link]) => (
              <button key={link} className={page === link ? "active" : ""} onClick={() => go(link)}>
                {label}
              </button>
            ))}
          </nav>
          <Button variant="gold" onClick={() => openForm("Вступить в партию")}>
            Вступить
          </Button>
          <button className="mobile-menu" onClick={() => setMenu(!menu)} aria-label="Меню">
            <Icon name={menu ? "close" : "menu"} />
          </button>
        </div>
        {menu && (
          <nav className="mobile-nav">
            {nav.map(([label, link]) => (
              <button
                key={link}
                onClick={() => {
                  go(link);
                  setMenu(false);
                }}
              >
                {label}
              </button>
            ))}
          </nav>
        )}
      </header>
    </>
  );
}

function Footer({ openForm }: { openForm: (type: string) => void }) {
  return (
    <footer>
      <div className="shell footer-grid">
        <div className="footer-brand">
          <img src="/assets/logo_full.png" alt="Новая Абхазия" />
          <p>
            Сильная Абхазия — наш дом,
            <br />
            наш народ, наше будущее.
          </p>
          <div className="socials">
            <a href="#">VK</a>
            <a href="#">TG</a>
            <a href="#">YT</a>
            <a href="#">OK</a>
          </div>
        </div>
        <div>
          <h4>Партия</h4>
          <button onClick={() => go("about")}>О партии</button>
          <button onClick={() => go("program")}>Программа</button>
          <button onClick={() => go("people")}>Люди</button>
          <button onClick={() => go("activity")}>Деятельность</button>
        </div>
        <div>
          <h4>Участвовать</h4>
          <button onClick={() => openForm("Вступить в партию")}>Вступить в партию</button>
          <button onClick={() => openForm("Стать волонтером")}>Стать волонтером</button>
          <button onClick={() => openForm("Предложить идею")}>Предложить идею</button>
          <button onClick={() => go("reception")}>Виртуальная приемная</button>
        </div>
        <div>
          <h4>Контакты</h4>
          <p>
            Республика Абхазия,
            <br />
            г. Сухум, ул. Лакоба, 12
          </p>
          <a href="tel:+79409280022">+7 940 928-00-22</a>
          <a href="mailto:info@nova-abkhazia.ru">info@nova-abkhazia.ru</a>
          <small>Пресс-служба: press@nova-abkhazia.ru</small>
        </div>
      </div>
      <div className="shell footer-bottom">
        <span>© 2025 Политическая партия «Новая Абхазия»</span>
        <span>Политика конфиденциальности · Правовая информация</span>
      </div>
    </footer>
  );
}

function SectionTitle({
  eyebrow,
  title,
  action,
}: {
  eyebrow: string;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-title">
      <div>
        <span>{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

function ProgramRoadmap() {
  return (
    <section className="section shell">
      <SectionTitle
        eyebrow="Стратегия развития"
        title="Наша программа"
        action={
          <Button variant="outline" onClick={() => go("program")}>
            Вся программа <Icon name="arrow" />
          </Button>
        }
      />
      <div className="roadmap">
        {programItems.slice(0, 4).map((item, i) => (
          <button key={item.id} onClick={() => go(`program/${item.id}`)} className="road-card">
            <div className="road-num">{item.number}</div>
            <div className="road-dot">{i + 1}</div>
            <h3>{item.title}</h3>
            <p>{item.text}</p>
            <span>
              Подробнее <Icon name="arrow" size={17} />
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function Leader() {
  return (
    <section className="leader-section">
      <div className="shell leader-grid">
        <div className="leader-photo">
          <img src="/assets/sakaniya.png" alt="Лаша Нодариевич Сакания" />
          <span>Лидер партии</span>
        </div>
        <div className="leader-quote">
          <Icon name="quote" size={42} />
          <blockquote>
            «Наша цель — сильная, современная и процветающая Абхазия, где каждый человек уверен в
            завтрашнем дне.»
          </blockquote>
          <h3>Лаша Нодариевич Сакания</h3>
          <p>Лидер политической партии «Новая Абхазия»</p>
          <Button variant="outline" onClick={() => go("about/leadership")}>
            Биография <Icon name="arrow" />
          </Button>
        </div>
      </div>
    </section>
  );
}

function PeopleStrip() {
  const [index, setIndex] = useState(0);
  return (
    <section className="section shell">
      <SectionTitle
        eyebrow="Команда перемен"
        title="Люди Новой Абхазии"
        action={
          <div className="slider-actions">
            <button onClick={() => setIndex((index + 2) % 3)}>←</button>
            <button onClick={() => setIndex((index + 1) % 3)}>→</button>
          </div>
        }
      />
      <div className="people-feature">
        <div className="avatar-large">{people[index].initials}</div>
        <div>
          <span className="gold-label">Истории людей</span>
          <h3>{people[index].name}</h3>
          <b>{people[index].role}</b>
          <p>{people[index].story}</p>
          <button className="text-link" onClick={() => go("people")}>
            Читать историю <Icon name="arrow" />
          </button>
        </div>
        <div className="story-count">
          0{index + 1}
          <small>/ 03</small>
        </div>
      </div>
    </section>
  );
}

const regionPoints = [
  { name: "Гагра", x: 19, y: 25, projects: 12 },
  { name: "Гудаута", x: 35, y: 39, projects: 9 },
  { name: "Сухум", x: 53, y: 52, projects: 18 },
  { name: "Очамчыра", x: 70, y: 63, projects: 8 },
  { name: "Ткуарчал", x: 80, y: 53, projects: 6 },
  { name: "Гал", x: 88, y: 76, projects: 7 },
];

function MapBlock({ compact = false }: { compact?: boolean }) {
  const [selected, setSelected] = useState(regionPoints[2]);
  return (
    <div className={`map-wrap ${compact ? "compact" : ""}`}>
      <div className="map-canvas">
        <svg className="map-shape" viewBox="0 0 800 430" aria-label="Карта Абхазии">
          <path
            d="M58 83C141 41 246 52 334 94c66 31 94 85 171 102 94 21 171 30 239 112l-53 63c-81-61-158-76-242-96-112-27-173-85-252-104-51-13-99-14-145-4Z"
            fill="#e6eee9"
            stroke="#055a39"
            strokeWidth="3"
          />
          <path
            d="M70 119c99-36 180-22 264 18m-219 50c92-18 142 11 213 46m57-101c30 45 73 68 130 78m31 24c53 11 93 36 132 78"
            fill="none"
            stroke="#c4d3c9"
            strokeWidth="2"
          />
        </svg>
        {regionPoints.map((p) => (
          <button
            key={p.name}
            className={`map-point ${selected.name === p.name ? "selected" : ""}`}
            style={{ left: `${p.x}%`, top: `${p.y}%` }}
            onClick={() => setSelected(p)}
            aria-label={p.name}
          >
            <span></span>
            <b>{p.name}</b>
          </button>
        ))}
      </div>
      <div className="map-info">
        <span>Выбранный район</span>
        <h3>{selected.name}</h3>
        <strong>{selected.projects}</strong>
        <p>реализованных проектов</p>
        <button className="text-link" onClick={() => go("regions")}>
          Смотреть проекты <Icon name="arrow" />
        </button>
      </div>
    </div>
  );
}

function NewsGrid() {
  return (
    <section className="section shell">
      <SectionTitle
        eyebrow="Будьте в курсе"
        title="Медиа"
        action={
          <Button variant="outline" onClick={() => go("media")}>
            Все публикации <Icon name="arrow" />
          </Button>
        }
      />
      <div className="news-grid">
        {news.map((n, i) => (
          <article key={n.title} className={i === 0 ? "news-card featured" : "news-card"}>
            <div className="news-image">
              <img src={n.image} alt="" />
              <span>{n.tag}</span>
            </div>
            <div className="news-content">
              <small>{n.date}</small>
              <h3>{n.title}</h3>
              <button onClick={() => go("media")}>
                Подробнее <Icon name="arrow" size={17} />
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function JoinBanner({ openForm }: { openForm: (type: string) => void }) {
  return (
    <section className="join-banner">
      <div className="shell">
        <img src="/assets/logo_short.png" alt="" />
        <div>
          <span>Станьте частью команды</span>
          <h2>Будущее Абхазии создаем вместе</h2>
        </div>
        <Button variant="gold" onClick={() => openForm("Вступить в партию")}>
          Вступить в партию <Icon name="arrow" />
        </Button>
      </div>
    </section>
  );
}

function Home({ openForm }: { openForm: (type: string) => void }) {
  return (
    <>
      <section
        className="hero"
        style={{
          backgroundImage: `linear-gradient(90deg, rgba(0,36,25,.91) 0%, rgba(0,36,25,.63) 48%, rgba(0,36,25,.18) 100%), url("${heroImage}")`,
        }}
      >
        <div className="shell hero-inner">
          <span className="hero-kicker">Политическая партия</span>
          <img src="/assets/logo_full.png" alt="Новая Абхазия" />
          <h1>
            Сильная Абхазия —<br />
            наш дом, наш народ,
            <br />
            наше будущее
          </h1>
          <p>Ацҳара ду — ҳатәыла, ҳажәлар, ҳ ԥеиԥш</p>
          <div className="hero-actions">
            <Button variant="gold" onClick={() => openForm("Вступить в партию")}>
              Вступить в партию <Icon name="arrow" />
            </Button>
            <Button variant="white" onClick={() => go("program")}>
              Наша программа
            </Button>
          </div>
        </div>
        <div className="hero-stat">
          <strong>7</strong>
          <span>
            региональных
            <br />
            отделений
          </span>
        </div>
      </section>
      <section className="principles">
        <div className="shell">
          {[
            ["01", "Сильное общество", "Никто не остается один"],
            ["02", "Развитая экономика", "Возможности для каждого"],
            ["03", "Сохранение традиций", "Идентичность и культура"],
            ["04", "Открытость миру", "Диалог и партнерство"],
          ].map((x) => (
            <div key={x[0]}>
              <span>{x[0]}</span>
              <h3>{x[1]}</h3>
              <p>{x[2]}</p>
            </div>
          ))}
        </div>
      </section>
      <ProgramRoadmap />
      <Leader />
      <PeopleStrip />
      <section className="section map-section shell">
        <SectionTitle
          eyebrow="Работа рядом с вами"
          title="Дела в регионах"
          action={
            <Button variant="outline" onClick={() => go("regions")}>
              Все регионы <Icon name="arrow" />
            </Button>
          }
        />
        <MapBlock />
      </section>
      <NewsGrid />
      <JoinBanner openForm={openForm} />
    </>
  );
}

const pageMeta: Record<string, [string, string]> = {
  about: [
    "О партии",
    "Мы объединяем людей, которые верят в сильную, свободную и справедливую Абхазию.",
  ],
  program: ["Программа развития", "Конкретный план действий для устойчивого будущего страны."],
  people: ["Люди", "Истории тех, кто каждый день меняет Абхазию к лучшему."],
  activity: ["Деятельность партии", "Законопроекты, обращения и общественные инициативы."],
  regions: ["Регионы", "Работаем во всех районах Абхазии — рядом с людьми."],
  media: ["Медиа", "Новости, видео и фото из жизни партии."],
  reception: ["Виртуальная приемная", "Задайте вопрос — мы обязательно ответим."],
  contacts: ["Контакты", "Свяжитесь с центральным аппаратом или отделением в вашем районе."],
};

function PageHero({ page, title, text }: { page: string; title: string; text: string }) {
  return (
    <section className={`page-hero page-hero-${page}`}>
      <div className="shell">
        <span>Новая Абхазия</span>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
    </section>
  );
}

function AboutPage() {
  return (
    <>
      <PageHero page="about" title={pageMeta.about[0]} text={pageMeta.about[1]} />
      <section className="section shell about-intro">
        <div className="manifest-heading">
          <div className="manifest-mark">
            <img src="/assets/logo_short.png" alt="" />
            <span>Программа партии</span>
          </div>
          <div className="manifest-title">
            <span>Манифест · 2025</span>
            <h2>
              Понятные правила.
              <br />
              Работающая экономика.
              <br />
              Сильная Абхазия.
            </h2>
          </div>
          <div className="manifest-index">
            <strong>12</strong>
            <span>приоритетов развития</span>
          </div>
        </div>
        <div className="manifest-lead">
          <p className="manifest-dropcap">
            Абхазия обладает уникальным потенциалом: благоприятным климатом, выходом к морю и
            трудолюбивыми людьми.
          </p>
          <p className="lead">
            Однако сегодня республика сталкивается с системными проблемами: высокой долей теневой
            экономики, зависимостью бюджета от внешних дотаций, износом инфраструктуры и оттоком
            населения.
          </p>
          <p>
            Партия «Новая Абхазия» предлагает прагматичную повестку. Наша цель — создать работающую
            экономику и понятные правила для граждан и бизнеса. Мы исходим из того, что эффективное
            управление и верховенство закона важнее громких лозунгов.
          </p>
        </div>
        <div className="manifest-divider">
          <span>Ниже представлены приоритетные направления нашей работы</span>
          <i></i>
        </div>
        <div className="manifest-priorities">
          {[
            {
              title: "Прозрачность бюджета и реформа энергетики",
              points: [
                "Открытый бюджет, где каждый гражданин может отследить движение средств.",
                "Борьба с нелегальным майнингом, модернизация сетей и понятная система тарифов ЖКХ.",
                "Жесткий аудит финансовой помощи и государственных закупок.",
              ],
            },
            {
              title: "Защита собственности и инвестиции",
              points: [
                "Неприкосновенность частной собственности для всех граждан.",
                "Равные условия для инвесторов, простая регистрация бизнеса и защита от давления.",
                "Прозрачный механизм аренды и использования земельных участков.",
              ],
            },
            {
              title: "Туризм и малый бизнес",
              points: [
                "Поддержка малых гостевых домов и местных гидов.",
                "Курортные сборы — на благоустройство территорий и вывоз мусора.",
                "Высокие стандарты сервиса и безопасности для отдыхающих.",
              ],
            },
            {
              title: "Сельское хозяйство и легализация экономики",
              points: [
                "Закупочные кооперативы для фермеров без цепочек спекулянтов.",
                "Льготный лизинг сельскохозяйственной техники.",
                "Упрощенные налоговые режимы для выхода малого бизнеса из тени.",
              ],
            },
            {
              title: "Реформа правоохранительной системы",
              points: [
                "Достойное материальное обеспечение сотрудников МВД и прокуратуры.",
                "Современные методы расследования и цифровой документооборот.",
                "Общественная безопасность в курортных зонах и жилых районах.",
              ],
            },
            {
              title: "Доступность медицины",
              points: [
                "Ремонт районных больниц и обеспечение базовым оборудованием.",
                "Социальные гарантии и ведомственное жилье для врачей.",
                "Бесперебойные поставки льготных лекарств.",
              ],
            },
            {
              title: "Модернизация образования",
              points: [
                "Обновление школьной инфраструктуры.",
                "Цифровые инструменты для изучения абхазского, русского и английского языков.",
                "Повышение квалификации учителей и равное качество образования в городе и селе.",
              ],
            },
            {
              title: "Развитие инфраструктуры",
              points: [
                "Приоритетный ремонт межпоселковых дорог и мостов.",
                "Поэтапная замена ветхих водопроводных сетей.",
                "Стабильная мобильная связь и интернет в удаленных районах.",
              ],
            },
            {
              title: "Межнациональное согласие",
              points: [
                "Равные права всех граждан республики перед законом.",
                "Поддержка культурных центров всех народов Абхазии.",
                "Снятие лишних барьеров в вопросах гражданства для соотечественников.",
              ],
            },
            {
              title: "Закрепление молодежи",
              points: [
                "Льготная ипотека для молодых специалистов и семей.",
                "Бизнес-инкубаторы в сфере IT и переработки сельхозпродукции.",
                "Поддержка программ стажировок внутри республики.",
              ],
            },
            {
              title: "Независимость судебной власти",
              points: [
                "Реальная состязательность сторон и прозрачность судебных процессов.",
                "Формирование судейского корпуса на основе профессиональных компетенций.",
              ],
            },
            {
              title: "Общественный контроль",
              points: [
                "Обязательные слушания по бюджету и градостроительным планам.",
                "Онлайн-инструменты для гражданских инициатив и петиций.",
                "Регулярная публичная отчетность депутатов перед избирателями.",
              ],
            },
          ].map((priority, index) => (
            <article key={priority.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{priority.title}</h3>
              <ul>
                {priority.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
        <div className="manifest-conclusion">
          <span>Наша задача</span>
          <p>
            Мы понимаем, что решение этих задач требует времени и политической воли. Наша задача —
            выстроить систему, которая работает на интересы граждан, а не отдельных групп влияния.
          </p>
          <img src="/assets/logo_short.png" alt="Новая Абхазия" />
        </div>
      </section>
      <section className="section shell">
        <SectionTitle eyebrow="Наш путь" title="История партии" />
        <div className="timeline">
          {[
            [
              "2018",
              "Основание движения",
              "Первая инициативная группа объединила экспертов и общественных деятелей.",
            ],
            ["2020", "Региональная сеть", "Открыты отделения во всех семи районах республики."],
            [
              "2023",
              "Большая программа",
              "Более 12 000 граждан приняли участие в формировании программы.",
            ],
            ["2025", "Новый этап", "Команда представила стратегию развития Абхазии до 2035 года."],
          ].map((x) => (
            <div key={x[0]}>
              <strong>{x[0]}</strong>
              <span></span>
              <h3>{x[1]}</h3>
              <p>{x[2]}</p>
            </div>
          ))}
        </div>
      </section>
      <Leader />
      <section className="section shell documents">
        <SectionTitle eyebrow="Документы" title="Открыто и прозрачно" />
        <div>
          <a href="#">
            <Icon name="download" />
            <span>
              <b>Устав партии</b>
              <small>PDF · 2,4 МБ</small>
            </span>
          </a>
          <a href="#">
            <Icon name="download" />
            <span>
              <b>Программа партии</b>
              <small>PDF · 4,8 МБ</small>
            </span>
          </a>
          <a href="#">
            <img src="/assets/logo_short.png" alt="" />
            <span>
              <b>Символика и гайдлайн</b>
              <small>Правила использования логотипа</small>
            </span>
          </a>
        </div>
      </section>
    </>
  );
}

function ProgramPage({ detail }: { detail?: string }) {
  const selected = programItems.find((p) => p.id === detail);
  if (selected)
    return (
      <>
        <PageHero page="program" title={selected.title} text={selected.text} />
        <section className="section shell program-detail">
          <button className="back-link" onClick={() => go("program")}>
            ← Все направления
          </button>
          <div className="detail-grid">
            <div>
              <span>{selected.number} / Направление</span>
              <h2>Что мы изменим</h2>
              <p className="lead">{selected.text}</p>
            </div>
            <div className="big-stat">
              <strong>{selected.stat}</strong>
              <span>{selected.statLabel}</span>
            </div>
          </div>
          <div className="initiative-list">
            {[
              "Открытые и понятные правила для граждан",
              "Современная инфраструктура во всех районах",
              "Поддержка профессионалов и молодых специалистов",
              "Ежегодный общественный отчет о результатах",
            ].map((x, i) => (
              <div key={x}>
                <span>0{i + 1}</span>
                <h3>{x}</h3>
                <Icon name="check" />
              </div>
            ))}
          </div>
        </section>
      </>
    );
  return (
    <>
      <PageHero page="program" title={pageMeta.program[0]} text={pageMeta.program[1]} />
      <section className="section shell program-showcase">
        <SectionTitle eyebrow="Абхазия 2035" title="Шесть приоритетов" />
        <div className="program-grid">
          {programItems.map((item) => (
            <button key={item.id} onClick={() => go(`program/${item.id}`)}>
              <span>{item.number}</span>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
              <div>
                <strong>{item.stat}</strong>
                <small>{item.statLabel}</small>
              </div>
              <i>
                <Icon name="arrow" />
              </i>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

function PeoplePage() {
  return (
    <>
      <PageHero page="people" title={pageMeta.people[0]} text={pageMeta.people[1]} />
      <section className="section shell">
        <SectionTitle eyebrow="Наша команда" title="Депутаты, волонтеры, сторонники" />
        <div className="people-grid">
          {people
            .concat([
              {
                initials: "ИА",
                name: "Инал Авидзба",
                role: "Юрист",
                story: "Разработал бесплатную правовую приемную.",
              },
              {
                initials: "СЧ",
                name: "Саида Чанба",
                role: "Педагог",
                story: "Создала сеть кружков абхазского языка.",
              },
              {
                initials: "РА",
                name: "Руслан Аршба",
                role: "Предприниматель",
                story: "Поддерживает проекты молодых фермеров.",
              },
            ])
            .map((p, i) => (
              <article key={p.name}>
                <div className={`person-avatar avatar-${i % 3}`}>{p.initials}</div>
                <small>{p.role}</small>
                <h3>{p.name}</h3>
                <p>{p.story}</p>
                <button className="text-link">
                  История <Icon name="arrow" />
                </button>
              </article>
            ))}
        </div>
      </section>
      <section className="success-section">
        <div className="shell">
          <SectionTitle eyebrow="Результат в лицах" title="Истории успеха" />
          <div className="success-grid">
            <div
              className="success-image"
              style={{ backgroundImage: `url(${mountainImage})` }}
            ></div>
            <div>
              <span>Гудаутский район</span>
              <h2>Школа снова стала центром села</h2>
              <p>
                Вместе с жителями отремонтировали библиотеку, открыли спортивный зал и запустили
                бесплатные занятия для 120 детей.
              </p>
              <div className="result-numbers">
                <b>
                  120<small>детей</small>
                </b>
                <b>
                  34<small>волонтера</small>
                </b>
                <b>
                  5<small>месяцев</small>
                </b>
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

const activities = [
  ["Законопроект", "Экономика", "О поддержке семейного предпринимательства", "Внесен в парламент"],
  ["Обращение", "Здравоохранение", "О доступности лекарств в горных селах", "Получен ответ"],
  ["Инициатива", "Образование", "Абхазский язык: цифровая платформа", "В работе"],
  ["Законопроект", "Экология", "О защите прибрежных территорий", "Обсуждение"],
  ["Обращение", "Инфраструктура", "Ремонт дороги Сухум — Кодор", "Решено"],
];

function ActivityPage() {
  const [filter, setFilter] = useState("Все");
  return (
    <>
      <PageHero page="activity" title={pageMeta.activity[0]} text={pageMeta.activity[1]} />
      <section className="section shell">
        <div className="filterbar">
          {["Все", "Законопроект", "Обращение", "Инициатива"].map((f) => (
            <button className={filter === f ? "active" : ""} onClick={() => setFilter(f)} key={f}>
              {f}
            </button>
          ))}
        </div>
        <div className="activity-list">
          {activities
            .filter((a) => filter === "Все" || a[0] === filter)
            .map((a, i) => (
              <article key={a[2]}>
                <span>0{i + 1}</span>
                <div>
                  <small>
                    {a[0]} · {a[1]}
                  </small>
                  <h3>{a[2]}</h3>
                </div>
                <b>{a[3]}</b>
                <button>
                  <Icon name="arrow" />
                </button>
              </article>
            ))}
        </div>
      </section>
    </>
  );
}

function RegionsPage() {
  return (
    <>
      <PageHero page="regions" title={pageMeta.regions[0]} text={pageMeta.regions[1]} />
      <section className="section shell">
        <MapBlock compact />
        <div className="region-cards">
          {regionPoints.map((r) => (
            <article key={r.name}>
              <span>
                <Icon name="pin" />
              </span>
              <div>
                <h3>{r.name}</h3>
                <p>Региональное отделение</p>
                <a href="tel:+79409280022">+7 940 928-00-22</a>
                <small>Пн–Пт, 09:00–18:00</small>
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function MediaPage() {
  const [tab, setTab] = useState("Новости");
  return (
    <>
      <PageHero page="media" title={pageMeta.media[0]} text={pageMeta.media[1]} />
      <section className="section shell">
        <div className="media-tabs">
          {["Новости", "Видео", "Фотоархив"].map((t) => (
            <button className={tab === t ? "active" : ""} onClick={() => setTab(t)} key={t}>
              {t}
            </button>
          ))}
        </div>
        {tab === "Новости" && (
          <div className="media-grid">
            {news.concat(news).map((n, i) => (
              <article key={i}>
                <img src={n.image} alt="" />
                <small>
                  {n.tag} · {n.date}
                </small>
                <h3>{n.title}</h3>
                <button className="text-link">
                  Читать <Icon name="arrow" />
                </button>
              </article>
            ))}
          </div>
        )}
        {tab === "Видео" && (
          <div
            className="video-feature"
            style={{
              backgroundImage: `linear-gradient(90deg,rgba(0,45,30,.8),rgba(0,45,30,.15)),url(${heroImage})`,
            }}
          >
            <button>
              <Icon name="play" size={36} />
            </button>
            <div>
              <span>Большой разговор</span>
              <h2>Какой мы видим Абхазию через десять лет</h2>
            </div>
          </div>
        )}
        {tab === "Фотоархив" && (
          <div className="photo-grid">
            {[heroImage, coastImage, mountainImage, coastImage, heroImage, mountainImage].map(
              (x, i) => (
                <img key={i} src={x} alt="События партии" />
              ),
            )}
          </div>
        )}
      </section>
    </>
  );
}

const questions = [
  {
    tag: "Решено",
    q: "Когда отремонтируют дорогу к селу Аацы?",
    a: "Работы включены в районный план и начнутся 12 июля. Контроль ведет региональное отделение.",
  },
  {
    tag: "В работе",
    q: "Как получить поддержку молодому предпринимателю?",
    a: "Подготовлен проект грантовой программы. Сейчас документ проходит общественное обсуждение.",
  },
  {
    tag: "Обращение закрыто",
    q: "Можно ли организовать выездной прием врача?",
    a: "Выездная бригада провела прием 46 жителей. Следующий визит запланирован на август.",
  },
];

function ReceptionPage({
  submitted,
  setSubmitted,
}: {
  submitted: boolean;
  setSubmitted: (x: boolean) => void;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };
  return (
    <>
      <PageHero page="reception" title={pageMeta.reception[0]} text={pageMeta.reception[1]} />
      <section className="section shell reception-grid">
        <div>
          <span className="gold-label">Напишите нам</span>
          <h2>Отправить обращение</h2>
          {submitted ? (
            <div className="success-message">
              <Icon name="check" size={32} />
              <h3>Обращение принято</h3>
              <p>Мы свяжемся с вами в течение трех рабочих дней.</p>
            </div>
          ) : (
            <form className="main-form" onSubmit={submit}>
              <div>
                <label>
                  Ваше имя
                  <input required placeholder="Имя и фамилия" />
                </label>
                <label>
                  Телефон
                  <input required type="tel" placeholder="+7 ___ ___-__-__" />
                </label>
              </div>
              <label>
                Тема
                <select>
                  <option>Выберите тему</option>
                  <option>Социальная поддержка</option>
                  <option>Инфраструктура</option>
                  <option>Предложение</option>
                </select>
              </label>
              <label>
                Обращение
                <textarea required rows={5} placeholder="Опишите вопрос подробно..." />
              </label>
              <label className="consent">
                <input type="checkbox" required /> Я согласен на обработку персональных данных
              </label>
              <Button type="submit" variant="green">
                Отправить обращение <Icon name="arrow" />
              </Button>
            </form>
          )}
        </div>
        <aside>
          <h3>Как это работает</h3>
          {[
            ["01", "Вы отправляете обращение"],
            ["02", "Мы передаем его специалисту"],
            ["03", "Ответ приходит на почту или телефон"],
          ].map((x) => (
            <div key={x[0]}>
              <span>{x[0]}</span>
              <p>{x[1]}</p>
            </div>
          ))}
          <p className="hotline">
            Горячая линия
            <br />
            <a href="tel:+79409280022">+7 940 928-00-22</a>
          </p>
        </aside>
      </section>
      <section className="faq-section">
        <div className="shell">
          <SectionTitle eyebrow="Открытый диалог" title="Вопросы и ответы" />
          <div className="faq-list">
            {questions.map((x) => (
              <details key={x.q}>
                <summary>
                  <span className={`status ${x.tag === "Решено" ? "done" : ""}`}>{x.tag}</span>
                  <h3>{x.q}</h3>
                  <i>+</i>
                </summary>
                <p>{x.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

function ContactsPage() {
  return (
    <>
      <PageHero page="contacts" title={pageMeta.contacts[0]} text={pageMeta.contacts[1]} />
      <section className="section shell contacts-grid">
        <div>
          <span className="gold-label">Центральный аппарат</span>
          <h2>Мы на связи</h2>
          <div className="contact-line">
            <Icon name="pin" />
            <div>
              <b>Адрес</b>
              <p>
                Республика Абхазия, г. Сухум,
                <br />
                ул. Лакоба, 12
              </p>
            </div>
          </div>
          <div className="contact-line">
            <Icon name="phone" />
            <div>
              <b>Телефон</b>
              <a href="tel:+79409280022">+7 940 928-00-22</a>
            </div>
          </div>
          <div className="contact-line">
            <Icon name="mail" />
            <div>
              <b>Почта</b>
              <a href="mailto:info@nova-abkhazia.ru">info@nova-abkhazia.ru</a>
              <small>Пресс-служба: press@nova-abkhazia.ru</small>
            </div>
          </div>
        </div>
        <div className="contacts-map">
          <div className="map-pin">
            <Icon name="pin" size={28} />
          </div>
          <span>Сухум</span>
          <p>
            Центральный аппарат
            <br />
            Пн–Пт, 09:00–18:00
          </p>
        </div>
      </section>
    </>
  );
}

function Modal({ type, close }: { type: string; close: () => void }) {
  const [done, setDone] = useState(false);
  const descriptions: Record<string, string> = {
    "Вступить в партию": "Станьте частью команды, которая создает будущее Абхазии.",
    "Стать волонтером": "Присоединяйтесь к проектам в своем районе.",
    "Предложить идею": "Расскажите, что можно изменить к лучшему.",
  };
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="modal">
        <button className="modal-close" onClick={close}>
          <Icon name="close" />
        </button>
        <img src="/assets/logo_short.png" alt="" />
        {done ? (
          <div className="modal-done">
            <span>
              <Icon name="check" size={32} />
            </span>
            <h2>Спасибо!</h2>
            <p>Ваша заявка принята. Координатор свяжется с вами в ближайшее время.</p>
            <Button onClick={close}>Готово</Button>
          </div>
        ) : (
          <>
            <span className="gold-label">Новая Абхазия</span>
            <h2>{type}</h2>
            <p>{descriptions[type]}</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setDone(true);
              }}
            >
              <label>
                Имя и фамилия
                <input required placeholder="Как к вам обращаться?" />
              </label>
              <label>
                Телефон
                <input required type="tel" placeholder="+7 ___ ___-__-__" />
              </label>
              <label>
                {type === "Предложить идею" ? "Ваша идея" : "Ваш район"}
                {type === "Предложить идею" ? (
                  <textarea required rows={3} placeholder="Расскажите коротко..." />
                ) : (
                  <select required>
                    <option value="">Выберите район</option>
                    {regionPoints.map((r) => (
                      <option key={r.name}>{r.name}</option>
                    ))}
                  </select>
                )}
              </label>
              <label className="consent">
                <input type="checkbox" required /> Согласен на обработку данных
              </label>
              <Button type="submit" variant="gold">
                Отправить <Icon name="arrow" />
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

function App() {
  const getPage = () => window.location.hash.slice(1) || "home";
  const [route, setRoute] = useState(getPage);
  const [modal, setModal] = useState("");
  const [submitted, setSubmitted] = useState(false);
  useEffect(() => {
    const onHash = () => setRoute(getPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    document.body.style.overflow = modal ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [modal]);
  const [page, detail] = useMemo(() => route.split("/"), [route]);
  let content: React.ReactNode;
  if (page === "about") content = <AboutPage />;
  else if (page === "program") content = <ProgramPage detail={detail} />;
  else if (page === "people") content = <PeoplePage />;
  else if (page === "activity") content = <ActivityPage />;
  else if (page === "regions") content = <RegionsPage />;
  else if (page === "media") content = <MediaPage />;
  else if (page === "reception")
    content = <ReceptionPage submitted={submitted} setSubmitted={setSubmitted} />;
  else if (page === "contacts") content = <ContactsPage />;
  else content = <Home openForm={setModal} />;
  return (
    <>
      <Header page={page} openForm={setModal} />
      <main>{content}</main>
      <Footer openForm={setModal} />
      {modal && <Modal type={modal} close={() => setModal("")} />}
    </>
  );
}

export default App;
