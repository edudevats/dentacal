/**
 * La Casa del Sr. Perez — Monitor Bot WhatsApp
 * Usa DOM seguro (textContent) para todo contenido dinámico.
 */

let todasLasConversaciones = [];
let numeroActivo = null;

document.addEventListener('DOMContentLoaded', () => {
  cargarLista();

  document.getElementById('botSearch').addEventListener('input', filtrarLista);
  document.getElementById('botFiltro').addEventListener('change', filtrarLista);
  document.getElementById('btnRefrescar').addEventListener('click', () => cargarLista());
});


// ── Lista de conversaciones ──────────────────────────────────────────────────

async function cargarLista() {
  const resp = await apiFetch('/api/bot/conversaciones');
  if (!resp.ok) {
    document.getElementById('botStats').textContent = 'Error al cargar conversaciones.';
    return;
  }
  todasLasConversaciones = await resp.json();

  const conocidos = todasLasConversaciones.filter(c => c.paciente_id).length;
  document.getElementById('botStats').textContent =
    `${todasLasConversaciones.length} chats · ${conocidos} pacientes identificados`;

  filtrarLista();

  if (numeroActivo) {
    const aun = todasLasConversaciones.find(c => c.numero_telefono === numeroActivo);
    if (aun) seleccionarItem(aun);
  }
}

function filtrarLista() {
  const texto  = document.getElementById('botSearch').value.toLowerCase().trim();
  const filtro = document.getElementById('botFiltro').value;

  const lista = todasLasConversaciones.filter(c => {
    if (filtro === 'conocido'    && !c.paciente_id) return false;
    if (filtro === 'desconocido' &&  c.paciente_id) return false;
    if (texto) {
      const nombre = (c.paciente_nombre || '').toLowerCase();
      const numero = (c.numero_telefono  || '').toLowerCase();
      if (!nombre.includes(texto) && !numero.includes(texto)) return false;
    }
    return true;
  });

  const contenedor = document.getElementById('botLista');
  while (contenedor.firstChild) contenedor.removeChild(contenedor.firstChild);

  if (!lista.length) {
    const p = document.createElement('p');
    p.className = 'text-muted small text-center p-3';
    p.textContent = 'Sin resultados';
    contenedor.appendChild(p);
    return;
  }

  lista.forEach(c => contenedor.appendChild(crearItemLista(c)));
}


// ── Elemento de lista (DOM seguro) ───────────────────────────────────────────

function crearItemLista(conv) {
  const esConocido = !!conv.paciente_id;
  const colorAvatar = esConocido ? 'var(--primary)' : '#9e9e9e';
  const iniciales   = esConocido
    ? (conv.paciente_nombre || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()
    : '?';

  const div = document.createElement('div');
  div.className = 'bot-item' + (conv.numero_telefono === numeroActivo ? ' active' : '');
  div.dataset.numero = conv.numero_telefono;
  div.addEventListener('click', () => seleccionarItem(conv));

  // Avatar
  const avatar = document.createElement('div');
  avatar.className = 'bot-item-avatar';
  avatar.style.background = colorAvatar;
  avatar.textContent = iniciales;

  // Cuerpo
  const body = document.createElement('div');
  body.className = 'bot-item-body';

  // Fila superior: nombre + hora
  const fila1 = document.createElement('div');
  fila1.className = 'd-flex justify-content-between align-items-start gap-1';

  const spanNombre = document.createElement('span');
  spanNombre.className = 'bot-item-nombre text-truncate';
  spanNombre.textContent = esConocido ? (conv.paciente_nombre || conv.numero_telefono) : conv.numero_telefono;

  if (conv.paciente_estatus_crm) {
    const badge = document.createElement('span');
    badge.className = `badge badge-${conv.paciente_estatus_crm} ms-1`;
    badge.style.fontSize = '9px';
    badge.textContent = conv.paciente_estatus_crm;
    spanNombre.appendChild(badge);
  }

  const spanHora = document.createElement('span');
  spanHora.className = 'bot-item-hora flex-shrink-0';
  spanHora.textContent = conv.ultima_interaccion ? formatearTiempoRelativo(conv.ultima_interaccion) : '';

  fila1.appendChild(spanNombre);
  fila1.appendChild(spanHora);

  // Número (solo si hay nombre)
  if (esConocido) {
    const spanNum = document.createElement('div');
    spanNum.className = 'bot-item-numero font-monospace';
    spanNum.textContent = conv.numero_telefono;
    body.appendChild(fila1);
    body.appendChild(spanNum);
  } else {
    body.appendChild(fila1);
  }

  // Preview último mensaje
  const preview = document.createElement('div');
  preview.className = 'bot-item-preview';

  if (conv.ultimo_es_bot) {
    const iconBot = document.createElement('i');
    iconBot.className = 'bi bi-robot text-muted me-1';
    iconBot.style.fontSize = '10px';
    preview.appendChild(iconBot);
  }

  const previewText = document.createTextNode(
    conv.ultimo_mensaje
      ? conv.ultimo_mensaje.substring(0, 55) + (conv.ultimo_mensaje.length > 55 ? '…' : '')
      : ''
  );
  preview.appendChild(previewText);

  body.appendChild(preview);

  // Badge de conteo
  const countBadge = document.createElement('div');
  countBadge.className = 'bot-item-count';
  countBadge.textContent = conv.total_mensajes;

  div.appendChild(avatar);
  div.appendChild(body);
  div.appendChild(countBadge);
  return div;
}


// ── Selecciona una conversación ──────────────────────────────────────────────

async function seleccionarItem(conv) {
  numeroActivo = conv.numero_telefono;

  document.querySelectorAll('.bot-item').forEach(el => {
    el.classList.toggle('active', el.dataset.numero === numeroActivo);
  });

  document.getElementById('chatVacio').classList.add('d-none');
  const panel = document.getElementById('chatPanel');
  panel.classList.remove('d-none');

  // Avatar
  const esConocido = !!conv.paciente_id;
  const iniciales  = esConocido
    ? (conv.paciente_nombre || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()
    : '?';

  const avatar = document.getElementById('chatAvatar');
  avatar.textContent = iniciales;
  avatar.style.background = esConocido ? 'var(--primary)' : '#9e9e9e';

  document.getElementById('chatNombre').textContent = esConocido ? conv.paciente_nombre : 'Desconocido';
  document.getElementById('chatNumero').textContent = conv.numero_telefono;
  document.getElementById('chatMsgCount').textContent = `${conv.total_mensajes} msgs`;

  // Badge CRM
  const badgeEl = document.getElementById('chatCrmBadge');
  while (badgeEl.firstChild) badgeEl.removeChild(badgeEl.firstChild);
  if (conv.paciente_estatus_crm) {
    const b = document.createElement('span');
    b.className = `badge badge-${conv.paciente_estatus_crm}`;
    b.textContent = conv.paciente_estatus_crm.toUpperCase();
    badgeEl.appendChild(b);
  }

  // Botón CRM
  const btnCRM = document.getElementById('btnVerCRM');
  if (esConocido) {
    btnCRM.classList.remove('d-none');
    btnCRM.title = `Ver perfil de ${conv.paciente_nombre}`;
  } else {
    btnCRM.classList.add('d-none');
  }

  // Última interacción
  document.getElementById('chatUltimaFecha').textContent = conv.ultima_interaccion
    ? formatearFechaExacta(conv.ultima_interaccion)
    : '—';

  // Mensajes
  const contenedor = document.getElementById('chatMensajes');
  while (contenedor.firstChild) contenedor.removeChild(contenedor.firstChild);

  const cargando = document.createElement('div');
  cargando.className = 'text-center text-muted small py-3';
  cargando.textContent = 'Cargando...';
  contenedor.appendChild(cargando);

  const resp = await apiFetch(`/api/bot/hilo/${encodeURIComponent(conv.numero_telefono)}`);
  if (!resp.ok) {
    while (contenedor.firstChild) contenedor.removeChild(contenedor.firstChild);
    const err = document.createElement('div');
    err.className = 'text-danger text-center p-3';
    err.textContent = 'Error al cargar mensajes';
    contenedor.appendChild(err);
    return;
  }

  const mensajes = await resp.json();
  renderizarMensajes(mensajes, contenedor);
}


// ── Burbujas de chat (DOM seguro) ────────────────────────────────────────────

function renderizarMensajes(mensajes, contenedor) {
  while (contenedor.firstChild) contenedor.removeChild(contenedor.firstChild);

  if (!mensajes.length) {
    const p = document.createElement('p');
    p.className = 'text-muted text-center p-4';
    p.textContent = 'Sin mensajes registrados';
    contenedor.appendChild(p);
    return;
  }

  let fechaAnterior = null;

  mensajes.forEach(m => {
    const fecha = m.timestamp.slice(0, 10);

    if (fecha !== fechaAnterior) {
      const sep = document.createElement('div');
      sep.className = 'chat-fecha-sep';
      sep.textContent = formatearFechaSep(m.timestamp);
      contenedor.appendChild(sep);
      fechaAnterior = fecha;
    }

    const wrapper = document.createElement('div');
    wrapper.className = `chat-bubble-wrapper ${m.es_bot ? 'bot' : 'user'}`;

    const burbuja = document.createElement('div');
    burbuja.className = `chat-bubble ${m.es_bot ? 'bot' : 'user'}`;
    burbuja.textContent = m.mensaje;

    const ts = document.createElement('div');
    ts.className = 'chat-ts';
    ts.textContent = m.timestamp.slice(11, 16) + (m.es_bot ? ' · bot' : ' · paciente');

    wrapper.appendChild(burbuja);
    wrapper.appendChild(ts);
    contenedor.appendChild(wrapper);
  });

  contenedor.scrollTop = contenedor.scrollHeight;
}


// ── Formato de fechas ────────────────────────────────────────────────────────

function formatearTiempoRelativo(isoStr) {
  const ahora   = new Date();
  const fecha   = new Date(isoStr);
  const diffMs  = ahora - fecha;
  const diffMin = Math.floor(diffMs / 60000);
  const diffH   = Math.floor(diffMs / 3600000);
  const diffD   = Math.floor(diffMs / 86400000);

  if (diffMin < 1)  return 'ahora';
  if (diffMin < 60) return `${diffMin}m`;
  if (diffH   < 24) return `${diffH}h`;
  if (diffD   <  7) return `${diffD}d`;
  return fecha.toLocaleDateString('es-MX', { day: '2-digit', month: 'short' });
}

function formatearFechaExacta(isoStr) {
  return new Date(isoStr).toLocaleString('es-MX', {
    weekday: 'long', year: 'numeric', month: 'long',
    day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function formatearFechaSep(isoStr) {
  return new Date(isoStr).toLocaleDateString('es-MX', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
}
