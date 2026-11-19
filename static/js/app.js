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
function notify(message) {
  const notice = document.getElementById('notification');
  if (notice) {
    notice.textContent = message;
    notice.hidden = false;
    setTimeout(() => { notice.hidden = true; }, 2500);
  }
}
document.querySelectorAll('[data-copy-url]').forEach(button => {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copyUrl);
      notify('Enlace copiado');
    } catch { button.textContent = 'Copiá el enlace desde la barra de direcciones'; }
  });
});
const copyForm = document.querySelector('[data-copy-ia]');
if (copyForm) {
  const box = copyForm.closest('.ai-box');
  const submit = copyForm.querySelector('button');
  const result = box.querySelector('[data-ai-result]');
  const text = box.querySelector('[data-ai-text]');
  const error = box.querySelector('[data-ai-error]');
  const remaining = box.querySelector('[data-ai-remaining]');
  copyForm.addEventListener('submit', async event => {
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = 'Generando…';
    error.hidden = true;
    let blocked = false;
    try {
      const response = await fetch(copyForm.action, {
        method: 'POST',
        body: new FormData(copyForm),
        headers: {'X-Requested-With': 'XMLHttpRequest'},
        credentials: 'same-origin',
      });
      const data = await response.json();
      if (!response.ok) {
        blocked = response.status === 429;
        throw new Error(data.error || 'No se pudo generar el copy.');
      }
      text.value = data.copy;
      result.hidden = false;
      text.focus();
      if (remaining) remaining.textContent = `Te quedan ${data.restantes} este mes.`;
      blocked = data.restantes <= 0;
    } catch (exc) {
      error.textContent = exc instanceof SyntaxError ? 'No se pudo generar el copy.' : exc.message;
      error.hidden = false;
    } finally {
      submit.textContent = 'Generar otro copy ✨';
      submit.disabled = blocked;
    }
  });
  box.querySelector('[data-ai-copy]').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(text.value);
      notify('Copy copiado');
    } catch { text.select(); }
  });
}
document.querySelectorAll('.card-image img, .article-cover, .article-gallery img').forEach(image => {
  image.addEventListener('error', () => { image.hidden = true; }, {once: true});
});
