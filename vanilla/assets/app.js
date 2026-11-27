(() => {
  const currentPath = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.desktop-nav a').forEach(a => { if (a.getAttribute('href').split('/').pop() === currentPath || (location.pathname.includes('/program/') && a.getAttribute('href').endsWith('/program.html'))) { a.classList.add('active'); a.setAttribute('aria-current', 'page'); } });
  const menu = document.querySelector('.mobile-menu');
  const mobileNav = document.querySelector('#mobile-nav');
  menu?.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    mobileNav.hidden = !open;
    menu.textContent = open ? '✕' : '☰';
  });
  const modal = document.querySelector('.modal-backdrop');
  let previousFocus;
  function closeModal() {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.style.overflow = '';
    previousFocus?.focus();
  }
  document.querySelectorAll('[data-modal]').forEach(button => button.addEventListener('click', () => {
    previousFocus = button;
    const type = button.dataset.modal;
    const descriptions = {'Вступить в партию':'Станьте частью команды, которая создает будущее Абхазии.', 'Стать волонтером':'Присоединяйтесь к проектам в своем районе.', 'Предложить идею':'Расскажите, что можно изменить к лучшему.'};
    modal.querySelector('form').reset();
    modal.querySelector('.form-status').textContent = '';
    modal.querySelector('#modal-title').textContent = type;
    modal.querySelector('#modal-description').textContent = descriptions[type];
    const idea = type === 'Предложить идею';
    modal.querySelector('#modal-field-label').textContent = idea ? 'Ваша идея' : 'Ваш район';
    const region = modal.querySelector('#modal-region');
    const textarea = modal.querySelector('#modal-idea');
    region.hidden = idea; region.required = !idea;
    textarea.hidden = !idea; textarea.required = idea;
    modal.hidden = false; document.body.style.overflow = 'hidden';
    modal.querySelector('.modal-close').focus();
  }));
  modal?.querySelector('.modal-close').addEventListener('click', closeModal);
  modal?.addEventListener('click', e => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (modal && !modal.hidden) closeModal();
      else if (menu && !mobileNav.hidden) { mobileNav.hidden = true; menu.setAttribute('aria-expanded','false'); menu.textContent = '☰'; menu.focus(); }
    }
    if (e.key === 'Tab' && modal && !modal.hidden) {
      const focusable = [...modal.querySelectorAll('button, input, select:not([hidden]), textarea:not([hidden]), a[href]')].filter(el => !el.disabled && el.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  document.querySelectorAll('[data-demo-form]').forEach(form => form.addEventListener('submit', e => {
    e.preventDefault();
    form.querySelector('.form-status').textContent = 'Отправка недоступна: форма не подключена к серверу.';
  }));
  document.querySelectorAll('.map-point').forEach(point => point.addEventListener('click', () => {
    const map = point.closest('.map-wrap');
    map.querySelectorAll('.map-point').forEach(p => p.classList.toggle('selected', p === point));
    map.querySelector('.map-info h3').textContent = point.dataset.region;
    map.querySelector('.map-info strong').textContent = point.dataset.projects;
  }));
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('active', b === button));
    let number = 0;
    document.querySelectorAll('[data-kind]').forEach(item => {
      item.hidden = button.dataset.filter !== 'Все' && item.dataset.kind !== button.dataset.filter;
      if (!item.hidden) item.querySelector('span').textContent = String(++number).padStart(2,'0');
    });
  }));
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b === button));
    document.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== button.dataset.tab; });
  }));
  const stories = [['АБ','Аслан Бжания','Депутат, экономист','Помог создать программу грантов для молодых предпринимателей.'],['МГ','Мадина Гунба','Волонтер, врач','Организует выездные приемы в отдаленных селах.'],['ДА','Денис Ардзинба','Координатор молодежи','Объединил 400 волонтеров по всей Абхазии.']];
  let current = 0;
  document.querySelectorAll('[data-slide]').forEach(button => button.addEventListener('click', () => {
    current = (current + Number(button.dataset.slide) + stories.length) % stories.length;
    const feature = document.querySelector('.people-feature'), [initials, name, role, story] = stories[current];
    feature.querySelector('.avatar-large').textContent = initials;
    feature.querySelector('h3').textContent = name; feature.querySelector('b').textContent = role;
    feature.querySelector('p').textContent = story;
    feature.querySelector('.story-count').innerHTML = `0${current + 1}<small>/ 03</small>`;
  }));
})();
