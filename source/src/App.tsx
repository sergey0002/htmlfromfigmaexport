import { useState } from 'react';

const site = 'https://xn--m1acsa.xn--p1ai';
const focus = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1479bb] focus-visible:ring-offset-4';
const documents = [
  {
    id: '01',
    title: 'Политика обработки персональных данных',
    description: 'Ознакомьтесь с порядком обработки и защиты ваших персональных данных.',
    audience: 'Для всех участников',
    file: 'politic.pdf',
    note: 'Для ознакомления',
  },
  {
    id: '02',
    title: 'Согласие на обработку персональных данных',
    description: 'Скачайте, заполните и подпишите согласие, если вам уже исполнилось 18 лет.',
    audience: 'Совершеннолетним игрокам',
    file: 'agreement_adult.pdf',
    note: 'Заполнить и подписать',
  },
  {
    id: '03',
    title: 'Согласие законного представителя на обработку персональных данных',
    description: 'Для игроков младше 18 лет согласие заполняет и подписывает законный представитель.',
    audience: 'Родителям и представителям',
    file: 'agreement_junior.pdf',
    note: 'Заполнить и подписать',
  },
];
const links = [
  ['О федерации', '/about/'],
  ['Турниры', '/tournaments/'],
  ['Команды', '/teams2/'],
  ['Медиа', '/events/'],
  ['Контакты', '/contacts/'],
];

function Icon({ name, className = '' }: { name: string; className?: string }) {
  const paths: Record<string, React.ReactNode> = {
    file: <><path d="M14 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9Z" /><path d="M14 2v7h7M7 13h10M7 17h7" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" /></>,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    external: <><path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v1" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    pin: <><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    pen: <><path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z" /><path d="M13 21h8" /></>,
  };
  return <svg className={`h-5 w-5 shrink-0 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.file}</svg>;
}

function Logo() {
  const [error, setError] = useState(false);
  return error
    ? <span className="flex items-center gap-3 text-white"><Icon name="file" /><span className="text-sm font-bold">НОВОСИБИРСКАЯ ОБЛАСТНАЯ<br />ФЕДЕРАЦИЯ ФЛОРБОЛА</span></span>
    : <img src="/images/federation-logo.png" width="240" height="53" alt="Новосибирская областная федерация флорбола" onError={() => setError(true)} className="h-auto w-[240px] max-w-full" />;
}

function DocumentCard({ document }: { document: typeof documents[number] }) {
  const [downloaded, setDownloaded] = useState(false);
  return (
    <article className="group flex min-w-0 flex-col rounded-2xl border border-[#d9e3e9] bg-white p-6 transition-all duration-300 hover:border-[#8ba9bb] hover:shadow-[0_12px_30px_-14px_#01345040] motion-safe:hover:-translate-y-1 lg:p-7">
      <div className="mb-6 flex items-start justify-between">
        <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-[#edf3f7] transition-colors group-hover:bg-[#dde9f0]">
          <Icon name="file" className="h-7 w-7 transition-transform motion-safe:group-hover:-rotate-6" />
        </div>
        <span className="pt-1 text-xs font-medium tracking-wider text-slate-600">PDF <span className="mx-2 text-slate-600">/</span> {document.id}</span>
      </div>
      <span className="mb-3 text-xs font-semibold text-[#426379]">{document.audience}</span>
      <h3 className="mb-4 text-lg leading-[1.4] font-bold">{document.title}</h3>
      <p className="mb-6 text-sm leading-[1.75] text-slate-600">{document.description}</p>
      <div className="mt-auto">
        <div className="mb-5 flex items-center gap-2 border-t border-[#e6edf1] pt-4 text-xs font-medium">
          <span className={`h-1.5 w-1.5 rounded-full ${document.id === '01' ? 'bg-[#1479bb]' : 'bg-[#e30613]'}`} />
          {document.note}
        </div>
        <a href={`/documents/${document.file}`} download onClick={() => setDownloaded(true)} className={`flex min-h-12 items-center justify-center gap-3 rounded-[10px] bg-[#013450] px-4 text-sm font-bold text-white transition-colors hover:bg-[#1479bb] active:scale-[.98] motion-reduce:transform-none ${focus}`}>
          <Icon name={downloaded ? 'check' : 'download'} />
          {downloaded ? 'Скачать ещё раз' : 'Скачать документ'}
        </a>
        <a href={`/documents/${document.file}`} target="_blank" rel="noreferrer" className={`mt-2 flex min-h-11 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors hover:bg-[#edf3f7] ${focus}`}>
          Открыть документ <Icon name="external" className="h-4 w-4" />
        </a>
      </div>
    </article>
  );
}

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="flex min-h-screen flex-col overflow-x-hidden bg-white font-sans text-[#013450]">
      <header className="z-20 bg-[#013450] text-white">
        <div className="mx-auto flex min-h-[88px] max-w-[1280px] items-center justify-between gap-5 px-5 py-4 md:px-12">
          <a href={site} aria-label="На главную" className={`shrink-0 rounded-sm ${focus}`}><Logo /></a>
          <nav aria-label="Основная навигация" className="hidden items-center gap-1 xl:flex">
            {links.map(([label, url]) => <a key={url} href={site + url} className={`flex min-h-11 items-center whitespace-nowrap rounded-sm px-3 text-sm font-bold uppercase transition-colors hover:bg-[#1479bb] ${focus}`}>{label}</a>)}
            <a href="#documents" aria-current="page" className={`ml-3 flex min-h-11 items-center rounded-full bg-[#e30613] px-5 text-sm font-bold uppercase hover:bg-[#b70510] ${focus}`}>Согласия</a>
          </nav>
          <a href="https://vk.com/floorballnsk" target="_blank" rel="noreferrer" aria-label="Федерация ВКонтакте" className={`hidden min-h-11 min-w-11 items-center justify-center text-xl font-extrabold xl:flex ${focus}`}>ᴠκ</a>
          <button aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'} aria-expanded={menuOpen} aria-controls="mobile-menu" onClick={() => setMenuOpen(!menuOpen)} className={`flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-white/40 xl:hidden ${focus}`}><Icon name={menuOpen ? 'close' : 'menu'} /></button>
        </div>
        {menuOpen && <nav id="mobile-menu" aria-label="Мобильная навигация" className="border-t border-white/20 px-5 pb-5 xl:hidden">
          {links.map(([label, url]) => <a key={url} href={site + url} className={`flex min-h-12 items-center text-sm font-bold uppercase ${focus}`}>{label}</a>)}
          <a href="#documents" onClick={() => setMenuOpen(false)} className={`flex min-h-12 items-center text-sm font-bold uppercase ${focus}`}>Согласия</a>
        </nav>}
      </header>

      <main className="mx-auto w-full max-w-[1280px] flex-1 px-5 pt-10 pb-16 md:px-12 md:pt-[60px] md:pb-20">
        <div className="mb-8 flex items-center gap-2.5 text-xs text-slate-600">
          <a href={site} className={`flex min-h-11 items-center hover:text-[#1479bb] ${focus}`}>Главная</a>
          <span>/</span><span>Согласия</span>
        </div>
        <div className="mb-8 max-w-[950px]">
          <div className="mb-4 inline-flex items-center rounded-full bg-[#edf3f7] px-3 py-1.5 text-xs font-semibold text-[#013450]">Сезон 2026/2027</div>
          <h1 className="text-[28px] leading-[1.15] font-bold uppercase md:text-[40px]">Согласия на обработку<br className="hidden md:block" /> персональных данных</h1>
          <p className="mt-5 max-w-[830px] text-base leading-[1.8] text-slate-600">Ознакомьтесь с документами, скачайте подходящее согласие и передайте подписанный экземпляр в Новосибирскую областную федерацию флорбола.</p>
        </div>

        <section aria-label="Важная информация" className="mb-10 flex items-start gap-4 rounded-r-xl border-l-[3px] border-[#e30613] bg-[#f5f7f9] px-5 py-5 md:gap-5 md:px-6">
          <Icon name="info" className="mt-0.5 h-6 w-6 text-[#c80917]" />
          <div>
            <h2 className="mb-2 text-base font-bold">Без оформленного согласия участие в турнирах невозможно</h2>
            <p className="max-w-[1000px] text-sm leading-[1.8] text-slate-600">Игроки, не предоставившие заполненное и подписанное согласие, не допускаются к турнирам под эгидой федерации. За несовершеннолетних игроков согласие заполняют и подписывают их законные представители.</p>
          </div>
        </section>

        <section id="documents" aria-labelledby="documents-title" className="scroll-mt-6">
          <div className="mb-6 flex items-center justify-between gap-4">
            <h2 id="documents-title" className="text-xl font-bold uppercase md:text-2xl">Документы для скачивания</h2>
            <span className="whitespace-nowrap text-xs font-medium text-slate-600">3 документа · PDF</span>
          </div>
          <div className="grid items-stretch gap-5 md:grid-cols-3">{documents.map(document => <DocumentCard key={document.id} document={document} />)}</div>
          <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-slate-600"><Icon name="info" className="mt-0.5 h-4 w-4" />Согласия заполняются на бумаге. Отправлять персональные данные через сайт не требуется.</p>
        </section>

        <section aria-labelledby="steps-title" className="mt-12 rounded-2xl bg-[#edf3f7] p-6 md:mt-14 md:p-8">
          <h2 id="steps-title" className="mb-7 text-xl font-bold uppercase md:text-2xl">Как передать согласие</h2>
          <div className="grid gap-7 md:grid-cols-3 md:gap-8">
            {[
              ['01', 'download', 'Скачайте документ', 'Ознакомьтесь с политикой и выберите согласие для себя или несовершеннолетнего игрока.'],
              ['02', 'pen', 'Заполните и подпишите', 'Распечатайте согласие, заполните все необходимые поля и поставьте личную подпись.'],
              ['03', 'pin', 'Передайте в федерацию', 'Принесите оригинал лично в приёмные часы или передайте в секретариат на любом турнире федерации.'],
            ].map(([number, icon, title, text]) => <div key={number} className="min-w-0">
              <div className="mb-4 flex items-center gap-3"><span className="text-xs font-bold text-[#426379]">{number}</span><span className="h-px flex-1 bg-[#ccdbe4]" /><Icon name={icon} /></div>
              <h3 className="mb-2 text-base font-bold">{title}</h3>
              <p className="text-sm leading-[1.8] text-slate-600">{text}</p>
            </div>)}
          </div>
          <div className="mt-7 flex flex-col items-start justify-between gap-3 border-t border-[#ccdbe4] pt-5 md:flex-row md:items-center">
            <p className="text-sm text-slate-600">Адрес и приёмные часы уточняйте у федерации.</p>
            <a href={`${site}/contacts/`} className={`flex min-h-11 items-center gap-3 rounded text-sm font-bold hover:text-[#1479bb] ${focus}`}>Контакты федерации <Icon name="arrow" /></a>
          </div>
        </section>
      </main>

      <footer className="bg-[#013450] py-10 text-white md:py-[45px]">
        <div className="mx-auto grid max-w-[1280px] gap-8 px-5 md:px-12 lg:grid-cols-[260px_1fr_280px] lg:gap-10">
          <a href={site} aria-label="На главную" className={`self-start rounded-sm lg:border-r lg:border-white/30 lg:pr-7 ${focus}`}><Logo /></a>
          <div className="text-sm leading-[1.7] lg:border-r lg:border-white/30 lg:pr-8">
            <p className="mb-3 font-semibold">Разработка и поддержка сайта:</p>
            <a href="https://m2profi.pro" className={`mb-2 block hover:underline ${focus}`}>ООО «М2». Разработка и внедрение IT-продуктов.</a>
            <a href="https://stalker.expert" className={`block hover:underline ${focus}`}>ООО «Сталкер». Проводник в маркетинговых коммуникациях.</a>
          </div>
          <div className="flex flex-col items-start gap-2 text-sm leading-[1.7]">
            <a href={`${site}/contacts/`} className={`flex min-h-11 items-center hover:underline ${focus}`}>Контактная информация</a>
            <a href="/documents/politic.pdf" target="_blank" rel="noreferrer" className={`flex min-h-11 items-center hover:underline ${focus}`}>Политика обработки<br />персональных данных</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
