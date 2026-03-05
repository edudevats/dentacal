/* ════════════════════════════════════════════════════════════════
   La Casa del Sr. Pérez — Calendar JS
   Gestión del calendario FullCalendar + modal de nueva cita (3 pasos)
════════════════════════════════════════════════════════════════ */

let calendar;
let offcanvasCita;
let modalNuevaCita;

// Estado del formulario
const _form = {
  fecha: null,        // Date object seleccionada
  horaInicio: null,   // string "HH:MM"
  horaFin: null,      // string "HH:MM"
  duracionMins: 60,   // duración del tipo seleccionado
  pasoActual: 1,
};

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
  offcanvasCita  = new bootstrap.Offcanvas(document.getElementById('offcanvasCita'));
  modalNuevaCita = new bootstrap.Modal(document.getElementById('modalNuevaCita'));

  initCalendar();
  initMiniCalendar();
  initBuscarPaciente();
  initTipoCards();

  // Botón topbar
  document.getElementById('btnNuevaCita').addEventListener('click', abrirModalNuevo);

  // Filtros de doctor
  document.querySelectorAll('.doctor-filter').forEach(cb => {
    cb.addEventListener('change', () => calendar.refetchEvents());
  });

  // Reset al cerrar modal
  document.getElementById('modalNuevaCita').addEventListener('hidden.bs.modal', resetForm);
});

// ── FullCalendar ──────────────────────────────────────────────────────────────

function initCalendar() {
  const calendarEl = document.getElementById('calendar');

  calendar = new FullCalendar.Calendar(calendarEl, {
    schedulerLicenseKey: 'GPL-My-Project-Is-Open-Source',
    initialView: 'resourceTimeGridDay',
    locale: 'es',
    timeZone: 'America/Mexico_City',
    slotMinTime: '07:00:00',
    slotMaxTime: '20:00:00',
    slotDuration: '00:30:00',
    height: 'auto',
    nowIndicator: true,
    editable: true,
    droppable: true,
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'resourceTimeGridDay,timeGridWeek,dayGridMonth',
    },
    views: {
      resourceTimeGridDay: { buttonText: 'Día' },
      timeGridWeek:        { buttonText: 'Semana' },
      dayGridMonth:        { buttonText: 'Mes' },
    },
    resources: fetchResources,
    events: fetchEvents,

    // Click en evento → detalle
    eventClick: function (info) {
      showCitaDetail(info.event);
    },

    // Drag & drop / resize → actualizar
    eventDrop:   function (info) { updateCitaFromEvent(info.event, info.revert); },
    eventResize: function (info) { updateCitaFromEvent(info.event, info.revert); },

    // Click en hueco → abrir modal con fecha/hora pre-seleccionada
    dateClick: function (info) {
      const date  = info.date;
      const fecha = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      const hora  = `${String(date.getHours()).padStart(2,'0')}:${String(date.getMinutes()).padStart(2,'0')}`;

      // Pre-seleccionar fecha y hora en el mini-calendario
      _form.fecha      = fecha;
      _form.horaInicio = hora;

      if (info.resource) {
        document.getElementById('selectConsultorio').value = info.resource.id;
      }

      abrirModalNuevo();

      // Aplicar selección en el mini-cal después de abrir
      setTimeout(() => {
        if (window._flatpickrInline) {
          window._flatpickrInline.setDate(fecha, false);
        }
        generarSlots(fecha, hora);
        marcarSlot(hora);
      }, 150);
    },

    eventDidMount: function (info) {
      const p = info.event.extendedProps;
      info.el.setAttribute('title',
        `${p.paciente_nombre}\n${p.tipo_cita || ''} · ${p.dentista_nombre}\nEstado: ${p.estado}`
      );
      if (p.estado === 'no_asistio' || p.estado === 'cancelada') {
        info.el.style.opacity = '0.45';
        info.el.style.textDecoration = 'line-through';
      }
    },
  });

  calendar.render();
}

function fetchResources(fetchInfo, successCb, failCb) {
  fetch('/api/calendario/resources')
    .then(r => r.json()).then(successCb).catch(failCb);
}

function fetchEvents(fetchInfo, successCb, failCb) {
  const ids = [];
  document.querySelectorAll('.doctor-filter:checked').forEach(cb => ids.push(cb.value));
  const params = new URLSearchParams({ start: fetchInfo.startStr, end: fetchInfo.endStr });
  ids.forEach(id => params.append('dentista_id', id));
  fetch(`/api/calendario/eventos?${params}`)
    .then(r => r.json()).then(successCb).catch(failCb);
}

// ── Mini-calendario inline (Flatpickr) ───────────────────────────────────────

function initMiniCalendar() {
  window._flatpickrInline = flatpickr('#inlineDatePicker', {
    inline: true,
    locale: 'es',
    minDate: 'today',
    dateFormat: 'Y-m-d',
    defaultDate: new Date(),
    onChange: function (selectedDates) {
      if (!selectedDates.length) return;
      const d = selectedDates[0];
      _form.fecha = new Date(d.getFullYear(), d.getMonth(), d.getDate());
      _form.horaInicio = null;
      generarSlots(_form.fecha, null);
    },
  });
}

// ── Generación de slots de hora ───────────────────────────────────────────────

function generarSlots(fecha, preselect) {
  const grid   = document.getElementById('slotGrid');
  const label  = document.getElementById('slotFechaLabel');
  const opciones = { weekday: 'long', day: 'numeric', month: 'long' };
  label.textContent = ` — ${fecha.toLocaleDateString('es-MX', opciones)}`;

  // Horas de 07:00 a 19:30 cada 30 min
  const horas = [];
  for (let h = 7; h < 20; h++) {
    horas.push(`${String(h).padStart(2,'0')}:00`);
    horas.push(`${String(h).padStart(2,'0')}:30`);
  }

  grid.innerHTML = '';
  horas.forEach(hora => {
    const btn = document.createElement('button');
    btn.type      = 'button';
    btn.className = 'slot-btn';
    btn.textContent = hora;
    btn.dataset.hora = hora;
    btn.addEventListener('click', () => seleccionarSlot(btn, hora));
    grid.appendChild(btn);
  });

  if (preselect) marcarSlot(preselect);
  actualizarSlotsBusy(fecha);
}

async function actualizarSlotsBusy(fecha) {
  // Consultar citas del día para marcar slots ocupados
  const iso = `${fecha.getFullYear()}-${String(fecha.getMonth()+1).padStart(2,'0')}-${String(fecha.getDate()).padStart(2,'0')}`;
  try {
    const res  = await fetch(`/api/calendario/eventos?start=${iso}T00:00:00&end=${iso}T23:59:59`);
    const data = await res.json();
    data.forEach(ev => {
      const start = new Date(ev.start);
      const end   = new Date(ev.end);
      document.querySelectorAll('.slot-btn').forEach(btn => {
        const [hh, mm] = btn.dataset.hora.split(':').map(Number);
        const slotTime = new Date(fecha);
        slotTime.setHours(hh, mm, 0, 0);
        if (slotTime >= start && slotTime < end) {
          btn.classList.add('busy');
          btn.title = 'Ocupado';
        }
      });
    });
  } catch(e) { /* no bloquear */ }
}

function seleccionarSlot(btn, hora) {
  if (btn.classList.contains('busy')) return;
  _form.horaInicio = hora;
  document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  // Calcular fin según duración del tipo seleccionado
  calcularHoraFin();
  // Avanzar step visual
  actualizarStepper(1, true);
}

function marcarSlot(hora) {
  const btn = document.querySelector(`.slot-btn[data-hora="${hora}"]`);
  if (btn && !btn.classList.contains('busy')) {
    document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    _form.horaInicio = hora;
    calcularHoraFin();
  }
}

function calcularHoraFin() {
  if (!_form.horaInicio) return;
  const [hh, mm] = _form.horaInicio.split(':').map(Number);
  const inicio   = new Date();
  inicio.setHours(hh, mm, 0, 0);
  const fin = new Date(inicio.getTime() + _form.duracionMins * 60000);
  _form.horaFin = `${String(fin.getHours()).padStart(2,'0')}:${String(fin.getMinutes()).padStart(2,'0')}`;
}

// ── Tipos de cita — cards con radio ──────────────────────────────────────────

function initTipoCards() {
  document.querySelectorAll('.tipo-card').forEach(label => {
    label.addEventListener('click', () => {
      document.querySelectorAll('.tipo-card').forEach(l => {
        l.classList.remove('border-teal', 'bg-light');
      });
      label.classList.add('border-teal', 'bg-light');
    });
  });
}

function onTipoChange(duracion) {
  _form.duracionMins = duracion;
  calcularHoraFin();
}

function onDoctorChange() {
  // Refrescar slots si ya hay fecha seleccionada
  if (_form.fecha) actualizarSlotsBusy(_form.fecha);
}

// ── Búsqueda de paciente ──────────────────────────────────────────────────────

function initBuscarPaciente() {
  let timeout;
  const input = document.getElementById('searchPaciente');
  if (!input) return;

  input.addEventListener('input', function () {
    clearTimeout(timeout);
    const q = this.value.trim();
    if (q.length < 2) {
      document.getElementById('pacienteResults').innerHTML = '';
      return;
    }
    timeout = setTimeout(() => buscarPacientes(q), 300);
  });
}

async function buscarPacientes(q) {
  const res = await fetch(`/api/pacientes?q=${encodeURIComponent(q)}`);
  const list = await res.json();
  const container = document.getElementById('pacienteResults');
  container.innerHTML = '';

  list.slice(0, 6).forEach(p => {
    const item = document.createElement('a');
    item.href      = '#';
    item.className = 'list-group-item list-group-item-action py-2';
    item.innerHTML = `<i class="bi bi-person me-2 text-muted"></i>
      <strong>${p.nombre}</strong> <span class="text-muted small">${p.telefono}</span>`;
    item.addEventListener('click', e => {
      e.preventDefault();
      seleccionarPaciente(p.id, p.nombre, p.telefono);
    });
    container.appendChild(item);
  });

  // Crear nuevo paciente
  if (q.length > 2) {
    const item = document.createElement('a');
    item.href      = '#';
    item.className = 'list-group-item list-group-item-action py-2 text-teal';
    item.innerHTML = `<i class="bi bi-person-plus me-2"></i>Crear paciente: <strong>"${q}"</strong>`;
    item.addEventListener('click', async e => {
      e.preventDefault();
      const tel = prompt('Teléfono del paciente (con código país, ej: +521234567890):');
      if (!tel) return;
      const r = await fetch('/api/pacientes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
        body: JSON.stringify({ nombre: q, telefono: tel }),
      });
      if (r.ok) {
        const p = await r.json();
        seleccionarPaciente(p.id, p.nombre, p.telefono);
      }
    });
    container.appendChild(item);
  }
}

function seleccionarPaciente(id, nombre, telefono) {
  document.getElementById('pacienteId').value       = id;
  document.getElementById('searchPaciente').value   = '';
  document.getElementById('pacienteResults').innerHTML = '';
  document.getElementById('nombrePaciente').textContent = `${nombre} — ${telefono}`;
  document.getElementById('pacienteSeleccionado').classList.remove('d-none');
  document.getElementById('searchPaciente').closest('.input-group').classList.add('d-none');
}

function limpiarPaciente() {
  document.getElementById('pacienteId').value = '';
  document.getElementById('pacienteSeleccionado').classList.add('d-none');
  document.getElementById('searchPaciente').closest('.input-group').classList.remove('d-none');
  document.getElementById('searchPaciente').value = '';
  document.getElementById('searchPaciente').focus();
}

// ── Stepper ───────────────────────────────────────────────────────────────────

function actualizarStepper(paso, done) {
  const dot  = document.getElementById(`dot${paso}`);
  const line = document.getElementById(`line${paso}`);
  if (done) {
    dot.classList.remove('active');
    dot.classList.add('done');
    if (line) line.classList.add('done');
    const nextDot = document.getElementById(`dot${paso + 1}`);
    if (nextDot) nextDot.classList.add('active');
  } else {
    dot.classList.add('active');
    dot.classList.remove('done');
  }
}

function irPaso(numero) {
  if (numero === 3) {
    // Validar antes de ir al resumen
    if (!validarPaso2()) return;
    mostrarResumen();
    document.getElementById('paso2').classList.add('d-none');
    document.getElementById('paso3').classList.remove('d-none');
    document.getElementById('btnSiguiente').classList.add('d-none');
    document.getElementById('btnAtras').classList.remove('d-none');
    document.getElementById('btnGuardarCita').classList.remove('d-none');
    actualizarStepper(2, true);
    _form.pasoActual = 3;
  } else if (numero === 2) {
    document.getElementById('paso3').classList.add('d-none');
    document.getElementById('paso2').classList.remove('d-none');
    document.getElementById('btnSiguiente').classList.remove('d-none');
    document.getElementById('btnAtras').classList.add('d-none');
    document.getElementById('btnGuardarCita').classList.add('d-none');
    // Revertir dot 2
    const dot2 = document.getElementById('dot2');
    dot2.classList.remove('done');
    dot2.classList.add('active');
    document.getElementById('line2').classList.remove('done');
    document.getElementById('dot3').classList.remove('active');
    _form.pasoActual = 2;
  }
}

function validarPaso2() {
  const errEl = document.getElementById('errorNuevaCita');
  errEl.classList.add('d-none');

  if (!_form.fecha || !_form.horaInicio) {
    errEl.textContent = 'Selecciona una fecha y hora en el calendario de la izquierda.';
    errEl.classList.remove('d-none');
    return false;
  }
  if (!document.getElementById('pacienteId').value) {
    errEl.textContent = 'Busca y selecciona un paciente.';
    errEl.classList.remove('d-none');
    return false;
  }
  if (!document.getElementById('selectDoctor').value) {
    errEl.textContent = 'Selecciona un doctor.';
    errEl.classList.remove('d-none');
    return false;
  }
  if (!document.querySelector('input[name="tipoCita"]:checked')) {
    errEl.textContent = 'Selecciona el tipo de cita.';
    errEl.classList.remove('d-none');
    return false;
  }
  return true;
}

function mostrarResumen() {
  const doctorEl  = document.getElementById('selectDoctor');
  const consSel   = document.getElementById('selectConsultorio');
  const tipoRadio = document.querySelector('input[name="tipoCita"]:checked');
  const tipoLabel = tipoRadio ? tipoRadio.closest('label').querySelector('.fw-semibold').textContent : '—';
  const paciente  = document.getElementById('nombrePaciente').textContent;
  const notas     = document.getElementById('notasCita').value.trim();

  // Construir fecha/hora display
  const fecha = _form.fecha;
  const fechaStr = fecha.toLocaleDateString('es-MX', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });

  calcularHoraFin();

  document.getElementById('resumenCita').innerHTML = `
    <div class="item"><i class="bi bi-person-fill"></i>
      <div><div class="fw-semibold">Paciente</div>${paciente}</div>
    </div>
    <div class="item"><i class="bi bi-calendar-event"></i>
      <div><div class="fw-semibold">Fecha</div>${fechaStr}</div>
    </div>
    <div class="item"><i class="bi bi-clock-fill"></i>
      <div><div class="fw-semibold">Horario</div>${_form.horaInicio} – ${_form.horaFin || '—'}</div>
    </div>
    <div class="item"><i class="bi bi-person-badge-fill"></i>
      <div><div class="fw-semibold">Doctor</div>${doctorEl.options[doctorEl.selectedIndex]?.text || '—'}</div>
    </div>
    <div class="item"><i class="bi bi-door-open-fill"></i>
      <div><div class="fw-semibold">Consultorio</div>${consSel.options[consSel.selectedIndex]?.text || '—'}</div>
    </div>
    <div class="item"><i class="bi bi-tag-fill"></i>
      <div><div class="fw-semibold">Tipo de cita</div>${tipoLabel} · ${_form.duracionMins} min</div>
    </div>
    ${notas ? `<div class="item"><i class="bi bi-chat-left-text-fill"></i>
      <div><div class="fw-semibold">Notas</div>${notas}</div>
    </div>` : ''}
  `;
}

// ── Guardar cita ──────────────────────────────────────────────────────────────

async function guardarNuevaCita() {
  const btn = document.getElementById('btnGuardarCita');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Guardando…';

  const tipoRadio = document.querySelector('input[name="tipoCita"]:checked');
  const fecha     = _form.fecha;

  // Construir ISO de inicio y fin
  const [hIni, mIni] = _form.horaInicio.split(':').map(Number);
  const inicio = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), hIni, mIni);
  calcularHoraFin();
  const [hFin, mFin] = _form.horaFin.split(':').map(Number);
  const fin = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), hFin, mFin);

  const isoInicio = `${inicio.getFullYear()}-${String(inicio.getMonth()+1).padStart(2,'0')}-${String(inicio.getDate()).padStart(2,'0')}T${_form.horaInicio}:00`;
  const isoFin    = `${fin.getFullYear()}-${String(fin.getMonth()+1).padStart(2,'0')}-${String(fin.getDate()).padStart(2,'0')}T${_form.horaFin}:00`;

  const body = {
    paciente_id:    parseInt(document.getElementById('pacienteId').value),
    dentista_id:    parseInt(document.getElementById('selectDoctor').value),
    consultorio_id: parseInt(document.getElementById('selectConsultorio').value),
    tipo_cita_id:   tipoRadio ? parseInt(tipoRadio.value) : null,
    fecha_inicio:   isoInicio,
    fecha_fin:      isoFin,
    notas:          document.getElementById('notasCita').value.trim(),
  };

  try {
    const res = await fetch('/api/citas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (res.ok) {
      modalNuevaCita.hide();
      calendar.refetchEvents();
      mostrarToast('¡Cita creada correctamente!', 'success');
    } else {
      document.getElementById('errorNuevaCita').textContent = data.error || 'Error al crear la cita';
      document.getElementById('errorNuevaCita').classList.remove('d-none');
      irPaso(2);
    }
  } catch(e) {
    mostrarToast('Error de conexión', 'danger');
    irPaso(2);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-calendar-check me-1"></i>Confirmar cita';
  }
}

// ── Abrir modal / Reset ───────────────────────────────────────────────────────

function abrirModalNuevo() {
  resetForm();
  modalNuevaCita.show();
}

function resetForm() {
  _form.fecha       = null;
  _form.horaInicio  = null;
  _form.horaFin     = null;
  _form.duracionMins = 60;
  _form.pasoActual  = 1;

  // Limpiar campos
  document.getElementById('pacienteId').value = '';
  document.getElementById('searchPaciente').value = '';
  document.getElementById('pacienteResults').innerHTML = '';
  document.getElementById('pacienteSeleccionado').classList.add('d-none');
  document.getElementById('searchPaciente').closest('.input-group').classList.remove('d-none');
  document.getElementById('selectDoctor').value = '';
  document.getElementById('notasCita').value = '';
  document.getElementById('errorNuevaCita').classList.add('d-none');
  document.querySelectorAll('input[name="tipoCita"]').forEach(r => r.checked = false);
  document.querySelectorAll('.tipo-card').forEach(l => l.classList.remove('border-teal','bg-light'));

  // Reset stepper
  ['dot1','dot2','dot3'].forEach((id, i) => {
    const el = document.getElementById(id);
    el.className = 'step-dot' + (i === 0 ? ' active' : '');
  });
  ['line1','line2'].forEach(id => document.getElementById(id).classList.remove('done'));

  // Reset pasos
  document.getElementById('paso2').classList.remove('d-none');
  document.getElementById('paso3').classList.add('d-none');
  document.getElementById('btnSiguiente').classList.remove('d-none');
  document.getElementById('btnAtras').classList.add('d-none');
  document.getElementById('btnGuardarCita').classList.add('d-none');

  // Reset mini-calendario
  const today = new Date();
  const todayClean = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (window._flatpickrInline) {
    window._flatpickrInline.setDate(todayClean, false);
  }
  _form.fecha = todayClean;
  generarSlots(todayClean, null);
  document.getElementById('slotGrid').innerHTML =
    '<div class="text-muted small" style="grid-column:1/-1">← Selecciona una fecha</div>';
}

// ── Detalle de cita (offcanvas) ───────────────────────────────────────────────

function showCitaDetail(event) {
  const p = event.extendedProps;
  const badgeColor = {
    pendiente: 'secondary', confirmada: 'success',
    no_asistio: 'danger',   cancelada: 'dark',
  }[p.estado] || 'secondary';

  document.getElementById('citaDetailBody').innerHTML = `
    <div class="mb-3 d-flex align-items-center gap-2">
      <span style="width:14px;height:14px;border-radius:50%;background:${p.dentista_color};display:inline-block;flex-shrink:0"></span>
      <div>
        <h5 class="mb-0">${p.paciente_nombre}</h5>
        <small class="text-muted">${p.tipo_cita || 'Sin tipo'}</small>
      </div>
      <span class="badge bg-${badgeColor} ms-auto">${p.estado}</span>
    </div>

    <table class="table table-sm table-borderless small mb-3">
      <tr><td class="text-muted">Doctor</td>    <td>${p.dentista_nombre}</td></tr>
      <tr><td class="text-muted">Consultorio</td><td>${p.consultorio}</td></tr>
      <tr><td class="text-muted">Inicio</td>     <td>${event.start?.toLocaleString('es-MX')}</td></tr>
      <tr><td class="text-muted">Fin</td>        <td>${event.end?.toLocaleString('es-MX')}</td></tr>
      <tr><td class="text-muted">Teléfono</td>   <td>
        <a href="https://wa.me/${(p.paciente_telefono||'').replace('+','')}" target="_blank">
          ${p.paciente_telefono || '—'}
        </a>
      </td></tr>
      <tr><td class="text-muted">Anticipo</td>   <td>${p.anticipo ? '✅ Registrado' : '—'}</td></tr>
      ${p.notas ? `<tr><td class="text-muted">Notas</td><td>${p.notas}</td></tr>` : ''}
    </table>

    <div class="mb-3">
      <label class="form-label small fw-semibold">Cambiar estado</label>
      <select class="form-select form-select-sm" onchange="cambiarEstado(${p.cita_id}, this.value)">
        <option ${p.estado==='pendiente'  ?'selected':''} value="pendiente">⏳ Pendiente</option>
        <option ${p.estado==='confirmada' ?'selected':''} value="confirmada">✅ Confirmada</option>
        <option ${p.estado==='no_asistio' ?'selected':''} value="no_asistio">❌ No asistió</option>
        <option ${p.estado==='cancelada'  ?'selected':''} value="cancelada">🚫 Cancelada</option>
      </select>
    </div>

    <div class="d-grid gap-2">
      <a href="/pacientes/${p.paciente_id}" class="btn btn-outline-teal btn-sm">
        <i class="bi bi-person-vcard me-1"></i>Ver ficha del paciente
      </a>
      <button class="btn btn-outline-danger btn-sm" onclick="cancelarCita(${p.cita_id})">
        <i class="bi bi-x-circle me-1"></i>Cancelar cita
      </button>
    </div>
  `;
  offcanvasCita.show();
}

async function cambiarEstado(citaId, nuevoEstado) {
  await fetch(`/api/citas/${citaId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
    body: JSON.stringify({ estado: nuevoEstado }),
  });
  calendar.refetchEvents();
}

async function cancelarCita(citaId) {
  if (!confirm('¿Cancelar esta cita?')) return;
  await fetch(`/api/citas/${citaId}/cancelar`, {
    method: 'PATCH',
    headers: { 'X-CSRFToken': CSRF_TOKEN },
  });
  offcanvasCita.hide();
  calendar.refetchEvents();
}

async function updateCitaFromEvent(event, revert) {
  const p = event.extendedProps;
  const body = {
    fecha_inicio: event.start.toISOString().slice(0, 19),
    fecha_fin:    event.end.toISOString().slice(0, 19),
    consultorio_id: event.getResources()[0]?.id || p.consultorio_id,
  };
  const res = await fetch(`/api/citas/${p.cita_id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json();
    mostrarToast(data.error || 'No se pudo mover la cita', 'danger');
    revert();
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function mostrarToast(msg, tipo = 'success') {
  const t = document.createElement('div');
  t.className = `toast align-items-center text-bg-${tipo} border-0 show position-fixed`;
  t.style.cssText = 'bottom:1.5rem;right:1.5rem;z-index:9999;min-width:280px;';
  t.innerHTML = `<div class="d-flex">
    <div class="toast-body">${msg}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto"
            onclick="this.closest('.toast').remove()"></button>
  </div>`;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}
