/**
 * La Casa del Sr. Perez - Gestion de Pacientes
 */
let paginaActual = 1;
let pacienteEditandoId = null;
let itiTelefono = null;
let itiWhatsapp = null;
window._waModifiedByUser = false;

document.addEventListener('DOMContentLoaded', () => {
  cargarPacientes();
  document.getElementById('searchInput')?.addEventListener('input', () => {
    clearTimeout(window._searchTimer);
    window._searchTimer = setTimeout(() => { paginaActual = 1; cargarPacientes(); }, 350);
  });
  document.getElementById('filtroEstatus')?.addEventListener('change', () => {
    paginaActual = 1; cargarPacientes();
  });
  document.getElementById('btnGuardarPaciente')?.addEventListener('click', guardarPaciente);
  document.getElementById('btnEliminarPaciente')?.addEventListener('click', eliminarPaciente);
  document.getElementById('btnGenerarJustificante')?.addEventListener('click', generarJustificante);

  cargarDoctores();
  initTutor();

  const inputTel = document.querySelector("#p_telefono");
  const inputWa = document.querySelector("#p_whatsapp");
  if (inputTel && window.intlTelInput) {
    itiTelefono = window.intlTelInput(inputTel, {
      initialCountry: "mx",
      preferredCountries: ["mx", "us", "co", "ar", "es"],
      utilsScript: "https://cdn.jsdelivr.net/npm/intl-tel-input@23.0.4/build/js/utils.js",
    });
    inputTel.addEventListener('input', () => {
      if (!window._waModifiedByUser && itiWhatsapp) {
        itiWhatsapp.setNumber(itiTelefono.getNumber());
      }
    });
  }
  if (inputWa && window.intlTelInput) {
    itiWhatsapp = window.intlTelInput(inputWa, {
      initialCountry: "mx",
      preferredCountries: ["mx", "us", "co", "ar", "es"],
      utilsScript: "https://cdn.jsdelivr.net/npm/intl-tel-input@23.0.4/build/js/utils.js",
    });
    inputWa.addEventListener('input', () => {
      window._waModifiedByUser = true;
    });
  }
});

async function cargarDoctores() {
  const select = document.getElementById('p_doctor');
  if (!select) return;
  try {
    const resp = await apiFetch('/api/dentistas?activos=true');
    const data = await resp.json();
    data.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = `${d.nombre} ${d.especialidad ? `(${d.especialidad})` : ''}`;
      select.appendChild(opt);
    });
  } catch (e) {
    console.error('Error cargando doctores:', e);
  }
}

function mkEl(tag, props = {}) {
  const el = document.createElement(tag);
  if (props.text !== undefined) el.textContent = props.text;
  if (props.cls) el.className = props.cls;
  if (props.style) el.setAttribute('style', props.style);
  if (props.title) el.title = props.title;
  if (props.type) el.type = props.type;
  if (props.onclick) el.addEventListener('click', props.onclick);
  return el;
}

async function cargarPacientes() {
  const q = document.getElementById('searchInput')?.value.trim() || '';
  const estatus = document.getElementById('filtroEstatus')?.value || '';
  const tbody = document.getElementById('pacientesTbody');

  let url = `/api/pacientes?page=${paginaActual}&per_page=50`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  if (estatus) url += `&estatus=${estatus}`;

  try {
    const resp = await apiFetch(url);
    const data = await resp.json();
    const pacs = data.pacientes || [];

    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

    if (pacs.length === 0) {
      const tr = document.createElement('tr');
      const td = mkEl('td', { text: 'Sin pacientes encontrados.', cls: 'text-center text-muted py-4' });
      td.colSpan = 6;
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      pacs.forEach(p => tbody.appendChild(crearFilaPaciente(p)));
    }

    const tot = document.getElementById('totalPacientes');
    if (tot) tot.textContent = `${data.total || 0} pacientes`;
    renderPaginacion(data.pages || 1);
  } catch (e) {
    console.error(e);
  }
}

function crearFilaPaciente(p) {
  const tr = document.createElement('tr');

  const tdNombre = document.createElement('td');
  const divNombre = mkEl('div', { text: p.nombre_completo || p.nombre, cls: 'fw-semibold' });
  tdNombre.appendChild(divNombre);
  if (p.fecha_nacimiento) {
    tdNombre.appendChild(mkEl('div', { text: 'Nac: ' + p.fecha_nacimiento, cls: 'text-muted small' }));
  }

  const tdWa = mkEl('td', { text: p.whatsapp || p.telefono || '\u2014' });

  const tdTutor = document.createElement('td');
  if (p.tutor_id && p.tutor_nombre) {
    tdTutor.appendChild(mkEl('i', { cls: 'bi bi-link-45deg text-success me-1' }));
    tdTutor.appendChild(document.createTextNode(p.tutor_nombre));
  } else {
    tdTutor.textContent = p.nombre_tutor || '\u2014';
  }
  if (p.es_menor_edad) {
    tdNombre.appendChild(mkEl('span', { text: ' (menor)', cls: 'badge bg-warning text-dark ms-1 small' }));
  }

  const tdStatus = document.createElement('td');
  const badge = mkEl('span', { text: p.estatus_crm, cls: `badge badge-${p.estatus_crm}` });
  tdStatus.appendChild(badge);
  if (p.es_problematico) {
    tdStatus.appendChild(mkEl('span', { text: 'Problematico', cls: 'badge bg-danger ms-1' }));
  }

  const tdCita = mkEl('td', { text: p.ultima_cita ? p.ultima_cita.slice(0, 10) : '\u2014' });

  const tdAcc = document.createElement('td');
  const btnEdit = mkEl('button', { cls: 'btn btn-sm btn-outline-primary me-1', title: 'Editar' });
  btnEdit.appendChild(mkEl('i', { cls: 'bi bi-pencil' }));
  btnEdit.addEventListener('click', () => abrirModalEditarPaciente(p));

  const btnProb = mkEl('button', {
    cls: `btn btn-sm ${p.es_problematico ? 'btn-danger' : 'btn-outline-danger'} me-1`,
    title: p.es_problematico ? 'Desmarcar problematico' : 'Marcar como problematico',
  });
  btnProb.appendChild(mkEl('i', { cls: 'bi bi-exclamation-triangle' }));
  btnProb.addEventListener('click', (e) => { e.stopPropagation(); toggleProblematico(p); });

  const btnJust = mkEl('button', { cls: 'btn btn-sm btn-outline-secondary', title: 'Justificante' });
  btnJust.appendChild(mkEl('i', { cls: 'bi bi-file-medical' }));
  btnJust.addEventListener('click', () => abrirModalJustificante(p));

  tdAcc.appendChild(btnEdit);
  tdAcc.appendChild(btnProb);
  tdAcc.appendChild(btnJust);

  if (p.es_problematico) tr.style.background = '#fff5f5';
  [tdNombre, tdWa, tdTutor, tdStatus, tdCita, tdAcc].forEach(td => tr.appendChild(td));
  return tr;
}

function renderPaginacion(totalPages) {
  const el = document.getElementById('paginacion');
  if (!el) return;
  while (el.firstChild) el.removeChild(el.firstChild);
  if (totalPages <= 1) return;

  const nav = document.createElement('nav');
  const ul = mkEl('ul', { cls: 'pagination pagination-sm mb-0' });

  const addPage = (label, page, disabled = false) => {
    const li = mkEl('li', { cls: `page-item${disabled ? ' disabled' : ''}${page === paginaActual ? ' active' : ''}` });
    const a = mkEl('a', { text: label, cls: 'page-link', style: 'cursor:pointer' });
    a.addEventListener('click', () => { if (!disabled) { paginaActual = page; cargarPacientes(); } });
    li.appendChild(a);
    ul.appendChild(li);
  };

  addPage('\u00ab', paginaActual - 1, paginaActual === 1);
  for (let i = 1; i <= totalPages; i++) addPage(String(i), i);
  addPage('\u00bb', paginaActual + 1, paginaActual === totalPages);

  nav.appendChild(ul);
  el.appendChild(nav);
}

function abrirModalNuevoPaciente() {
  pacienteEditandoId = null;
  document.getElementById('p_id').value = '';
  document.getElementById('modalPacienteTitulo').textContent = 'Nuevo Paciente';
  document.getElementById('btnEliminarPaciente').classList.add('d-none');
  limpiarFormPaciente();
  new bootstrap.Modal(document.getElementById('modalPaciente')).show();
}

function abrirModalEditarPaciente(p) {
  pacienteEditandoId = p.id;
  document.getElementById('p_id').value = p.id;
  document.getElementById('modalPacienteTitulo').textContent = 'Editar Paciente';
  document.getElementById('btnEliminarPaciente').classList.remove('d-none');
  document.getElementById('p_nombre').value = p.nombre || '';
  document.getElementById('p_fecha_nac').value = p.fecha_nacimiento || '';
  document.getElementById('p_telefono').value = p.telefono || '';
  document.getElementById('p_whatsapp').value = p.whatsapp || '';
  if (itiTelefono) itiTelefono.setNumber(p.telefono || '');
  if (itiWhatsapp) itiWhatsapp.setNumber(p.whatsapp || '');
  window._waModifiedByUser = !!p.whatsapp && (p.whatsapp !== p.telefono);

  document.getElementById('p_tutor').value = p.nombre_tutor || '';
  document.getElementById('p_tel_tutor').value = p.telefono_tutor || '';
  document.getElementById('p_escuela').value = p.escuela || '';
  document.getElementById('p_doctor').value = p.doctor_id || '';
  document.getElementById('p_estatus').value = p.estatus_crm || 'prospecto';
  document.getElementById('p_notas').value = p.notas || '';

  // Tutor vinculado
  document.getElementById('p_tutor_id').value = p.tutor_id || '';
  document.getElementById('p_tutor_search').value = '';
  const vinc = document.getElementById('tutorVinculado');
  if (p.tutor_id && p.tutor_nombre) {
    vinc.style.display = 'block';
    document.getElementById('tutorVinculadoNombre').textContent =
      `${p.tutor_nombre} (${p.tutor_whatsapp || 'sin WA'})`;
  } else {
    vinc.style.display = 'none';
  }
  // Calcular edad y mostrar/ocultar seccion tutor
  onFechaNacChange();

  new bootstrap.Modal(document.getElementById('modalPaciente')).show();
}

function limpiarFormPaciente() {
  ['p_nombre', 'p_fecha_nac', 'p_telefono', 'p_whatsapp',
    'p_tutor', 'p_tel_tutor', 'p_escuela', 'p_doctor', 'p_notas',
    'p_tutor_id', 'p_tutor_search'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
  if (itiTelefono) itiTelefono.setNumber('');
  if (itiWhatsapp) itiWhatsapp.setNumber('');
  window._waModifiedByUser = false;
  const est = document.getElementById('p_estatus');
  if (est) est.value = 'prospecto';

  // Reset tutor UI
  const edadEl = document.getElementById('edadDisplay');
  if (edadEl) edadEl.textContent = '';
  const card = document.getElementById('tutorCard');
  if (card) card.style.display = 'none';
  const vinc = document.getElementById('tutorVinculado');
  if (vinc) vinc.style.display = 'none';
}

async function guardarPaciente() {
  const body = {
    nombre: document.getElementById('p_nombre').value.trim(),
    fecha_nacimiento: document.getElementById('p_fecha_nac').value || null,
    telefono: itiTelefono ? itiTelefono.getNumber() : document.getElementById('p_telefono').value.trim(),
    whatsapp: itiWhatsapp ? itiWhatsapp.getNumber() : document.getElementById('p_whatsapp').value.trim(),
    nombre_tutor: document.getElementById('p_tutor').value.trim(),
    telefono_tutor: document.getElementById('p_tel_tutor').value.trim(),
    escuela: document.getElementById('p_escuela').value.trim(),
    doctor_id: document.getElementById('p_doctor').value || null,
    estatus_crm: document.getElementById('p_estatus').value,
    notas: document.getElementById('p_notas').value.trim(),
    tutor_id: document.getElementById('p_tutor_id').value || null,
  };
  if (!body.nombre) {
    document.getElementById('pacienteMsg').textContent = 'El nombre es requerido.';
    return;
  }
  const url = pacienteEditandoId ? `/api/pacientes/${pacienteEditandoId}` : '/api/pacientes';
  const method = pacienteEditandoId ? 'PUT' : 'POST';
  const resp = await apiFetch(url, { method, body: JSON.stringify(body) });
  const data = await resp.json();
  const msg = document.getElementById('pacienteMsg');
  if (resp.ok) {
    bootstrap.Modal.getInstance(document.getElementById('modalPaciente'))?.hide();
    cargarPacientes();
  } else {
    msg.className = 'mt-2 text-danger small';
    msg.textContent = data.error || 'Error al guardar';
  }
}

async function eliminarPaciente() {
  if (!pacienteEditandoId || !confirm('Eliminar este paciente del sistema?')) return;
  const resp = await apiFetch(`/api/pacientes/${pacienteEditandoId}`, { method: 'DELETE' });
  if (resp.ok) {
    bootstrap.Modal.getInstance(document.getElementById('modalPaciente'))?.hide();
    cargarPacientes();
  }
}

function abrirModalJustificante(p) {
  document.getElementById('j_paciente_id').value = p.id;
  document.getElementById('j_escuela').value = p.escuela || '';
  document.getElementById('j_tratamiento').value = '';
  new bootstrap.Modal(document.getElementById('modalJustificante')).show();
}

// ─── Tutor: edad, autocomplete, vincular/desvincular ──────────────────────

function initTutor() {
  document.getElementById('p_fecha_nac')?.addEventListener('change', onFechaNacChange);

  // Autocomplete tutor
  let tutorTimer;
  document.getElementById('p_tutor_search')?.addEventListener('input', (e) => {
    clearTimeout(tutorTimer);
    const q = e.target.value.trim();
    if (q.length < 2) {
      document.getElementById('tutor_results').classList.add('d-none');
      return;
    }
    tutorTimer = setTimeout(() => buscarTutores(q), 300);
  });

  // Click fuera cierra dropdown
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#p_tutor_search') && !e.target.closest('#tutor_results')) {
      document.getElementById('tutor_results')?.classList.add('d-none');
    }
  });

  // Desvincular tutor
  document.getElementById('btnDesvincularTutor')?.addEventListener('click', () => {
    document.getElementById('p_tutor_id').value = '';
    document.getElementById('tutorVinculado').style.display = 'none';
  });
}

function onFechaNacChange() {
  const val = document.getElementById('p_fecha_nac').value;
  const edadEl = document.getElementById('edadDisplay');
  const badgeEdad = document.getElementById('badgeEdad');
  const card = document.getElementById('tutorCard');

  if (!val) {
    if (edadEl) edadEl.textContent = '';
    if (badgeEdad) badgeEdad.textContent = '';
    actualizarVisibilidadTutor(false);
    return;
  }

  const hoy = new Date();
  const nac = new Date(val + 'T00:00:00');
  let edad = hoy.getFullYear() - nac.getFullYear();
  const m = hoy.getMonth() - nac.getMonth();
  if (m < 0 || (m === 0 && hoy.getDate() < nac.getDate())) edad--;

  const txt = edad + (edad === 1 ? ' anio' : ' anios');
  if (edadEl) edadEl.textContent = txt;
  if (badgeEdad) badgeEdad.textContent = txt;

  actualizarVisibilidadTutor(edad < 18);
}

function actualizarVisibilidadTutor(esMenor) {
  const card = document.getElementById('tutorCard');
  if (!card) return;
  const tieneData = document.getElementById('p_tutor').value
    || document.getElementById('p_tel_tutor').value
    || document.getElementById('p_tutor_id').value;
  card.style.display = (esMenor || tieneData) ? 'block' : 'none';
}

async function buscarTutores(q) {
  const listEl = document.getElementById('tutor_results');
  try {
    const resp = await apiFetch(`/api/pacientes/adultos?q=${encodeURIComponent(q)}`);
    const data = await resp.json();
    const pacs = data.pacientes || [];

    while (listEl.firstChild) listEl.removeChild(listEl.firstChild);

    if (pacs.length === 0) {
      const a = document.createElement('a');
      a.className = 'list-group-item list-group-item-action small text-muted';
      a.textContent = 'Sin resultados. Llena el tutor manualmente.';
      listEl.appendChild(a);
    } else {
      pacs.forEach(p => {
        const a = document.createElement('a');
        a.className = 'list-group-item list-group-item-action small';
        a.style.cursor = 'pointer';

        const strong = document.createElement('strong');
        strong.textContent = p.nombre_completo;
        a.appendChild(strong);

        if (p.whatsapp || p.telefono) {
          const span = document.createElement('span');
          span.className = 'text-muted ms-2';
          span.textContent = p.whatsapp || p.telefono;
          a.appendChild(span);
        }

        a.addEventListener('click', () => seleccionarTutor(p));
        listEl.appendChild(a);
      });
    }
    listEl.classList.remove('d-none');
  } catch (e) {
    console.error('Error buscando tutores:', e);
  }
}

function seleccionarTutor(p) {
  document.getElementById('p_tutor_id').value = p.id;
  document.getElementById('p_tutor').value = p.nombre_completo;
  document.getElementById('p_tel_tutor').value = p.whatsapp || p.telefono || '';
  document.getElementById('p_tutor_search').value = '';
  document.getElementById('tutor_results').classList.add('d-none');

  const vinc = document.getElementById('tutorVinculado');
  if (vinc) {
    vinc.style.display = 'block';
    document.getElementById('tutorVinculadoNombre').textContent =
      `${p.nombre_completo} (${p.whatsapp || p.telefono || 'sin WA'})`;
  }
}

// ─── Problematico toggle ──────────────────────────────────────────────────

async function toggleProblematico(p) {
  const accion = p.es_problematico ? 'desmarcar' : 'marcar';
  const advertencia = !p.es_problematico
    ? '\n\nSu estatus CRM cambiara a "baja", no recibira mensajes automaticos y no podra agendar citas por WhatsApp.'
    : '';
  if (!confirm(`Desea ${accion} a ${p.nombre} como paciente problematico?${advertencia}`)) return;
  try {
    const resp = await apiFetch(`/api/pacientes/${p.id}/problematico`, {
      method: 'POST',
      body: JSON.stringify({ es_problematico: !p.es_problematico }),
    });
    if (resp.ok) cargarPacientes();
  } catch (e) {
    console.error('Error toggle problematico:', e);
  }
}

// ─── Justificantes ────────────────────────────────────────────────────────

async function generarJustificante() {
  const body = {
    paciente_id: parseInt(document.getElementById('j_paciente_id').value),
    escuela: document.getElementById('j_escuela').value,
    tratamiento_realizado: document.getElementById('j_tratamiento').value.trim(),
    doctor_firmante: document.getElementById('j_doctor').value,
  };
  if (!body.tratamiento_realizado) { alert('Describe el tratamiento realizado.'); return; }
  const resp = await apiFetch('/api/justificantes', { method: 'POST', body: JSON.stringify(body) });
  const data = await resp.json();
  if (resp.ok && data.id) {
    bootstrap.Modal.getInstance(document.getElementById('modalJustificante'))?.hide();
    window.open(`/api/justificantes/${data.id}/pdf`, '_blank');
  } else {
    alert(data.error || 'Error al generar justificante');
  }
}
