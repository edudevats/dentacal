# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database with sample data (run once)
python init_db.py

# Run development server (http://localhost:5000)
python app.py
```

## Architecture

Flask app using the application factory pattern (`create_app()` in `app.py`). All routes live in a single Blueprint called `main` (`routes.py`). Database is SQLite via SQLAlchemy. Google Calendar integration is isolated in `calendar_service.py`.

**Request flow for scheduling:**
1. Frontend (`static/js/main.js`) uses FullCalendar v5 to display a doctor's busy blocks
2. `GET /api/eventos_doctor/<id>` → `obtener_disponibilidad()` → Google FreeBusy API → returns busy blocks
3. `GET /api/horarios_disponibles/<id>?fecha&duracion` → `calcular_slots_disponibles()` → computes free slots from busy blocks and doctor's working hours
4. `POST /api/agendar` → `agendar_cita()` → creates Google Calendar event, invites doctor, sets reminders

**Google Calendar auth:** Service Account only (no user OAuth). Credentials loaded from `credentials.json` in the project root. Upload via `/settings` page. The service account must be granted access to each doctor's calendar.

**Timezone:** All datetime operations use `America/Mexico_City` via `pytz`. FreeBusy API returns UTC (with `Z` suffix); `calcular_slots_disponibles()` converts to local time before comparison.

## Key Files

| File | Purpose |
|---|---|
| `calendar_service.py` | All Google Calendar logic: `get_calendar_service()`, `obtener_disponibilidad()`, `calcular_slots_disponibles()`, `agendar_cita()` |
| `routes.py` | Flask Blueprint `main` — all HTTP endpoints |
| `models.py` | `Doctor` (id, nombre, email, google_calendar_id, hora_inicio_trabajo, hora_fin_trabajo) and `SystemSettings` (clinic_name, admin_calendar_id) |
| `static/js/main.js` | FullCalendar init, slots panel logic (`cargarSlots`, `renderizarSlots`, `buscarProximaDisponibilidad`), booking modal |
| `templates/dashboard.html` | 3-column grid: sidebar (doctors) \| calendar \| slots panel |

## Data Model Notes

- `Doctor.google_calendar_id`: the calendar ID that the service account has read access to (used for FreeBusy queries)
- `SystemSettings.admin_calendar_id`: the calendar where events are *created* (the clinic's own calendar); doctors are added as attendees
- There is no `Appointment` model — all appointment data lives in Google Calendar

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/eventos_doctor/<id>?start&end` | Busy blocks for FullCalendar (red events) |
| `GET /api/horarios_disponibles/<id>?fecha=YYYY-MM-DD&duracion=60` | Computed free/busy slots. Valid durations: 15, 30, 45, 60, 90, 120 |
| `GET /api/proxima_disponibilidad/<id>?duracion&dias` | Next available day within N days (skips weekends) |
| `POST /api/agendar` | Create appointment. Body: `{doctor_id, paciente_info, inicio, fin, tipo_consulta?, telefono?, notas?}` |

## Frontend Conventions

- `openModal(start, end)` is a global function — both FullCalendar `select` and slot buttons call it with ISO strings
- After a successful booking, call `doctorCalendar.refetchEvents()` and `cargarSlots(currentDoctorId)` to refresh both views
- Clicking a date header in FullCalendar triggers `navLinkDayClick` → updates `#slots-fecha` and reloads the slots panel
- CSS variables: `--primary` (#0ea5e9), `--secondary` (#10b981 — used for available slots), `--danger` (#ef4444)
