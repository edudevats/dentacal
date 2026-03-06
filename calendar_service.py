import os
import datetime
import pytz
from dateutil.parser import isoparse
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    """Builds and returns the Google Calendar service using Service Account credentials."""
    creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    if os.path.exists(creds_path):
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        return service
    return None

def obtener_disponibilidad(servicio_google, calendar_id, tiempo_inicio, tiempo_fin):
    """Checks the FreeBusy API for a specific calendar ID and time range."""
    if not servicio_google:
        return []
    
    body = {
        "timeMin": tiempo_inicio.isoformat() + 'Z',
        "timeMax": tiempo_fin.isoformat() + 'Z',
        "items": [{"id": calendar_id}]
    }
    
    try:
        eventos = servicio_google.freebusy().query(body=body).execute()
        ocupado = eventos['calendars'][calendar_id]['busy']
        return ocupado
    except Exception as e:
        print(f"Error checking freebusy: {e}")
        return []

def calcular_slots_disponibles(bloques_ocupados, hora_inicio, hora_fin, fecha, duracion_minutos=30):
    """Calcula slots disponibles para una fecha dado el horario del doctor y sus bloques ocupados."""
    tz = pytz.timezone('America/Mexico_City')

    ventana_inicio = tz.localize(datetime.datetime.combine(fecha, hora_inicio))
    ventana_fin = tz.localize(datetime.datetime.combine(fecha, hora_fin))

    busy = []
    for b in bloques_ocupados:
        bs = isoparse(b['start'])
        be = isoparse(b['end'])
        if bs.tzinfo is None:
            bs = pytz.utc.localize(bs)
        if be.tzinfo is None:
            be = pytz.utc.localize(be)
        busy.append((bs, be))

    slots = []
    delta = datetime.timedelta(minutes=duracion_minutos)
    cursor = ventana_inicio

    while cursor + delta <= ventana_fin:
        slot_fin = cursor + delta
        solapamiento = any(cursor < be and slot_fin > bs for bs, be in busy)
        slots.append({
            "inicio": cursor.isoformat(),
            "fin": slot_fin.isoformat(),
            "disponible": not solapamiento
        })
        cursor += delta

    return slots


def agendar_cita(servicio_google, calendar_id_admin, doctor_email, paciente_info, inicio, fin,
                 tipo_consulta=None, telefono=None, notas=None):
    """Creates a calendar event and invites the doctor."""
    if not servicio_google:
        return None

    tipo_labels = {
        'primera_vez': '1a Vez',
        'seguimiento': 'Seguimiento',
        'cirugia': 'Cirugía',
        'urgencia': 'URGENCIA',
    }
    tipo_label = tipo_labels.get(tipo_consulta, 'Cita') if tipo_consulta else 'Cita'

    descripcion_parts = []
    if telefono:
        descripcion_parts.append(f'Tel: {telefono}')
    if notas:
        descripcion_parts.append(notas)
    descripcion = '\n'.join(descripcion_parts)

    evento = {
        'summary': f'[{tipo_label}] {paciente_info}',
        'description': descripcion,
        'start': {
            'dateTime': inicio.isoformat(),
            'timeZone': 'America/Mexico_City',
        },
        'end': {
            'dateTime': fin.isoformat(),
            'timeZone': 'America/Mexico_City',
        },
        'attendees': [
            {'email': doctor_email}
        ],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 30},
            ],
        },
    }

    try:
        evento_creado = servicio_google.events().insert(
            calendarId=calendar_id_admin, 
            body=evento,
            sendUpdates='all'
        ).execute()
        
        return evento_creado.get('htmlLink')
    except Exception as e:
        print(f"Error creating event: {e}")
        return None
