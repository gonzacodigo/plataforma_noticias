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
const iaBox = document.querySelector('[data-ia]');
if (iaBox) {
  const remaining = iaBox.querySelector('[data-ai-remaining]');
  const tabs = [...iaBox.querySelectorAll('[data-ia-tab]')];
  const panels = [...iaBox.querySelectorAll('[data-ia-panel]')];
  const csrf = iaBox.querySelector('input[name=csrfmiddlewaretoken]');
  const pasos = {
    resumen_tendencia: ['Leyendo lo que publicó cada medio…', 'Cruzando los datos…', 'Armando el resumen…', 'Últimos retoques…'],
    guion: ['Leyendo la nota…', 'Buscando el hook…', 'Armando el guion…', 'Últimos retoques…'],
    otro: ['Leyendo la nota…', 'Eligiendo lo importante…', 'Escribiendo…', 'Últimos retoques…'],
  };
  const pausa = ms => new Promise(resolve => setTimeout(resolve, ms));
  const mostrar = tab => {
    tabs.forEach(t => {
      const activa = t === tab;
      t.setAttribute('aria-selected', activa ? 'true' : 'false');
      t.tabIndex = activa ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !activa;
    });
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => mostrar(tab));
    tab.addEventListener('keydown', event => {
      const paso = {ArrowRight: 1, ArrowLeft: -1}[event.key];
      if (!paso) return;
      const siguiente = tabs[(i + paso + tabs.length) % tabs.length];
      mostrar(siguiente);
      siguiente.focus();
    });
  });
  const actualizarRestantes = n => {
    if (remaining) remaining.textContent = n === 1 ? 'Te queda 1 generación este mes.' : `Te quedan ${n} generaciones este mes.`;
    if (n <= 0) iaBox.querySelectorAll('[data-ia-generar]').forEach(b => { b.disabled = true; });
  };
  panels.forEach(panel => {
    const form = panel.querySelector('[data-ia-form]');
    const generar = panel.querySelector('[data-ia-generar]');
    const nueva = panel.querySelector('[data-ia-nueva]');
    const loading = panel.querySelector('[data-ia-loading]');
    const estado = panel.querySelector('[data-ia-estado]');
    const result = panel.querySelector('[data-ia-result]');
    const text = panel.querySelector('[data-ia-text]');
    const guardar = panel.querySelector('[data-ia-guardar]');
    const guardado = panel.querySelector('[data-ia-guardado]');
    const error = panel.querySelector('[data-ia-error]');
    const mensajes = pasos[panel.dataset.tipo] || pasos.otro;
    let original = text.value;
    const fallar = mensaje => { error.textContent = mensaje; error.hidden = false; };

    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (text.value !== original && !confirm('Tenés cambios sin guardar. ¿Generar otra versión igual?')) return;
      generar.disabled = true;
      error.hidden = true;
      result.hidden = true;
      loading.hidden = false;
      let i = 0;
      estado.textContent = mensajes[0];
      const reloj = setInterval(() => { i = Math.min(i + 1, mensajes.length - 1); estado.textContent = mensajes[i]; }, 1600);
      let restantes = null;
      try {
        // Todas las generaciones tardan parecido, sean nuevas o reutilizadas.
        const [response] = await Promise.all([
          fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'X-Requested-With': 'XMLHttpRequest'}, credentials: 'same-origin'}),
          pausa(4000 + Math.random() * 3000),
        ]);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'No se pudo generar el texto.');
        text.value = original = data.texto;
        panel.dataset.guardarUrl = data.guardar_url;
        nueva.value = '1';
        generar.textContent = 'Generar otra versión ✨';
        guardar.disabled = true;
        guardado.textContent = '';
        panel.querySelector('.ai-note')?.remove();
        restantes = data.restantes;
      } catch (exc) {
        fallar(exc instanceof SyntaxError || exc instanceof TypeError ? 'No se pudo generar el texto. Probá de nuevo en un rato.' : exc.message);
      } finally {
        clearInterval(reloj);
        loading.hidden = true;
        result.hidden = !text.value;
        generar.disabled = false;
        if (restantes !== null) actualizarRestantes(restantes);
        if (restantes !== null) text.focus();
      }
    });

    text.addEventListener('input', () => {
      guardar.disabled = text.value === original;
      guardado.textContent = text.value === original ? '' : 'Cambios sin guardar';
    });

    guardar.addEventListener('click', async () => {
      guardar.disabled = true;
      error.hidden = true;
      const body = new FormData();
      body.append('csrfmiddlewaretoken', csrf.value);
      body.append('texto', text.value);
      try {
        const response = await fetch(panel.dataset.guardarUrl, {method: 'POST', body, headers: {'X-Requested-With': 'XMLHttpRequest'}, credentials: 'same-origin'});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'No se pudieron guardar los cambios.');
        original = text.value;
        guardado.textContent = 'Cambios guardados ✓';
      } catch (exc) {
        guardar.disabled = false;
        fallar(exc instanceof SyntaxError || exc instanceof TypeError ? 'No se pudieron guardar los cambios.' : exc.message);
      }
    });

    panel.querySelector('[data-ia-copiar]').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(text.value);
        notify('Texto copiado');
      } catch { text.select(); }
    });
  });
}
document.querySelectorAll('.card-image img, .article-cover, .article-gallery img').forEach(image => {
  image.addEventListener('error', () => { image.hidden = true; }, {once: true});
});
