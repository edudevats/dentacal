(function exposeEDR(root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.EDR = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function buildEDR(root) {
  function formatMoney(value) {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency', currency: 'MXN', minimumFractionDigits: 2
    }).format(Number(value || 0));
  }

  function currentMonth(now = new Date()) {
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }

  function today(now = new Date()) {
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }

  async function apiJson(url, options = {}) {
    const fetcher = typeof root.apiFetch === 'function'
      ? root.apiFetch
      : (typeof apiFetch === 'function' ? apiFetch : null);
    if (!fetcher) throw new Error('No está disponible el cliente de la aplicación.');
    const response = await fetcher(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.mensaje || data.error || 'No se pudo completar la operación.');
      error.fields = data.fields || {};
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function setText(id, value) {
    const element = root.document?.getElementById(id);
    if (element) element.textContent = value;
  }

  function entriesFromForm(form) {
    if (typeof root.FormData === 'function' && form?.tagName) {
      return new root.FormData(form).entries();
    }
    return form.elements.entries();
  }

  function formPayload(form, { nullableIds = [], requiredIds = [] } = {}) {
    const payload = {};
    for (const [key, rawValue] of entriesFromForm(form)) {
      const value = typeof rawValue === 'string' ? rawValue.trim() : rawValue;
      if (nullableIds.includes(key)) payload[key] = value === '' ? null : Number(value);
      else if (requiredIds.includes(key)) payload[key] = Number(value);
      else payload[key] = value;
    }
    return payload;
  }

  function clearFieldErrors(form) {
    form.querySelectorAll('.edr-field-error').forEach((node) => node.remove());
    form.querySelectorAll('.is-invalid').forEach((node) => node.classList.remove('is-invalid'));
  }

  function showFieldErrors(form, fields = {}) {
    clearFieldErrors(form);
    Object.entries(fields).forEach(([name, message]) => {
      const input = form.elements.namedItem(name);
      if (!input) return;
      input.classList.add('is-invalid');
      const error = root.document.createElement('div');
      error.className = 'invalid-feedback edr-field-error';
      error.textContent = message;
      input.insertAdjacentElement('afterend', error);
    });
  }

  function fillSelect(select, items, { placeholder = 'Selecciona', label = 'nombre' } = {}) {
    select.replaceChildren();
    const empty = root.document.createElement('option');
    empty.value = '';
    empty.textContent = placeholder;
    select.appendChild(empty);
    items.forEach((item) => {
      const option = root.document.createElement('option');
      option.value = String(item.id);
      option.textContent = item[label] || item.nombre || '';
      select.appendChild(option);
    });
  }

  return {
    apiJson, clearFieldErrors, currentMonth, fillSelect, formPayload,
    formatMoney, setText, showFieldErrors, today
  };
}));
