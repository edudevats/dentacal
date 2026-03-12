"""
Bot IA Recepcionista - La Casa del Sr. Perez
Usa google-genai SDK con Gemini y function calling para gestionar citas via WhatsApp.
"""
import json
import logging
from datetime import datetime, timedelta
from flask import current_app

logger = logging.getLogger(__name__)

MAX_HISTORIAL = 15  # mensajes de contexto en memoria

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
                "escuela": {"type": "string", "description": "Nombre de la escuela si es menor"},
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
        "description": "Busca horarios disponibles para una cita en una fecha especifica.",
        "parameters": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD"
                },
                "dentista_id": {
                    "type": "integer",
                    "description": "ID del dentista especifico (opcional)"
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
        "description": "Marca el anticipo como pagado para una cita pendiente.",
        "parameters": {
            "type": "object",
            "properties": {
                "cita_id": {"type": "integer", "description": "ID de la cita"},
                "monto": {"type": "number", "description": "Monto recibido"}
            },
            "required": ["cita_id"]
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
]


def _get_system_prompt():
    config = _get_config()
    return f"""Eres la recepcionista virtual de {config['nombre_consultorio']}, un consultorio dental pediatrico y de adultos ubicado en {config['direccion']}.

PERSONALIDAD: Amable, profesional, con lenguaje calido y uso de emojis apropiados. Siempre en Espanol.

SERVICIOS Y PRECIOS:
- Primera Consulta: ${config['precio_primera_consulta']} (incluye diagnostico, plan de tratamiento, presupuesto y radiografias intraorales)
- Limpieza y Fluor, Ortodoncia, Operatoria, Revision, Extraccion, Endodoncia, Sonrisas Magicas

PROTOCOLO DE CITAS - PRIMERA VEZ:
1. Saluda y presenta el consultorio
2. Cuando el paciente pregunte por informacion, responde: "La consulta tiene un costo de ${config['precio_primera_consulta']} le incluye su diagnostico, plan de tratamiento, presupuesto y radiografias intraorales que requiera su pequeno o pequena :)"
3. Si acepta y quiere cita, usa buscar_disponibilidad para ofrecer opciones
4. Una vez que el paciente confirme el horario, explica: "Para garantizar su cita solicitamos un pago anticipado del {config['porcentaje_anticipo']}% ($275.00). En caso de no poder acudir les pedimos reagendar con 24hrs de anticipacion, si no acuden no sera reembolsable."
5. Comparte datos bancarios:
   BBVA - {config['titular_cuenta']}
   Tarjeta: {config['tarjeta']}
   CLABE: {config['clabe']}
6. Cuando confirmen el pago, crea la cita con crear_solicitud_cita y confirma: "Nos vemos el dia [fecha] de [hora_inicio] a las [hora_fin]"

PROTOCOLO RECORDATORIO DE CONFIRMACION (cuando el paciente responde al recordatorio de 24h):
- Si confirma: actualiza el status de la cita

REGLAS IMPORTANTES:
- SIEMPRE usar buscar_paciente al inicio para saber si es paciente nuevo o recurrente
- Si el paciente es nuevo, usar registrar_paciente con sus datos
- NUNCA inventar disponibilidad, siempre usar buscar_disponibilidad
- NUNCA crear cita sin confirmar horario y anticipo (para primera vez)
- Si hay dudas tecnicas, decir: "Permita que transfiera su consulta a nuestra recepcionista, estare con usted en un momento."
- Manejar cancelaciones con empatia, recordar politica de 24h
- Horario del consultorio: {config['horario_apertura']} - {config['horario_cierre']}

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


def _cargar_historial(numero):
    """Carga ultimos mensajes de la conversacion para dar contexto al bot."""
    from models import ConversacionWhatsapp
    mensajes = ConversacionWhatsapp.query.filter_by(numero_telefono=numero)\
        .order_by(ConversacionWhatsapp.timestamp.desc())\
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
    model_name = current_app.config.get('AI_MODEL', 'gemini-3-flash-preview')

    if not api_key or api_key.startswith('test') or api_key.startswith('AIzaSy'):
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
        contexto_paciente = f'\n[CONTEXTO: Paciente identificado: {paciente.nombre_completo}, ID={paciente.id}, estatus={paciente.estatus_crm.value}]'

    system_prompt = _get_system_prompt() + contexto_paciente

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
                        result = _ejecutar_tool(nombre, arg_dict)
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
        return 'Lo siento, no pude procesar tu solicitud. Por favor contacta al consultorio directamente.'

    return 'Lo siento, no pude procesar tu solicitud. Por favor contacta al consultorio directamente.'



def _ejecutar_tool(nombre, args):
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
        else:
            return {'error': f'Tool desconocida: {nombre}'}
    except Exception as e:
        logger.error(f'Error ejecutando tool {nombre}: {e}')
        return {'error': str(e)}


def _tool_buscar_paciente(args):
    from models import Paciente
    from extensions import db
    numero = args.get('numero_whatsapp', '')
    numero_limpio = numero.replace('+', '').replace(' ', '')
    paciente = Paciente.query.filter(
        db.or_(
            Paciente.whatsapp == numero,
            Paciente.whatsapp == f'+{numero_limpio}',
        ),
        Paciente.eliminado == False
    ).first()

    if paciente:
        from models import Cita, EstatusCita
        ultima_cita = Cita.query.filter_by(paciente_id=paciente.id)\
            .order_by(Cita.fecha_inicio.desc()).first()
        return {
            'encontrado': True,
            'paciente': paciente.to_dict(),
            'ultima_cita': ultima_cita.to_dict() if ultima_cita else None,
        }
    return {'encontrado': False}


def _tool_registrar_paciente(args):
    from models import Paciente, EstatusCRM
    from extensions import db
    p = Paciente(
        nombre=args.get('nombre', ''),
        whatsapp=args.get('numero_whatsapp', ''),
        nombre_tutor=args.get('nombre_tutor', ''),
        escuela=args.get('escuela', ''),
        estatus_crm=EstatusCRM.prospecto,
    )
    if args.get('fecha_nacimiento'):
        try:
            from datetime import datetime as dt
            p.fecha_nacimiento = dt.strptime(args['fecha_nacimiento'], '%Y-%m-%d').date()
        except ValueError:
            pass
    db.session.add(p)
    db.session.commit()
    return {'ok': True, 'paciente_id': p.id, 'nombre': p.nombre_completo}


def _tool_info_consultorio():
    config = _get_config()
    from models import TipoCita
    tipos = TipoCita.query.filter_by(activo=True).all()
    servicios = [{'nombre': t.nombre, 'precio': float(t.precio), 'duracion': t.duracion_minutos} for t in tipos]
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
        return {'disponible': False, 'mensaje': 'El consultorio no atiende domingos'}

    from services.scheduler_service import obtener_slots_disponibles
    from models import Dentista

    dentista_id = args.get('dentista_id')
    duracion = args.get('duracion_minutos', 60)

    if dentista_id:
        dentistas = [Dentista.query.get(dentista_id)]
        if not dentistas[0]:
            return {'error': 'Dentista no encontrado'}
    else:
        dentistas = Dentista.query.filter_by(activo=True).all()

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
                'slots': disponibles[:8],  # Max 8 opciones por dentista
            })

    if not todos_slots:
        return {'disponible': False, 'fecha': args['fecha'],
                'mensaje': f'No hay disponibilidad para el {fecha.strftime("%d/%m/%Y")}'}

    return {
        'disponible': True,
        'fecha': args['fecha'],
        'fecha_formato': fecha.strftime('%A %d de %B de %Y'),
        'opciones': todos_slots,
    }


def _tool_crear_cita(args):
    from models import Cita, Paciente, EstatusCRM
    from extensions import db
    from services.scheduler_service import verificar_disponibilidad

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

    cita = Cita(
        paciente_id=args['paciente_id'],
        dentista_id=args['dentista_id'],
        consultorio_id=args['consultorio_id'],
        tipo_cita_id=args.get('tipo_cita_id'),
        fecha_inicio=inicio,
        fecha_fin=fin,
        notas=args.get('notas', 'Cita creada via WhatsApp'),
    )
    db.session.add(cita)

    paciente = Paciente.query.get(args['paciente_id'])
    if paciente:
        paciente.ultima_cita = inicio
        if paciente.estatus_crm.value == 'prospecto':
            paciente.estatus_crm = EstatusCRM.activo

    db.session.commit()

    return {
        'ok': True,
        'cita_id': cita.id,
        'fecha': inicio.strftime('%d/%m/%Y'),
        'hora': inicio.strftime('%H:%M'),
        'hora_fin': fin.strftime('%H:%M'),
        'mensaje': f'Cita registrada para el {inicio.strftime("%d/%m/%Y")} a las {inicio.strftime("%H:%M")}',
    }


def _tool_confirmar_anticipo(args):
    from models import Cita
    from extensions import db
    cita = Cita.query.get(args.get('cita_id'))
    if not cita:
        return {'error': 'Cita no encontrada'}
    cita.anticipo_pagado = True
    if args.get('monto'):
        cita.anticipo_monto = args['monto']
    db.session.commit()
    return {'ok': True, 'mensaje': 'Anticipo confirmado. Su cita esta garantizada.'}


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
