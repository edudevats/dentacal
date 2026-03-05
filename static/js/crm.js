/* CRM — La Casa del Sr. Pérez */

document.addEventListener('DOMContentLoaded', function () {
  cargarCrm();

  document.getElementById('btnBuscarCrm').addEventListener('click', cargarCrm);
  document.getElementById('searchCrm').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') cargarCrm();
  });
  document.getElementById('filterEstado').addEventListener('change', cargarCrm);
  document.getElementById('btnEnviarWA').addEventListener('click', enviarWA);
});

async function cargarCrm() {
  const q = document.getElementById('searchCrm').value.trim();
  const estado = document.getElementById('filterEstado').value;

  const params = new URLSearchParams();
  if (q) params.append('q', q);
  if (estado) params.append('estado', estado);

  const res = await fetch(`/api/crm/pacientes?${params}`);
  const pacientes = await res.json();
  renderTabla(pacientes);
}

function renderTabla(pacientes) {
  const tbody = document.getElementById('crmBody');
  if (!pacientes.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">Sin resultados</td></tr>';
    return;
  }

  tbody.innerHTML = pacientes.map(p => {
    const color = ESTADO_COLORES[p.estado_crm] || '#6c757d';
    const ultimaCita = p.fecha_ultima_cita
      ? new Date(p.fecha_ultima_cita).toLocaleDateString('es-MX')
      : '—';
    return `
      <tr>
        <td>
          <a href="#" class="fw-semibold text-decoration-none"
             onclick="verPaciente(${p.id},'${escHtml(p.nombre)}'); return false;">
            ${escHtml(p.nombre)}
          </a>
        </td>
        <td>
          <a href="https://wa.me/${p.telefono.replace('+','')}" target="_blank"
             class="text-decoration-none">
            <i class="bi bi-whatsapp text-success"></i> ${p.telefono}
          </a>
        </td>
        <td>${ultimaCita}</td>
        <td>
          <span class="badge" style="background:${color}; color:#fff">
            ${p.estado_crm.replace('_',' ')}
          </span>
        </td>
        <td>${p.total_citas}</td>
        <td>
          <div class="d-flex gap-1">
            <button class="btn btn-xs btn-outline-secondary" onclick="verPaciente(${p.id},'${escHtml(p.nombre)}')">
              <i class="bi bi-eye"></i>
            </button>
            <button class="btn btn-xs btn-success" onclick="abrirEnviarWA(${p.id})">
              <i class="bi bi-whatsapp"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function verPaciente(id, nombre) {
  const res = await fetch(`/api/pacientes/${id}`);
  const p = await res.json();

  document.getElementById('modalPacienteNombre').textContent = nombre;

  const ultimaCita = p.fecha_ultima_cita
    ? new Date(p.fecha_ultima_cita).toLocaleString('es-MX')
    : 'Sin citas';

  const citasHtml = (p.citas || []).slice(0, 8).map(c => {
    const fecha = new Date(c.fecha_inicio).toLocaleString('es-MX');
    return `<tr>
      <td>${fecha}</td>
      <td>${c.tipo_cita_nombre || '—'}</td>
      <td>${c.dentista_nombre || '—'}</td>
      <td><span class="badge estado-${c.estado}">${c.estado}</span></td>
    </tr>`;
  }).join('');

  const color = ESTADO_COLORES[p.estado_crm] || '#6c757d';

  document.getElementById('modalPacienteBody').innerHTML = `
    <div class="row g-3">
      <div class="col-12 col-md-5">
        <table class="table table-sm table-borderless small">
          <tr><td class="text-muted">Teléfono</td><td>${p.telefono}</td></tr>
          ${p.email ? `<tr><td class="text-muted">Email</td><td>${p.email}</td></tr>` : ''}
          <tr><td class="text-muted">Estado CRM</td>
              <td><span class="badge" style="background:${color};color:#fff">${p.estado_crm.replace('_',' ')}</span></td></tr>
          <tr><td class="text-muted">Última cita</td><td>${ultimaCita}</td></tr>
          ${p.nombre_escuela ? `<tr><td class="text-muted">Escuela</td><td>${p.nombre_escuela}</td></tr>` : ''}
        </table>
        <div class="d-flex gap-1 mt-2">
          <select class="form-select form-select-sm" id="nuevoEstadoCrm">
            ${['nuevo','activo','seguimiento_1','seguimiento_2','llamada_pendiente','perdido'].map(e =>
              `<option value="${e}" ${e === p.estado_crm ? 'selected':''}>${e.replace('_',' ')}</option>`
            ).join('')}
          </select>
          <button class="btn btn-teal btn-sm" onclick="cambiarEstadoCrm(${p.id})">Cambiar</button>
        </div>
        <div class="mt-2">
          <a href="/pacientes/${p.id}" class="btn btn-outline-teal btn-sm w-100">
            <i class="bi bi-person-vcard"></i> Ficha completa
          </a>
        </div>
      </div>
      <div class="col-12 col-md-7">
        <h6 class="mb-2">Últimas citas</h6>
        <div class="table-responsive">
          <table class="table table-sm table-hover mb-0">
            <thead class="table-light"><tr><th>Fecha</th><th>Tipo</th><th>Doctor</th><th>Estado</th></tr></thead>
            <tbody>${citasHtml || '<tr><td colspan="4" class="text-muted text-center">Sin citas</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  new bootstrap.Modal(document.getElementById('modalPacienteCrm')).show();
}

async function cambiarEstadoCrm(pacienteId) {
  const estado = document.getElementById('nuevoEstadoCrm').value;
  const res = await fetch(`/api/crm/pacientes/${pacienteId}/estado`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ estado_crm: estado }),
  });
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('modalPacienteCrm'))?.hide();
    cargarCrm();
  }
}

function abrirEnviarWA(pacienteId) {
  document.getElementById('waPacienteId').value = pacienteId;
  document.getElementById('waMensajeCustom').value = '';
  document.getElementById('waError').classList.add('d-none');
  new bootstrap.Modal(document.getElementById('modalEnviarWA')).show();
}

async function enviarWA() {
  const pacienteId = document.getElementById('waPacienteId').value;
  const tipo = document.getElementById('waTipo').value;
  const mensajeCustom = document.getElementById('waMensajeCustom').value.trim();
  const errEl = document.getElementById('waError');
  errEl.classList.add('d-none');

  const body = { paciente_id: parseInt(pacienteId), tipo };
  if (mensajeCustom) body.mensaje = mensajeCustom;

  const res = await fetch('/api/crm/enviar_wa', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('modalEnviarWA'))?.hide();
    showToast('Mensaje enviado correctamente ✅');
  } else {
    const data = await res.json();
    errEl.textContent = data.error || 'Error al enviar';
    errEl.classList.remove('d-none');
  }
}

function showToast(msg) {
  const toast = document.createElement('div');
  toast.className = 'position-fixed bottom-0 end-0 m-3 alert alert-success shadow';
  toast.style.zIndex = '9999';
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
