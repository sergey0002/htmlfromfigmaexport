import { useEffect, useState } from 'react';

const base = 'https://em-nsk.ru';
const focus = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600 focus-visible:ring-offset-4';
const banks = [
  ['sber.jpg', 'Сбербанк'], ['vtb.jpg', 'ВТБ'],
  ['gazprom.jpg', 'Газпромбанк'], ['domrf.jpg', 'Банк ДОМ.РФ'],
  ['otkritie.jpg', 'Открытие'], ['absolut.jpg', 'Абсолют Банк'],
  ['uralsib.png', 'Уралсиб'], ['roskap.jpg', 'Российский капитал'],
];
const options = [
  { id: 'installment', label: 'Рассрочка' },
  { id: 'mortgage', label: 'Ипотека' },
  { id: 'capital', label: 'Материнский капитал' },
  { id: 'military', label: 'Военная ипотека' },
  { id: 'tradein', label: 'Трейд-ин' },
];

function Icon({ name, className = '' }: { name: string; className?: string }) {
  const paths: Record<string, React.ReactNode> = {
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    diagonal: <><path d="M6 18 18 6M6 6h12v12" /></>,
    home: <><path d="m3 10 9-7 9 7v11H3zM9 21v-8h6v8" /></>,
    calendar: <><rect x="4" y="5" width="16" height="16" rx="2" /><path d="M8 3v5m8-5v5M4 11h16m-11 4h2m2 0h2m-6 3h2" /></>,
    bank: <><path d="m3 8 9-5 9 5H3Zm2 3v7m7-7v7m7-7v7M3 21h18" /></>,
    family: <><circle cx="8" cy="7" r="3" /><circle cx="17" cy="9" r="2" /><path d="M2 21v-4a6 6 0 0 1 12 0v4m2-8a5 5 0 0 1 6 5v3" /></>,
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z" /><path d="m8 12 3 3 5-6" /></>,
    exchange: <><path d="M4 8h15l-4-4M20 16H5l4 4M4 8v5m16 3v-5" /></>,
    phone: <path d="m7 3 3 5-3 3a16 16 0 0 0 6 6l3-3 5 3c-1 6-6 4-10 2S3 12 3 7c0-3 2-4 4-4Z" />,
    plus: <path d="M5 12h14m-7-7v14" />,
  };
  return <svg className={`h-6 w-6 shrink-0 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.arrow}</svg>;
}

function Image({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  return failed
    ? <span className="flex items-center gap-2 text-sm font-semibold"><Icon name="bank" />{alt}</span>
    : <img src={src} alt={alt} className={className} onError={() => setFailed(true)} />;
}

function ContactLink({ children = 'Получить консультацию', light = false }: { children?: React.ReactNode; light?: boolean }) {
  return <a href="#consultation" className={`group inline-flex min-h-11 items-center justify-between gap-5 text-sm font-medium ${light ? 'text-white' : 'text-[#e30613]'} ${focus}`}>
    {children}<Icon name="arrow" className="transition-transform duration-300 group-hover:translate-x-1 motion-reduce:transform-none" />
  </a>;
}

function SmallCard({ id, number, icon, title, description, children }: {
  id: string; number: string; icon: string; title: string; description: string; children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  return <article id={id} className="group flex scroll-mt-8 flex-col rounded-lg border border-[#e8e8e8] bg-white p-7 transition duration-300 hover:border-red-200 hover:shadow-lg hover:shadow-black/4 motion-reduce:transition-none lg:p-8">
    <div className="mb-7 flex items-center justify-between"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-[#fff2f2] text-[#e30613]"><Icon name={icon} /></span><span className="text-sm text-neutral-500">/ {number}</span></div>
    <h2 className="mb-4 max-w-72 text-2xl font-semibold leading-tight">{title}</h2>
    <p className="mb-6 text-sm leading-relaxed text-neutral-600">{description}</p>
    {expanded && <div className="mb-5 border-t border-neutral-200 pt-5 text-sm leading-relaxed text-neutral-600">{children}</div>}
    <button onClick={() => setExpanded(!expanded)} aria-expanded={expanded} className={`mt-auto flex min-h-11 items-center justify-between border-t border-neutral-200 pt-4 text-left text-sm font-medium ${focus}`}>
      {expanded ? 'Свернуть' : 'Подробнее об условиях'}<Icon name="plus" className={`text-[#e30613] transition-transform duration-300 ${expanded ? 'rotate-45' : ''}`} />
    </button>
  </article>;
}

const companyLinks = [
  ['Контакты', '/contact/'], ['Сданные объекты', '/portfolio/'],
  ['Партнерская программа', '/reg'], ['История', '/about'],
  ['Миссия', '/mission'], ['Знак компании', '/symbol'],
  ['Вакансии', '/ads'], ['Документы', '/doc'],
  ['Служба клиентского сервиса', '/feedback.php'],
];
const propertyLinks = [
  ['Квартиры', '/catalog'], ['Парковки', '/parking/'],
  ['Способы покупки', '/sposob'], ['Акции', '/actions'],
  ['Квартиры со стилем', '/remont'],
];
const topLinks = [
  ['О компании', '/about'], ['Миссия', '/mission'],
  ['Пресс-центр', '/media'], ['Контакты', '/contact'], ['Карта проектов', '/map'],
];
const pressLinks = [
  ['Фотоальбом', '/media/#foto'], ['Видео', '/media/#video'],
  ['Газета «Калининский родник»', '/media/#rodnik'],
];
const maxContact = 'https://max.ru/u/f9LHodD0cOLt4Wmw4kICkJra993QCbOhidJG1q49Mu8lMLkKI33obmY4vIg';

function SiteLink({ href, children, className = '' }: {
  href: string; children: React.ReactNode; className?: string;
}) {
  return <a href={href.startsWith('/') ? base + href : href} className={`transition-colors hover:text-[#e30613] ${focus} ${className}`}>{children}</a>;
}

function SocialLinks({ footer = false }: { footer?: boolean }) {
  const links = footer ? [
    ['vk.svg', 'ВКонтакте', 'https://vk.com/emnsk'],
    ['tg-2.svg', 'Telegram', 'https://t.me/energomontazh_nsk'],
    ['ok.svg', 'Одноклассники', 'https://ok.ru/group/52030414454992'],
    ['max.svg', 'MAX', 'https://max.ru/id2225191580_biz'],
  ] : [
    ['tg.svg', 'Telegram', 'https://t.me/+79132679200'],
    ['mlogo.png', 'MAX', maxContact],
  ];
  return <div className={footer ? 'grid grid-cols-2 gap-4 self-start' : 'flex items-center gap-2 lg:gap-3'}>
    {links.map(([file, name, url]) => <a key={file} href={url} target="_blank" rel="noopener noreferrer" aria-label={name} className={`flex h-11 w-11 shrink-0 items-center justify-center ${focus}`}>
      <Image src={`/images/site/${file}`} alt={name} className="h-[35px] w-[35px] object-contain" />
    </a>)}
  </div>;
}

function SiteHeader() {
  const [menu, setMenu] = useState(false);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const onScroll = () => setCompact(window.scrollY > 80);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return <header className="sticky top-0 z-30 bg-white text-black">
    <div className="relative shadow-[0_1px_24px_8px_rgba(0,0,0,0.1)]">
      <div className="mx-auto flex min-h-11 max-w-[1416px] items-center justify-between gap-2 px-4 md:px-12 lg:px-[15px]">
        <button onClick={() => setMenu(!menu)} aria-label={menu ? 'Закрыть меню' : 'Открыть меню'} aria-expanded={menu} aria-controls="site-mobile-menu" className={`flex min-h-11 items-center gap-2 text-base font-semibold md:text-xl lg:hidden ${focus}`}>
          <Image src="/images/site/burger.svg" alt="" className="h-7 w-7 md:h-11 md:w-11" />Меню
        </button>
        <nav aria-label="О компании" className="hidden items-center gap-2.5 text-sm lg:flex xl:gap-4">
          {topLinks.map(([label, href]) => <SiteLink key={href} href={href} className="flex min-h-11 items-center whitespace-nowrap">{label}</SiteLink>)}
          <SiteLink href="/sign_up_key/" className="flex min-h-11 items-center"><span className="rounded-[17px] border border-[#e30613] px-2.5 py-1 text-xs">Новосёлам</span></SiteLink>
        </nav>
        <div className="hidden items-center gap-[19px] lg:flex">
          <SiteLink href="/feedback.php" className="flex min-h-11 items-center"><span className="rounded-[17px] bg-[#26b99a] px-3 py-1 text-sm font-semibold text-[#102e27]">Служба клиентского сервиса</span></SiteLink>
          <SiteLink href="https://em.m2profi.pro/sahmatka/user.php" className="flex min-h-11 items-center"><span className="min-w-[132px] rounded-[17px] bg-[#e30613] px-3 py-1 text-center text-sm font-semibold text-white xl:min-w-[162px]">Агентствам</span></SiteLink>
        </div>
        <SiteLink href="tel:+73833474700" className="ml-auto whitespace-nowrap text-sm font-semibold md:hidden">+ 7 (383) 347-47-00</SiteLink>
        <div className="lg:hidden"><SocialLinks /></div>
      </div>
    </div>
    <div className={`mx-auto flex max-w-[1416px] items-center justify-between gap-3 px-4 transition-[padding] duration-150 motion-reduce:transition-none md:gap-10 md:px-12 lg:gap-8 lg:px-[15px] ${compact ? 'py-2.5' : 'py-[19px] md:py-[30px] lg:py-6'}`}>
      <SiteLink href="/" className="w-[92px] shrink-0 md:w-[156px] lg:w-[116px]"><Image src="/images/logo.svg" alt="Энергомонтаж" className="w-full" /></SiteLink>
      <nav aria-label="Выбор недвижимости" className="flex min-w-0 items-center gap-3">
        <SiteLink href="/projects/" className="flex min-h-11 shrink-0 items-center"><span className="whitespace-nowrap rounded-[17px] border-2 border-[#e30613] px-2.5 py-1 text-sm font-semibold leading-none md:px-5 md:text-base lg:px-2.5 lg:text-sm xl:px-5 xl:text-base">Выбрать недвижимость</span></SiteLink>
        <ul className="hidden items-center gap-3 text-sm lg:flex xl:gap-[15px] xl:text-base">
          {propertyLinks.map(([label, href]) => <li key={href}><SiteLink href={href} className="flex min-h-11 items-center whitespace-nowrap">{label}</SiteLink></li>)}
        </ul>
      </nav>
      <div className="ml-auto hidden shrink-0 items-center gap-[17px] md:flex">
        <SiteLink href="tel:+73833474700" className="flex min-h-11 items-center whitespace-nowrap text-xl font-semibold lg:text-sm xl:text-xl">+ 7 (383) 347-47-00</SiteLink>
        <div className="hidden min-[1400px]:block"><SocialLinks /></div>
      </div>
    </div>
    {menu && <nav id="site-mobile-menu" aria-label="Меню сайта" className="max-h-[65vh] overflow-y-auto border-t border-[#f7e8e8] px-4 py-6 md:px-12 lg:hidden">
      <div className="grid gap-x-8 md:grid-cols-2">
        {[...propertyLinks, ...topLinks, ['Новосёлам', '/sign_up_key/'], ['Служба клиентского сервиса', '/feedback.php'], ['Агентствам', 'https://em.m2profi.pro/sahmatka/user.php']].map(([label, href]) => <SiteLink key={`${label}-${href}`} href={href} className="flex min-h-11 items-center border-b border-[#f7e8e8] text-base">{label}</SiteLink>)}
      </div>
    </nav>}
  </header>;
}

function FooterGroup({ title, href, links }: { title: string; href: string; links: string[][] }) {
  return <div className="min-w-0">
    <SiteLink href={href} className="inline-flex min-h-11 items-center text-base font-semibold uppercase leading-tight text-[#161616]">{title}</SiteLink>
    <ul className="flex flex-col">
      {links.map(([label, url]) => <li key={`${label}-${url}`}><SiteLink href={url} className="inline-flex min-h-11 items-center text-sm leading-relaxed text-[#6b6b6b]">{label}</SiteLink></li>)}
    </ul>
  </div>;
}

function SiteFooter() {
  return <footer className="bg-[#f7e8e8] pb-[60px] pt-[25px] md:py-8 lg:pb-[30px] lg:pt-14">
    <div className="mx-auto max-w-[1218px] px-4 md:px-12 lg:px-[15px]">
      <div className="grid grid-cols-2 gap-x-6 pb-10 lg:grid-cols-[1.2fr_1fr] lg:pb-7">
        <div className="col-span-2 mb-8 flex flex-col gap-6 border-b border-[#e30613] pb-7 lg:col-span-1 lg:col-start-1 lg:row-start-2 lg:mb-0 lg:mt-5 lg:border-0 lg:pb-0">
          <SiteLink href="/" className="w-[116px]"><Image src="/images/logo.svg" alt="Энергомонтаж" className="w-full" /></SiteLink>
          <p className="text-xs font-medium leading-tight text-[#6b6b6b]">© Группа компаний «Энергомонтаж»</p>
        </div>
        <div className="flex min-w-0 flex-col gap-6 md:gap-10 lg:col-start-1 lg:row-start-1 lg:flex-row lg:justify-between lg:gap-6">
          <FooterGroup title="Проекты" href="/projects/" links={[
            ['Атом', '/projects/atom'], ['Династия', '/projects/dynasty/'],
            ['Приозерный', '/projects/priozerny/'], ['Infinity', '/projects/infinity/'],
          ]} />
          <FooterGroup title="Выбрать недвижимость" href="/catalog/" links={[
            ['Квартиры', '/catalog/'], ['Парковки', '/parking/'], ['Коммерческие помещения', '/commerce/'],
          ]} />
          <div className="flex min-w-0 flex-col gap-1">
            {[['Офисы продаж', '/contact/'], ['Способы покупки', '/sposob'], ['АКЦИИ', '/actions/']].map(([label, href]) => <SiteLink key={href} href={href} className="inline-flex min-h-11 items-center text-base font-semibold uppercase leading-tight text-[#161616]">{label}</SiteLink>)}
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-6 md:flex-row lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <FooterGroup title="О компании" href="/about" links={companyLinks} />
          <div className="flex min-w-0 flex-col gap-7 md:max-w-[197px]">
            <FooterGroup title="Пресс-Центр" href="/media/" links={pressLinks} />
            <SocialLinks footer />
          </div>
        </div>
      </div>
      <div className="flex flex-col justify-between gap-6 border-t border-[#e30613] pt-[19px] md:flex-row">
        <div className="flex max-w-[755px] flex-col gap-7 md:gap-[47px]">
          <div className="text-xs font-medium leading-tight text-[#6b6b6b]">
            <SiteLink href="/content/sitedoc/agreement.docx" className="inline-flex min-h-11 items-center">Согласие на обработку персональных данных</SiteLink><br />
            <SiteLink href="/content/sitedoc/politic.docx" className="inline-flex min-h-11 items-center">Политика обработки персональных данных</SiteLink>
          </div>
          <p className="text-xs font-medium leading-tight text-[#6b6b6b]">Любая информация, представленная на данном сайте, носит исключительно информационный характер и ни при каких условиях не является публичной офертой, определяемой положениями статьи 437 ГК РФ.</p>
        </div>
        <div className="flex shrink-0 flex-col items-start text-xs font-medium leading-tight text-[#6b6b6b] md:max-w-[290px] md:items-end md:text-right">
          <p>Разработка и поддержка сайта:</p>
          <SiteLink href="https://m2profi.pro" className="flex min-h-11 items-center gap-1.5"><Image src="/images/site/m2.svg" alt="" className="h-[15px] w-[21px] shrink-0" /><span>ООО «М2».<br />Разработка и внедрение IT-продуктов.</span></SiteLink>
          <SiteLink href="https://stalker.group" className="flex min-h-11 items-center gap-1.5"><Image src="/images/site/stalker.svg" alt="" className="h-[18px] w-[17px] shrink-0" /><span>ООО «Сталкер».<br />Проводник в маркетинговых коммуникациях.</span></SiteLink>
        </div>
      </div>
    </div>
  </footer>;
}

export default function App() {
  const [active, setActive] = useState('');
  return <div className="min-h-screen overflow-x-hidden bg-white font-sans text-[#202020] selection:bg-red-100">
    <SiteHeader />

    <main id="purchase" className="mx-auto max-w-[1188px] px-6 pb-20 lg:px-10">
      <div className="flex items-center gap-3 pt-8 text-xs text-neutral-600"><a href={base} className={`min-h-11 content-center hover:text-red-600 ${focus}`}>Главная</a><span>/</span><span>Способы покупки</span></div>
      <section className="relative pb-10 pt-7 md:pt-10">
        <div className="mb-5 flex items-center gap-3 text-xs font-medium uppercase tracking-[0.16em] text-[#e30613]"><span className="h-px w-8 bg-[#e30613]" />Ближе к своей квартире</div>
        <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
          <h1 className="text-[38px] font-semibold uppercase leading-[1.08] tracking-[-0.025em] md:text-[56px] lg:text-[64px]">Как купить<br />квартиру<span className="text-[#e30613]">.</span></h1>
          <p className="max-w-[390px] pb-1 text-base leading-relaxed text-neutral-600">Планы у всех разные. Квартира — своя.<br className="hidden md:block" /> Выберите удобный способ покупки,<br className="hidden md:block" /> а мы поможем на каждом этапе.</p>
        </div>
      </section>

      <nav aria-label="Способы покупки" className="mb-10 flex flex-wrap gap-2 border-b border-neutral-200 pb-8">
        {options.map((item, i) => <a key={item.id} href={`#${item.id}`} onClick={() => setActive(item.id)} className={`group inline-flex min-h-11 items-center gap-3 rounded-full border px-5 text-sm transition-colors duration-200 ${focus} ${active === item.id ? 'border-[#e30613] bg-[#e30613] text-white' : 'border-neutral-200 bg-white hover:border-[#e30613] hover:text-[#e30613]'}`}><span className={active === item.id ? 'text-white' : 'text-neutral-500'}>0{i + 1}</span>{item.label}</a>)}
      </nav>

      <div className="grid gap-5 lg:grid-cols-3">
        <article id="installment" className="relative flex scroll-mt-8 flex-col overflow-hidden rounded-lg bg-[#f5f5f5] p-7 lg:p-8">
          <div className="mb-8 flex items-center justify-between"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-[#e30613]"><Icon name="calendar" /></span><span className="text-sm text-neutral-500">/ 01</span></div>
          <h2 className="text-[28px] font-semibold">Рассрочка</h2>
          <p className="mb-7 mt-3 text-sm leading-relaxed text-neutral-600">Квартира сейчас —<br />оплата в удобном ритме.</p>
          <div className="mb-8 grid grid-cols-2 gap-4 border-y border-neutral-300 py-5">
            <div><div className="text-[35px] font-medium leading-tight">от 30<span className="text-xl">%</span></div><p className="mt-2 text-xs text-neutral-600">первоначальный взнос</p></div>
            <div className="border-l border-neutral-300 pl-5"><div className="text-[35px] font-medium leading-tight">от 3<span className="ml-1 text-lg">мес.</span></div><p className="mt-2 text-xs text-neutral-600">срок рассрочки</p></div>
          </div>
          <p className="mb-7 text-sm leading-relaxed text-neutral-600">График и суммы платежей обсуждаем индивидуально — с учётом ваших возможностей.</p>
          <div className="mt-auto"><ContactLink>Узнать условия</ContactLink></div>
        </article>

        <article id="mortgage" className="scroll-mt-8 rounded-lg border border-[#e8e8e8] p-7 lg:col-span-2 lg:p-8">
          <div className="mb-6 flex items-center justify-between"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-[#fff2f2] text-[#e30613]"><Icon name="bank" /></span><span className="rounded-full bg-[#f5f5f5] px-3 py-1.5 text-xs text-neutral-600">/ 02</span></div>
          <div className="flex flex-wrap items-start justify-between gap-4"><h2 className="max-w-[340px] text-[28px] font-semibold leading-tight">Ипотека ведущих<br className="hidden md:block" /> банков <span className="text-[#e30613]">от 6%</span></h2><span className="rounded-full border border-red-200 px-3 py-1.5 text-xs text-[#c30511]">По 214-ФЗ</span></div>
          <p className="mb-6 mt-4 max-w-[620px] text-sm leading-relaxed text-neutral-600">Подберём индивидуальные условия кредитования, поможем с документами и поддержим на всех этапах оформления ипотеки.</p>
          <div className="mb-3 flex items-center justify-between"><h3 className="text-xs font-medium uppercase tracking-wider text-neutral-600">Наши банки-партнёры</h3><span className="text-xs text-neutral-600">{String(banks.length).padStart(2, '0')} банков</span></div>
          <div className="mb-5 grid grid-cols-2 gap-2 md:grid-cols-4">
            {[
              ['sber.svg', 'Сбербанк'],
              ['vtb.svg', 'ВТБ'],
              ['alfa.svg', 'Альфа-Банк'],
              ['domrf.svg', 'Банк ДОМ.РФ'],
              ['akcept.svg', 'Банк Акцепт'],
              ['levoberezhny.svg', 'Банк Левобережный'],
              ['psb.svg', 'ПСБ'],
              ['bspb.png', 'Банк Санкт-Петербург'],
            ].map(([file, name]) => <div key={file} className="flex h-[70px] items-center justify-center rounded border border-neutral-200 bg-white px-3 py-2 transition duration-300 hover:-translate-y-1 hover:border-red-300 hover:shadow-sm motion-reduce:transform-none"><Image src={`/images/partners/${file}`} alt={name} className={`h-full w-full object-contain${['vtb.svg', 'psb.svg', 'bspb.png'].includes(file) ? ' scale-80' : ''}`} /></div>)}
          </div>
          <ContactLink>Подобрать ипотечную программу</ContactLink>
        </article>

        <SmallCard id="capital" number="03" icon="family" title="Материнский капитал" description="Используйте материнский капитал для частичного погашения ипотечного кредита — основного долга и процентов.">
          Оформите ипотеку, соберите пакет документов и подайте заявление в Социальный фонд России. После регистрации договора средства будут перечислены в банк. Это позволит уменьшить срок кредита или ежемесячный платёж.
        </SmallCard>
        <SmallCard id="military" number="04" icon="shield" title="Военная ипотека" description="Новая квартира для вашей семьи на специальных условиях. Больше пространства и всё для комфортной жизни рядом.">
          Рассмотрите наши микрорайоны «Родники» и «Приозерный» с развитой инфраструктурой Калининского района. Условия участия и доступные квартиры уточняйте в отделе продаж.
        </SmallCard>
        <SmallCard id="tradein" number="05" icon="exchange" title="Квартира в трейд-ин" description="Переезжайте в новое, не откладывая планы. Поможем продать вашу недвижимость и зачесть её стоимость в счёт покупки.">
          Не нужно искать покупателя самостоятельно: мы поможем организовать продажу вашей недвижимости. Индивидуальный расчёт и консультацию можно получить в офисе продаж.
        </SmallCard>
      </div>

      <section id="consultation" className="relative mt-10 flex scroll-mt-8 flex-col justify-between gap-8 overflow-hidden rounded-lg bg-[#e30613] p-8 text-white md:flex-row md:items-center lg:p-11">
        <div className="pointer-events-none absolute -right-14 -top-28 h-96 w-96 rounded-full border border-white/20" aria-hidden="true" />
        <div className="pointer-events-none absolute -right-1 -top-16 h-72 w-72 rounded-full border border-white/20" aria-hidden="true" />
        <div className="relative"><p className="mb-3 text-xs uppercase tracking-[0.15em]">Ваш следующий шаг</p><h2 className="mb-3 text-3xl font-medium md:text-[36px]">Найдём ваш способ покупки</h2><p className="max-w-lg text-sm leading-relaxed">Расскажем об условиях, ответим на вопросы<br className="hidden md:block" /> и поможем сделать первый шаг к новой квартире.</p></div>
        <div className="relative shrink-0"><a href="tel:+73833474700" className={`group flex min-h-14 items-center justify-center gap-6 rounded bg-white px-6 text-sm font-medium text-[#202020] transition-colors hover:bg-red-50 ${focus}`}><Icon name="phone" />+7 (383) 347-47-00<Icon name="diagonal" /></a><p className="mt-3 text-center text-xs">Консультация отдела продаж</p></div>
      </section>
      <p className="mt-5 max-w-4xl text-xs leading-relaxed text-neutral-600">Условия покупки и кредитования уточняйте в отделе продаж. Решение о предоставлении кредита принимает банк. Информация на сайте не является публичной офертой.</p>
    </main>
    <SiteFooter />
  </div>;
}
