/* bot_logs.js — Log viewer for the bot monitor (safe DOM methods, no innerHTML) */

let logsPageActual = 1;

function cargarLogsBotTab(page) {
  if (page) logsPageActual = page;
  const nivel = document.getElementById('logNivelFiltro').value;
  const params = new URLSearchParams({ page: logsPageActual, per_page: 50 });
  if (nivel) params.set('nivel', nivel);

  apiFetch('/api/bot/logs?' + params.toString())
    .then(function (r) { return r.json(); })
    .then(function (data) {
      renderLogsTable(data.logs);
      renderLogsPaginacion(data.page, data.pages, data.total);
      document.getElementById('logsTotalText').textContent =
        data.total + ' registro' + (data.total !== 1 ? 's' : '');
    })
    .catch(function (err) {
      console.error('Error cargando logs:', err);
    });
}

function renderLogsTable(logs) {
  var tbody = document.getElementById('logsBody');
  tbody.textContent = '';

  if (!logs || logs.length === 0) {
    var tr = document.createElement('tr');
    var td = document.createElement('td');
    td.setAttribute('colspan', '6');
    td.className = 'text-center text-muted py-4';
    td.textContent = 'No hay logs registrados';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  logs.forEach(function (log) {
    var tr = document.createElement('tr');

    // Fecha
    var tdFecha = document.createElement('td');
    tdFecha.className = 'small';
    tdFecha.textContent = formatearFechaLog(log.created_at);
    tr.appendChild(tdFecha);

    // Nivel badge
    var tdNivel = document.createElement('td');
    var badge = document.createElement('span');
    badge.className = 'badge ' + badgeClassNivel(log.nivel);
    badge.textContent = log.nivel;
    tdNivel.appendChild(badge);
    tr.appendChild(tdNivel);

    // Tool
    var tdTool = document.createElement('td');
    if (log.tool_name) {
      var code = document.createElement('code');
      code.className = 'small';
      code.textContent = log.tool_name;
      tdTool.appendChild(code);
    }
    tr.appendChild(tdTool);

    // Mensaje
    var tdMsg = document.createElement('td');
    var msgSpan = document.createElement('span');
    msgSpan.className = 'small';
    msgSpan.textContent = log.mensaje;
    tdMsg.appendChild(msgSpan);
    if (log.detalle) {
      var detBtn = document.createElement('button');
      detBtn.className = 'btn btn-link btn-sm p-0 ms-1';
      detBtn.title = 'Ver detalle';
      var detIcon = document.createElement('i');
      detIcon.className = 'bi bi-chevron-down';
      detBtn.appendChild(detIcon);
      detBtn.addEventListener('click', function () {
        toggleDetalle(tr, log.detalle);
      });
      tdMsg.appendChild(detBtn);
    }
    tr.appendChild(tdMsg);

    // Telefono
    var tdTel = document.createElement('td');
    tdTel.className = 'small font-monospace';
    tdTel.textContent = log.numero_telefono || '';
    tr.appendChild(tdTel);

    // Acciones
    var tdAcc = document.createElement('td');
    var delBtn = document.createElement('button');
    delBtn.className = 'btn btn-sm btn-outline-danger';
    delBtn.title = 'Eliminar';
    var delIcon = document.createElement('i');
    delIcon.className = 'bi bi-trash';
    delBtn.appendChild(delIcon);
    delBtn.addEventListener('click', function () {
      eliminarLogBot(log.id);
    });
    tdAcc.appendChild(delBtn);
    tr.appendChild(tdAcc);

    tbody.appendChild(tr);
  });
}

function toggleDetalle(tr, detalle) {
  var next = tr.nextElementSibling;
  if (next && next.classList.contains('log-detalle-row')) {
    next.remove();
    return;
  }
  var detRow = document.createElement('tr');
  detRow.className = 'log-detalle-row';
  var detTd = document.createElement('td');
  detTd.setAttribute('colspan', '6');
  detTd.className = 'bg-light small py-2 px-3';
  var pre = document.createElement('pre');
  pre.className = 'mb-0 text-wrap';
  pre.style.fontSize = '.8rem';
  pre.textContent = detalle;
  detTd.appendChild(pre);
  detRow.appendChild(detTd);
  tr.parentNode.insertBefore(detRow, tr.nextSibling);
}

function renderLogsPaginacion(page, pages, total) {
  var container = document.getElementById('logsPaginacion');
  container.textContent = '';
  if (pages <= 1) return;

  var nav = document.createElement('nav');
  var ul = document.createElement('ul');
  ul.className = 'pagination pagination-sm mb-0';

  // Previous
  var liPrev = document.createElement('li');
  liPrev.className = 'page-item' + (page <= 1 ? ' disabled' : '');
  var aPrev = document.createElement('a');
  aPrev.className = 'page-link';
  aPrev.href = '#';
  aPrev.textContent = '\u2039';
  aPrev.addEventListener('click', function (e) {
    e.preventDefault();
    if (page > 1) cargarLogsBotTab(page - 1);
  });
  liPrev.appendChild(aPrev);
  ul.appendChild(liPrev);

  // Pages
  var start = Math.max(1, page - 2);
  var end = Math.min(pages, page + 2);
  for (var i = start; i <= end; i++) {
    (function (p) {
      var li = document.createElement('li');
      li.className = 'page-item' + (p === page ? ' active' : '');
      var a = document.createElement('a');
      a.className = 'page-link';
      a.href = '#';
      a.textContent = p;
      a.addEventListener('click', function (e) {
        e.preventDefault();
        cargarLogsBotTab(p);
      });
      li.appendChild(a);
      ul.appendChild(li);
    })(i);
  }

  // Next
  var liNext = document.createElement('li');
  liNext.className = 'page-item' + (page >= pages ? ' disabled' : '');
  var aNext = document.createElement('a');
  aNext.className = 'page-link';
  aNext.href = '#';
  aNext.textContent = '\u203A';
  aNext.addEventListener('click', function (e) {
    e.preventDefault();
    if (page < pages) cargarLogsBotTab(page + 1);
  });
  liNext.appendChild(aNext);
  ul.appendChild(liNext);

  nav.appendChild(ul);
  container.appendChild(nav);
}

function eliminarLogBot(id) {
  if (!confirm('Eliminar este log?')) return;
  apiFetch('/api/bot/logs/' + id, { method: 'DELETE' })
    .then(function () { cargarLogsBotTab(); })
    .catch(function (err) { console.error('Error eliminando log:', err); });
}

function limpiarLogsBot() {
  if (!confirm('Eliminar TODOS los logs del bot?')) return;
  apiFetch('/api/bot/logs/clear', { method: 'DELETE' })
    .then(function () {
      cargarLogsBotTab(1);
      actualizarBadgeLogs();
    })
    .catch(function (err) { console.error('Error limpiando logs:', err); });
}

function actualizarBadgeLogs() {
  apiFetch('/api/bot/logs?' + new URLSearchParams({ page: 1, per_page: 1, nivel: 'error' }))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var badge = document.getElementById('logsCountBadge');
      if (data.total > 0) {
        badge.textContent = data.total > 99 ? '99+' : data.total;
        badge.classList.remove('d-none');
      } else {
        badge.classList.add('d-none');
      }
    })
    .catch(function () {});
}

function badgeClassNivel(nivel) {
  switch (nivel) {
    case 'error':   return 'bg-danger';
    case 'warning': return 'bg-warning text-dark';
    case 'info':    return 'bg-info text-dark';
    default:        return 'bg-secondary';
  }
}

function formatearFechaLog(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  var pad = function (n) { return n < 10 ? '0' + n : n; };
  return (
    pad(d.getDate()) + '/' + pad(d.getMonth() + 1) + '/' + d.getFullYear() +
    ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())
  );
}

// Load error count badge on page load
document.addEventListener('DOMContentLoaded', function () {
  actualizarBadgeLogs();
});
