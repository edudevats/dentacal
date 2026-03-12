/**
 * La Casa del Sr. Perez - Agenda
 * FullCalendar 6 con resourceTimeGrid (3 consultorios en columnas)
 */

let calendar;
let citaEditandoId = null;
let dentistasOcultos = new Set();

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
  initCalendario();
  initModal();
});

// ==================== INIT CALENDARIO ====================

function initCalendario() {
  const el = document.getElementById('calendar');
  if (!el) return;

  calendar = new FullCalendar.Calendar(el, {
    schedulerLicenseKey: 'CC-Attribution-NonCommercial-NoDerivatives',
    initialView: 'resourceTimeGridDay',
    locale: 'es',
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'resourceTimeGridDay,resourceTimeGridWeek,dayGridMonth',
    },
    resources: window.CONSULTORIOS || [],
    events: cargarEventos,

    slotMinTime: '08:00:00',
    slotMaxTime: '20:00:00',
    slotDuration: '00:30:00',
    slotLabelInterval: '01:00:00',
    allDaySlot: false,

    selectable: true,
    selectMirror: true,
    select: onSelect,

    eventClick: onEventClick,

    editable: true,
    eventDrop: onEventDrop,
    eventResize: onEventResize,

    businessHours: {
      daysOfWeek: [1, 2, 3, 4, 5, 6],
      startTime: '09:00',
      endTime: '18:00',
    },

    eventDidMount(info) {
      const status = info.event.extendedProps.status;
      if (status === 'completada') {
        info.el.style.opacity = '0.85';
        info.el.style.borderLeft = '4px solid #4CAF50';
      }
      if (status === 'no_asistencia') {
        info.el.style.opacity = '0.6';
        info.el.style.textDecoration = 'line-through';
      }
      if (status === 'cancelada') {
        info.el.style.opacity = '0.4';
      }
      info.el.title = info.event.title + ' - ' + status;
    },

    initialDate: new Date(),
    nowIndicator: true,
    height: 'parent',
  });

  calendar.render();

  document.getElementById('filtro-dentista')?.addEventListener('change', () => calendar.refetchEvents());
  document.getElementById('filtro-consultorio')?.addEventListener('change', () => calendar.refetchEvents());
}

async function cargarEventos(info, successCallback, failureCallback) {
  const dentistaId = document.getElementById('filtro-dentista')?.value || '';
  const consultoId = document.getElementById('filtro-consultorio')?.value || '';

  let url = `/api/calendario/eventos?start=${encodeURIComponent(info.startStr)}&end=${encodeURIComponent(info.endStr)}`;
  if (dentistaId) url += `&dentista_id=${dentistaId}`;
  if (consultoId) url += `&consultorio_id=${consultoId}`;

  try {
    const resp = await apiFetch(url);
    if (!resp.ok) throw new Error('Error cargando eventos');
    let eventos = await resp.json();
    if (dentistasOcultos.size > 0) {
      eventos = eventos.filter(e => !dentistasOcultos.has(String(e.extendedProps?.dentista_id)));
    }
    successCallback(eventos);
  } catch (err) {
    console.error(err);
    failureCallback(err);
  }
}

// ==================== LEYENDA ====================

function toggleDentista(dentistaId, el) {
  const id = String(dentistaId);
  if (dentistasOcultos.has(id)) {
    dentistasOcultos.delete(id);
    el.classList.remove('inactive');
  } else {
    dentistasOcultos.add(id);
    el.classList.add('inactive');
  }
  calendar.refetchEvents();
}

// ==================== MODAL ====================

function initModal() {
  document.getElementById('btnNuevaCita')?.addEventListener('click', () => abrirModalNuevo());
  document.getElementById('btnGuardarCita')?.addEventListener('click', guardarCita);
  document.getElementById('btnCancelarCita')?.addEventListener('click', cancelarCitaActual);

  // Mostrar/ocultar seccion proxima visita segun status
  document.getElementById('status_cita')?.addEventListener('change', (e) => {
    const wrapper = document.getElementById('proximaVisitaWrapper');
    if (wrapper) {
      wrapper.style.display = e.target.value === 'completada' ? 'block' : 'none';
      if (e.target.value !== 'completada') {
        document.getElementById('toggle_proxima_visita').checked = false;
        document.getElementById('proxima_visita_input_wrapper').style.display = 'none';
        document.getElementById('proxima_visita_mes').value = '';
      }
    }
  });

  // Toggle para mostrar/ocultar input de mes
  document.getElementById('toggle_proxima_visita')?.addEventListener('change', (e) => {
    const inputWrapper = document.getElementById('proxima_visita_input_wrapper');
    if (inputWrapper) {
      inputWrapper.style.display = e.target.checked ? 'block' : 'none';
      if (!e.target.checked) {
        document.getElementById('proxima_visita_mes').value = '';
      }
    }
  });

  // Setear min del month input
  const monthInput = document.getElementById('proxima_visita_mes');
  if (monthInput) {
    const now = new Date();
    monthInput.min = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }

  document.getElementById('tipo_cita_id')?.addEventListener('change', (e) => {
    const opt = e.target.selectedOptions[0];
    const duracion = parseInt(opt?.dataset.duracion || 60);
    const horaInicio = document.getElementById('hora_inicio').value;
    if (horaInicio) {
      const [h, m] = horaInicio.split(':').map(Number);
      const totalMin = h * 60 + m + duracion;
      const hf = Math.floor(totalMin / 60) % 24;
      const mf = totalMin % 60;
      document.getElementById('hora_fin').value =
        `${String(hf).padStart(2, '0')}:${String(mf).padStart(2, '0')}`;
    }
  });

  let debounceTimer;
  document.getElementById('paciente_search')?.addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    const q = e.target.value.trim();
    if (q.length < 2) {
      document.getElementById('paciente_results').classList.add('d-none');
      return;
    }
    debounceTimer = setTimeout(() => buscarPacientes(q), 300);
  });

  document.getElementById('btnBuscarPaciente')?.addEventListener('click', () => {
    const q = document.getElementById('paciente_search').value.trim();
    if (q) buscarPacientes(q);
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#paciente_search') && !e.target.closest('#paciente_results')) {
      document.getElementById('paciente_results')?.classList.add('d-none');
    }
  });
}

function abrirModalNuevo(start = null, end = null, resourceId = null) {
  citaEditandoId = null;
  limpiarFormulario();
  document.getElementById('modalCitaTitulo').textContent = 'Nueva Cita';
  document.getElementById('statusWrapper').style.display = 'none';
  document.getElementById('btnCancelarCita').classList.add('d-none');
  document.getElementById('formMsg').textContent = '';

  if (start) {
    const d = new Date(start);
    document.getElementById('fecha_cita').value = d.toISOString().slice(0, 10);
    document.getElementById('hora_inicio').value =
      `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
  if (end) {
    const d = new Date(end);
    document.getElementById('hora_fin').value =
      `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
  if (resourceId) {
    document.getElementById('consultorio_id').value = resourceId;
  }

  new bootstrap.Modal(document.getElementById('modalCita')).show();
}

function abrirModalEditar(evento) {
  citaEditandoId = evento.id;
  const ext = evento.extendedProps;

  document.getElementById('cita_id').value = evento.id;
  document.getElementById('modalCitaTitulo').textContent = 'Editar Cita';
  document.getElementById('statusWrapper').style.display = 'block';
  document.getElementById('btnCancelarCita').classList.remove('d-none');
  document.getElementById('formMsg').textContent = '';

  document.getElementById('paciente_id').value = ext.paciente_id || '';
  document.getElementById('paciente_search').value = evento.title.split(' - ')[0];
  document.getElementById('paciente_info').textContent = '';
  document.getElementById('dentista_id').value = ext.dentista_id || '';
  document.getElementById('consultorio_id').value = ext.consultorio_id || '';
  document.getElementById('notas_cita').value = ext.notas || '';
  document.getElementById('status_cita').value = ext.status || 'pendiente';
  document.getElementById('anticipo_pagado').checked = ext.anticipo_pagado || false;

  // Proxima visita: mostrar solo si completada
  const pvw = document.getElementById('proximaVisitaWrapper');
  if (pvw) pvw.style.display = ext.status === 'completada' ? 'block' : 'none';
  document.getElementById('toggle_proxima_visita').checked = false;
  document.getElementById('proxima_visita_input_wrapper').style.display = 'none';
  document.getElementById('proxima_visita_mes').value = '';

  const start = new Date(evento.start);
  const end = new Date(evento.end);
  document.getElementById('fecha_cita').value = start.toISOString().slice(0, 10);
  document.getElementById('hora_inicio').value =
    `${String(start.getHours()).padStart(2, '0')}:${String(start.getMinutes()).padStart(2, '0')}`;
  document.getElementById('hora_fin').value =
    `${String(end.getHours()).padStart(2, '0')}:${String(end.getMinutes()).padStart(2, '0')}`;

  new bootstrap.Modal(document.getElementById('modalCita')).show();
}

function limpiarFormulario() {
  ['paciente_id', 'paciente_search', 'dentista_id', 'consultorio_id',
    'tipo_cita_id', 'notas_cita', 'anticipo_monto', 'fecha_cita',
    'hora_inicio', 'hora_fin', 'proxima_visita_mes'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
  const ap = document.getElementById('anticipo_pagado');
  if (ap) ap.checked = false;
  const pi = document.getElementById('paciente_info');
  if (pi) pi.textContent = '';
  const pvw = document.getElementById('proximaVisitaWrapper');
  if (pvw) pvw.style.display = 'none';
  const tpv = document.getElementById('toggle_proxima_visita');
  if (tpv) tpv.checked = false;
  const pviw = document.getElementById('proxima_visita_input_wrapper');
  if (pviw) pviw.style.display = 'none';
}

async function guardarCita() {
  const btnGuardar = document.getElementById('btnGuardarCita');
  const msgEl = document.getElementById('formMsg');
  msgEl.textContent = '';

  const fecha = document.getElementById('fecha_cita').value;
  const hInicio = document.getElementById('hora_inicio').value;
  const hFin = document.getElementById('hora_fin').value;
  const pId = document.getElementById('paciente_id').value;
  const dId = document.getElementById('dentista_id').value;
  const cId = document.getElementById('consultorio_id').value;

  if (!fecha || !hInicio || !hFin || !pId || !dId || !cId) {
    msgEl.textContent = 'Completa los campos obligatorios.';
    msgEl.className = 'mt-2 text-danger small';
    return;
  }

  const body = {
    paciente_id: parseInt(pId),
    dentista_id: parseInt(dId),
    consultorio_id: parseInt(cId),
    tipo_cita_id: document.getElementById('tipo_cita_id').value
      ? parseInt(document.getElementById('tipo_cita_id').value) : null,
    fecha_inicio: `${fecha}T${hInicio}:00`,
    fecha_fin: `${fecha}T${hFin}:00`,
    notas: document.getElementById('notas_cita').value,
    anticipo_pagado: document.getElementById('anticipo_pagado').checked,
    anticipo_monto: parseFloat(document.getElementById('anticipo_monto').value || 0),
  };

  if (citaEditandoId) {
    body.status = document.getElementById('status_cita').value;
    // Si marco completada y selecciono mes de proxima visita
    const pvMes = document.getElementById('proxima_visita_mes').value;
    if (body.status === 'completada' && pvMes) {
      body.proximo_recordatorio_fecha = pvMes + '-01';
    }
  }

  btnGuardar.disabled = true;
  btnGuardar.textContent = 'Guardando...';

  try {
    const url = citaEditandoId ? `/api/citas/${citaEditandoId}` : '/api/citas';
    const method = citaEditandoId ? 'PUT' : 'POST';
    const resp = await apiFetch(url, { method, body: JSON.stringify(body) });
    const data = await resp.json();

    if (!resp.ok) {
      const err = data.conflicto
        ? `Conflicto con ${data.conflicto.dentista} - ${data.conflicto.consultorio}`
        : (data.error || 'Error al guardar');
      msgEl.textContent = err;
      msgEl.className = 'mt-2 text-danger small';
      return;
    }

    bootstrap.Modal.getInstance(document.getElementById('modalCita'))?.hide();
    calendar.refetchEvents();
  } catch (err) {
    msgEl.textContent = 'Error de red: ' + err.message;
    msgEl.className = 'mt-2 text-danger small';
  } finally {
    btnGuardar.disabled = false;
    btnGuardar.textContent = 'Guardar';
  }
}

async function cancelarCitaActual() {
  if (!citaEditandoId) return;
  if (!confirm('Confirmar cancelacion de esta cita?')) return;
  const resp = await apiFetch(`/api/citas/${citaEditandoId}`, { method: 'DELETE' });
  if (resp.ok) {
    bootstrap.Modal.getInstance(document.getElementById('modalCita'))?.hide();
    calendar.refetchEvents();
  }
}

// ==================== BUSQUEDA PACIENTES (DOM seguro) ====================

async function buscarPacientes(q) {
  const listEl = document.getElementById('paciente_results');
  try {
    const resp = await apiFetch(`/api/pacientes?q=${encodeURIComponent(q)}&per_page=10`);
    const data = await resp.json();
    const pacs = data.pacientes || [];

    // Limpiar lista con metodo DOM seguro
    while (listEl.firstChild) listEl.removeChild(listEl.firstChild);

    if (pacs.length === 0) {
      const a = document.createElement('a');
      a.className = 'list-group-item list-group-item-action small text-muted';
      a.textContent = 'Sin resultados. Verifica el nombre o telefono.';
      listEl.appendChild(a);
    } else {
      pacs.forEach(p => {
        const a = document.createElement('a');
        a.className = 'list-group-item list-group-item-action small';
        a.style.cursor = 'pointer';

        const strong = document.createElement('strong');
        strong.textContent = p.nombre_completo || p.nombre;
        a.appendChild(strong);

        if (p.whatsapp || p.telefono) {
          const span = document.createElement('span');
          span.className = 'text-muted ms-2';
          span.textContent = p.whatsapp || p.telefono;
          a.appendChild(span);
        }

        const badge = document.createElement('span');
        badge.className = `badge ms-1 badge-${p.estatus_crm}`;
        badge.textContent = p.estatus_crm;
        a.appendChild(badge);

        a.addEventListener('click', () =>
          seleccionarPaciente(p.id, p.nombre_completo || p.nombre, p.whatsapp || p.telefono || '')
        );
        listEl.appendChild(a);
      });
    }
    listEl.classList.remove('d-none');
  } catch (e) {
    console.error(e);
  }
}

function seleccionarPaciente(id, nombre, telefono) {
  document.getElementById('paciente_id').value = id;
  document.getElementById('paciente_search').value = nombre;
  const pi = document.getElementById('paciente_info');
  pi.textContent = telefono ? `Tel: ${telefono}` : '';
  document.getElementById('paciente_results').classList.add('d-none');
}

// ==================== DRAG & DROP ====================

function onSelect(info) {
  abrirModalNuevo(info.start, info.end, info.resource?.id);
}

function onEventClick(info) {
  abrirModalEditar(info.event);
}

async function onEventDrop(info) {
  if (!confirm('Confirmar cambio de horario?')) { info.revert(); return; }
  const body = {
    fecha_inicio: info.event.start.toISOString().slice(0, 19),
    fecha_fin: info.event.end.toISOString().slice(0, 19),
  };
  if (info.newResource?.id) body.consultorio_id = parseInt(info.newResource.id);
  const resp = await apiFetch(`/api/citas/${info.event.id}`, { method: 'PUT', body: JSON.stringify(body) });
  if (!resp.ok) { const d = await resp.json(); alert(d.error || 'No se pudo reagendar'); info.revert(); }
}

async function onEventResize(info) {
  const body = {
    fecha_inicio: info.event.start.toISOString().slice(0, 19),
    fecha_fin: info.event.end.toISOString().slice(0, 19),
  };
  const resp = await apiFetch(`/api/citas/${info.event.id}`, { method: 'PUT', body: JSON.stringify(body) });
  if (!resp.ok) info.revert();
}
