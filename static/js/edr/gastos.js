(function () {
  const {
    apiJson, clearFieldErrors, currentMonth, fillSelect, formPayload,
    formatMoney, setText, showFieldErrors, today
  } = window.EDR;
  const month = document.getElementById('edr-month');
  const form = document.getElementById('expense-form');
  const modal = bootstrap.Modal.getOrCreateInstance('#expense-modal');
  const rows = document.getElementById('expense-rows');
  let editingId = null;

  function setValue(name, value) { form.elements.namedItem(name).value = value ?? ''; }
  function appendCell(row, value, className = '') {
    const cell = document.createElement('td');
    cell.className = className;
    cell.textContent = value ?? '';
    row.appendChild(cell);
  }
  function openCreate() {
    editingId = null;
    form.reset();
    clearFieldErrors(form);
    setValue('fecha', today());
    document.getElementById('expense-modal-title').textContent = 'Nuevo gasto';
  }
  function openEdit(item) {
    openCreate();
    editingId = item.id;
    document.getElementById('expense-modal-title').textContent = 'Editar gasto';
    ['fecha', 'concepto_id', 'concepto_nombre', 'tipo', 'monto', 'comentarios']
      .forEach((name) => setValue(name, item[name]));
    modal.show();
  }
  function updateTotals(items) {
    const fixed = items.filter((item) => item.tipo === 'fijo').reduce((sum, item) => sum + Number(item.monto), 0);
    const variable = items.filter((item) => item.tipo === 'variable').reduce((sum, item) => sum + Number(item.monto), 0);
    setText('expense-fixed-total', formatMoney(fixed));
    setText('expense-variable-total', formatMoney(variable));
    setText('expense-total', formatMoney(fixed + variable));
  }
  async function cancelExpense(id) {
    if (!window.confirm('¿Anular este gasto?')) return;
    try {
      await apiJson(`/api/edr/gastos/${id}`, { method: 'DELETE' });
      showToast('Gasto anulado.');
      await loadExpenses();
    } catch (error) { showToast(error.message, 'danger'); }
  }
  function render(items) {
    rows.replaceChildren();
    items.forEach((item) => {
      const row = document.createElement('tr');
      appendCell(row, item.fecha);
      appendCell(row, item.concepto_nombre);
      appendCell(row, item.tipo === 'fijo' ? 'Fijo' : 'Variable');
      appendCell(row, formatMoney(item.monto), 'text-end');
      const actions = document.createElement('td');
      const edit = document.createElement('button');
      edit.type = 'button'; edit.className = 'btn btn-sm btn-outline-primary me-2'; edit.textContent = 'Editar';
      edit.addEventListener('click', () => openEdit(item));
      const cancel = document.createElement('button');
      cancel.type = 'button'; cancel.className = 'btn btn-sm btn-outline-danger'; cancel.textContent = 'Anular';
      cancel.addEventListener('click', () => cancelExpense(item.id));
      actions.append(edit, cancel); row.appendChild(actions); rows.appendChild(row);
    });
    document.getElementById('expense-empty').hidden = items.length > 0;
    updateTotals(items);
  }
  async function loadExpenses() {
    try { render(await apiJson(`/api/edr/gastos?mes=${encodeURIComponent(month.value)}`)); }
    catch (error) { showToast(error.message, 'danger'); }
  }
  form.elements.namedItem('concepto_id').addEventListener('change', (event) => {
    const selected = event.target.selectedOptions[0];
    if (event.target.value && selected) {
      setValue('concepto_nombre', selected.dataset.nombre);
      setValue('tipo', selected.dataset.tipo);
    }
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); clearFieldErrors(form);
    const payload = formPayload(form, { nullableIds: ['concepto_id'] });
    try {
      await apiJson(editingId ? `/api/edr/gastos/${editingId}` : '/api/edr/gastos', {
        method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload)
      });
      modal.hide(); showToast(editingId ? 'Gasto actualizado.' : 'Gasto registrado.'); await loadExpenses();
    } catch (error) { showFieldErrors(form, error.fields); showToast(error.message, 'danger'); }
  });
  async function init() {
    month.value = currentMonth();
    const catalogs = await apiJson('/api/edr/catalogos');
    const select = form.elements.namedItem('concepto_id');
    fillSelect(select, catalogs.gastos_conceptos, { placeholder: 'Concepto libre' });
    catalogs.gastos_conceptos.forEach((item, index) => {
      select.options[index + 1].dataset.nombre = item.nombre;
      select.options[index + 1].dataset.tipo = item.tipo_default;
    });
    await loadExpenses();
  }
  document.getElementById('expense-new').addEventListener('click', () => {
    openCreate();
    modal.show();
  });
  month.addEventListener('change', loadExpenses);
  init().catch((error) => showToast(error.message, 'danger'));
}());
