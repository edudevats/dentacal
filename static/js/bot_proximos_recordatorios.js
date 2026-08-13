/* Próximos recordatorios: renderizado DOM seguro y estado de carga aislado. */

const PROXIMOS_TIPOS = {
  confirmacion_24h: 'Confirmación 24 h',
  confirmacion_mismo_dia: 'Confirmar hoy',
  recordatorio_cita_hoy: 'Recordatorio de cita hoy'
};

const PROXIMOS_ESTADOS = {
  enviado: 'Enviado',
  pendiente: 'Pendiente',
  fallido: 'Reintentando',
  fallido_definitivo: 'Fallido',
  caducado: 'Caducado'
};

function limpiarProximosRecordatorios() {
  document.getElementById('proximosBody').textContent = '';
  document.getElementById('proximosTotalText').textContent = '';
}

function limpiarErrorProximos() {
  const error = document.getElementById('proximosError');
  error.textContent = '';
  error.classList.add('d-none');
}

function mostrarErrorProximos() {
  const error = document.getElementById('proximosError');
  error.textContent = 'No se pudieron cargar los próximos recordatorios. Intenta de nuevo.';
  error.classList.remove('d-none');
}

function formatearFechaProximo(iso) {
  if (!iso) return '—';
  const fecha = new Date(iso);
  return fecha.toLocaleDateString('es-MX') + ' ' +
    fecha.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
}

function agregarCeldaProximo(fila, texto, clase) {
  const celda = document.createElement('td');
  celda.textContent = texto === null || texto === undefined ? '—' : texto;
  if (clase) celda.className = clase;
  fila.appendChild(celda);
  return celda;
}

function claseEstadoProximo(estado) {
  if (estado === 'enviado') return 'bg-success';
  if (estado === 'fallido') return 'bg-warning text-dark';
  if (estado === 'fallido_definitivo') return 'bg-danger';
  if (estado === 'caducado') return 'bg-secondary';
  return 'bg-light text-dark';
}

function agregarBadgeProximo(celda, texto, clase) {
  const badge = document.createElement('span');
  badge.className = 'badge ' + clase;
  badge.textContent = texto;
  celda.textContent = '';
  celda.appendChild(badge);
}

function renderEstadoProximo(celda, envio) {
  if (!envio || !envio.estado) {
    celda.textContent = 'Por enviar';
    celda.className = 'small text-muted';
    return;
  }
  agregarBadgeProximo(
    celda,
    PROXIMOS_ESTADOS[envio.estado] || envio.estado,
    claseEstadoProximo(envio.estado)
  );
  if (envio.fecha) celda.title = formatearFechaProximo(envio.fecha);
}

function renderProximosRecordatorios(filas) {
  const tbody = document.getElementById('proximosBody');
  tbody.textContent = '';
  if (!filas || filas.length === 0) {
    const fila = document.createElement('tr');
    const celda = agregarCeldaProximo(
      fila, 'No hay citas próximas con recordatorios',
      'text-center text-muted py-4');
    celda.setAttribute('colspan', '9');
    tbody.appendChild(fila);
    return;
  }

  filas.forEach(function (item) {
    const fila = document.createElement('tr');
    agregarCeldaProximo(fila, formatearFechaProximo(item.fecha_cita), 'small text-nowrap');
    agregarCeldaProximo(fila, item.paciente_nombre || '—', 'small');
    agregarCeldaProximo(fila, item.doctor_nombre || '—', 'small');

    const estado = agregarCeldaProximo(fila, '');
    agregarBadgeProximo(
      estado,
      item.estado_cita === 'confirmada' ? 'Confirmada' : 'Pendiente',
      item.estado_cita === 'confirmada' ? 'bg-success' : 'bg-warning text-dark'
    );

    agregarCeldaProximo(
      fila,
      item.proximo_mensaje ?
        (PROXIMOS_TIPOS[item.proximo_mensaje] || item.proximo_mensaje) :
        'Sin envío pendiente',
      'small'
    );
    const envio24 = agregarCeldaProximo(fila, '');
    renderEstadoProximo(envio24, item.recordatorio_24h);
    const envioHoy = agregarCeldaProximo(fila, '');
    renderEstadoProximo(envioHoy, item.mensaje_mismo_dia);

    const respondio = agregarCeldaProximo(fila, '');
    agregarBadgeProximo(
      respondio,
      item.respondio ? 'Sí' : 'No',
      item.respondio ? 'bg-info text-dark' : 'bg-light text-dark'
    );
    agregarCeldaProximo(
      fila, formatearFechaProximo(item.ultima_respuesta),
      'small text-nowrap');
    tbody.appendChild(fila);
  });
}

function cargarProximosRecordatorios() {
  limpiarErrorProximos();
  const params = new URLSearchParams();
  const fecha = document.getElementById('proximosFechaFiltro').value;
  const estado = document.getElementById('proximosEstadoFiltro').value;
  if (fecha) params.set('fecha', fecha);
  if (estado) params.set('estado', estado);
  const query = params.toString();

  return apiFetch('/api/bot/proximos-recordatorios' + (query ? '?' + query : ''))
    .then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(function (data) {
      renderProximosRecordatorios(data.recordatorios);
      document.getElementById('proximosTotalText').textContent =
        data.total + ' cita' + (data.total === 1 ? '' : 's');
      limpiarErrorProximos();
    })
    .catch(function (error) {
      limpiarProximosRecordatorios();
      mostrarErrorProximos();
      console.error('Error cargando próximos recordatorios:', error);
    });
}
