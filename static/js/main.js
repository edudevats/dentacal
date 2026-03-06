document.addEventListener('DOMContentLoaded', function () {

    const doctorCalendarEl = document.getElementById('doctor-calendar');
    const placeholderMsg = document.getElementById('placeholder-msg');
    const calendarHeader = document.getElementById('calendar-header');
    const calendarTitle = document.getElementById('calendar-title');
    const slotsSidebar = document.getElementById('slots-sidebar');
    const slotsLista = document.getElementById('slots-list');
    const slotsSummary = document.getElementById('slots-summary');
    const slotsLoading = document.getElementById('slots-loading');
    const proximaResult = document.getElementById('proxima-result');

    let doctorCalendar;
    let currentDoctorId = null;

    // Direct initialization if on doctor_view (fallback)
    if (doctorCalendarEl && doctorCalendarEl.dataset.doctorId) {
        initCalendar(doctorCalendarEl.dataset.doctorId);
    }

    // Setup listeners for dashboard buttons
    const loadButtons = document.querySelectorAll('.load-calendar-btn');
    loadButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const doctorId = this.dataset.doctorId;
            const doctorName = this.dataset.doctorName;

            currentDoctorId = doctorId;

            // Update UI
            if (placeholderMsg) placeholderMsg.style.display = 'none';
            if (calendarHeader) {
                calendarHeader.style.display = 'block';
                calendarTitle.textContent = `Calendario: ${doctorName}`;
            }

            document.getElementById('doctor-id').value = doctorId;

            // Reset active state of buttons
            loadButtons.forEach(b => {
                b.classList.remove('btn-primary');
                b.classList.add('btn-outline');
            });
            this.classList.remove('btn-outline');
            this.classList.add('btn-primary');

            initCalendar(doctorId);
        });
    });

    function initCalendar(doctorId) {
        if (doctorCalendar) {
            doctorCalendar.destroy();
        }

        doctorCalendar = new FullCalendar.Calendar(doctorCalendarEl, {
            initialView: 'timeGridWeek',
            slotMinTime: '08:00:00',
            slotMaxTime: '20:00:00',
            allDaySlot: false,
            selectable: true,
            selectMirror: true,
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'timeGridWeek,timeGridDay'
            },
            events: `/api/eventos_doctor/${doctorId}`,
            navLinks: true,

            navLinkDayClick: function (date, jsEvent) {
                jsEvent.preventDefault();
                const fechaStr = date.toISOString().split('T')[0];
                const fechaInput = document.getElementById('slots-fecha');
                if (fechaInput) {
                    fechaInput.value = fechaStr;
                    cargarSlots(doctorId);
                }
            },

            select: function (info) {
                openModal(info.startStr, info.endStr);
                doctorCalendar.unselect();
            },

            dateClick: function (info) {
                const fechaInput = document.getElementById('slots-fecha');
                if (fechaInput) {
                    fechaInput.value = info.dateStr;
                    cargarSlots(doctorId);
                }
            },

            eventClick: function (info) {
                if (info.event.title === 'Ocupado') {
                    alert('Este horario ya está ocupado.');
                }
            }
        });

        doctorCalendar.render();
        initSlotsPanel(doctorId);
    }

    // ===== PANEL DE SLOTS DISPONIBLES =====

    function initSlotsPanel(doctorId) {
        if (!slotsSidebar) return;
        slotsSidebar.style.display = 'flex';

        const fechaInput = document.getElementById('slots-fecha');
        if (fechaInput && !fechaInput.value) {
            const hoy = new Date();
            fechaInput.value = hoy.toISOString().split('T')[0];
        }

        cargarSlots(doctorId);
    }

    function cargarSlots(doctorId) {
        if (!slotsSidebar || !doctorId) return;

        const fecha = document.getElementById('slots-fecha').value;
        const duracion = document.getElementById('slots-duracion').value;

        if (!fecha) return;

        // Mostrar loading
        slotsLoading.style.display = 'block';
        slotsLista.innerHTML = '';
        slotsSummary.style.display = 'none';
        proximaResult.style.display = 'none';

        fetch(`/api/horarios_disponibles/${doctorId}?fecha=${fecha}&duracion=${duracion}`)
            .then(r => r.json())
            .then(data => {
                slotsLoading.style.display = 'none';
                if (data.slots) {
                    renderizarSlots(data.slots, doctorId);
                } else {
                    slotsLista.innerHTML = '<p style="color:var(--danger);font-size:0.85rem;">Error al cargar horarios.</p>';
                }
            })
            .catch(() => {
                slotsLoading.style.display = 'none';
                slotsLista.innerHTML = '<p style="color:var(--danger);font-size:0.85rem;">Error de conexión.</p>';
            });
    }

    function renderizarSlots(slots, doctorId) {
        slotsLista.innerHTML = '';

        const numDisponibles = slots.filter(s => s.disponible).length;
        slotsSummary.style.display = 'block';
        slotsSummary.innerHTML = `<span class="count-available">${numDisponibles}</span> de ${slots.length} slots disponibles`;

        if (slots.length === 0) {
            slotsLista.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;text-align:center;padding:1rem 0;">Sin horarios para este día.</p>';
            return;
        }

        slots.forEach(slot => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `slot-btn ${slot.disponible ? 'disponible' : 'ocupado'}`;

            const inicio = formatHora(slot.inicio);
            const fin = formatHora(slot.fin);
            const indicador = slot.disponible ? '✓' : '✗';

            btn.innerHTML = `<span class="slot-indicator">${indicador}</span> ${inicio} – ${fin}`;

            if (slot.disponible) {
                btn.addEventListener('click', () => openModal(slot.inicio, slot.fin));
            } else {
                btn.disabled = true;
            }

            slotsLista.appendChild(btn);
        });
    }

    function buscarProximaDisponibilidad(doctorId) {
        if (!doctorId) return;

        const duracion = document.getElementById('slots-duracion').value;
        const btnProxima = document.getElementById('btn-proxima');

        btnProxima.disabled = true;
        btnProxima.textContent = 'Buscando...';
        proximaResult.style.display = 'none';

        fetch(`/api/proxima_disponibilidad/${doctorId}?duracion=${duracion}`)
            .then(r => r.json())
            .then(data => {
                proximaResult.style.display = 'block';

                if (data.encontrado) {
                    const horaSlot = formatHora(data.primer_slot.inicio);
                    proximaResult.innerHTML = `
                        <div class="proxima-result-box">
                            <strong>Próxima disponibilidad</strong>
                            ${formatFecha(data.fecha)} a las ${horaSlot}
                            <br><small>${data.total_disponibles} slots disponibles ese día</small>
                            <br><button type="button" class="btn btn-outline btn-sm" id="btn-ver-dia"
                                style="margin-top:0.5rem;">Ver ese día</button>
                        </div>`;
                    document.getElementById('btn-ver-dia').addEventListener('click', () => {
                        document.getElementById('slots-fecha').value = data.fecha;
                        cargarSlots(doctorId);
                    });
                } else {
                    proximaResult.innerHTML = `
                        <div class="proxima-result-box not-found">
                            <strong>Sin disponibilidad</strong>
                            No se encontró disponibilidad en los próximos 7 días.
                        </div>`;
                }
            })
            .catch(() => {
                proximaResult.style.display = 'block';
                proximaResult.innerHTML = '<p style="color:var(--danger);font-size:0.85rem;">Error de conexión.</p>';
            })
            .finally(() => {
                btnProxima.disabled = false;
                btnProxima.textContent = 'Próxima disponibilidad →';
            });
    }

    function formatHora(isoString) {
        return new Date(isoString).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false });
    }

    function formatFecha(fechaStr) {
        const [y, m, d] = fechaStr.split('-');
        const fecha = new Date(y, m - 1, d);
        return fecha.toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' });
    }

    // Event listeners del panel de slots
    const btnBuscar = document.getElementById('btn-buscar-slots');
    if (btnBuscar) {
        btnBuscar.addEventListener('click', () => {
            if (currentDoctorId) cargarSlots(currentDoctorId);
        });
    }

    const slotsDuracion = document.getElementById('slots-duracion');
    if (slotsDuracion) {
        slotsDuracion.addEventListener('change', () => {
            if (currentDoctorId) cargarSlots(currentDoctorId);
        });
    }

    const slotsFecha = document.getElementById('slots-fecha');
    if (slotsFecha) {
        slotsFecha.addEventListener('change', () => {
            if (currentDoctorId) cargarSlots(currentDoctorId);
        });
    }

    const btnProxima = document.getElementById('btn-proxima');
    if (btnProxima) {
        btnProxima.addEventListener('click', () => {
            if (currentDoctorId) buscarProximaDisponibilidad(currentDoctorId);
        });
    }

    // Modal Logic
    const modal = document.getElementById('booking-modal');
    if (modal) {
        const closeBtn = document.querySelector('.close-btn');
        const form = document.getElementById('booking-form');
        const startInput = document.getElementById('event-start');
        const endInput = document.getElementById('event-end');
        const timeSlotLabel = document.getElementById('modal-time-slot');
        const msgDiv = document.getElementById('form-msg');
        const submitBtn = document.getElementById('submit-btn');

        window.openModal = function (start, end) {
            startInput.value = start;
            endInput.value = end;

            const startDate = new Date(start);
            const endDate = new Date(end);

            timeSlotLabel.textContent = `${startDate.toLocaleString('es-MX')} - ${endDate.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false })}`;
            msgDiv.textContent = '';
            msgDiv.className = 'msg';
            form.reset();

            modal.style.display = 'flex';
        };

        closeBtn.onclick = function () {
            modal.style.display = 'none';
        }

        window.onclick = function (event) {
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        }

        form.addEventListener('submit', async function (e) {
            e.preventDefault();

            const doctorId = document.getElementById('doctor-id').value;
            const pacienteInfo = document.getElementById('paciente-info').value;
            const inicio = startInput.value;
            const fin = endInput.value;
            const tipoConsulta = document.getElementById('tipo-consulta').value;
            const telefono = document.getElementById('paciente-telefono').value || null;
            const notas = document.getElementById('notas').value || null;

            submitBtn.disabled = true;
            submitBtn.textContent = 'Agendando...';

            try {
                const response = await fetch('/api/agendar', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        doctor_id: doctorId,
                        paciente_info: pacienteInfo,
                        inicio: inicio,
                        fin: fin,
                        tipo_consulta: tipoConsulta,
                        telefono: telefono,
                        notas: notas
                    })
                });

                const data = await response.json();

                if (data.success) {
                    msgDiv.textContent = 'Cita agendada con éxito!';
                    msgDiv.className = 'msg success';

                    if (doctorCalendar) {
                        doctorCalendar.refetchEvents();
                    }

                    // Refrescar los slots disponibles tras agendar
                    if (currentDoctorId) {
                        setTimeout(() => cargarSlots(currentDoctorId), 500);
                    }

                    setTimeout(() => {
                        modal.style.display = 'none';
                    }, 2000);
                } else {
                    msgDiv.textContent = 'Error: ' + data.error;
                    msgDiv.className = 'msg error';
                }
            } catch (error) {
                msgDiv.textContent = 'Error de conexión.';
                msgDiv.className = 'msg error';
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Confirmar Cita';
            }
        });
    }
});
