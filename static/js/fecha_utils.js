/**
 * Utilidades de fecha/hora LOCAL para la agenda.
 *
 * IMPORTANTE: nunca usar `toISOString()` para llenar campos de fecha u hora de
 * una cita. `toISOString()` convierte a UTC y en Mexico (UTC-6) eso empuja
 * cualquier hora de las 18:00 en adelante al dia siguiente, con lo que la cita
 * se guardaba con la fecha de manana.
 *
 * El backend guarda datetimes naive (hora de pared del consultorio), asi que
 * el frontend debe mandar siempre componentes locales.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;           // node / tests
  } else {
    Object.assign(root, api);       // navegador: globales
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {

  const dosDigitos = (n) => String(n).padStart(2, '0');

  /** Date -> 'YYYY-MM-DD' usando el calendario local, no UTC. */
  function fechaLocalISO(fecha) {
    const d = new Date(fecha);
    return `${d.getFullYear()}-${dosDigitos(d.getMonth() + 1)}-${dosDigitos(d.getDate())}`;
  }

  /** Date -> 'HH:MM' en hora local. */
  function horaLocalHM(fecha) {
    const d = new Date(fecha);
    return `${dosDigitos(d.getHours())}:${dosDigitos(d.getMinutes())}`;
  }

  /** Date -> 'YYYY-MM-DDTHH:MM:SS' local, sin zona: lo que espera el backend. */
  function fechaHoraLocalISO(fecha) {
    const d = new Date(fecha);
    return `${fechaLocalISO(d)}T${horaLocalHM(d)}:${dosDigitos(d.getSeconds())}`;
  }

  return { fechaLocalISO, horaLocalHM, fechaHoraLocalISO };
});
