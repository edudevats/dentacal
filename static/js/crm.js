/**
 * La Casa del Sr. Perez - CRM Kanban
 */
document.addEventListener('DOMContentLoaded', () => {
  cargarCRM();

  document.getElementById('btnGuardarCRM')?.addEventListener('click', guardarStatusCRM);
  document.getElementById('btnEnviarWA')?.addEventListener('click', enviarWhatsApp);
  document.getElementById('btnAgregarSeguimiento')?.addEventListener('click', agregarSeguimiento);
});

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
}

function crearTarjetaCRM(p) {
  const div = document.createElement('div');
  div.className = 'crm-card';
  div.addEventListener('click', () => abrirDetalleCRM(p.id));

  const nombre = document.createElement('div');
  nombre.className = 'patient-name';
  nombre.textContent = p.nombre_completo || p.nombre;
  div.appendChild(nombre);

  const meta = document.createElement('div');
  meta.className = 'patient-meta';
  const wa = p.whatsapp || p.telefono_tutor || '—';
  meta.textContent = wa;
  div.appendChild(meta);

  if (p.ultima_cita) {
    const ult = document.createElement('div');
    ult.className = 'patient-meta';
    ult.textContent = 'Ultima cita: ' + p.ultima_cita.slice(0, 10);
    div.appendChild(ult);
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

  // Citas
  const citasDiv = document.getElementById('crm_citas');
  while (citasDiv.firstChild) citasDiv.removeChild(citasDiv.firstChild);
  (p.citas || []).slice(0, 3).forEach(c => {
    const div = document.createElement('div');
    div.className = `mb-1 p-1 border-start border-3 ps-2 cita-${c.status}`;
    const txt = document.createElement('span');
    txt.textContent = `${c.fecha_inicio.slice(0,16).replace('T',' ')} - ${c.dentista} (${c.status})`;
    div.appendChild(txt);
    citasDiv.appendChild(div);
  });

  // Seguimientos
  const segDiv = document.getElementById('crm_seguimientos');
  while (segDiv.firstChild) segDiv.removeChild(segDiv.firstChild);
  (p.seguimientos || []).forEach(s => {
    const div = document.createElement('div');
    div.className = `d-flex justify-content-between align-items-center mb-1 p-1 border rounded ${s.completado ? 'bg-light text-muted' : ''}`;

    const info = document.createElement('span');
    info.textContent = `${s.tipo} - ${s.fecha_programada ? s.fecha_programada.slice(0,10) : 'Sin fecha'}`;
    div.appendChild(info);

    if (!s.completado) {
      const btn = document.createElement('button');
      btn.className = 'btn btn-sm btn-outline-success';
      btn.textContent = 'Completado';
      btn.addEventListener('click', () => completarSeguimiento(s.id));
      div.appendChild(btn);
    } else {
      const span = document.createElement('span');
      span.className = 'badge bg-success';
      span.textContent = 'Listo';
      div.appendChild(span);
    }
    segDiv.appendChild(div);
  });

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

async function agregarSeguimiento() {
  const id   = document.getElementById('crm_paciente_id').value;
  const tipo = prompt('Tipo de seguimiento:\n1. whatsapp_1\n2. whatsapp_2\n3. llamada\n\nEscribe el tipo:');
  if (!tipo) return;
  await apiFetch(`/api/crm/${id}/seguimiento`, {
    method: 'POST',
    body: JSON.stringify({ tipo: tipo.trim() }),
  });
  abrirDetalleCRM(id);
}

async function completarSeguimiento(segId) {
  await apiFetch(`/api/crm/seguimiento/${segId}/completar`, { method: 'POST', body: '{}' });
  const id = document.getElementById('crm_paciente_id').value;
  abrirDetalleCRM(id);
}
