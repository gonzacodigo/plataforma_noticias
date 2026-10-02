'use strict';
const menu = document.querySelector('.menu-toggle');
const navigation = document.getElementById('main-nav');
if (menu && navigation) {
  menu.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    navigation.classList.toggle('is-open', open);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      menu.setAttribute('aria-expanded', 'false');
      navigation.classList.remove('is-open');
    }
  });
}
document.querySelectorAll('[data-copy-url]').forEach(button => {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copyUrl);
      const notice = document.getElementById('notification');
      if (notice) {
        notice.textContent = 'Enlace copiado';
        notice.hidden = false;
        setTimeout(() => { notice.hidden = true; }, 2500);
      }
    } catch { button.textContent = 'Copiá el enlace desde la barra de direcciones'; }
  });
});
document.querySelectorAll('.card-image img, .article-cover, .article-gallery img').forEach(image => {
  image.addEventListener('error', () => { image.hidden = true; }, {once: true});
});
