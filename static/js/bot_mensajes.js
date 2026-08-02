/* Bitácora de mensajes salientes: métodos DOM seguros. */

let mensajesPageActual = 1;

const ETIQUETA_ESTATUS = {
  enviado: 'Enviado',
  fallido: 'Reintentando',
  fallido_definitivo: 'Fallido',
  caducado: 'Caducado',
  pendiente: 'Pendiente'
};

function badgeClassEstatus(estatus) {
  if (estatus === 'enviado') return 'bg-success';
  if (estatus === 'fallido') return 'bg-warning text-dark';
  if (estatus === 'fallido_definitivo') return 'bg-danger';
  if (estatus === 'caducado') return 'bg-secondary';
  return 'bg-light text-dark';
}

function formatearFechaMensaje(iso) {
  if (!iso) return '';
  const fecha = new Date(iso);
  return fecha.toLocaleDateString('es-MX') + ' ' +
    fecha.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
}

function limpiarErrorMensajes() {
  const alerta = document.getElementById('mensajesError');
  alerta.textContent = '';
  alerta.classList.add('d-none');
}

function mostrarErrorMensajes() {
  const alerta = document.getElementById('mensajesError');
  alerta.textContent = 'No se pudieron cargar los mensajes. Intenta de nuevo.';
  alerta.classList.remove('d-none');
}

function limpiarMensajesMostrados() {
  document.getElementById('mensajesBody').textContent = '';
  document.getElementById('mensajesPaginacion').textContent = '';
  document.getElementById('msgTotalText').textContent = '';
  document.getElementById('resumenEnviados').textContent = '0';
  document.getElementById('resumenFallidos').textContent = '0';
  document.getElementById('resumenReintentando').textContent = '0';
}

function cargarMensajesTab(page) {
  if (page) mensajesPageActual = page;
  limpiarErrorMensajes();

  const estatus = document.getElementById('msgEstatusFiltro').value;
  const tipo = document.getElementById('msgTipoFiltro').value;
  const fechaDesde = document.getElementById('msgFechaDesde').value;
  const fechaHasta = document.getElementById('msgFechaHasta').value;
  const params = new URLSearchParams({ page: mensajesPageActual, per_page: 50 });

  if (estatus) params.set('estatus', estatus);
  if (tipo) params.set('tipo', tipo);
  if (fechaDesde) params.set('fecha_desde', fechaDesde);
  if (fechaHasta) params.set('fecha_hasta', fechaHasta);

  return apiFetch('/api/bot/mensajes?' + params.toString())
    .then(function (response) {
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      renderMensajesTable(data.mensajes);
      renderMensajesPaginacion(data.page, data.pages);
      document.getElementById('msgTotalText').textContent =
        data.total + ' mensaje' + (data.total !== 1 ? 's' : '');
      document.getElementById('resumenEnviados').textContent = data.resumen.enviados;
      document.getElementById('resumenFallidos').textContent = data.resumen.fallidos;
      document.getElementById('resumenReintentando').textContent = data.resumen.reintentando;
      limpiarErrorMensajes();
    })
    .catch(function (err) {
      limpiarMensajesMostrados();
      mostrarErrorMensajes();
      console.error('Error cargando mensajes:', err);
    });
}

function renderMensajesTable(mensajes) {
  const tbody = document.getElementById('mensajesBody');
  tbody.textContent = '';

  if (!mensajes || mensajes.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.setAttribute('colspan', '8');
    td.className = 'text-center text-muted py-4';
    td.textContent = 'No hay mensajes registrados';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  mensajes.forEach(function (mensaje) {
    const tr = document.createElement('tr');

    const tdFecha = document.createElement('td');
    tdFecha.className = 'small text-nowrap';
    tdFecha.textContent = formatearFechaMensaje(mensaje.fecha_creacion);
    tr.appendChild(tdFecha);

    const tdTipo = document.createElement('td');
    const tipoBadge = document.createElement('span');
    tipoBadge.className = 'badge bg-light text-dark';
    tipoBadge.textContent = mensaje.tipo || '';
    tdTipo.appendChild(tipoBadge);
    tr.appendChild(tdTipo);

    const tdPaciente = document.createElement('td');
    tdPaciente.className = 'small';
    tdPaciente.textContent = mensaje.paciente_nombre || '—';
    tr.appendChild(tdPaciente);

    const tdNumero = document.createElement('td');
    tdNumero.className = 'small text-nowrap';
    tdNumero.textContent = mensaje.numero_destino || '';
    tr.appendChild(tdNumero);

    const tdMensaje = document.createElement('td');
    tdMensaje.className = 'small';
    tdMensaje.style.maxWidth = '260px';
    tdMensaje.style.overflow = 'hidden';
    tdMensaje.style.textOverflow = 'ellipsis';
    tdMensaje.style.whiteSpace = 'nowrap';
    tdMensaje.title = mensaje.mensaje || '';
    tdMensaje.textContent = mensaje.mensaje || '';
    tr.appendChild(tdMensaje);

    const tdEstatus = document.createElement('td');
    const estatusBadge = document.createElement('span');
    estatusBadge.className = 'badge ' + badgeClassEstatus(mensaje.estatus);
    estatusBadge.textContent = ETIQUETA_ESTATUS[mensaje.estatus] || mensaje.estatus || '';
    if (mensaje.error) estatusBadge.title = mensaje.error;
    tdEstatus.appendChild(estatusBadge);
    tr.appendChild(tdEstatus);

    const tdIntentos = document.createElement('td');
    tdIntentos.className = 'small text-center';
    tdIntentos.textContent = mensaje.intentos;
    tr.appendChild(tdIntentos);

    const tdConfirmo = document.createElement('td');
    tdConfirmo.className = 'small text-center';
    if (mensaje.cita_confirmada === null || mensaje.cita_confirmada === undefined) {
      tdConfirmo.textContent = '—';
    } else {
      const icono = document.createElement('i');
      icono.className = mensaje.cita_confirmada
        ? 'bi bi-check-circle-fill text-success'
        : 'bi bi-clock text-muted';
      icono.title = mensaje.cita_confirmada ? 'Cita confirmada' : 'Sin confirmar';
      tdConfirmo.appendChild(icono);
    }
    tr.appendChild(tdConfirmo);

    tbody.appendChild(tr);
  });
}

function renderMensajesPaginacion(page, pages) {
  const ul = document.getElementById('mensajesPaginacion');
  ul.textContent = '';
  if (!pages || pages <= 1) return;

  function agregarItem(etiqueta, destino, activo, deshabilitado) {
    const li = document.createElement('li');
    li.className = 'page-item' + (activo ? ' active' : '') +
      (deshabilitado ? ' disabled' : '');
    const enlace = document.createElement('a');
    enlace.className = 'page-link';
    enlace.href = '#';
    enlace.textContent = etiqueta;
    enlace.addEventListener('click', function (evento) {
      evento.preventDefault();
      if (!deshabilitado && !activo) cargarMensajesTab(destino);
    });
    li.appendChild(enlace);
    ul.appendChild(li);
  }

  agregarItem('«', page - 1, false, page <= 1);
  for (let pagina = Math.max(1, page - 2); pagina <= Math.min(pages, page + 2); pagina++) {
    agregarItem(String(pagina), pagina, pagina === page, false);
  }
  agregarItem('»', page + 1, false, page >= pages);
}
