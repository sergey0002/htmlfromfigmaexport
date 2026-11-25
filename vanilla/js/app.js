/* Behaviour translated from the Figma React export; no framework runtime. */
(() => {
  const header = document.querySelector('header');
  const headerBar = header.children[1];
  const menuButton = header.querySelector('[aria-controls="site-mobile-menu"]');
  const menuTemplate = document.getElementById('mobile-menu-template');

  menuButton.addEventListener('click', () => {
    const existing = document.getElementById('site-mobile-menu');
    const open = !existing;
    if (existing) existing.remove();
    else header.append(menuTemplate.content.cloneNode(true));
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
  });

  function updateHeader() {
    const compact = window.scrollY > 80;
    headerBar.classList.toggle('py-2.5', compact);
    for (const name of ['py-[19px]', 'md:py-[30px]', 'lg:py-6']) {
      headerBar.classList.toggle(name, !compact);
    }
  }
  window.addEventListener('scroll', updateHeader, { passive: true });
  updateHeader();

  for (const id of ['capital', 'military', 'tradein']) {
    const card = document.getElementById(id);
    const button = card.querySelector('button');
    const template = document.getElementById(`details-${id}`);
    button.addEventListener('click', () => {
      const current = card.querySelector('[data-card-details]');
      const expanded = !current;
      if (current) current.remove();
      else {
        const content = template.content.firstElementChild.cloneNode(true);
        content.dataset.cardDetails = '';
        button.before(content);
      }
      button.setAttribute('aria-expanded', String(expanded));
      button.firstChild.textContent = expanded ? 'Свернуть' : 'Подробнее об условиях';
      button.querySelector('svg').classList.toggle('rotate-45', expanded);
    });
  }

  const options = document.querySelectorAll('nav[aria-label="Способы покупки"] a');
  for (const link of options) {
    link.addEventListener('click', () => {
      for (const option of options) {
        const active = option === link;
        for (const name of ['border-[#e30613]', 'bg-[#e30613]', 'text-white']) option.classList.toggle(name, active);
        for (const name of ['border-neutral-200', 'bg-white', 'hover:border-[#e30613]', 'hover:text-[#e30613]']) option.classList.toggle(name, !active);
        option.firstElementChild.classList.toggle('text-white', active);
        option.firstElementChild.classList.toggle('text-neutral-500', !active);
      }
    });
  }

  // The source replaces unavailable images with an icon and the alt text. Keep
  // the fallback visible without JS, and use the original asset if it appears.
  for (const fallback of document.querySelectorAll('[data-image-src]')) {
    const image = new Image();
    image.alt = fallback.dataset.imageAlt;
    image.className = fallback.dataset.imageClass;
    image.addEventListener('load', () => fallback.replaceWith(image), { once: true });
    image.src = fallback.dataset.imageSrc;
  }

  // Match the source's Image component for other assets that fail to load.
  function replaceBrokenImage(image) {
    if (!image.isConnected) return;
    const span = document.createElement('span');
    span.className = 'flex items-center gap-2 text-sm font-semibold';
    span.innerHTML = '<svg class="h-6 w-6 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 8 9-5 9 5H3Zm2 3v7m7-7v7m7-7v7M3 21h18"></path></svg>';
    span.append(document.createTextNode(image.alt));
    image.replaceWith(span);
  }
  for (const image of document.querySelectorAll('#root img')) {
    if (image.complete && !image.naturalWidth) replaceBrokenImage(image);
    else image.addEventListener('error', () => replaceBrokenImage(image), { once: true });
  }
})();
