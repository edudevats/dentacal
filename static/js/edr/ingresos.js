(function () {
  const {
    apiJson, clearFieldErrors, currentMonth, fillSelect, formPayload,
    formatMoney, showFieldErrors, today
  } = window.EDR;
  const month = document.getElementById('edr-month');
  const form = document.getElementById('income-form');
  const modal = bootstrap.Modal.getOrCreateInstance('#income-modal');
  const rows = document.getElementById('income-rows');
  const patientResults = document.getElementById('income-patient-results');
  const appointmentResults = document.getElementById('income-appointment-results');
  let catalogs = null;
  let editingId = null;

  function appendCell(row, value, className = '') {
    const cell = document.createElement('td');
    cell.className = className;
    cell.textContent = value ?? '';
    row.appendChild(cell);
  }

  function setFormValue(name, value) {
    const input = form.elements.namedItem(name);
    if (input) input.value = value ?? '';
  }

  function openCreate() {
    editingId = null;
    form.reset();
    clearFieldErrors(form);
    patientResults.replaceChildren();
    appointmentResults.replaceChildren();
    setFormValue('fecha', today());
    setFormValue('comision_bancaria', '0.00');
    setFormValue('comision_doctor', '0.00');
    setFormValue('descuento_pct', '0.00');
    document.getElementById('income-modal-title').textContent = 'Nuevo ingreso';
  }

  function openEdit(item) {
    openCreate();
    editingId = item.id;
    document.getElementById('income-modal-title').textContent = 'Editar ingreso';
    [
      'fecha', 'cita_id', 'paciente_id', 'paciente_nombre',
      'nombre_tratamiento', 'dentista_id', 'tipo_cita_id',
      'metodo_pago_id', 'monto', 'comision_bancaria',
      'comision_doctor', 'descuento_pct', 'comentarios'
    ].forEach((name) => setFormValue(name, item[name]));
    modal.show();
  }

  async function cancelIncome(id) {
    if (!window.confirm('¿Anular este ingreso? El registro seguirá en auditoría.')) return;
    try {
      await apiJson(`/api/edr/ingresos/${id}`, { method: 'DELETE' });
      showToast('Ingreso anulado correctamente.');
      await loadIncomes();
    } catch (error) {
      showToast(error.message, 'danger');
    }
  }

  function renderRows(items) {
    rows.replaceChildren();
    items.forEach((item) => {
      const row = document.createElement('tr');
      appendCell(row, item.fecha);
      appendCell(row, item.paciente_nombre);
      appendCell(row, item.nombre_tratamiento);
      appendCell(row, formatMoney(item.monto), 'text-end');
      const actions = document.createElement('td');
      actions.className = 'text-nowrap';
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'btn btn-sm btn-outline-primary me-2';
      edit.textContent = 'Editar';
      edit.addEventListener('click', () => openEdit(item));
      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'btn btn-sm btn-outline-danger';
      cancel.textContent = 'Anular';
      cancel.addEventListener('click', () => cancelIncome(item.id));
      actions.append(edit, cancel);
      row.appendChild(actions);
      rows.appendChild(row);
    });
    document.getElementById('income-empty').hidden = items.length > 0;
  }

  async function loadIncomes() {
    try {
      renderRows(await apiJson(`/api/edr/ingresos?mes=${encodeURIComponent(month.value)}`));
    } catch (error) {
      showToast(error.message, 'danger');
    }
  }

  async function loadCatalogs() {
    catalogs = await apiJson('/api/edr/catalogos');
    fillSelect(form.elements.namedItem('dentista_id'), catalogs.dentistas, { placeholder: 'Sin dentista' });
    fillSelect(form.elements.namedItem('tipo_cita_id'), catalogs.tipos_cita, { placeholder: 'Sin tipo' });
    fillSelect(form.elements.namedItem('metodo_pago_id'), catalogs.metodos_pago, { placeholder: 'Método de pago' });
  }

  function renderChoices(container, items, onSelect, label) {
    container.replaceChildren();
    items.forEach((item) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'list-group-item list-group-item-action';
      button.textContent = label(item);
      button.addEventListener('click', () => {
        onSelect(item);
        container.replaceChildren();
      });
      container.appendChild(button);
    });
  }

  async function searchPatients(event) {
    const query = event.target.value.trim();
    if (query.length < 2) return patientResults.replaceChildren();
    try {
      const items = await apiJson(`/api/edr/pacientes?q=${encodeURIComponent(query)}`);
      renderChoices(patientResults, items, (item) => {
        setFormValue('paciente_id', item.id);
        setFormValue('paciente_nombre', item.nombre);
      }, (item) => item.nombre);
    } catch (error) { showToast(error.message, 'danger'); }
  }

  async function searchAppointments(event) {
    const query = event.target.value.trim();
    if (query.length < 2) return appointmentResults.replaceChildren();
    try {
      const items = await apiJson(`/api/edr/citas?mes=${encodeURIComponent(month.value)}&q=${encodeURIComponent(query)}`);
      renderChoices(appointmentResults, items, (item) => {
        setFormValue('cita_id', item.id);
        setFormValue('paciente_id', item.paciente_id);
        setFormValue('paciente_nombre', item.paciente_nombre);
        setFormValue('dentista_id', item.dentista_id);
        setFormValue('tipo_cita_id', item.tipo_cita_id);
        setFormValue('nombre_tratamiento', item.nombre_tratamiento);
        if (item.monto) setFormValue('monto', item.monto);
      }, (item) => `${item.fecha} · ${item.paciente_nombre} · ${item.nombre_tratamiento}`);
    } catch (error) { showToast(error.message, 'danger'); }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFieldErrors(form);
    const payload = formPayload(form, {
      nullableIds: ['cita_id', 'paciente_id', 'dentista_id', 'tipo_cita_id'],
      requiredIds: ['metodo_pago_id'],
    });
    try {
      await apiJson(editingId ? `/api/edr/ingresos/${editingId}` : '/api/edr/ingresos', {
        method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload)
      });
      modal.hide();
      showToast(editingId ? 'Ingreso actualizado.' : 'Ingreso registrado.');
      await loadIncomes();
    } catch (error) {
      showFieldErrors(form, error.fields);
      showToast(error.message, 'danger');
    }
  });

  document.getElementById('income-new').addEventListener('click', () => {
    openCreate();
    modal.show();
  });
  document.getElementById('income-patient-search').addEventListener('input', searchPatients);
  document.getElementById('income-appointment-search').addEventListener('input', searchAppointments);
  month.value = currentMonth();
  month.addEventListener('change', loadIncomes);
  Promise.all([loadCatalogs(), loadIncomes()]).catch((error) => showToast(error.message, 'danger'));
}());
