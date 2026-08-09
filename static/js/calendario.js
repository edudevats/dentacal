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

  const isMobileView = window.innerWidth <= 768;

  // Horario del consultorio por dia, configurado en Ajustes
  const horario = window.HORARIO_CONSULTORIO || {
    slot_min: '08:00:00', slot_max: '20:00:00',
    dias: [0, 1, 2, 3, 4, 5, 6].map(d => ({
      dia_semana: d, apertura: '09:00', cierre: '18:00', cerrado: d === 6,
    })),
  };

  // FullCalendar usa 0=domingo; nuestro dia_semana usa 0=lunes
  const businessHours = (horario.dias || [])
    .filter(d => !d.cerrado)
    .map(d => ({
      daysOfWeek: [(d.dia_semana + 1) % 7],
      startTime: d.apertura,
      endTime: d.cierre,
    }));

  calendar = new FullCalendar.Calendar(el, {
    schedulerLicenseKey: 'CC-Attribution-NonCommercial-NoDerivatives',
    initialView: isMobileView ? 'timeGridDay' : 'resourceTimeGridDay',
    locale: 'es',
    headerToolbar: isMobileView
      ? { left: 'prev,next', center: 'title', right: 'timeGridDay,dayGridMonth' }
      : { left: 'prev,next today', center: 'title', right: 'resourceTimeGridDay,resourceTimeGridWeek,dayGridMonth' },
    resources: window.CONSULTORIOS || [],
    events: cargarEventos,

    slotMinTime: horario.slot_min,
    slotMaxTime: horario.slot_max,
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

    businessHours: businessHours,

    eventDidMount(info) {
      const status = info.event.extendedProps.status;
      if (status === 'pre_cita') {
        info.el.style.opacity = '0.65';
        info.el.style.borderLeft = '4px solid #F2853D';
        info.el.style.borderStyle = 'dashed';
        info.el.style.backgroundImage =
          'repeating-linear-gradient(45deg, transparent, transparent 5px, rgba(255,255,255,0.15) 5px, rgba(255,255,255,0.15) 10px)';
        const expira = info.event.extendedProps.pre_cita_expira;
        const expiraStr = expira ? ' | Expira: ' + new Date(expira).toLocaleString('es-MX', {dateStyle:'short', timeStyle:'short'}) : '';
        info.el.title = info.event.title + ' - PRE-CITA (reserva temporal)' + expiraStr;
      } else if (status === 'completada') {
        info.el.style.opacity = '0.85';
        info.el.style.borderLeft = '4px solid #4CAF50';
      } else if (status === 'no_asistencia') {
        info.el.style.opacity = '0.6';
        info.el.style.textDecoration = 'line-through';
      } else if (status === 'cancelada') {
        info.el.style.opacity = '0.4';
      }
      if (status !== 'pre_cita') {
        info.el.title = info.event.title + ' - ' + status;
      }
    },

    dayHeaderContent(arg) {
      const dayNames = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
      const day = dayNames[arg.date.getDay()];
      const date = arg.date.getDate() + '/' + (arg.date.getMonth() + 1);
      const wrapper = document.createElement('div');
      wrapper.className = 'day-header-custom';
      const nameEl = document.createElement('div');
      nameEl.className = 'day-header-name';
      nameEl.textContent = day;
      const dateEl = document.createElement('div');
      dateEl.className = 'day-header-date';
      dateEl.textContent = date;
      wrapper.appendChild(nameEl);
      wrapper.appendChild(dateEl);
      return { domNodes: [wrapper] };
    },

    datesSet() {
      // Recalcular conteo de leyenda al cambiar vista o rango de fechas
      recalcularConteoDesdeVista();
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
    actualizarConteoLeyenda(eventos);
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

function actualizarConteoLeyenda(eventos) {
  const conteo = {};
  eventos.forEach(e => {
    const did = String(e.extendedProps?.dentista_id || '');
    if (did) conteo[did] = (conteo[did] || 0) + 1;
  });
  document.querySelectorAll('[data-dentista-count]').forEach(el => {
    const did = el.getAttribute('data-dentista-count');
    const n = conteo[did] || 0;
    el.textContent = '(' + n + (n === 1 ? ' cita' : ' citas') + ')';
  });
}

function recalcularConteoDesdeVista() {
  if (!calendar) return;
  const view = calendar.view;
  const start = view.activeStart;
  const end = view.activeEnd;
  const conteo = {};
  calendar.getEvents().forEach(ev => {
    if (ev.start >= start && ev.start < end) {
      const did = String(ev.extendedProps?.dentista_id || '');
      if (did) conteo[did] = (conteo[did] || 0) + 1;
    }
  });
  document.querySelectorAll('[data-dentista-count]').forEach(el => {
    const did = el.getAttribute('data-dentista-count');
    const n = conteo[did] || 0;
    el.textContent = '(' + n + (n === 1 ? ' cita' : ' citas') + ')';
  });
}

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

  initReagendar();
}

function abrirModalNuevo(start = null, end = null, resourceId = null) {
  citaEditandoId = null;
  limpiarFormulario();
  document.getElementById('modalCitaTitulo').textContent = 'Nueva Cita';
  document.getElementById('statusWrapper').style.display = 'none';
  document.getElementById('btnCancelarCita').classList.add('d-none');
  document.getElementById('btnReagendar')?.classList.add('d-none');
  document.getElementById('formMsg').textContent = '';

  if (start) {
    const d = new Date(start);
    document.getElementById('fecha_cita').value = fechaLocalISO(d);
    document.getElementById('hora_inicio').value = horaLocalHM(d);
  }
  if (end) {
    const d = new Date(end);
    document.getElementById('hora_fin').value = horaLocalHM(d);
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
  document.getElementById('btnReagendar')?.classList.remove('d-none');
  document.getElementById('formMsg').textContent = '';

  document.getElementById('paciente_id').value = ext.paciente_id || '';
  document.getElementById('paciente_search').value = evento.title.split(' - ')[0];
  document.getElementById('paciente_info').textContent = '';
  document.getElementById('dentista_id').value = ext.dentista_id || '';
  document.getElementById('dentista_cabecera_hint')?.classList.add('d-none');
  document.getElementById('consultorio_id').value = ext.consultorio_id || '';
  document.getElementById('notas_cita').value = ext.notas || '';
  document.getElementById('status_cita').value = ext.status || 'pendiente';
  document.getElementById('anticipo_pagado').checked = ext.anticipo_pagado || false;

  // Anticipo: solo mostrar si el paciente lo requiere
  const anticipoWrapper = document.getElementById('anticipoWrapper');
  if (anticipoWrapper) {
    anticipoWrapper.style.display = ext.requiere_anticipo ? 'block' : 'none';
  }

  // Proxima visita: mostrar solo si completada
  const pvw = document.getElementById('proximaVisitaWrapper');
  if (pvw) pvw.style.display = ext.status === 'completada' ? 'block' : 'none';
  document.getElementById('toggle_proxima_visita').checked = false;
  document.getElementById('proxima_visita_input_wrapper').style.display = 'none';
  document.getElementById('proxima_visita_mes').value = '';

  const start = new Date(evento.start);
  const end = new Date(evento.end);
  document.getElementById('fecha_cita').value = fechaLocalISO(start);
  document.getElementById('hora_inicio').value = horaLocalHM(start);
  document.getElementById('hora_fin').value = horaLocalHM(end);

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
  const aw = document.getElementById('anticipoWrapper');
  if (aw) aw.style.display = 'block';
  const pi = document.getElementById('paciente_info');
  if (pi) pi.textContent = '';
  const hint = document.getElementById('dentista_cabecera_hint');
  if (hint) hint.classList.add('d-none');
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
    let resp = await apiFetch(url, { method, body: JSON.stringify(body) });

    // Fuera del horario del consultorio: advertir y dejar que recepcion decida
    if (resp.status === 409) {
      const err = await resp.clone().json().catch(() => ({}));
      // El backend manda `codigo` en los dos casos de horario (fuera_de_horario
      // y dia_cerrado) y acepta el override en ambos. El 409 por colision
      // de citas no trae `codigo` y debe seguir cayendo al manejo generico.
      if (err.codigo === 'fuera_de_horario' || err.codigo === 'dia_cerrado') {
        const ok = confirm(
          `${err.error}\n\nHorario del consultorio: ${err.apertura} a ${err.cierre}.\n\n` +
          `¿Agendar de todos modos?`
        );
        if (!ok) {
          msgEl.textContent = 'No se guardó: la cita queda fuera del horario del consultorio.';
          msgEl.className = 'mt-2 text-warning small';
          btnGuardar.disabled = false;
          btnGuardar.textContent = 'Guardar';
          return;
        }
        body.permitir_fuera_horario = true;
        resp = await apiFetch(url, { method, body: JSON.stringify(body) });
      }
    }

    const data = await resp.json();

    if (!resp.ok) {
      // El backend ya arma el mensaje de conflicto explicando si choca el
      // consultorio o el doctor, con nombre y hora. No lo re-armes aqui.
      msgEl.textContent = data.error || 'Error al guardar';
      msgEl.className = 'mt-2 text-danger small';
      return;
    }

    bootstrap.Modal.getInstance(document.getElementById('modalCita'))?.hide();
    calendar.refetchEvents();

    // Al marcar como completada: ofrecer programar recordatorio de seguimiento
    if (citaEditandoId && body.status === 'completada') {
      const nombrePaciente = data.paciente || document.getElementById('paciente_search').value;
      const pacienteId = data.paciente_id || parseInt(document.getElementById('paciente_id').value);
      setTimeout(() => {
        if (typeof abrirModalRecordatorio === 'function') {
          abrirModalRecordatorio(pacienteId, citaEditandoId, nombrePaciente);
        }
      }, 400);
    }
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

// ==================== REAGENDAR CITA ====================

function initReagendar() {
  document.getElementById('btnReagendar')?.addEventListener('click', abrirModalReagendar);
  document.getElementById('btnConfirmarReagendar')?.addEventListener('click', confirmarReagendar);
  document.getElementById('rea_fecha')?.addEventListener('change', () => {
    cargarSlotsReagendar();
    actualizarPreviewReagendar();
  });
  document.getElementById('rea_hora_inicio')?.addEventListener('change', actualizarPreviewReagendar);
  document.getElementById('rea_avisar')?.addEventListener('change', actualizarPreviewReagendar);
}

function abrirModalReagendar() {
  if (!citaEditandoId) return;
  document.getElementById('rea_fecha').value = document.getElementById('fecha_cita').value;
  document.getElementById('rea_hora_inicio').value = document.getElementById('hora_inicio').value;
  document.getElementById('rea_hora_fin').value = document.getElementById('hora_fin').value;
  document.getElementById('rea_avisar').checked = true;
  document.getElementById('reaMsg').textContent = '';
  cargarSlotsReagendar();
  actualizarPreviewReagendar();
  bootstrap.Modal.getInstance(document.getElementById('modalCita'))?.hide();
  new bootstrap.Modal(document.getElementById('modalReagendar')).show();
}

async function cargarSlotsReagendar() {
  const cont = document.getElementById('rea_slots');
  if (!cont) return;
  cont.replaceChildren();

  const fecha = document.getElementById('rea_fecha').value;
  const dentistaId = document.getElementById('dentista_id').value;
  if (!fecha || !dentistaId) return;

  try {
    const resp = await apiFetch(
      `/api/citas/disponibilidad?fecha=${fecha}&dentista_id=${dentistaId}&duracion=60`);
    if (!resp.ok) return;
    const data = await resp.json();
    const libres = (data.slots || []).filter(s => s.disponible);

    if (!libres.length) {
      const span = document.createElement('span');
      span.className = 'text-muted small';
      span.textContent = 'Sin huecos libres ese día.';
      cont.appendChild(span);
      return;
    }

    libres.forEach(s => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-outline-secondary btn-sm';
      btn.textContent = s.inicio;
      btn.addEventListener('click', () => {
        document.getElementById('rea_hora_inicio').value = s.inicio;
        document.getElementById('rea_hora_fin').value = s.fin;
        actualizarPreviewReagendar();
      });
      cont.appendChild(btn);
    });
  } catch (_e) {
    // Sin huecos que mostrar: la recepcionista igual puede teclear la hora
  }
}

function actualizarPreviewReagendar() {
  const el = document.getElementById('rea_preview');
  if (!el) return;
  if (!document.getElementById('rea_avisar').checked) {
    el.textContent = 'No se enviará ningún mensaje al paciente.';
    return;
  }
  const f = document.getElementById('rea_fecha').value;
  const h = document.getElementById('rea_hora_inicio').value;
  el.textContent = `Se enviará: "Su cita fue reagendada para el ${f} a las ${h}."`;
}

async function confirmarReagendar() {
  const msgEl = document.getElementById('reaMsg');
  const fecha = document.getElementById('rea_fecha').value;
  const hIni = document.getElementById('rea_hora_inicio').value;
  const hFin = document.getElementById('rea_hora_fin').value;

  if (!fecha || !hIni || !hFin) {
    msgEl.textContent = 'Completa fecha y horas.';
    msgEl.className = 'mt-2 text-danger small';
    return;
  }

  const body = {
    fecha_inicio: `${fecha}T${hIni}:00`,
    fecha_fin: `${fecha}T${hFin}:00`,
    avisar_paciente: document.getElementById('rea_avisar').checked,
  };
  const url = `/api/citas/${citaEditandoId}/reagendar`;

  let resp = await apiFetch(url, { method: 'POST', body: JSON.stringify(body) });

  if (resp.status === 409) {
    const err = await resp.json().catch(() => ({}));
    // El backend manda `codigo` en los dos casos de horario (fuera_de_horario
    // y dia_cerrado) y acepta el override en ambos, igual que en guardarCita().
    // El 409 por colision de citas no trae `codigo` y cae al else generico.
    if (err.codigo === 'fuera_de_horario' || err.codigo === 'dia_cerrado') {
      const ok = confirm(
        `${err.error}\n\nHorario del consultorio: ${err.apertura} a ${err.cierre}.\n\n` +
        `¿Reagendar de todos modos?`
      );
      if (!ok) {
        msgEl.textContent = 'No se reagendó: queda fuera del horario del consultorio.';
        msgEl.className = 'mt-2 text-warning small';
        return;
      }
      body.permitir_fuera_horario = true;
      resp = await apiFetch(url, { method: 'POST', body: JSON.stringify(body) });
    } else {
      msgEl.textContent = err.error || 'Ese horario ya está ocupado.';
      msgEl.className = 'mt-2 text-danger small';
      return;
    }
  }

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    msgEl.textContent = err.error || 'No se pudo reagendar.';
    msgEl.className = 'mt-2 text-danger small';
    return;
  }

  const data = await resp.json();
  if (body.avisar_paciente && !data.aviso_enviado) {
    alert('La cita se reagendó, pero no se pudo enviar el aviso por WhatsApp. Avisa al paciente por otro medio.');
  }
  bootstrap.Modal.getInstance(document.getElementById('modalReagendar')).hide();
  calendar.refetchEvents();
}

// ==================== BUSQUEDA PACIENTES (DOM seguro) ====================

async function buscarPacientes(q) {
  const listEl = document.getElementById('paciente_results');
  try {
    // per_page alto para no ocultar pacientes existentes: con per_page=10 y
    // apellidos comunes (p.ej. "hernandez" ~164) el paciente buscado quedaba
    // fuera de la lista y parecia "borrado". Si aun asi hay mas coincidencias
    // que las mostradas, se avisa al usuario que afine la busqueda.
    const resp = await apiFetch(`/api/pacientes?q=${encodeURIComponent(q)}&per_page=50`);
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
          seleccionarPaciente(p.id, p.nombre_completo || p.nombre, p.whatsapp || p.telefono || '',
                              p.doctor_id, p.doctor_nombre)
        );
        listEl.appendChild(a);
      });

      // Aviso si hay mas coincidencias de las mostradas: el paciente buscado
      // podria no estar en la lista. Se invita a escribir el nombre completo.
      const total = data.total || pacs.length;
      if (total > pacs.length) {
        const aviso = document.createElement('div');
        aviso.className = 'list-group-item small text-warning bg-light';
        aviso.textContent =
          `Mostrando ${pacs.length} de ${total} coincidencias. ` +
          `Escribe el nombre o telefono completo para afinar la busqueda.`;
        listEl.appendChild(aviso);
      }
    }
    listEl.classList.remove('d-none');
  } catch (e) {
    console.error(e);
  }
}

function seleccionarPaciente(id, nombre, telefono, doctorId, doctorNombre) {
  document.getElementById('paciente_id').value = id;
  document.getElementById('paciente_search').value = nombre;
  const pi = document.getElementById('paciente_info');
  pi.textContent = telefono ? `Tel: ${telefono}` : '';
  document.getElementById('paciente_results').classList.add('d-none');

  // Auto-llenar dentista con el doctor de cabecera (solo en citas nuevas).
  // Queda editable: en emergencia se cambia el select manualmente.
  const esNueva = !document.getElementById('cita_id').value;
  const hint = document.getElementById('dentista_cabecera_hint');
  if (esNueva && doctorId) {
    document.getElementById('dentista_id').value = String(doctorId);
    if (hint) {
      hint.querySelector('span').textContent =
        `Doctor de cabecera: ${doctorNombre || 'asignado'} — cambialo solo en emergencia`;
      hint.classList.remove('d-none');
    }
  } else if (hint) {
    hint.classList.add('d-none');
  }
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
    fecha_inicio: fechaHoraLocalISO(info.event.start),
    fecha_fin: fechaHoraLocalISO(info.event.end),
  };
  if (info.newResource?.id) body.consultorio_id = parseInt(info.newResource.id);
  const resp = await apiFetch(`/api/citas/${info.event.id}`, { method: 'PUT', body: JSON.stringify(body) });
  if (!resp.ok) { const d = await resp.json(); alert(d.error || 'No se pudo reagendar'); info.revert(); }
}

async function onEventResize(info) {
  const body = {
    fecha_inicio: fechaHoraLocalISO(info.event.start),
    fecha_fin: fechaHoraLocalISO(info.event.end),
  };
  const resp = await apiFetch(`/api/citas/${info.event.id}`, { method: 'PUT', body: JSON.stringify(body) });
  if (!resp.ok) info.revert();
}
