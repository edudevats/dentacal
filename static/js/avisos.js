/**
 * Campanita de avisos de recepcion (calendario).
 * GET /api/avisos/hoy, POST /api/avisos/leidos. Polling cada 90 s.
 */
(function () {
  const TIPOS = ['confirmo', 'no_contesto', 'cancelo_reagendo', 'comentario'];
  const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
  let datos = null;
  let tipoActivo = 'confirmo';

  function fechaCorta(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.split('-').map(Number);
    const dt = new Date(y, m - 1, d); // local, sin toISOString
    return DIAS[dt.getDay()] + ' ' + String(d).padStart(2, '0');
  }

  function el(tag, cls, texto) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function render() {
    if (!datos) return;
    const badge = document.getElementById('avisosBadge');
    badge.textContent = datos.no_leidos;
    badge.classList.toggle('d-none', !datos.no_leidos);

    document.querySelectorAll('#avisosTabs .avisos-tab').forEach(t => {
      const tipo = t.dataset.tipo;
      t.classList.toggle('on', tipo === tipoActivo);
      t.querySelector('.avisos-cnt').textContent = (datos[tipo] || []).length;
    });

    const lista = document.getElementById('avisosLista');
    lista.replaceChildren();
    const items = datos[tipoActivo] || [];
    if (!items.length) {
      lista.appendChild(el('div', 'avisos-vacio', 'Sin avisos'));
      return;
    }
    items.forEach(a => {
      const item = el('div', 'avisos-item' + (a.leido ? '' : ' nuevo'));
      item.appendChild(el('div', 'avisos-dot ' + a.tipo));
      const cuerpo = el('div');
      cuerpo.appendChild(el('b', null, a.paciente_nombre || 'Paciente'));
      const meta = [fechaCorta(a.cita_fecha), a.cita_hora, a.dentista, a.creado]
        .filter(Boolean).join(' · ');
      if (meta) cuerpo.appendChild(el('div', 'avisos-meta', meta));
      if (a.detalle) cuerpo.appendChild(el('div', 'avisos-detalle', a.detalle));
      item.appendChild(cuerpo);
      if (a.cita_id) {
        item.addEventListener('click', () => {
          bootstrap.Dropdown.getOrCreateInstance(document.getElementById('avisosBell')).hide();
          if (window.irACita) window.irACita(a.cita_id, a.cita_fecha);
        });
      } else {
        item.style.cursor = 'default';
      }
      lista.appendChild(item);
    });
  }

  async function cargar() {
    try {
      const resp = await apiFetch('/api/avisos/hoy');
      if (!resp.ok) return;
      datos = await resp.json();
      render();
    } catch (e) { /* red caida: se reintenta en el siguiente ciclo */ }
  }

  async function marcarLeidos(ev) {
    ev.preventDefault();
    try {
      const resp = await apiFetch('/api/avisos/leidos', { method: 'POST', body: '{}' });
      if (resp.ok) await cargar();
    } catch (e) { /* ignorar */ }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const bell = document.getElementById('avisosBell');
    if (!bell) return;
    document.querySelectorAll('#avisosTabs .avisos-tab').forEach(t => {
      t.addEventListener('click', () => { tipoActivo = t.dataset.tipo; render(); });
    });
    document.getElementById('avisosMarcarLeidos')?.addEventListener('click', marcarLeidos);
    bell.addEventListener('show.bs.dropdown', cargar);
    cargar();
    setInterval(cargar, 90000);
  });
})();
