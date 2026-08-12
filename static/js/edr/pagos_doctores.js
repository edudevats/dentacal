(function () {
  const {
    apiJson, clearFieldErrors, currentMonth, fillSelect, formPayload,
    formatMoney, showFieldErrors, today
  } = window.EDR;
  const month = document.getElementById('edr-month');
  const pendingRoot = document.getElementById('pending-commissions');
  const paymentRows = document.getElementById('payment-rows');
  const directForm = document.getElementById('direct-payment-form');
  const directModal = bootstrap.Modal.getOrCreateInstance('#direct-payment-modal');
  const settlementModal = bootstrap.Modal.getOrCreateInstance('#settlement-modal');
  let settlement = null;
  let editingId = null;

  function appendCell(row, value, className = '') {
    const cell = document.createElement('td');
    cell.className = className;
    cell.textContent = value ?? '';
    row.appendChild(cell);
  }
  function setDirectValue(name, value) {
    directForm.elements.namedItem(name).value = value ?? '';
  }
  function openDirectCreate() {
    editingId = null;
    directForm.reset();
    clearFieldErrors(directForm);
    setDirectValue('fecha', today());
    setDirectValue('descuento_saldo', '0.00');
    document.getElementById('direct-payment-modal-title').textContent = 'Registrar pago';
  }
  function openDirectEdit(item) {
    openDirectCreate();
    editingId = item.id;
    document.getElementById('direct-payment-modal-title').textContent = 'Editar pago';
    ['fecha', 'dentista_id', 'concepto', 'tipo', 'monto', 'descuento_saldo']
      .forEach((name) => setDirectValue(name, item[name]));
    directModal.show();
  }
  function selectedCommissions(group) {
    return [...group.querySelectorAll('input[data-ingreso-id]:checked')];
  }
  function openSettlement(group, doctor) {
    const selected = selectedCommissions(group);
    if (!selected.length) return showToast('Selecciona al menos una comisión.', 'warning');
    settlement = {
      dentistaId: doctor.dentista_id,
      ingresoIds: selected.map((input) => Number(input.dataset.ingresoId)),
    };
    const total = selected.reduce((sum, input) => sum + Number(input.dataset.amount), 0);
    document.getElementById('settlement-total').textContent = formatMoney(total);
    document.getElementById('settlement-date').value = today();
    settlementModal.show();
  }
  function renderPending(doctors) {
    pendingRoot.replaceChildren();
    if (!doctors.length) {
      const empty = document.createElement('p');
      empty.className = 'text-muted mb-0';
      empty.textContent = 'No hay comisiones pendientes.';
      pendingRoot.appendChild(empty);
      return;
    }
    doctors.forEach((doctor) => {
      const group = document.createElement('section');
      group.className = 'border rounded p-3 mb-3';
      const heading = document.createElement('div');
      heading.className = 'd-flex justify-content-between align-items-center gap-2 mb-2';
      const title = document.createElement('strong');
      title.textContent = `${doctor.dentista_nombre} · ${formatMoney(doctor.total_pendiente)}`;
      const selectAllLabel = document.createElement('label');
      selectAllLabel.className = 'form-check-label small';
      const selectAll = document.createElement('input');
      selectAll.type = 'checkbox'; selectAll.className = 'form-check-input me-1';
      selectAllLabel.append(selectAll, document.createTextNode('Seleccionar todas'));
      heading.append(title, selectAllLabel); group.appendChild(heading);
      doctor.comisiones.forEach((commission) => {
        const label = document.createElement('label');
        label.className = 'form-check border-top py-2 mb-0 d-block';
        const check = document.createElement('input');
        check.type = 'checkbox'; check.className = 'form-check-input me-2';
        check.dataset.ingresoId = String(commission.ingreso_id);
        check.dataset.amount = String(commission.comision_doctor);
        const text = document.createElement('span');
        text.textContent = `${commission.fecha} · ${commission.paciente_nombre} · ${commission.nombre_tratamiento} · ${formatMoney(commission.comision_doctor)}`;
        label.append(check, text); group.appendChild(label);
      });
      selectAll.addEventListener('change', () => {
        group.querySelectorAll('input[data-ingreso-id]').forEach((input) => { input.checked = selectAll.checked; });
      });
      const settle = document.createElement('button');
      settle.type = 'button'; settle.className = 'btn btn-sm btn-primary mt-3'; settle.textContent = 'Liquidar seleccionadas';
      settle.addEventListener('click', () => openSettlement(group, doctor));
      group.appendChild(settle); pendingRoot.appendChild(group);
    });
  }
  async function cancelPayment(id) {
    if (!window.confirm('¿Anular este pago? Las comisiones asociadas volverán a pendientes.')) return;
    try {
      await apiJson(`/api/edr/pagos-doctores/${id}`, { method: 'DELETE' });
      showToast('Pago anulado.'); await loadPage();
    } catch (error) { showToast(error.message, 'danger'); }
  }
  function renderPayments(items) {
    paymentRows.replaceChildren();
    items.forEach((item) => {
      const row = document.createElement('tr');
      appendCell(row, item.fecha); appendCell(row, item.dentista_nombre);
      appendCell(row, item.concepto); appendCell(row, item.tipo);
      appendCell(row, formatMoney(item.monto), 'text-end');
      const actions = document.createElement('td');
      if (item.tipo !== 'comision') {
        const edit = document.createElement('button');
        edit.type = 'button'; edit.className = 'btn btn-sm btn-outline-primary me-2'; edit.textContent = 'Editar';
        edit.addEventListener('click', () => openDirectEdit(item)); actions.appendChild(edit);
      }
      const cancel = document.createElement('button');
      cancel.type = 'button'; cancel.className = 'btn btn-sm btn-outline-danger'; cancel.textContent = 'Anular';
      cancel.addEventListener('click', () => cancelPayment(item.id)); actions.appendChild(cancel);
      row.appendChild(actions); paymentRows.appendChild(row);
    });
  }
  async function loadPage() {
    try {
      const [pending, payments] = await Promise.all([
        apiJson('/api/edr/comisiones/pendientes'),
        apiJson(`/api/edr/pagos-doctores?mes=${encodeURIComponent(month.value)}`),
      ]);
      renderPending(pending.doctores); renderPayments(payments);
    } catch (error) { showToast(error.message, 'danger'); }
  }
  document.getElementById('settlement-confirm').addEventListener('click', async () => {
    if (!settlement) return;
    try {
      const payment = await apiJson('/api/edr/comisiones/pagar', {
        method: 'POST', body: JSON.stringify({
          dentista_id: settlement.dentistaId,
          ingreso_ids: settlement.ingresoIds,
          fecha: document.getElementById('settlement-date').value,
        })
      });
      settlementModal.hide(); settlement = null;
      showToast(`Comisiones liquidadas por ${formatMoney(payment.monto)}.`);
      await loadPage();
    } catch (error) { showToast(error.message, 'danger'); }
  });
  directForm.addEventListener('submit', async (event) => {
    event.preventDefault(); clearFieldErrors(directForm);
    const payload = formPayload(directForm, { requiredIds: ['dentista_id'] });
    try {
      await apiJson(editingId ? `/api/edr/pagos-doctores/${editingId}` : '/api/edr/pagos-doctores', {
        method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload)
      });
      directModal.hide(); showToast(editingId ? 'Pago actualizado.' : 'Pago registrado.'); await loadPage();
    } catch (error) { showFieldErrors(directForm, error.fields); showToast(error.message, 'danger'); }
  });
  async function init() {
    month.value = currentMonth();
    const catalogs = await apiJson('/api/edr/catalogos');
    fillSelect(directForm.elements.namedItem('dentista_id'), catalogs.dentistas, { placeholder: 'Selecciona dentista' });
    await loadPage();
  }
  document.getElementById('direct-payment-new').addEventListener('click', () => {
    openDirectCreate();
    directModal.show();
  });
  month.addEventListener('change', loadPage);
  init().catch((error) => showToast(error.message, 'danger'));
}());
