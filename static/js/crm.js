/**
 * La Casa del Sr. Perez - CRM Kanban
 */
document.addEventListener('DOMContentLoaded', () => {
  cargarCRM();
  initCrmFilters();
  initCrmBuscar();
  cargarDoctoresCRM();
  document.getElementById('crmDoctorFiltro')?.addEventListener('change', filtrarTarjetasCRM);

  document.getElementById('btnGuardarCRM')?.addEventListener('click', guardarStatusCRM);
  document.getElementById('btnEnviarWA')?.addEventListener('click', enviarWhatsApp);
  document.getElementById('btnAgregarSeguimiento')?.addEventListener('click', mostrarFormSeguimiento);
  document.getElementById('btnCancelarSeg')?.addEventListener('click', ocultarFormSeguimiento);
  document.getElementById('btnGuardarSeg')?.addEventListener('click', guardarSeguimiento);
});

/* ── Etiquetas de seguimiento y cita ── */
const SEG_LABEL = {
  confirmacion_cita: 'Confirmación de cita',
  recordatorio_cita: 'Recordatorio de cita',
  post_consulta: 'Post-consulta',
  reactivacion: 'Reactivación (inactivo)',
  presupuesto: 'Seguimiento de presupuesto',
  tratamiento_pendiente: 'Tratamiento pendiente',
  limpieza_control: 'Limpieza / control semestral',
  anticipo_pendiente: 'Anticipo pendiente',
  resena: 'Reseña Google',
  cumpleanos: 'Felicitación cumpleaños',
  whatsapp_1: 'WhatsApp 1',
  whatsapp_2: 'WhatsApp 2',
  llamada: 'Llamada',
};
const SEG_ICON = {
  confirmacion_cita: 'bi-calendar-check',
  recordatorio_cita: 'bi-alarm',
  post_consulta: 'bi-heart-pulse',
  reactivacion: 'bi-arrow-repeat',
  presupuesto: 'bi-cash-coin',
  tratamiento_pendiente: 'bi-clipboard2-pulse',
  limpieza_control: 'bi-calendar2-week',
  anticipo_pendiente: 'bi-credit-card',
  resena: 'bi-star',
  cumpleanos: 'bi-gift',
  whatsapp_1: 'bi-whatsapp',
  whatsapp_2: 'bi-whatsapp',
  llamada: 'bi-telephone',
};
const CITA_BADGE = {
  pre_cita:      { cls: 'bg-info text-dark',    label: 'Pre-cita' },
  pendiente:     { cls: 'bg-warning text-dark', label: 'Pendiente' },
  confirmada:    { cls: 'bg-success',           label: 'Confirmada' },
  completada:    { cls: 'bg-success',           label: 'Completada' },
  no_asistencia: { cls: 'bg-danger',            label: 'No asistio' },
};

/* ── Search ── */
function initCrmBuscar() {
  const input = document.getElementById('crmBuscar');
  if (!input) return;
  input.addEventListener('input', () => filtrarTarjetasCRM());
}

async function cargarDoctoresCRM() {
  const select = document.getElementById('crmDoctorFiltro');
  if (!select) return;
  try {
    const resp = await apiFetch('/api/dentistas?activos=true');
    const data = await resp.json();
    data.forEach(d => {
      const opt = document.createElement('option');
      opt.value = String(d.id);
      opt.textContent = d.nombre;
      select.appendChild(opt);
    });
  } catch (e) {
    console.error('Error cargando doctores (crm):', e);
  }
}

function filtrarTarjetasCRM() {
  const query = (document.getElementById('crmBuscar')?.value || '').toLowerCase().trim();
  const doctorSel = document.getElementById('crmDoctorFiltro')?.value || '';
  document.querySelectorAll('#crmKanban .crm-card').forEach(card => {
    const texto = card.textContent.toLowerCase();
    const matchTexto = (!query || texto.includes(query));
    const matchDoctor = (!doctorSel || card.dataset.doctorId === doctorSel);
    card.style.display = (matchTexto && matchDoctor) ? '' : 'none';
  });
  // Update visible counts
  ['alta', 'activo', 'prospecto', 'baja'].forEach(status => {
    const col = document.getElementById(`col-${status}`);
    if (!col) return;
    const visible = col.querySelectorAll('.crm-card:not([style*="display: none"])').length;
    const cnt = document.getElementById(`count-${status}`);
    const stat = document.getElementById(`stat-${status}`);
    if (cnt) cnt.textContent = visible;
    if (stat) stat.textContent = visible;
  });
}

/* ── Filter buttons ── */
function initCrmFilters() {
  document.querySelectorAll('.crm-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.classList.toggle('active');
      aplicarFiltrosCRM();
    });
  });
}

function aplicarFiltrosCRM() {
  const activos = new Set();
  document.querySelectorAll('.crm-filter-btn.active').forEach(b => {
    activos.add(b.dataset.status);
  });

  document.querySelectorAll('#crmKanban > .crm-col').forEach(col => {
    const status = col.dataset.status;
    col.style.display = activos.has(status) ? '' : 'none';
  });
}

async function cargarCRM() {
  const resp = await apiFetch('/api/crm');
  const pacientes = await resp.json();

  const cols = { alta: [], activo: [], prospecto: [], baja: [] };
  pacientes.forEach(p => {
    const status = p.estatus_crm || 'prospecto';
    if (cols[status]) cols[status].push(p);
  });

  ['alta', 'activo', 'prospecto', 'baja'].forEach(status => {
    const col = document.getElementById(`col-${status}`);
    const cnt = document.getElementById(`count-${status}`);
    const stat = document.getElementById(`stat-${status}`);
    if (!col) return;

    while (col.firstChild) col.removeChild(col.firstChild);
    const lista = cols[status];
    if (cnt) cnt.textContent = lista.length;
    if (stat) stat.textContent = lista.length;

    lista.forEach(p => {
      const card = crearTarjetaCRM(p);
      col.appendChild(card);
    });
  });

  // Re-apply search filter if there's text in the search box
  filtrarTarjetasCRM();
}

function crearTarjetaCRM(p) {
  const div = document.createElement('div');
  div.className = 'crm-card';
  div.dataset.doctorId = (p.doctor_id != null) ? String(p.doctor_id) : '';
  div.addEventListener('click', () => abrirDetalleCRM(p.id));

  const nombre = document.createElement('div');
  nombre.className = 'patient-name';
  nombre.textContent = p.nombre_completo || p.nombre;
  if (p.es_problematico) {
    const warn = document.createElement('span');
    warn.className = 'badge bg-danger ms-1';
    warn.style.fontSize = '10px';
    warn.textContent = 'PROBLEMATICO';
    nombre.appendChild(warn);
  }
  div.appendChild(nombre);

  const meta = document.createElement('div');
  meta.className = 'patient-meta';
  const wa = p.whatsapp || p.telefono_tutor || '—';
  meta.textContent = wa;
  div.appendChild(meta);

  const docMeta = document.createElement('div');
  docMeta.className = 'patient-meta';
  docMeta.textContent = 'Dr: ' + (p.doctor_nombre || 'Sin asignar');
  div.appendChild(docMeta);

  if (p.proxima_cita) {
    const prox = document.createElement('div');
    prox.className = 'mt-1';
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.style.background = 'var(--primary)';
    badge.style.color = '#fff';
    const ico = document.createElement('i');
    ico.className = 'bi bi-calendar-check me-1';
    badge.appendChild(ico);
    badge.appendChild(document.createTextNode('Proxima: ' + formatearFechaCita(p.proxima_cita)));
    prox.appendChild(badge);
    div.appendChild(prox);
  } else if (p.ultima_cita) {
    const ult = document.createElement('div');
    ult.className = 'patient-meta';
    ult.textContent = 'Ultima cita: ' + p.ultima_cita.slice(0, 10);
    div.appendChild(ult);
  }

  if (p.ultima_interaccion_bot) {
    const bot = document.createElement('div');
    bot.className = 'patient-meta mt-1';
    const icono = document.createElement('i');
    icono.className = 'bi bi-robot me-1';
    icono.style.color = 'var(--primary)';
    const txt = document.createTextNode('Bot: ' + formatearFechaCorta(p.ultima_interaccion_bot));
    bot.appendChild(icono);
    bot.appendChild(txt);
    div.appendChild(bot);
  }

  if (p.siguiente_seguimiento) {
    const seg = document.createElement('div');
    seg.className = 'mt-1';
    const badge = document.createElement('span');
    badge.className = 'badge bg-warning text-dark';
    badge.textContent = 'Seguimiento: ' + (p.siguiente_seguimiento.tipo || '');
    seg.appendChild(badge);
    div.appendChild(seg);
  }

  return div;
}

async function abrirDetalleCRM(pacienteId) {
  const resp = await apiFetch(`/api/crm/${pacienteId}`);
  const p = await resp.json();

  document.getElementById('crm_paciente_id').value = pacienteId;
  document.getElementById('crmNombrePaciente').textContent = p.nombre_completo || p.nombre;
  document.getElementById('crm_estatus').value = p.estatus_crm;

  // Historial conversacion
  const histDiv = document.getElementById('crm_historial');
  const convResp = await apiFetch(`/api/crm/${pacienteId}/conversacion`);
  const mensajes = await convResp.json();
  while (histDiv.firstChild) histDiv.removeChild(histDiv.firstChild);

  if (mensajes.length === 0) {
    const p2 = document.createElement('p');
    p2.className = 'text-muted text-center';
    p2.textContent = 'Sin mensajes';
    histDiv.appendChild(p2);
  } else {
    mensajes.forEach(m => {
      const d = document.createElement('div');
      d.className = `mb-1 p-1 rounded ${m.es_bot ? 'bg-light text-end' : ''}`;
      const texto = document.createElement('div');
      texto.textContent = m.mensaje;
      const ts = document.createElement('div');
      ts.className = 'text-muted' ;
      ts.style.fontSize = '10px';
      ts.textContent = m.timestamp.slice(0, 16).replace('T', ' ') + (m.es_bot ? ' (bot)' : ' (paciente)');
      d.appendChild(texto);
      d.appendChild(ts);
      histDiv.appendChild(d);
    });
    histDiv.scrollTop = histDiv.scrollHeight;
  }

  // Proximas citas (solo futuras)
  const citasDiv = document.getElementById('crm_citas');
  while (citasDiv.firstChild) citasDiv.removeChild(citasDiv.firstChild);
  const proximas = p.proximas_citas || [];
  if (proximas.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'text-muted text-center mb-0';
    empty.textContent = 'Sin citas proximas';
    citasDiv.appendChild(empty);
  } else {
    proximas.forEach(c => {
      const div = document.createElement('div');
      div.className = `d-flex justify-content-between align-items-center mb-1 p-2 border-start border-3 ps-2 cita-${c.status}`;

      const info = document.createElement('div');
      const fecha = document.createElement('div');
      fecha.className = 'fw-semibold';
      fecha.textContent = formatearFechaCita(c.fecha_inicio);
      const detalle = document.createElement('div');
      detalle.className = 'text-muted';
      detalle.style.fontSize = '11px';
      detalle.textContent = `${c.dentista}${c.tipo_cita ? ' · ' + c.tipo_cita : ''}`;
      info.appendChild(fecha);
      info.appendChild(detalle);
      div.appendChild(info);

      const b = CITA_BADGE[c.status] || { cls: 'bg-secondary', label: c.status };
      const badge = document.createElement('span');
      badge.className = `badge ${b.cls}`;
      badge.textContent = b.label;
      div.appendChild(badge);

      citasDiv.appendChild(div);
    });
  }

  // Historial de asistencias
  const asistDiv = document.getElementById('crm_historial_asistencias');
  const statsDiv = document.getElementById('crm_stats_asistencia');
  while (asistDiv.firstChild) asistDiv.removeChild(asistDiv.firstChild);

  const stats = p.estadisticas_asistencia;
  if (stats && stats.total > 0) {
    statsDiv.textContent = `${stats.asistencias}/${stats.total} (${stats.tasa_asistencia}%)`;
  } else {
    statsDiv.textContent = '';
  }

  const historial = p.historial_asistencias || [];
  if (historial.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'text-muted text-center';
    empty.textContent = 'Sin registro de asistencias';
    asistDiv.appendChild(empty);
  } else {
    historial.forEach(h => {
      const row = document.createElement('div');
      row.className = 'd-flex justify-content-between align-items-center mb-1 p-1 border rounded';

      const info = document.createElement('span');
      const fecha = h.fecha ? h.fecha.slice(0, 10) : '';
      info.textContent = `${fecha} - ${h.tipo_cita} - ${h.dentista}`;
      row.appendChild(info);

      const badge = document.createElement('span');
      if (h.status === 'completada') {
        badge.className = 'badge bg-success';
        badge.textContent = 'Asistio';
      } else {
        badge.className = 'badge bg-danger';
        badge.textContent = 'No asistio';
      }
      row.appendChild(badge);
      asistDiv.appendChild(row);
    });
  }

  // Seguimientos
  ocultarFormSeguimiento();
  const segDiv = document.getElementById('crm_seguimientos');
  while (segDiv.firstChild) segDiv.removeChild(segDiv.firstChild);
  const seguimientos = p.seguimientos || [];
  if (seguimientos.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'text-muted text-center mb-0';
    empty.textContent = 'Sin seguimientos';
    segDiv.appendChild(empty);
  } else {
    seguimientos.forEach(s => {
      const div = document.createElement('div');
      div.className = `d-flex justify-content-between align-items-center mb-1 p-2 border rounded ${s.completado ? 'bg-light' : ''}`;

      const info = document.createElement('div');
      info.className = 'd-flex align-items-center gap-2';
      const icon = document.createElement('i');
      icon.className = `bi ${SEG_ICON[s.tipo] || 'bi-bell'}`;
      icon.style.color = 'var(--primary)';
      const texto = document.createElement('div');
      const titulo = document.createElement('div');
      titulo.className = `fw-semibold ${s.completado ? 'text-muted' : ''}`;
      titulo.textContent = SEG_LABEL[s.tipo] || s.tipo;
      const sub = document.createElement('div');
      sub.className = 'text-muted';
      sub.style.fontSize = '11px';
      sub.textContent = s.fecha_programada ? formatearFechaCita(s.fecha_programada, false) : 'Sin fecha';
      if (s.notas) sub.textContent += ' · ' + s.notas;
      texto.appendChild(titulo);
      texto.appendChild(sub);
      info.appendChild(icon);
      info.appendChild(texto);
      div.appendChild(info);

      if (!s.completado) {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-outline-success';
        btn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Completar';
        btn.addEventListener('click', () => completarSeguimiento(s.id));
        div.appendChild(btn);
      } else {
        const span = document.createElement('span');
        span.className = 'badge bg-success';
        span.innerHTML = '<i class="bi bi-check-lg me-1"></i>Listo';
        div.appendChild(span);
      }
      segDiv.appendChild(div);
    });
  }

  new bootstrap.Modal(document.getElementById('modalCRM')).show();
}

async function guardarStatusCRM() {
  const id      = document.getElementById('crm_paciente_id').value;
  const estatus = document.getElementById('crm_estatus').value;
  const resp = await apiFetch(`/api/crm/${id}/estatus`, {
    method: 'PUT',
    body: JSON.stringify({ estatus }),
  });
  if (resp.ok) {
    bootstrap.Modal.getInstance(document.getElementById('modalCRM'))?.hide();
    cargarCRM();
  }
}

async function enviarWhatsApp() {
  const id      = document.getElementById('crm_paciente_id').value;
  const mensaje = document.getElementById('crm_wa_mensaje').value.trim();
  if (!mensaje) { alert('Escribe el mensaje.'); return; }

  const resp = await apiFetch(`/api/crm/${id}/enviar-whatsapp`, {
    method: 'POST',
    body: JSON.stringify({ mensaje }),
  });
  const data = await resp.json();

  const btn = document.getElementById('btnEnviarWA');
  if (resp.ok) {
    btn.textContent = 'Enviado!';
    document.getElementById('crm_wa_mensaje').value = '';
    setTimeout(() => { btn.textContent = 'Enviar'; }, 3000);
  } else {
    alert(data.error || 'Error al enviar');
  }
}

function mostrarFormSeguimiento() {
  const form = document.getElementById('crm_seg_form');
  if (form) form.style.display = '';
}

function ocultarFormSeguimiento() {
  const form = document.getElementById('crm_seg_form');
  if (!form) return;
  form.style.display = 'none';
  document.getElementById('seg_tipo').value = 'confirmacion_cita';
  document.getElementById('seg_fecha').value = '';
  document.getElementById('seg_notas').value = '';
}

async function guardarSeguimiento() {
  const id    = document.getElementById('crm_paciente_id').value;
  const tipo  = document.getElementById('seg_tipo').value;
  const fecha = document.getElementById('seg_fecha').value;
  const notas = document.getElementById('seg_notas').value.trim();

  const payload = { tipo };
  if (fecha) payload.fecha_programada = fecha;
  if (notas) payload.notas = notas;

  const resp = await apiFetch(`/api/crm/${id}/seguimiento`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (resp.ok) {
    abrirDetalleCRM(id);
  } else {
    const data = await resp.json().catch(() => ({}));
    alert(data.error || 'Error al guardar el seguimiento');
  }
}

async function completarSeguimiento(segId) {
  await apiFetch(`/api/crm/seguimiento/${segId}/completar`, { method: 'POST', body: '{}' });
  const id = document.getElementById('crm_paciente_id').value;
  abrirDetalleCRM(id);
}

function formatearFechaCita(isoStr, conHora = true) {
  const fecha = new Date(isoStr);
  if (isNaN(fecha)) return isoStr;
  const opts = { day: '2-digit', month: 'short', year: 'numeric' };
  if (conHora) { opts.hour = '2-digit'; opts.minute = '2-digit'; }
  return fecha.toLocaleString('es-MX', opts);
}

function formatearFechaCorta(isoStr) {
  const ahora   = new Date();
  const fecha   = new Date(isoStr);
  const diffMs  = ahora - fecha;
  const diffMin = Math.floor(diffMs / 60000);
  const diffH   = Math.floor(diffMs / 3600000);
  const diffD   = Math.floor(diffMs / 86400000);

  if (diffMin < 1)  return 'ahora';
  if (diffMin < 60) return `hace ${diffMin}m`;
  if (diffH   < 24) return `hace ${diffH}h`;
  if (diffD   <  7) return `hace ${diffD}d`;
  return fecha.toLocaleDateString('es-MX', { day: '2-digit', month: 'short' });
}
