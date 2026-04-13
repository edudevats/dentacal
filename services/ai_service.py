"""
Bot IA Recepcionista - La Casa del Sr. Perez
Usa google-genai SDK con Gemini y function calling para gestionar citas via WhatsApp.
"""
import json
import logging
import traceback
from datetime import datetime, timedelta
from flask import current_app

logger = logging.getLogger(__name__)

MAX_HISTORIAL = 15  # mensajes de contexto en memoria


def _guardar_log_bot(nivel, mensaje, detalle=None, numero_telefono=None, paciente_id=None, tool_name=None):
    """Guarda un log del bot en la BD para consulta desde la app."""
    try:
        from models import LogBot
        from extensions import db
        log = LogBot(
            nivel=nivel,
            mensaje=mensaje[:500],
            detalle=detalle[:2000] if detalle else None,
            numero_telefono=numero_telefono,
            paciente_id=paciente_id,
            tool_name=tool_name,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        # No fallar si el log mismo falla
        pass

# Definicion de tools (function declarations) del bot para el nuevo SDK
BOT_FUNCTION_DECLARATIONS = [
    {
        "name": "buscar_paciente",
        "description": "Busca un paciente existente por numero de WhatsApp. Usar siempre al inicio de la conversacion.",
        "parameters": {
            "type": "object",
            "properties": {
                "numero_whatsapp": {
                    "type": "string",
                    "description": "Numero de WhatsApp del paciente en formato +52XXXXXXXXXX"
                }
            },
            "required": ["numero_whatsapp"]
        }
    },
    {
        "name": "registrar_paciente",
        "description": "Registra un nuevo paciente en el sistema. Usar cuando el paciente no existe.",
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre completo del paciente"},
                "fecha_nacimiento": {"type": "string", "description": "Fecha nacimiento YYYY-MM-DD (opcional)"},
                "nombre_tutor": {"type": "string", "description": "Nombre del padre/madre/tutor si es menor"},
                "numero_whatsapp": {"type": "string", "description": "Numero de WhatsApp"}
            },
            "required": ["nombre", "numero_whatsapp"]
        }
    },
    {
        "name": "obtener_info_consultorio",
        "description": "Obtiene informacion del consultorio: ubicacion, precios, horarios, datos bancarios.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "buscar_disponibilidad",
        "description": "Busca horarios disponibles para una cita en una fecha especifica. Si se pasa paciente_id, filtra automaticamente por el doctor asignado al paciente Y verifica compatibilidad nino/adulto. Si se indica hora_preferida y no esta disponible, devuelve la alternativa mas cercana.",
        "parameters": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD"
                },
                "paciente_id": {
                    "type": "integer",
                    "description": "ID del paciente. Si se proporciona, el sistema buscara SOLO con el doctor asignado y filtrara segun si el paciente es nino o adulto."
                },
                "hora_preferida": {
                    "type": "string",
                    "description": "Hora preferida del paciente en formato HH:MM (ej: 10:00). Si se proporciona y no esta disponible, el sistema sugerira la alternativa mas cercana."
                },
                "dentista_id": {
                    "type": "integer",
                    "description": "ID del dentista especifico (opcional, se autodetecta si se pasa paciente_id)"
                },
                "duracion_minutos": {
                    "type": "integer",
                    "description": "Duracion de la cita en minutos (default 60)"
                }
            },
            "required": ["fecha"]
        }
    },
    {
        "name": "crear_solicitud_cita",
        "description": "Crea una cita pendiente en el sistema. Usar solo cuando el paciente confirme el horario.",
        "parameters": {
            "type": "object",
            "properties": {
                "paciente_id": {"type": "integer", "description": "ID del paciente"},
                "dentista_id": {"type": "integer", "description": "ID del dentista"},
                "consultorio_id": {"type": "integer", "description": "ID del consultorio"},
                "tipo_cita_id": {"type": "integer", "description": "ID del tipo de cita"},
                "fecha_inicio": {"type": "string", "description": "Fecha y hora inicio ISO 8601"},
                "fecha_fin": {"type": "string", "description": "Fecha y hora fin ISO 8601"},
                "notas": {"type": "string", "description": "Notas adicionales"}
            },
            "required": ["paciente_id", "dentista_id", "consultorio_id", "fecha_inicio", "fecha_fin"]
        }
    },
    {
        "name": "confirmar_anticipo",
        "description": "Confirma el pago del anticipo para una pre-cita. Acepta cita_id O paciente_id (busca automaticamente la pre-cita activa del paciente). Usar cuando el paciente dice que ya pago/deposito/transfirio el anticipo.",
        "parameters": {
            "type": "object",
            "properties": {
                "cita_id": {"type": "integer", "description": "ID de la cita (opcional si se pasa paciente_id)"},
                "paciente_id": {"type": "integer", "description": "ID del paciente (busca su pre-cita activa automaticamente)"},
                "monto": {"type": "number", "description": "Monto recibido (opcional)"}
            },
            "required": []
        }
    },
    {
        "name": "cancelar_cita",
        "description": "Cancela una cita del paciente.",
        "parameters": {
            "type": "object",
            "properties": {
                "cita_id": {"type": "integer", "description": "ID de la cita a cancelar"},
                "motivo": {"type": "string", "description": "Motivo de cancelacion"}
            },
            "required": ["cita_id"]
        }
    },
    {
        "name": "reagendar_cita",
        "description": "Reagenda (cambia fecha/hora) de una cita existente.",
        "parameters": {
            "type": "object",
            "properties": {
                "cita_id": {"type": "integer", "description": "ID de la cita a reagendar"},
                "nueva_fecha_inicio": {"type": "string", "description": "Nueva fecha inicio ISO 8601"},
                "nueva_fecha_fin": {"type": "string", "description": "Nueva fecha fin ISO 8601"},
                "nuevo_consultorio_id": {"type": "integer", "description": "Nuevo consultorio (opcional)"}
            },
            "required": ["cita_id", "nueva_fecha_inicio", "nueva_fecha_fin"]
        }
    },
    {
        "name": "confirmar_asistencia_cita",
        "description": "Confirma que el paciente asistira a su cita proxima. Usar cuando el paciente responde al recordatorio de 24h indicando que si asistira (ej: 'si', 'confirmo', 'ahi estaremos').",
        "parameters": {
            "type": "object",
            "properties": {
                "paciente_id": {"type": "integer", "description": "ID del paciente que confirma"},
                "cita_id": {"type": "integer", "description": "ID de la cita a confirmar (opcional, si no se da busca la proxima)"}
            },
            "required": ["paciente_id"]
        }
    },
    {
        "name": "registrar_solicitud_contacto",
        "description": "Registra la solicitud de un paciente NUEVO (no registrado en el sistema) que desea que la recepcionista le llame para darlo de alta. Usar SOLO cuando el numero del contacto no esta en la BD.",
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre completo de la persona"},
                "numero_whatsapp": {"type": "string", "description": "Numero de WhatsApp del contacto"},
                "fecha_preferida": {"type": "string", "description": "Fecha u horario preferido para recibir la llamada (texto libre, ej: 'lunes en la manana', '14 de abril')"},
                "hora_preferida": {"type": "string", "description": "Hora preferida para la llamada, formato HH:MM (opcional)"},
                "notas": {"type": "string", "description": "Notas adicionales: motivo de consulta, tipo de tratamiento, nombre del paciente si es para un familiar, etc."}
            },
            "required": ["nombre", "numero_whatsapp"]
        }
    },
]


def _get_doctor_schedule_summary():
    """Genera resumen de horarios de doctores activos y ausencias proximas."""
    from models import Dentista, HorarioDentista, BloqueoDentista
    dias_nombres = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab', 'Dom']

    dentistas = Dentista.query.filter_by(activo=True).order_by(Dentista.nombre).all()
    lineas = []

    for d in dentistas:
        horarios_activos = {h.dia_semana: h for h in d.horarios if h.activo}
        if not horarios_activos:
            lineas.append(f"- {d.nombre} (ID:{d.id}): Sin horario configurado")
            continue

        dias_str = ', '.join(
            f"{dias_nombres[dia]} {h.hora_inicio.strftime('%H:%M')}-{h.hora_fin.strftime('%H:%M')}"
            for dia, h in sorted(horarios_activos.items())
        )

        ahora = datetime.utcnow()
        limite = ahora + timedelta(days=30)
        bloqueos = BloqueoDentista.query.filter(
            BloqueoDentista.dentista_id == d.id,
            BloqueoDentista.fecha_fin > ahora,
            BloqueoDentista.fecha_inicio < limite,
        ).all()

        bloqueo_str = ''
        if bloqueos:
            bloqueos_info = [
                f"{b.fecha_inicio.strftime('%d/%m')}-{b.fecha_fin.strftime('%d/%m')} ({b.motivo or 'ausencia'})"
                for b in bloqueos
            ]
            bloqueo_str = f" | AUSENCIAS: {'; '.join(bloqueos_info)}"

        # Info de que tipo de pacientes atiende
        atiende_tags = []
        if d.atiende_ninos:
            atiende_tags.append('niños')
        if d.atiende_adultos:
            atiende_tags.append('adultos')
        atiende_str = f" | Atiende: {' y '.join(atiende_tags)}" if atiende_tags else " | SIN TIPO DE PACIENTE CONFIGURADO"

        lineas.append(f"- {d.nombre} (ID:{d.id}): {dias_str}{atiende_str}{bloqueo_str}")

    return '\n'.join(lineas)


def _get_system_prompt(numero_whatsapp=None):
    config = _get_config()

    # Fecha/hora actual en zona horaria de Mexico
    try:
        import pytz
        tz = pytz.timezone('America/Mexico_City')
        ahora = datetime.now(tz)
    except Exception:
        ahora = datetime.now()

    dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
    meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    fecha_legible = f"{dias_semana[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]} de {ahora.year}"
    hora_legible = ahora.strftime('%H:%M')
    fecha_iso = ahora.strftime('%Y-%m-%d')
    
    # Inyectar contexto de familia si hay numero
    contexto_familia = ""
    es_paciente_nuevo = True
    if numero_whatsapp:
        from models import Paciente, Cita, EstatusCita
        variantes = _variantes_numero_mx(numero_whatsapp)
        familia = Paciente.query.filter(
            Paciente.whatsapp.in_(variantes),
            Paciente.eliminado == False
        ).all()

        if familia:
            es_paciente_nuevo = False
            info_pacientes = []
            es_problematico = False
            for p in familia:
                if p.es_problematico: es_problematico = True
                proxima = Cita.query.filter(
                    Cita.paciente_id == p.id,
                    Cita.fecha_inicio >= datetime.utcnow(),
                    Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada])
                ).order_by(Cita.fecha_inicio).first()

                # Historial: contar citas pasadas que SI se concretaron
                # (completadas o confirmadas pasadas). Esto define si el
                # paciente es RECURRENTE (no necesita anticipo) o PRIMERA VEZ.
                citas_previas = Cita.query.filter(
                    Cita.paciente_id == p.id,
                    Cita.fecha_inicio < datetime.utcnow(),
                    Cita.status.in_([EstatusCita.completada, EstatusCita.confirmada, EstatusCita.pendiente]),
                ).count()
                es_recurrente = citas_previas > 0
                historial_tag = (
                    f"RECURRENTE ({citas_previas} cita(s) previa(s) — NO requiere anticipo)"
                    if es_recurrente
                    else "PRIMERA VEZ (requiere anticipo)"
                )

                if proxima:
                    estado_pago = "(Anticipo PAGADO)" if proxima.anticipo_pagado else "(Anticipo PENDIENTE DE PAGO)"
                    str_proxima = f"Proxima cita: {proxima.fecha_inicio.strftime('%Y-%m-%d %H:%M')} {estado_pago}"
                else:
                    str_proxima = "Sin citas proximas"

                doctor_str = f"Doctor: {p.doctor.nombre}" if p.doctor_id and p.doctor else "Doctor: Sin asignar"

                # Tipo de paciente y compatibilidad con doctor
                if p.fecha_nacimiento:
                    tipo_pac = "NIÑO" if p.es_menor_edad else "ADULTO"
                else:
                    tipo_pac = "EDAD NO REGISTRADA"

                compat_str = ""
                if p.doctor_id and p.doctor and p.fecha_nacimiento:
                    doc = p.doctor
                    if p.es_menor_edad and not doc.atiende_ninos:
                        compat_str = " ⚠️ DOCTOR NO ATIENDE NIÑOS — necesita reasignacion"
                    elif not p.es_menor_edad and not doc.atiende_adultos:
                        compat_str = " ⚠️ DOCTOR NO ATIENDE ADULTOS — necesita reasignacion"

                info_pacientes.append(
                    f"- {p.nombre_completo} (ID: {p.id}) | {tipo_pac} | {historial_tag} | {doctor_str}{compat_str} | {str_proxima}"
                )

            pacientes_str = "\n".join(info_pacientes)
            multi = f" (grupo familiar de {len(familia)} personas — SIEMPRE pregunta para cual de ellas es la accion antes de proceder)" if len(familia) > 1 else ""
            contexto_familia = f"\n\nINFORMACION DEL CONTACTO ({numero_whatsapp}){multi}:\n{pacientes_str}"
            if es_problematico:
                contexto_familia += "\nALERTA IMPORTANTE: Este paciente (o alguien en su familia) esta marcado como PROBLEMATICO. NO AGENDES NINGUNA CITA por este medio. Pide amablemente que llame directamente al consultorio."
        else:
            contexto_familia = "\n\nINFORMACION DEL CONTACTO: NUMERO NUEVO — no hay pacientes registrados con este numero."

    doctor_schedule = _get_doctor_schedule_summary()

    flujo_nuevo = """
════════════════════════════════
FLUJO PARA PACIENTE NUEVO (numero no registrado)
════════════════════════════════
Este contacto NO esta registrado en nuestra base de datos. El proceso de registro requiere muchas preguntas que nuestro equipo debe hacer personalmente para brindar el mejor trato posible, por lo que NO debes registrarlo en este momento.

Tu objetivo es:
1. Presentar el consultorio con el menu de lo que podemos hacer por ellos.
2. Preguntar su nombre.
3. Preguntar en que fecha y hora prefieren que nuestra recepcionista les llame para completar su registro y agendar su primera cita.
4. Usar registrar_solicitud_contacto para guardar la solicitud con nombre, numero, fecha preferida y hora.
5. Confirmar que un miembro del equipo les contactara en ese horario.

NO uses registrar_paciente, buscar_disponibilidad, crear_solicitud_cita ni ninguna otra tool de citas con pacientes no registrados."""

    flujo_registrado = """
════════════════════════════════
FLUJO PARA PACIENTE REGISTRADO
════════════════════════════════
Este contacto SI esta registrado. Puedes ayudarle con cualquiera de estas acciones:
1️⃣  Agendar una nueva cita
2️⃣  Cancelar una cita
3️⃣  Mover/reagendar una cita a otro dia u hora
4️⃣  Consultar sus citas proximas

Si hay multiples pacientes en el grupo familiar, SIEMPRE pregunta primero para quien es la accion antes de proceder.

AGENDAMIENTO CON DOCTOR ASIGNADO:
- SIEMPRE pasa paciente_id a buscar_disponibilidad para que el sistema filtre por el doctor asignado.
- NUNCA preguntes en que consultorio quiere su cita; se asigna automaticamente.
- Usa el consultorio_id que devuelva buscar_disponibilidad al crear la cita.
- Si el horario pedido no esta libre, presenta la alternativa mas cercana que devuelva el sistema.

COMPATIBILIDAD DOCTOR-PACIENTE (niños/adultos):
- Cada doctor puede atender niños, adultos o ambos. La info aparece en DOCTORES Y HORARIOS.
- El sistema filtra automaticamente los doctores segun la edad del paciente al buscar disponibilidad.
- Si el doctor asignado al paciente NO atiende su tipo (niño/adulto), el sistema devolvera un error. En ese caso informa al paciente que su doctor no atiende ese tipo de paciente y sugiere que contacte al consultorio para que le asignen otro doctor.
- Si el paciente no tiene fecha de nacimiento registrada, no se aplica filtro.

ANTICIPOS Y PRE-CITAS (REGLA CRITICA — revisar el historial del paciente antes de pedir anticipo):
- PACIENTE RECURRENTE (tiene citas previas — historial_tag "RECURRENTE" o requiere_anticipo=false): NO pidas anticipo, NO menciones anticipo, NO compartas datos bancarios. Agenda la cita directamente con crear_solicitud_cita y confirma el horario. La cita se crea como PENDIENTE normal. Estos pacientes ya tienen historial con nosotros y no necesitan adelanto.
- PACIENTE DE PRIMERA VEZ (historial_tag "PRIMERA VEZ"): El sistema creara automaticamente una PRE-CITA que reserva el espacio en el calendario por 12 horas. Explica al paciente:
  1. "Su espacio queda reservado por 12 horas."
  2. Comparte datos bancarios para el anticipo del {porcentaje_anticipo}%:
     BBVA — {titular_cuenta} | Tarjeta: {tarjeta} | CLABE: {clabe}
  3. "Una vez que nos envie su comprobante de pago, la cita queda confirmada."
  4. Si pagan con tarjeta llamando al consultorio, la recepcionista confirma desde el sistema.
  5. Si no se paga el anticipo en 12 horas, la pre-cita se cancela automaticamente y el horario queda libre.

⚠️ CUANDO EL PACIENTE DICE QUE YA PAGO EL ANTICIPO (ej: "ya hice el deposito", "ya pague", "ya transferi"):
  - SIEMPRE usa confirmar_anticipo con el paciente_id. NUNCA vuelvas a buscar disponibilidad.
  - El sistema buscara automaticamente la pre-cita activa del paciente y la confirmara.
  - Si la recepcionista ya lo marco como pagado desde el sistema, confirmar_anticipo te lo indicara (ya_confirmado=true). En ese caso simplemente confirma al paciente que todo esta listo.
  - NUNCA intentes crear otra cita ni buscar disponibilidad de nuevo despues de que el paciente diga que pago.

- Si la cita dice "Anticipo PENDIENTE" y es de primera vez, recuerda enviarlo para garantizar el espacio.
- Si dice "Anticipo PAGADO", confirma alegremente que su cita esta 100% asegurada.
- En grupos familiares, evalua el historial de CADA paciente por separado.

CONFIRMACION 24h:
- Si el paciente responde "si"/"confirmo"/"ahi estaremos", usar confirmar_asistencia_cita.
- Si quiere cancelar o reagendar, usar cancelar_cita o reagendar_cita.""".format(
        porcentaje_anticipo=config['porcentaje_anticipo'],
        titular_cuenta=config['titular_cuenta'],
        tarjeta=config['tarjeta'],
        clabe=config['clabe'],
    )

    flujo_activo = flujo_nuevo if es_paciente_nuevo else flujo_registrado

    return f"""Eres Muelina, la recepcionista virtual de {config['nombre_consultorio']}, un consultorio dental pediatrico y de adultos ubicado en {config['direccion']}.

FECHA Y HORA ACTUAL: Hoy es {fecha_legible}, son las {hora_legible} (fecha ISO: {fecha_iso}).
Usa esta informacion para interpretar correctamente expresiones como "manana", "el proximo lunes", "esta semana", etc.{contexto_familia}

{flujo_activo}

DOCTORES Y HORARIOS:
{doctor_schedule}

PERSONALIDAD: Amable, profesional, con lenguaje calido y uso de emojis apropiados. Siempre en Espanol.

MENU DEL BOT (mostrar al inicio o cuando el paciente no sabe que puede hacer):
Hola! Soy Muelina, la recepcionista virtual de {config['nombre_consultorio']} 😊
Puedo ayudarte con:
1️⃣  Agendar una cita
2️⃣  Cancelar una cita
3️⃣  Mover tu cita a otro dia u hora
4️⃣  Consultar tus citas proximas
5️⃣  Informacion del consultorio (ubicacion, horarios, precios)

Si eres paciente nuevo, con gusto coordinamos una llamada para registrarte y darte la mejor atencion 🦷✨

SERVICIOS Y PRECIOS:
- Primera Consulta: ${config['precio_primera_consulta']} (incluye diagnostico, plan de tratamiento, presupuesto y radiografias intraorales)
- Limpieza y Fluor, Ortodoncia, Operatoria, Revision, Extraccion, Endodoncia, Sonrisas Magicas
- Horario: {config['horario_apertura']} - {config['horario_cierre']} (Lunes a Sabado)

REGLAS IMPORTANTES:
- Si el paciente esta marcado como PROBLEMATICO, NO agendar citas; pedir que llame directamente al consultorio.
- NUNCA inventar disponibilidad; siempre usar buscar_disponibilidad.
- NUNCA crear cita sin confirmar horario (y anticipo en primera vez).
- Manejar cancelaciones con empatia, recordar politica de 24h.
- Si hay dudas tecnicas: "Permita que transfiera su consulta a nuestra recepcionista."

NOTIFICACIONES DEL SISTEMA EN EL HISTORIAL:
- Mensajes que empiecen con "[NOTIFICACION AUTOMATICA DEL SISTEMA]" fueron enviados por el sistema (no por ti).
- Si ves una notificacion de "anticipo confirmado por recepcionista", significa que la recepcionista YA confirmo el pago desde el sistema.
- En ese caso, si el paciente te escribe, simplemente confirma alegremente que su cita esta asegurada. NO busques disponibilidad de nuevo ni intentes crear otra cita.

FORMATO DE RESPUESTA: Mensajes cortos y naturales para WhatsApp, usa emojis con moderacion."""


def _get_config():
    """Obtiene la configuracion del consultorio."""
    try:
        from models import ConfiguracionConsultorio
        config = ConfiguracionConsultorio.query.first()
        if config:
            return {
                'nombre_consultorio': config.nombre_consultorio,
                'direccion': config.direccion or 'Av. Claveria, CDMX',
                'precio_primera_consulta': float(config.precio_primera_consulta or 550),
                'porcentaje_anticipo': config.porcentaje_anticipo or 50,
                'clabe': config.clabe or '012180015419659725',
                'tarjeta': config.tarjeta or '4152314207155287',
                'titular_cuenta': config.titular_cuenta or 'Paulina Mendoza Ordonez',
                'horario_apertura': config.horario_apertura.strftime('%H:%M') if config.horario_apertura else '09:00',
                'horario_cierre': config.horario_cierre.strftime('%H:%M') if config.horario_cierre else '18:00',
            }
    except Exception:
        pass
    return {
        'nombre_consultorio': 'La Casa del Sr. Perez',
        'direccion': 'Av. Claveria (puerta negra lado derecho de Farmacia Similares), Azcapotzalco, CDMX',
        'precio_primera_consulta': 550,
        'porcentaje_anticipo': 50,
        'clabe': '012180015419659725',
        'tarjeta': '4152314207155287',
        'titular_cuenta': 'Paulina Mendoza Ordonez',
        'horario_apertura': '09:00',
        'horario_cierre': '18:00',
    }


SESSION_TIMEOUT_HOURS = 4  # Iniciar conversacion fresca despues de 4 horas de inactividad


def _cargar_historial(numero):
    """Carga ultimos mensajes de la conversacion dentro de la sesion activa (max 4h)."""
    from models import ConversacionWhatsapp
    corte = datetime.utcnow() - timedelta(hours=SESSION_TIMEOUT_HOURS)
    mensajes = ConversacionWhatsapp.query.filter(
        ConversacionWhatsapp.numero_telefono == numero,
        ConversacionWhatsapp.timestamp >= corte,
    ).order_by(ConversacionWhatsapp.timestamp.desc())\
        .limit(MAX_HISTORIAL).all()
    mensajes.reverse()

    historial = []
    for m in mensajes:
        rol = 'assistant' if m.es_bot else 'user'
        historial.append({'role': rol, 'content': m.mensaje})
    return historial


def procesar_mensaje_bot(mensaje_usuario, numero_telefono, paciente=None):
    """
    Procesa un mensaje entrante de WhatsApp con el bot IA.
    Usa el nuevo SDK google-genai (from google import genai).
    Retorna la respuesta en texto.
    """
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    model_name = current_app.config.get('AI_MODEL', 'gemini-3.1-flash-lite-preview')

    if not api_key or api_key.startswith('test'):
        return 'Hola! Gracias por contactarnos. En este momento el bot no esta disponible. Por favor llama al consultorio.'

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return 'Servicio no disponible temporalmente. Por favor contacta al consultorio directamente.'

    # Crear cliente con API key
    client = genai.Client(api_key=api_key)

    # Cargar historial y construir contents con el nuevo formato
    historial = _cargar_historial(numero_telefono)
    contents = []
    for msg in historial:
        role = 'model' if msg['role'] == 'assistant' else 'user'
        contents.append(
            types.Content(role=role, parts=[types.Part(text=msg['content'])])
        )

    # Contexto del paciente si ya lo tenemos
    contexto_paciente = ''
    if paciente:
        problematico_ctx = ', PROBLEMATICO=SI - NO AGENDAR CITAS' if paciente.es_problematico else ''
        contexto_paciente = f'\n[CONTEXTO: Paciente identificado que inicio chat: {paciente.nombre_completo}, ID={paciente.id}, estatus={paciente.estatus_crm.value}{problematico_ctx}]'

    system_prompt = _get_system_prompt(numero_whatsapp=numero_telefono) + contexto_paciente

    # Configurar tools y config para el nuevo SDK
    tools = types.Tool(function_declarations=BOT_FUNCTION_DECLARATIONS)
    gen_config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tools],
    )

    # Agregar el mensaje actual del usuario
    contents.append(
        types.Content(role='user', parts=[types.Part(text=mensaje_usuario)])
    )

    try:
        max_iteraciones = 5  # Evitar loops infinitos

        for _ in range(max_iteraciones):
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=gen_config,
            )

            # Verificar si hay function calls en la respuesta
            candidate = response.candidates[0]
            has_function_calls = any(
                hasattr(part, 'function_call') and part.function_call and part.function_call.name
                for part in candidate.content.parts
            )

            if has_function_calls:
                # Agregar la respuesta del modelo al historial
                contents.append(candidate.content)

                # Ejecutar las funciones y construir respuestas
                function_response_parts = []
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call and part.function_call.name:
                        func_call = part.function_call
                        nombre = func_call.name
                        arg_dict = dict(func_call.args) if func_call.args else {}
                        result = _ejecutar_tool(nombre, arg_dict, numero_telefono=numero_telefono)
                        function_response_parts.append(
                            types.Part.from_function_response(
                                name=nombre,
                                response={"result": result}
                            )
                        )

                # Agregar las respuestas de funciones al historial
                contents.append(
                    types.Content(role='user', parts=function_response_parts)
                )
            else:
                # Respuesta de texto final
                if response.text:
                    return response.text
                return 'Gracias por tu mensaje. Te atenderemos en breve.'

    except Exception as e:
        logger.error(f'Error procesando mensaje con Gemini: {e}')
        tb = traceback.format_exc()
        logger.error(f'Traceback completo:\n{tb}')
        _guardar_log_bot(
            'error', f'Error Gemini: {e}', detalle=tb,
            numero_telefono=numero_telefono,
        )
        return 'Lo siento, no pude procesar tu solicitud. Por favor contacta al consultorio directamente.'

    return 'Lo siento, no pude procesar tu solicitud. Por favor contacta al consultorio directamente.'



def _ejecutar_tool(nombre, args, numero_telefono=None):
    """Ejecuta una tool del bot y retorna el resultado."""
    try:
        if nombre == 'buscar_paciente':
            return _tool_buscar_paciente(args)
        elif nombre == 'registrar_paciente':
            return _tool_registrar_paciente(args)
        elif nombre == 'obtener_info_consultorio':
            return _tool_info_consultorio()
        elif nombre == 'buscar_disponibilidad':
            return _tool_buscar_disponibilidad(args)
        elif nombre == 'crear_solicitud_cita':
            return _tool_crear_cita(args)
        elif nombre == 'confirmar_anticipo':
            return _tool_confirmar_anticipo(args)
        elif nombre == 'cancelar_cita':
            return _tool_cancelar_cita(args)
        elif nombre == 'reagendar_cita':
            return _tool_reagendar_cita(args)
        elif nombre == 'confirmar_asistencia_cita':
            return _tool_confirmar_asistencia_cita(args)
        elif nombre == 'registrar_solicitud_contacto':
            # Forzar el numero real del contacto (no el que Gemini invente)
            if numero_telefono:
                args['numero_whatsapp'] = numero_telefono
            return _tool_registrar_solicitud_contacto(args)
        else:
            _guardar_log_bot('warning', f'Tool desconocida: {nombre}', detalle=json.dumps(args), tool_name=nombre, numero_telefono=numero_telefono)
            return {'error': f'Tool desconocida: {nombre}'}
    except Exception as e:
        logger.error(f'Error ejecutando tool {nombre}: {e}')
        _guardar_log_bot(
            'error', f'Error en tool {nombre}: {e}',
            detalle=traceback.format_exc(), tool_name=nombre,
            numero_telefono=numero_telefono,
        )
        return {'error': str(e)}


def _variantes_numero_mx(numero):
    """Genera todas las variantes posibles de un numero mexicano.
    Twilio envia +521XXXXXXXXXX pero en la BD puede estar como
    +52XXXXXXXXXX, 52XXXXXXXXXX, XXXXXXXXXX, +521XXXXXXXXXX, etc.
    """
    limpio = numero.replace('+', '').replace(' ', '').replace('-', '')
    if limpio.startswith('521') and len(limpio) == 13:
        base10 = limpio[3:]
    elif limpio.startswith('52') and len(limpio) == 12:
        base10 = limpio[2:]
    elif len(limpio) == 10:
        base10 = limpio
    else:
        return list(set([numero, f'+{limpio}', limpio]))

    return list(set([
        base10,
        f'52{base10}',
        f'+52{base10}',
        f'521{base10}',
        f'+521{base10}',
        numero,
    ]))


def _tool_buscar_paciente(args):
    from models import Paciente
    from extensions import db
    numero = args.get('numero_whatsapp', '')
    variantes = _variantes_numero_mx(numero)
    pacientes = Paciente.query.filter(
        Paciente.whatsapp.in_(variantes),
        Paciente.eliminado == False
    ).all()

    if not pacientes:
        return {'encontrado': False}

    from models import Cita, EstatusCita
    
    familia_info = []
    for paciente in pacientes:
        ultima_cita = Cita.query.filter_by(paciente_id=paciente.id)\
            .order_by(Cita.fecha_inicio.desc()).first()
        proxima_cita = Cita.query.filter(
            Cita.paciente_id == paciente.id,
            Cita.fecha_inicio >= datetime.utcnow(),
            Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
        ).order_by(Cita.fecha_inicio).first()

        # Pre-cita activa pendiente de anticipo
        pre_cita_activa = Cita.query.filter(
            Cita.paciente_id == paciente.id,
            Cita.status == EstatusCita.pre_cita,
        ).order_by(Cita.fecha_inicio.desc()).first()

        # Historial: citas previas concretadas (sin contar canceladas/no asistencias)
        citas_previas = Cita.query.filter(
            Cita.paciente_id == paciente.id,
            Cita.fecha_inicio < datetime.utcnow(),
            Cita.status.in_([EstatusCita.completada, EstatusCita.confirmada, EstatusCita.pendiente]),
        ).count()
        es_recurrente = citas_previas > 0

        # Determinar tipo de paciente para filtro de doctor
        tipo_paciente = 'niño' if paciente.es_menor_edad else ('adulto' if paciente.fecha_nacimiento else 'sin edad registrada')

        info = {
            'id': paciente.id,
            'nombre': paciente.nombre_completo,
            'es_menor': paciente.es_menor_edad,
            'tipo_paciente': tipo_paciente,
            'problema': paciente.es_problematico,
            'ultima_cita': ultima_cita.to_dict() if ultima_cita else None,
            'proxima_cita': proxima_cita.to_dict() if proxima_cita else None,
            'citas_previas': citas_previas,
            'es_recurrente': es_recurrente,
            'requiere_anticipo': not es_recurrente,
            'nota_anticipo': (
                'NO requiere anticipo (paciente recurrente con historial)'
                if es_recurrente
                else 'Requiere anticipo del 50% (primera vez)'
            ),
        }

        # Agregar info de pre-cita activa si existe
        if pre_cita_activa:
            info['pre_cita_activa'] = {
                'cita_id': pre_cita_activa.id,
                'fecha': pre_cita_activa.fecha_inicio.strftime('%d/%m/%Y'),
                'hora': pre_cita_activa.fecha_inicio.strftime('%H:%M'),
                'anticipo_pagado': pre_cita_activa.anticipo_pagado,
                'expira': pre_cita_activa.pre_cita_expira.strftime('%d/%m/%Y %H:%M') if pre_cita_activa.pre_cita_expira else None,
                'nota': 'TIENE PRE-CITA ACTIVA — si el paciente dice que ya pago, usa confirmar_anticipo con paciente_id. NO busques disponibilidad de nuevo.',
            }
        familia_info.append(info)

    result = {
        'encontrado': True,
        'mensaje': f'Se encontraron {len(pacientes)} pacientes asociados a este numero.',
        'pacientes': familia_info,
    }

    # Mantener retrocompatibilidad agregando la info del paciente principal en la raiz
    paciente_principal = pacientes[0]
    result['paciente'] = paciente_principal.to_dict()
    result['es_problematico'] = any(p['problema'] for p in familia_info)
    
    if len(pacientes) > 1:
        result['mensaje_familia'] = f'Hay {len(pacientes)} pacientes usando este numero. Revisa la lista de pacientes devuelta para ver quien tiene citas proximas y pregunta al usuario para quien es la cita o accion que desea realizar.'

    return result


def _tool_registrar_paciente(args):
    from models import Paciente, GrupoFamiliar, EstatusCRM
    from extensions import db

    numero = args.get('numero_whatsapp', '')
    variantes = _variantes_numero_mx(numero)

    # Buscar pacientes existentes con mismo numero
    existentes = Paciente.query.filter(
        Paciente.whatsapp.in_(variantes),
        Paciente.eliminado == False
    ).all()

    # Si hay existentes, crear/asignar grupo familiar automaticamente
    grupo_familiar_id = None
    if existentes:
        grupo = existentes[0].grupo_familiar
        if not grupo:
            apellido = existentes[0].nombre.split()[-1] if existentes[0].nombre else 'Sin nombre'
            grupo = GrupoFamiliar(nombre=f'Familia {apellido}', telefono_principal=numero)
            db.session.add(grupo)
            db.session.flush()
            for e in existentes:
                e.grupo_familiar_id = grupo.id
        grupo_familiar_id = grupo.id

    p = Paciente(
        nombre=args.get('nombre', ''),
        whatsapp=args.get('numero_whatsapp', ''),
        nombre_tutor=args.get('nombre_tutor', ''),
        estatus_crm=EstatusCRM.prospecto,
        grupo_familiar_id=grupo_familiar_id,
    )
    if args.get('fecha_nacimiento'):
        try:
            from datetime import datetime as dt
            p.fecha_nacimiento = dt.strptime(args['fecha_nacimiento'], '%Y-%m-%d').date()
        except ValueError:
            pass
    db.session.add(p)
    db.session.commit()
    result = {'ok': True, 'paciente_id': p.id, 'nombre': p.nombre_completo}
    if grupo_familiar_id:
        result['grupo_familiar'] = f'Agregado al grupo familiar (comparte numero con {len(existentes)} paciente(s))'
    return result


def _tool_info_consultorio():
    config = _get_config()
    from models import TipoCita, Dentista
    tipos = TipoCita.query.filter_by(activo=True).all()
    servicios = [{'nombre': t.nombre, 'precio': float(t.precio), 'duracion': t.duracion_minutos} for t in tipos]

    # Doctores agrupados por tipo de paciente
    dentistas_activos = Dentista.query.filter_by(activo=True).order_by(Dentista.nombre).all()
    doctores_ninos = [d.nombre for d in dentistas_activos if d.atiende_ninos]
    doctores_adultos = [d.nombre for d in dentistas_activos if d.atiende_adultos]

    return {
        'nombre': config['nombre_consultorio'],
        'direccion': config['direccion'],
        'horario': f"{config['horario_apertura']} - {config['horario_cierre']} (Lunes a Sabado)",
        'precio_primera_consulta': config['precio_primera_consulta'],
        'anticipo_requerido': f"{config['porcentaje_anticipo']}% para primera cita",
        'datos_bancarios': {
            'banco': 'BBVA',
            'titular': config['titular_cuenta'],
            'tarjeta': config['tarjeta'],
            'clabe': config['clabe'],
        },
        'politica_cancelacion': 'Reagendar con 24hrs de anticipacion. Sin reembolso en no asistencia.',
        'servicios': servicios,
        'doctores_que_atienden_ninos': doctores_ninos,
        'doctores_que_atienden_adultos': doctores_adultos,
    }


def _tool_buscar_disponibilidad(args):
    from datetime import datetime as dt, date as date_type
    try:
        fecha = dt.strptime(args['fecha'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        return {'error': 'Fecha invalida. Usa formato YYYY-MM-DD'}

    if fecha < date_type.today():
        return {'error': 'No se pueden buscar fechas pasadas'}

    if fecha.weekday() == 6:  # Domingo
        return {'disponible': False, 'mensaje': 'El consultorio no atiende domingos. Prueba con otro dia.'}

    from services.scheduler_service import obtener_slots_disponibles
    from models import Dentista, Paciente, BloqueoDentista, HorarioDentista

    dentista_id = args.get('dentista_id')
    duracion = args.get('duracion_minutos', 60)
    hora_preferida = args.get('hora_preferida')  # formato HH:MM
    paciente_id = args.get('paciente_id')
    doctor_asignado_info = None

    # Si hay paciente_id, filtrar por su doctor asignado
    if paciente_id and not dentista_id:
        paciente = Paciente.query.get(paciente_id)
        if paciente and paciente.doctor_id:
            dentista_id = paciente.doctor_id
            doctor_asignado_info = {
                'dentista_id': paciente.doctor_id,
                'nombre': paciente.doctor.nombre if paciente.doctor else None,
            }

    # Verificar bloqueo del doctor en esa fecha
    if dentista_id:
        fecha_inicio_dt = dt(fecha.year, fecha.month, fecha.day, 0, 0)
        fecha_fin_dt = dt(fecha.year, fecha.month, fecha.day, 23, 59, 59)
        bloqueo_activo = BloqueoDentista.query.filter(
            BloqueoDentista.dentista_id == dentista_id,
            BloqueoDentista.fecha_inicio < fecha_fin_dt,
            BloqueoDentista.fecha_fin > fecha_inicio_dt,
        ).first()
        if bloqueo_activo:
            d = Dentista.query.get(dentista_id)
            nombre = d.nombre if d else 'El doctor'
            result = {
                'disponible': False,
                'mensaje': f'{nombre} no esta disponible el {fecha.strftime("%d/%m/%Y")} por: {bloqueo_activo.motivo or "ausencia programada"}. Fecha de regreso: {bloqueo_activo.fecha_fin.strftime("%d/%m/%Y")}.',
                'motivo_ausencia': bloqueo_activo.motivo,
                'fecha_regreso': bloqueo_activo.fecha_fin.strftime('%Y-%m-%d'),
            }
            if doctor_asignado_info:
                result['doctor_asignado'] = doctor_asignado_info
            return result

        # Verificar si el doctor trabaja ese dia
        horario_dia = HorarioDentista.query.filter_by(
            dentista_id=dentista_id, dia_semana=fecha.weekday(), activo=True
        ).first()
        if not horario_dia:
            d = Dentista.query.get(dentista_id)
            nombre = d.nombre if d else 'El doctor'
            # Obtener dias que si trabaja
            dias_nombres = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
            dias_activos = HorarioDentista.query.filter_by(
                dentista_id=dentista_id, activo=True
            ).all()
            dias_str = ', '.join(dias_nombres[h.dia_semana] for h in sorted(dias_activos, key=lambda x: x.dia_semana))
            result = {
                'disponible': False,
                'mensaje': f'{nombre} no atiende los {dias_nombres[fecha.weekday()]}. Sus dias de consulta son: {dias_str}.',
                'dias_laborales': dias_str,
            }
            if doctor_asignado_info:
                result['doctor_asignado'] = doctor_asignado_info
            return result

    if dentista_id:
        dentistas = [Dentista.query.get(dentista_id)]
        if not dentistas[0]:
            return {'error': 'Dentista no encontrado'}
        # Validar que el doctor atienda al tipo de paciente
        if paciente_id:
            paciente_check = Paciente.query.get(paciente_id)
            if paciente_check and paciente_check.fecha_nacimiento:
                d = dentistas[0]
                if paciente_check.es_menor_edad and not d.atiende_ninos:
                    return {
                        'error': f'{d.nombre} no atiende niños. Consulta con la recepcionista para asignar otro doctor.',
                        'doctor_no_compatible': True,
                    }
                if not paciente_check.es_menor_edad and not d.atiende_adultos:
                    return {
                        'error': f'{d.nombre} no atiende adultos. Consulta con la recepcionista para asignar otro doctor.',
                        'doctor_no_compatible': True,
                    }
    else:
        dentistas = Dentista.query.filter_by(activo=True).all()
        # Filtrar por tipo de paciente si hay paciente_id
        if paciente_id:
            paciente_check = Paciente.query.get(paciente_id)
            if paciente_check and paciente_check.fecha_nacimiento:
                if paciente_check.es_menor_edad:
                    dentistas = [d for d in dentistas if d.atiende_ninos]
                else:
                    dentistas = [d for d in dentistas if d.atiende_adultos]

    todos_slots = []
    for dentista in dentistas:
        if not dentista:
            continue
        slots = obtener_slots_disponibles(fecha, dentista.id, duracion_minutos=duracion)
        disponibles = [s for s in slots if s['disponible']]
        if disponibles:
            todos_slots.append({
                'dentista_id': dentista.id,
                'dentista': dentista.nombre,
                'especialidad': dentista.especialidad,
                'atiende_ninos': dentista.atiende_ninos,
                'atiende_adultos': dentista.atiende_adultos,
                'slots': disponibles[:8],
            })

    # Si no hay slots en la fecha pedida, buscar alternativas en los proximos dias
    if not todos_slots:
        alternativa = _buscar_alternativa_cercana(fecha, dentistas, duracion, hora_preferida)
        result = {
            'disponible': False,
            'fecha': args['fecha'],
            'mensaje': f'No hay disponibilidad para el {fecha.strftime("%d/%m/%Y")}.',
        }
        if alternativa:
            result['alternativa_sugerida'] = alternativa
            result['mensaje'] += f' La alternativa mas cercana es el {alternativa["fecha_formato"]} a las {alternativa["slot"]["inicio"]}.'
        if doctor_asignado_info:
            result['doctor_asignado'] = doctor_asignado_info
        return result

    # Si hay hora preferida, verificar si esa hora especifica esta libre
    if hora_preferida:
        slot_exacto = None
        for opcion in todos_slots:
            for s in opcion['slots']:
                if s['inicio'] == hora_preferida:
                    slot_exacto = {
                        'dentista_id': opcion['dentista_id'],
                        'dentista': opcion['dentista'],
                        'especialidad': opcion['especialidad'],
                        'slot': s,
                    }
                    break
            if slot_exacto:
                break

        if slot_exacto:
            result = {
                'disponible': True,
                'hora_solicitada_disponible': True,
                'fecha': args['fecha'],
                'fecha_formato': fecha.strftime('%A %d de %B de %Y'),
                'horario_confirmado': slot_exacto,
                'todas_las_opciones': todos_slots,
            }
            if doctor_asignado_info:
                result['doctor_asignado'] = doctor_asignado_info
            return result
        else:
            # La hora preferida no esta disponible, buscar la mas cercana en el mismo dia
            mejor = _encontrar_slot_mas_cercano(todos_slots, hora_preferida)
            result = {
                'disponible': True,
                'hora_solicitada_disponible': False,
                'fecha': args['fecha'],
                'fecha_formato': fecha.strftime('%A %d de %B de %Y'),
                'mensaje': f'El horario de las {hora_preferida} no esta disponible.',
                'alternativa_sugerida': mejor,
                'todas_las_opciones': todos_slots,
            }
            if doctor_asignado_info:
                result['doctor_asignado'] = doctor_asignado_info
            return result

    result = {
        'disponible': True,
        'fecha': args['fecha'],
        'fecha_formato': fecha.strftime('%A %d de %B de %Y'),
        'opciones': todos_slots,
    }
    if doctor_asignado_info:
        result['doctor_asignado'] = doctor_asignado_info
    return result


def _encontrar_slot_mas_cercano(todos_slots, hora_preferida):
    """Encuentra el slot disponible mas cercano a la hora preferida."""
    try:
        h, m = map(int, hora_preferida.split(':'))
        minutos_pref = h * 60 + m
    except (ValueError, AttributeError):
        return None

    mejor = None
    menor_diff = float('inf')
    for opcion in todos_slots:
        for s in opcion['slots']:
            sh, sm = map(int, s['inicio'].split(':'))
            diff = abs((sh * 60 + sm) - minutos_pref)
            if diff < menor_diff:
                menor_diff = diff
                mejor = {
                    'dentista_id': opcion['dentista_id'],
                    'dentista': opcion['dentista'],
                    'especialidad': opcion['especialidad'],
                    'slot': s,
                }
    return mejor


def _buscar_alternativa_cercana(fecha_original, dentistas, duracion, hora_preferida=None):
    """Busca el slot disponible mas cercano en los proximos 5 dias habiles."""
    from datetime import timedelta
    from services.scheduler_service import obtener_slots_disponibles

    for i in range(1, 8):  # buscar hasta 7 dias adelante
        fecha_alt = fecha_original + timedelta(days=i)
        if fecha_alt.weekday() == 6:  # saltar domingos
            continue

        for dentista in dentistas:
            if not dentista:
                continue
            slots = obtener_slots_disponibles(fecha_alt, dentista.id, duracion_minutos=duracion)
            disponibles = [s for s in slots if s['disponible']]
            if disponibles:
                # Si hay hora preferida, buscar el mas cercano a esa hora
                if hora_preferida:
                    try:
                        h, m = map(int, hora_preferida.split(':'))
                        minutos_pref = h * 60 + m
                        disponibles.sort(key=lambda s: abs((int(s['inicio'].split(':')[0]) * 60 + int(s['inicio'].split(':')[1])) - minutos_pref))
                    except (ValueError, AttributeError):
                        pass
                return {
                    'fecha': fecha_alt.strftime('%Y-%m-%d'),
                    'fecha_formato': fecha_alt.strftime('%A %d de %B de %Y'),
                    'dentista_id': dentista.id,
                    'dentista': dentista.nombre,
                    'especialidad': dentista.especialidad,
                    'slot': disponibles[0],
                }
    return None


def _tool_crear_cita(args):
    from models import Cita, Paciente, Dentista, EstatusCita, EstatusCRM
    from extensions import db
    from services.scheduler_service import verificar_disponibilidad

    # Verificar que el paciente no sea problematico
    paciente_check = Paciente.query.get(args['paciente_id'])
    if paciente_check and paciente_check.es_problematico:
        return {'error': 'No se pueden crear citas para este paciente. Favor de contactar al consultorio directamente.'}

    # Verificar compatibilidad doctor-paciente (niño/adulto)
    if paciente_check and paciente_check.fecha_nacimiento:
        dentista = Dentista.query.get(args['dentista_id'])
        if dentista:
            if paciente_check.es_menor_edad and not dentista.atiende_ninos:
                return {
                    'error': f'{dentista.nombre} no atiende niños. Se requiere un doctor que atienda pacientes pediatricos. Contacta al consultorio para asignar otro doctor.',
                }
            if not paciente_check.es_menor_edad and not dentista.atiende_adultos:
                return {
                    'error': f'{dentista.nombre} no atiende adultos. Se requiere un doctor que atienda adultos. Contacta al consultorio para asignar otro doctor.',
                }

    try:
        inicio = datetime.fromisoformat(args['fecha_inicio'])
        fin = datetime.fromisoformat(args['fecha_fin'])
    except (ValueError, KeyError):
        return {'error': 'Fechas invalidas'}

    conflicto = verificar_disponibilidad(
        dentista_id=args['dentista_id'],
        consultorio_id=args['consultorio_id'],
        fecha_inicio=inicio,
        fecha_fin=fin,
    )
    if conflicto:
        return {'error': 'El horario ya no esta disponible. Por favor elige otro.'}

    # Determinar si el paciente es de primera vez (sin citas previas concretadas)
    paciente = Paciente.query.get(args['paciente_id'])
    citas_previas = Cita.query.filter(
        Cita.paciente_id == args['paciente_id'],
        Cita.fecha_inicio < datetime.utcnow(),
        Cita.status.in_([EstatusCita.completada, EstatusCita.confirmada, EstatusCita.pendiente]),
    ).count()
    es_primera_vez = citas_previas == 0

    # Primera vez → pre_cita (reserva 12h); recurrente → pendiente directa
    if es_primera_vez:
        status_cita = EstatusCita.pre_cita
        expira = datetime.utcnow() + timedelta(hours=12)
        notas_default = 'Pre-cita via WhatsApp (reserva 12h — pendiente de anticipo)'
    else:
        status_cita = EstatusCita.pendiente
        expira = None
        notas_default = 'Cita creada via WhatsApp'

    cita = Cita(
        paciente_id=args['paciente_id'],
        dentista_id=args['dentista_id'],
        consultorio_id=args['consultorio_id'],
        tipo_cita_id=args.get('tipo_cita_id'),
        fecha_inicio=inicio,
        fecha_fin=fin,
        status=status_cita,
        pre_cita_expira=expira,
        notas=args.get('notas', notas_default),
    )
    db.session.add(cita)

    if paciente:
        paciente.ultima_cita = inicio
        if paciente.estatus_crm.value == 'prospecto':
            paciente.estatus_crm = EstatusCRM.activo

    db.session.commit()

    if es_primera_vez:
        return {
            'ok': True,
            'cita_id': cita.id,
            'es_pre_cita': True,
            'fecha': inicio.strftime('%d/%m/%Y'),
            'hora': inicio.strftime('%H:%M'),
            'hora_fin': fin.strftime('%H:%M'),
            'expira': expira.strftime('%d/%m/%Y %H:%M'),
            'mensaje': (
                f'Pre-cita registrada para el {inicio.strftime("%d/%m/%Y")} a las {inicio.strftime("%H:%M")}. '
                f'El espacio queda reservado por 12 horas. '
                f'Una vez que envies el comprobante de anticipo, la cita queda confirmada.'
            ),
        }
    else:
        return {
            'ok': True,
            'cita_id': cita.id,
            'es_pre_cita': False,
            'fecha': inicio.strftime('%d/%m/%Y'),
            'hora': inicio.strftime('%H:%M'),
            'hora_fin': fin.strftime('%H:%M'),
            'mensaje': f'Cita registrada para el {inicio.strftime("%d/%m/%Y")} a las {inicio.strftime("%H:%M")}',
        }


def _tool_confirmar_anticipo(args):
    from models import Cita, EstatusCita
    from extensions import db

    cita = None
    cita_id = args.get('cita_id')
    paciente_id = args.get('paciente_id')

    if cita_id:
        cita = Cita.query.get(int(cita_id))
    elif paciente_id:
        pid = int(paciente_id)
        # Buscar pre-cita activa del paciente
        cita = Cita.query.filter(
            Cita.paciente_id == pid,
            Cita.status == EstatusCita.pre_cita,
        ).order_by(Cita.fecha_inicio.desc()).first()
        # Si no hay pre-cita, buscar pendiente sin anticipo
        if not cita:
            cita = Cita.query.filter(
                Cita.paciente_id == pid,
                Cita.status == EstatusCita.pendiente,
                Cita.anticipo_pagado == False,
                Cita.fecha_inicio >= datetime.utcnow(),
            ).order_by(Cita.fecha_inicio).first()
        # Si tampoco, buscar si ya tiene una cita futura con anticipo pagado (ya confirmada)
        if not cita:
            cita_ya_pagada = Cita.query.filter(
                Cita.paciente_id == pid,
                Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
                Cita.anticipo_pagado == True,
                Cita.fecha_inicio >= datetime.utcnow(),
            ).order_by(Cita.fecha_inicio).first()
            if cita_ya_pagada:
                return {
                    'ok': True,
                    'ya_confirmado': True,
                    'cita_id': cita_ya_pagada.id,
                    'fecha': cita_ya_pagada.fecha_inicio.strftime('%d/%m/%Y'),
                    'hora': cita_ya_pagada.fecha_inicio.strftime('%H:%M'),
                    'mensaje': f'El anticipo ya fue confirmado previamente. La cita del {cita_ya_pagada.fecha_inicio.strftime("%d/%m/%Y")} a las {cita_ya_pagada.fecha_inicio.strftime("%H:%M")} esta asegurada.',
                }

    if not cita:
        return {'error': 'No se encontro una pre-cita o cita pendiente de anticipo para este paciente.'}

    # Si el anticipo ya fue marcado como pagado (por cita_id directo)
    if cita.anticipo_pagado:
        return {
            'ok': True,
            'ya_confirmado': True,
            'cita_id': cita.id,
            'fecha': cita.fecha_inicio.strftime('%d/%m/%Y'),
            'hora': cita.fecha_inicio.strftime('%H:%M'),
            'mensaje': f'El anticipo ya fue confirmado previamente. La cita del {cita.fecha_inicio.strftime("%d/%m/%Y")} a las {cita.fecha_inicio.strftime("%H:%M")} esta asegurada.',
        }

    cita.anticipo_pagado = True
    if args.get('monto'):
        cita.anticipo_monto = args['monto']
    # Si era pre-cita, promover a pendiente
    if cita.status == EstatusCita.pre_cita:
        cita.status = EstatusCita.pendiente
        cita.pre_cita_expira = None
    db.session.commit()
    return {
        'ok': True,
        'cita_id': cita.id,
        'fecha': cita.fecha_inicio.strftime('%d/%m/%Y'),
        'hora': cita.fecha_inicio.strftime('%H:%M'),
        'mensaje': f'Anticipo confirmado. La cita del {cita.fecha_inicio.strftime("%d/%m/%Y")} a las {cita.fecha_inicio.strftime("%H:%M")} esta garantizada.',
    }


def _tool_cancelar_cita(args):
    from models import Cita, EstatusCita
    from extensions import db
    cita = Cita.query.get(args.get('cita_id'))
    if not cita:
        return {'error': 'Cita no encontrada'}
    cita.status = EstatusCita.cancelada
    if args.get('motivo'):
        cita.notas = (cita.notas or '') + f' | Cancelada: {args["motivo"]}'
    db.session.commit()
    return {'ok': True, 'mensaje': 'Cita cancelada. Recuerda que para reagendar puedes escribirnos cuando gustes.'}


def _tool_reagendar_cita(args):
    from models import Cita, EstatusCita
    from extensions import db
    from services.scheduler_service import verificar_disponibilidad

    cita = Cita.query.get(args.get('cita_id'))
    if not cita:
        return {'error': 'Cita no encontrada'}

    if cita.paciente and cita.paciente.es_problematico:
        return {'error': 'No se puede reagendar. Favor de contactar al consultorio directamente.'}

    try:
        nueva_inicio = datetime.fromisoformat(args['nueva_fecha_inicio'])
        nueva_fin = datetime.fromisoformat(args['nueva_fecha_fin'])
    except (ValueError, KeyError):
        return {'error': 'Fechas invalidas'}

    consultorio_id = args.get('nuevo_consultorio_id', cita.consultorio_id)
    conflicto = verificar_disponibilidad(
        dentista_id=cita.dentista_id,
        consultorio_id=consultorio_id,
        fecha_inicio=nueva_inicio,
        fecha_fin=nueva_fin,
        ignorar_cita_id=cita.id,
    )
    if conflicto:
        return {'error': 'El nuevo horario no esta disponible. Por favor elige otro.'}

    cita.fecha_inicio = nueva_inicio
    cita.fecha_fin = nueva_fin
    cita.consultorio_id = consultorio_id
    cita.status = EstatusCita.pendiente
    cita.reminder_24h_sent = False
    db.session.commit()

    return {
        'ok': True,
        'cita_id': cita.id,
        'nueva_fecha': nueva_inicio.strftime('%d/%m/%Y'),
        'nueva_hora': nueva_inicio.strftime('%H:%M'),
        'mensaje': f'Cita reagendada para el {nueva_inicio.strftime("%d/%m/%Y")} a las {nueva_inicio.strftime("%H:%M")}.',
    }


def _tool_confirmar_asistencia_cita(args):
    """Confirma la asistencia del paciente a su proxima cita."""
    from models import Cita, EstatusCita
    from extensions import db

    cita_id = args.get('cita_id')
    paciente_id = args.get('paciente_id')

    if cita_id:
        cita = Cita.query.get(cita_id)
    elif paciente_id:
        # Buscar la proxima cita pendiente o confirmada del paciente
        cita = Cita.query.filter(
            Cita.paciente_id == paciente_id,
            Cita.fecha_inicio >= datetime.utcnow() - timedelta(hours=1),
            Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
        ).order_by(Cita.fecha_inicio).first()
    else:
        return {'error': 'Se requiere cita_id o paciente_id'}

    if not cita:
        return {'error': 'No se encontro cita proxima para este paciente'}

    if cita.status == EstatusCita.confirmada:
        return {
            'ok': True,
            'mensaje': 'La cita ya estaba confirmada.',
            'cita_id': cita.id,
            'fecha': cita.fecha_inicio.strftime('%d/%m/%Y'),
            'hora': cita.fecha_inicio.strftime('%H:%M'),
        }

    cita.status = EstatusCita.confirmada
    cita.confirmacion_fecha = datetime.utcnow()
    db.session.commit()

    return {
        'ok': True,
        'cita_id': cita.id,
        'fecha': cita.fecha_inicio.strftime('%d/%m/%Y'),
        'hora': cita.fecha_inicio.strftime('%H:%M'),
        'mensaje': f'Cita confirmada para el {cita.fecha_inicio.strftime("%d/%m/%Y")} a las {cita.fecha_inicio.strftime("%H:%M")}.',
    }


def _tool_registrar_solicitud_contacto(args):
    """Guarda la solicitud de un paciente nuevo para ser contactado por la recepcionista."""
    from models import SolicitudRegistro
    from extensions import db

    nombre = (args.get('nombre') or '').strip()
    numero = (args.get('numero_whatsapp') or '').strip()

    if not nombre or not numero:
        return {'error': 'Se requiere nombre y numero_whatsapp'}

    solicitud = SolicitudRegistro(
        nombre=nombre,
        numero_whatsapp=numero,
        fecha_preferida=args.get('fecha_preferida', ''),
        hora_preferida=args.get('hora_preferida', ''),
        notas=args.get('notas', ''),
    )
    db.session.add(solicitud)
    db.session.commit()

    return {
        'ok': True,
        'solicitud_id': solicitud.id,
        'mensaje': (
            f'Solicitud registrada para {nombre}. '
            'Un miembro de nuestro equipo se pondra en contacto contigo para completar tu registro.'
        ),
    }
