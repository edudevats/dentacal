/* Doctores — La Casa del Sr. Pérez */

document.addEventListener('DOMContentLoaded', function () {
  // Guardar doctor (nuevo / editar)
  document.getElementById('btnGuardarDoctor').addEventListener('click', guardarDoctor);
  document.getElementById('btnAgregarHorario').addEventListener('click', agregarHorario);
  document.getElementById('btnAgregarBloqueo').addEventListener('click', agregarBloqueo);
});

function editarDoctor(id) {
  fetch(`/api/doctores/${id}`)
    .then(r => r.json())
    .then(d => {
      document.getElementById('docId').value = d.id;
      document.getElementById('docNombre').value = d.nombre;
      document.getElementById('docColor').value = d.color || '#3788d8';
      document.getElementById('docEspecialidad').value = d.especialidad || '';
      document.getElementById('docTelefono').value = d.telefono || '';
      document.getElementById('docActivo').checked = d.activo;
      document.getElementById('tituloModalDoctor').textContent = 'Editar Doctor';
      new bootstrap.Modal(document.getElementById('modalNuevoDoctor')).show();
    });
}

async function guardarDoctor() {
  const id = document.getElementById('docId').value;
  const errEl = document.getElementById('errorDoctor');
  errEl.classList.add('d-none');

  const body = {
    nombre: document.getElementById('docNombre').value.trim(),
    color: document.getElementById('docColor').value,
    especialidad: document.getElementById('docEspecialidad').value.trim(),
    telefono: document.getElementById('docTelefono').value.trim(),
    activo: document.getElementById('docActivo').checked,
  };

  if (!body.nombre) {
    errEl.textContent = 'El nombre es requerido';
    errEl.classList.remove('d-none');
    return;
  }

  const url = id ? `/api/doctores/${id}` : '/api/doctores';
  const method = id ? 'PUT' : 'POST';

  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (res.ok) {
    window.location.reload();
  } else {
    const data = await res.json();
    errEl.textContent = data.error || 'Error al guardar';
    errEl.classList.remove('d-none');
  }
}

/* ── Horarios ─────────────────────────────────────────────────────────────── */

function abrirHorario(docId, docNombre) {
  document.getElementById('horarioDocId').value = docId;
  document.getElementById('horarioDocNombre').textContent = docNombre;
  cargarHorarios(docId);
  new bootstrap.Modal(document.getElementById('modalHorario')).show();
}

async function cargarHorarios(docId) {
  const res = await fetch(`/api/doctores/${docId}/horarios`);
  const horarios = await res.json();
  const container = document.getElementById('listaHorarios');

  if (!horarios.length) {
    container.innerHTML = '<p class="text-muted small">Sin horarios registrados</p>';
    return;
  }

  container.innerHTML = horarios.map(h => `
    <div class="d-flex align-items-center justify-content-between mb-1">
      <span class="badge bg-light text-dark border">
        ${h.dia_nombre} ${h.hora_inicio}–${h.hora_fin}
      </span>
      <button class="btn btn-xs btn-outline-danger ms-2"
              onclick="eliminarHorario(${h.id}, ${docId})">
        <i class="bi bi-trash"></i>
      </button>
    </div>
  `).join('');
}

async function agregarHorario() {
  const docId = document.getElementById('horarioDocId').value;
  const body = {
    dia_semana: parseInt(document.getElementById('horDia').value),
    hora_inicio: document.getElementById('horInicio').value,
    hora_fin: document.getElementById('horFin').value,
  };
  const res = await fetch(`/api/doctores/${docId}/horarios`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) cargarHorarios(docId);
}

async function eliminarHorario(horarioId, docId) {
  await fetch(`/api/horarios/${horarioId}`, { method: 'DELETE' });
  cargarHorarios(docId);
}

/* ── Bloqueos ─────────────────────────────────────────────────────────────── */

function abrirBloqueo(docId, docNombre) {
  document.getElementById('bloqueoDocId').value = docId;
  document.getElementById('bloqueoDocNombre').textContent = docNombre;
  cargarBloqueos(docId);
  new bootstrap.Modal(document.getElementById('modalBloqueo')).show();
}

async function cargarBloqueos(docId) {
  const res = await fetch(`/api/doctores/${docId}/bloqueos`);
  const bloqueos = await res.json();
  const container = document.getElementById('listaBloqueos');

  if (!bloqueos.length) {
    container.innerHTML = '<p class="text-muted small">Sin ausencias registradas</p>';
    return;
  }

  container.innerHTML = bloqueos.map(b => `
    <div class="d-flex align-items-center justify-content-between mb-1">
      <span class="badge bg-warning text-dark">
        ${b.fecha_inicio} → ${b.fecha_fin}
        ${b.motivo ? '· ' + b.motivo : ''}
      </span>
      <button class="btn btn-xs btn-outline-danger ms-2"
              onclick="eliminarBloqueo(${b.id}, ${docId})">
        <i class="bi bi-trash"></i>
      </button>
    </div>
  `).join('');
}

async function agregarBloqueo() {
  const docId = document.getElementById('bloqueoDocId').value;
  const body = {
    fecha_inicio: document.getElementById('blqInicio').value,
    fecha_fin: document.getElementById('blqFin').value,
    motivo: document.getElementById('blqMotivo').value.trim(),
  };
  if (!body.fecha_inicio || !body.fecha_fin) {
    alert('Ingresa las fechas de inicio y fin');
    return;
  }
  const res = await fetch(`/api/doctores/${docId}/bloqueos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) cargarBloqueos(docId);
}

async function eliminarBloqueo(bloqueoId, docId) {
  await fetch(`/api/bloqueos/${bloqueoId}`, { method: 'DELETE' });
  cargarBloqueos(docId);
}
