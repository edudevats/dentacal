/**
 * Campanas de WhatsApp masivo - CRM
 * All user-provided content is escaped via esc() before DOM insertion.
 */

let campanaRefreshInterval = null;

// Cargar campanas cuando se activa el tab
document.addEventListener('DOMContentLoaded', function() {
  const tabCampanas = document.getElementById('tab-campanas');
  if (tabCampanas) {
    tabCampanas.addEventListener('shown.bs.tab', function() {
      cargarCampanas();
    });
  }

  // Toggle fecha programada
  document.querySelectorAll('input[name="campProgramar"]').forEach(radio => {
    radio.addEventListener('change', function() {
      const container = document.getElementById('campFechaContainer');
      container.style.display = this.value === 'programar' ? 'block' : 'none';
    });
  });

  // Limpiar interval al cerrar modal detalle
  const modalDetalle = document.getElementById('modalDetalleCampana');
  if (modalDetalle) {
    modalDetalle.addEventListener('hidden.bs.modal', function() {
      if (campanaRefreshInterval) {
        clearInterval(campanaRefreshInterval);
        campanaRefreshInterval = null;
      }
    });
  }
});


/** Escape HTML entities to prevent XSS */
function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}


function cargarCampanas() {
  apiFetch('/api/crm/campanas')
    .then(r => r.json())
    .then(campanas => {
      const container = document.getElementById('campanasList');
      container.textContent = ''; // Clear safely

      if (!campanas.length) {
        _renderEmptyCampanas(container);
        return;
      }

      _renderCampanasTable(container, campanas);
    })
    .catch(err => {
      console.error('Error cargando campanas:', err);
    });
}


function _renderEmptyCampanas(container) {
  const wrapper = document.createElement('div');
  wrapper.className = 'text-center py-5 text-muted';

  const icon = document.createElement('i');
  icon.className = 'bi bi-megaphone';
  icon.style.cssText = 'font-size:3rem;opacity:0.3';
  wrapper.appendChild(icon);

  const p = document.createElement('p');
  p.className = 'mt-2';
  p.textContent = 'No hay campanas creadas';
  wrapper.appendChild(p);

  const btn = document.createElement('button');
  btn.className = 'btn btn-primary btn-sm';
  btn.onclick = abrirNuevaCampana;
  btn.textContent = 'Crear primera campaña';
  wrapper.appendChild(btn);

  container.appendChild(wrapper);
}


function _renderCampanasTable(container, campanas) {
  const wrapper = document.createElement('div');
  wrapper.className = 'table-responsive';

  const table = document.createElement('table');
  table.className = 'table table-hover align-middle';

  // Header
  const thead = document.createElement('thead');
  thead.className = 'table-light';
  const headerRow = document.createElement('tr');
  ['Nombre', 'Estatus', 'Destinatarios', 'Enviados', 'Fecha', 'Acciones'].forEach(text => {
    const th = document.createElement('th');
    th.textContent = text;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Body
  const tbody = document.createElement('tbody');
  campanas.forEach(c => {
    const tr = document.createElement('tr');

    // Nombre
    const tdNombre = document.createElement('td');
    tdNombre.className = 'fw-semibold';
    tdNombre.textContent = c.nombre;
    tr.appendChild(tdNombre);

    // Estatus
    const tdEstatus = document.createElement('td');
    tdEstatus.appendChild(_crearBadgeEstatus(c.estatus));
    tr.appendChild(tdEstatus);

    // Destinatarios
    const tdDest = document.createElement('td');
    tdDest.textContent = c.total_destinatarios;
    tr.appendChild(tdDest);

    // Enviados
    const tdEnv = document.createElement('td');
    const spanOk = document.createElement('span');
    spanOk.className = 'text-success';
    spanOk.textContent = c.enviados;
    tdEnv.appendChild(spanOk);
    if (c.fallidos > 0) {
      const spanFail = document.createElement('span');
      spanFail.className = 'text-danger ms-1';
      spanFail.textContent = `(${c.fallidos} fallidos)`;
      tdEnv.appendChild(spanFail);
    }
    tr.appendChild(tdEnv);

    // Fecha
    const tdFecha = document.createElement('td');
    tdFecha.className = 'small text-muted';
    tdFecha.textContent = c.created_at ? new Date(c.created_at).toLocaleDateString('es-MX', {
      day: '2-digit', month: 'short', year: 'numeric'
    }) : '-';
    tr.appendChild(tdFecha);

    // Acciones
    const tdAcc = document.createElement('td');
    const btnVer = document.createElement('button');
    btnVer.className = 'btn btn-sm btn-outline-info';
    btnVer.title = 'Ver detalle';
    btnVer.onclick = () => verDetalleCampana(c.id);
    const iconVer = document.createElement('i');
    iconVer.className = 'bi bi-eye';
    btnVer.appendChild(iconVer);
    tdAcc.appendChild(btnVer);

    if (c.estatus === 'borrador') {
      const btnEnv = document.createElement('button');
      btnEnv.className = 'btn btn-sm btn-outline-success ms-1';
      btnEnv.title = 'Enviar';
      btnEnv.onclick = () => enviarCampanaDirecto(c.id);
      const iconEnv = document.createElement('i');
      iconEnv.className = 'bi bi-send';
      btnEnv.appendChild(iconEnv);
      tdAcc.appendChild(btnEnv);

      const btnDel = document.createElement('button');
      btnDel.className = 'btn btn-sm btn-outline-danger ms-1';
      btnDel.title = 'Eliminar';
      btnDel.onclick = () => eliminarCampana(c.id);
      const iconDel = document.createElement('i');
      iconDel.className = 'bi bi-trash';
      btnDel.appendChild(iconDel);
      tdAcc.appendChild(btnDel);
    }

    if (c.estatus === 'programada') {
      const btnCancel = document.createElement('button');
      btnCancel.className = 'btn btn-sm btn-outline-danger ms-1';
      btnCancel.title = 'Cancelar';
      btnCancel.onclick = () => eliminarCampana(c.id);
      const iconCancel = document.createElement('i');
      iconCancel.className = 'bi bi-x-circle';
      btnCancel.appendChild(iconCancel);
      tdAcc.appendChild(btnCancel);
    }

    tr.appendChild(tdAcc);
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}


function _crearBadgeEstatus(estatus) {
  const span = document.createElement('span');
  span.className = 'badge ';
  const map = {
    borrador:   { cls: 'campana-badge-borrador', text: 'Borrador' },
    programada: { cls: 'campana-badge-programada', text: 'Programada' },
    enviando:   { cls: 'campana-badge-enviando', text: 'Enviando...' },
    completada: { cls: 'campana-badge-completada', text: 'Completada' },
    cancelada:  { cls: 'campana-badge-cancelada', text: 'Cancelada' },
  };
  const info = map[estatus] || { cls: 'bg-secondary', text: estatus };
  span.className += info.cls;
  span.textContent = info.text;
  return span;
}


function abrirNuevaCampana() {
  document.getElementById('campNombre').value = '';
  document.getElementById('campMensaje').value = '';
  document.getElementById('campMesesSinCita').value = '0';
  document.getElementById('campEnviarAhora').checked = true;
  document.getElementById('campFechaContainer').style.display = 'none';
  document.getElementById('campFechaProgramada').value = '';
  document.getElementById('campPreview').style.display = 'none';

  document.querySelectorAll('.camp-estatus-check input').forEach(cb => {
    cb.checked = (cb.value === 'alta' || cb.value === 'activo');
  });

  const modal = new bootstrap.Modal(document.getElementById('modalNuevaCampana'));
  modal.show();
}


function _getFiltros() {
  const estatus_crm = [];
  document.querySelectorAll('.camp-estatus-check input:checked').forEach(cb => {
    estatus_crm.push(cb.value);
  });
  const meses = parseInt(document.getElementById('campMesesSinCita').value) || 0;
  return { estatus_crm, meses_sin_cita: meses };
}


function previewAudiencia() {
  const filtros = _getFiltros();
  const previewDiv = document.getElementById('campPreview');
  previewDiv.style.display = 'block';
  document.getElementById('campPreviewTotal').textContent = '...';
  document.getElementById('campPreviewMuestra').textContent = '';

  apiFetch('/api/crm/campanas/preview', {
    method: 'POST',
    body: JSON.stringify({ filtros }),
  })
    .then(r => r.json())
    .then(data => {
      document.getElementById('campPreviewTotal').textContent = data.total;
      const muestraDiv = document.getElementById('campPreviewMuestra');
      muestraDiv.textContent = '';

      if (data.muestra && data.muestra.length > 0) {
        data.muestra.forEach(p => {
          const badge = document.createElement('span');
          badge.className = 'badge bg-light text-dark border me-1 mb-1';
          badge.textContent = p.nombre;
          muestraDiv.appendChild(badge);
        });
        if (data.total > 10) {
          const more = document.createElement('span');
          more.className = 'text-muted';
          more.textContent = '...y mas';
          muestraDiv.appendChild(more);
        }
      }
    })
    .catch(err => {
      document.getElementById('campPreviewTotal').textContent = 'Error';
      console.error(err);
    });
}


function guardarCampana(enviar) {
  const nombre = document.getElementById('campNombre').value.trim();
  const mensaje = document.getElementById('campMensaje').value.trim();

  if (!nombre || !mensaje) {
    alert('El nombre y el mensaje son requeridos');
    return;
  }

  const filtros = _getFiltros();
  if (filtros.estatus_crm.length === 0) {
    alert('Selecciona al menos un estatus CRM');
    return;
  }

  const programar = document.getElementById('campProgramarFecha').checked;
  let fecha_programada = null;
  if (programar) {
    fecha_programada = document.getElementById('campFechaProgramada').value;
    if (!fecha_programada) {
      alert('Selecciona la fecha y hora para programar el envio');
      return;
    }
  }

  const body = { nombre, mensaje, filtros, fecha_programada };

  apiFetch('/api/crm/campanas', {
    method: 'POST',
    body: JSON.stringify(body),
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        alert(data.error);
        return;
      }

      if (enviar) {
        _confirmarYEnviar(data.id);
      } else {
        bootstrap.Modal.getInstance(document.getElementById('modalNuevaCampana')).hide();
        cargarCampanas();
      }
    })
    .catch(err => {
      alert('Error al crear la campana');
      console.error(err);
    });
}


function _confirmarYEnviar(campanaId) {
  const filtros = _getFiltros();
  apiFetch('/api/crm/campanas/preview', {
    method: 'POST',
    body: JSON.stringify({ filtros }),
  })
    .then(r => r.json())
    .then(data => {
      const programar = document.getElementById('campProgramarFecha').checked;
      const accion = programar ? 'programar' : 'enviar';
      if (!confirm('Se van a ' + accion + ' ' + data.total + ' mensajes de WhatsApp. Continuar?')) {
        return;
      }
      _enviarCampana(campanaId);
    });
}


function enviarCampanaDirecto(campanaId) {
  apiFetch('/api/crm/campanas/' + campanaId)
    .then(r => r.json())
    .then(data => {
      const filtros = data.filtros || {};
      return apiFetch('/api/crm/campanas/preview', {
        method: 'POST',
        body: JSON.stringify({ filtros }),
      }).then(r => r.json());
    })
    .then(preview => {
      if (!confirm('Se van a enviar ' + preview.total + ' mensajes de WhatsApp. Continuar?')) return;
      _enviarCampana(campanaId);
    });
}


function _enviarCampana(campanaId) {
  apiFetch('/api/crm/campanas/' + campanaId + '/enviar', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        alert(data.error);
        return;
      }

      const modalNueva = bootstrap.Modal.getInstance(document.getElementById('modalNuevaCampana'));
      if (modalNueva) modalNueva.hide();

      if (data.programada) {
        alert('Campana programada. ' + data.total_destinatarios + ' destinatarios.');
      } else {
        alert('Envio iniciado. ' + data.total_destinatarios + ' mensajes en cola.');
      }

      cargarCampanas();
    })
    .catch(err => {
      alert('Error al enviar la campana');
      console.error(err);
    });
}


function verDetalleCampana(campanaId) {
  apiFetch('/api/crm/campanas/' + campanaId)
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        alert(data.error);
        return;
      }

      document.getElementById('detCampNombre').textContent = data.nombre;
      document.getElementById('detCampMensaje').textContent = data.mensaje;

      // Estatus badge - replace safely
      const estatusContainer = document.getElementById('detCampEstatus');
      if (estatusContainer) {
        const parent = estatusContainer.parentNode;
        const newBadge = _crearBadgeEstatus(data.estatus);
        newBadge.id = 'detCampEstatus';
        parent.replaceChild(newBadge, estatusContainer);
      }

      document.getElementById('detCampFecha').textContent = data.created_at
        ? new Date(data.created_at).toLocaleString('es-MX') : '-';

      const progDiv = document.getElementById('detCampProgramada');
      if (data.fecha_programada) {
        progDiv.style.display = 'block';
        document.getElementById('detCampFechaProg').textContent =
          new Date(data.fecha_programada).toLocaleString('es-MX');
      } else {
        progDiv.style.display = 'none';
      }

      _actualizarProgresoCampana(data);
      _renderDestinatarios(data.destinatarios || []);

      const modal = new bootstrap.Modal(document.getElementById('modalDetalleCampana'));
      modal.show();

      if (data.estatus === 'enviando') {
        campanaRefreshInterval = setInterval(() => {
          _refreshDetalleCampana(campanaId);
        }, 5000);
      }
    })
    .catch(err => {
      console.error('Error cargando detalle campana:', err);
    });
}


function _actualizarProgresoCampana(data) {
  const total = data.total_destinatarios || 1;
  const enviados = data.enviados || 0;
  const fallidos = data.fallidos || 0;

  document.getElementById('detCampEnviados').textContent = enviados;
  document.getElementById('detCampTotal').textContent = data.total_destinatarios;
  document.getElementById('detCampFallidos').textContent = fallidos;
  document.getElementById('detCampFallidosWrap').style.display = fallidos > 0 ? 'inline' : 'none';

  const pctOk = (enviados / total * 100).toFixed(1);
  const pctFail = (fallidos / total * 100).toFixed(1);
  document.getElementById('detCampProgress').style.width = pctOk + '%';
  document.getElementById('detCampProgressFail').style.width = pctFail + '%';
}


function _renderDestinatarios(destinatarios) {
  const container = document.getElementById('detCampDestinatarios');
  container.textContent = '';

  if (!destinatarios.length) {
    const p = document.createElement('p');
    p.className = 'text-muted text-center small';
    p.textContent = 'Sin destinatarios';
    container.appendChild(p);
    return;
  }

  const listGroup = document.createElement('div');
  listGroup.className = 'list-group list-group-flush';

  destinatarios.forEach(d => {
    const item = document.createElement('div');
    item.className = 'list-group-item py-1 px-2 d-flex align-items-center small';

    const icon = document.createElement('i');
    if (d.estatus === 'enviado') {
      icon.className = 'bi bi-check-circle-fill text-success me-2';
    } else if (d.estatus === 'fallido') {
      icon.className = 'bi bi-x-circle-fill text-danger me-2';
    } else {
      icon.className = 'bi bi-clock text-muted me-2';
    }
    item.appendChild(icon);

    const nombre = document.createElement('span');
    if (d.estatus === 'fallido') nombre.className = 'text-danger';
    nombre.textContent = d.paciente_nombre;
    item.appendChild(nombre);

    const numero = document.createElement('span');
    numero.className = 'text-muted ms-2';
    numero.textContent = d.numero_destino || '';
    item.appendChild(numero);

    if (d.error_mensaje) {
      const errSpan = document.createElement('span');
      errSpan.className = 'text-danger ms-auto small';
      errSpan.title = d.error_mensaje;
      errSpan.textContent = 'Error';
      item.appendChild(errSpan);
    }

    listGroup.appendChild(item);
  });

  container.appendChild(listGroup);
}


function _refreshDetalleCampana(campanaId) {
  apiFetch('/api/crm/campanas/' + campanaId)
    .then(r => r.json())
    .then(data => {
      _actualizarProgresoCampana(data);
      _renderDestinatarios(data.destinatarios || []);

      // Actualizar badge estatus
      const estatusEl = document.getElementById('detCampEstatus');
      if (estatusEl) {
        const parent = estatusEl.parentNode;
        const newBadge = _crearBadgeEstatus(data.estatus);
        newBadge.id = 'detCampEstatus';
        parent.replaceChild(newBadge, estatusEl);
      }

      if (data.estatus !== 'enviando' && campanaRefreshInterval) {
        clearInterval(campanaRefreshInterval);
        campanaRefreshInterval = null;
        cargarCampanas();
      }
    });
}


function eliminarCampana(campanaId) {
  if (!confirm('Estas seguro de eliminar/cancelar esta campana?')) return;

  apiFetch('/api/crm/campanas/' + campanaId, { method: 'DELETE' })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        alert(data.error);
        return;
      }
      cargarCampanas();
    })
    .catch(err => {
      alert('Error al eliminar');
      console.error(err);
    });
}
