(function () {
  const { apiJson, currentMonth, formatMoney, setText } = window.EDR;
  const month = document.getElementById('edr-month');
  const breakdown = document.getElementById('edr-breakdown');

  function addBreakdown(label, value) {
    const row = document.createElement('tr');
    const name = document.createElement('th');
    const amount = document.createElement('td');
    name.scope = 'row';
    name.textContent = label;
    amount.className = 'text-end';
    amount.textContent = formatMoney(value);
    row.append(name, amount);
    breakdown.appendChild(row);
  }

  async function loadSummary() {
    try {
      const data = await apiJson(`/api/edr/resumen?mes=${encodeURIComponent(month.value)}`);
      setText('edr-ventas', formatMoney(data.pnl.ventas));
      setText('edr-utilidad-bruta', formatMoney(data.pnl.utilidad_bruta));
      setText('edr-utilidad-neta', formatMoney(data.pnl.utilidad_neta));
      setText('edr-punto-equilibrio', formatMoney(data.pnl.punto_equilibrio));
      setText('edr-margen-bruto', `${(data.pnl.pct_utilidad_bruta * 100).toFixed(2)}%`);
      setText('edr-margen-neto', `${(data.pnl.pct_utilidad * 100).toFixed(2)}%`);
      breakdown.replaceChildren();
      addBreakdown('Comisiones bancarias', data.pnl.comisiones_bancarias);
      addBreakdown('Comisiones de doctores', data.pnl.comisiones_doctores);
      addBreakdown('Gastos variables', data.pnl.gastos_variables);
      addBreakdown('Pagos adicionales a doctores', data.pnl.pagos_doctores_adicionales);
      addBreakdown('Gastos fijos', data.pnl.gastos_fijos);
      document.getElementById('edr-empty').hidden =
        Object.values(data.conteos).some((count) => count > 0);
    } catch (error) {
      showToast(error.message, 'danger');
    }
  }

  month.value = currentMonth();
  month.addEventListener('change', loadSummary);
  loadSummary();
}());
