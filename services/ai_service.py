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
        "description": "Busca horarios disponibles para una cita en una fecha especifica. Si se indica hora_preferida y no esta disponible, devuelve la alternativa mas cercana en el mismo dia y en los siguientes dias.",
        "parameters": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD"
                },
                "hora_preferida": {
                    "type": "string",
                    "description": "Hora preferida del paciente en formato HH:MM (ej: 10:00). Si se proporciona y no esta disponible, el sistema sugerira la alternativa mas cercana."
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
]


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
    if numero_whatsapp:
        from models import Paciente, Cita, EstatusCita
        variantes = _variantes_numero_mx(numero_whatsapp)
        familia = Paciente.query.filter(
            Paciente.whatsapp.in_(variantes),
            Paciente.eliminado == False
        ).all()
        
        if familia:
            info_pacientes = []
            es_problematico = False
            for p in familia:
                if p.es_problematico: es_problematico = True
                proxima = Cita.query.filter(
                    Cita.paciente_id == p.id,
                    Cita.fecha_inicio >= datetime.utcnow(),
                    Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada])
                ).order_by(Cita.fecha_inicio).first()
                
                if proxima:
                    estado_pago = "(Anticipo PAGADO)" if proxima.anticipo_pagado else "(Anticipo PENDIENTE DE PAGO)"
                    str_proxima = f"Proxima cita: {proxima.fecha_inicio.strftime('%Y-%m-%d %H:%M')} {estado_pago}"
                else:
                    str_proxima = "Sin citas proximas"
                    
                info_pacientes.append(f"- {p.nombre_completo} (ID: {p.id}) | {str_proxima}")
            
            pacientes_str = "\n".join(info_pacientes)
            contexto_familia = f"\n\nINFORMACION DEL CONTACTO ({numero_whatsapp}):\nTiene {len(familia)} paciente(s) registrado(s):\n{pacientes_str}"
            if es_problematico:
                contexto_familia += "\nALERTA IMPORTANTE: Este paciente (o alguien en su familia) esta marcado como PROBLEMATICO. NO AGENDES NINGUNA CITA por este medio. Pide amablemente que llame directamente al consultorio."
        else:
            contexto_familia = "\n\nINFORMACION DEL CONTACTO: Numero nuevo, no hay pacientes registrados todavia."

    return f"""Eres la recepcionista virtual de {config['nombre_consultorio']}, un consultorio dental pediatrico y de adultos ubicado en {config['direccion']}.

FECHA Y HORA ACTUAL: Hoy es {fecha_legible}, son las {hora_legible} (fecha ISO: {fecha_iso}).
Usa esta informacion para interpretar correctamente expresiones como "manana", "el proximo lunes", "esta semana", etc.{contexto_familia}

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

MANEJO DE ANTICIPOS Y PAGOS:
- Al ver el perfil del paciente suministrado al inicio, revisa el estado de su proxima cita.
- Si dice "(Anticipo PENDIENTE DE PAGO)", recuerda amablemente que es necesario enviar el comprobante de pago con 24 hrs de anticipacion para garantizar el espacio. Si lo solicitan, proporcionales los datos bancarios nuevamente.
- Si dice "(Anticipo PAGADO)", confirma al paciente alegremente que su cita esta 100% confirmada y asegurada.

MANEJO DE FAMILIAS Y MULTIPLES PACIENTES:
- Es muy comun que un padre/madre use su mismo numero de WhatsApp para agendar citas de varios hijos.
- Al usar buscar_paciente, el sistema te devolvera TODOS los pacientes asociados a ese numero, junto con las proximas citas de CADA UNO.
- Si ves multiples pacientes en la respuesta, SIEMPRE pregunta amablemente para que miembro de la familia es la cita o consulta que desean realizar (ej: "Veo que tengo registrados a Juanito y a Pedrito, para quien seria la cita?").
- Usa el paciente_id correcto de ese miembro especifico al agendar o buscar historial.
- Si el padre/madre pregunta si tienen cita, revisa las proximas citas de TODOS los pacientes listados bajo ese numero.

AGENDAMIENTO AUTOMATICO DE CONSULTORIO Y SUGERENCIAS:
- NUNCA preguntes al paciente en que consultorio quiere su cita. El consultorio se asigna automaticamente segun disponibilidad.
- Cuando el paciente pregunte que horarios tienen disponibles un dia especifico, usa buscar_disponibilidad con esa fecha y muestrale TODOS los horarios libres que devuelva el sistema.
- Si el paciente pide un horario especifico, usa buscar_disponibilidad con la fecha y hora_preferida. Si el horario solicitado NO esta disponible, el sistema te devolvera automaticamente la alternativa mas cercana. Presentala de forma profesional, por ejemplo: "Lamento informarle que ese horario no esta disponible, pero tengo un espacio libre el [dia] a las [hora]. Le gustaria agendar en este horario o prefiere que busquemos otra opcion?"
- Al usar crear_solicitud_cita, SIEMPRE usa el consultorio_id que te devolvio buscar_disponibilidad en el slot elegido. El paciente NO necesita saber el nombre del consultorio.

PROTOCOLO RECORDATORIO DE CONFIRMACION (cuando el paciente responde al recordatorio de 24h):
- Si el paciente confirma asistencia (dice "si", "confirmo", "ahi estaremos", "si asistire", etc.): usar confirmar_asistencia_cita con el paciente_id para marcar la cita como confirmada
- Si el paciente quiere cancelar o reagendar: usar cancelar_cita o reagendar_cita segun corresponda

REGLAS IMPORTANTES:
- Si el paciente esta marcado como PROBLEMATICO (es_problematico=True), NO agendar citas bajo ninguna circunstancia. Responder amablemente que por el momento no es posible atenderle por este medio y que contacte directamente al consultorio.
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
        logger.error(f'Traceback completo:\n{traceback.format_exc()}')
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
        elif nombre == 'confirmar_asistencia_cita':
            return _tool_confirmar_asistencia_cita(args)
        else:
            return {'error': f'Tool desconocida: {nombre}'}
    except Exception as e:
        logger.error(f'Error ejecutando tool {nombre}: {e}')
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

        info = {
            'id': paciente.id,
            'nombre': paciente.nombre_completo,
            'es_menor': paciente.es_menor_edad,
            'problema': paciente.es_problematico,
            'ultima_cita': ultima_cita.to_dict() if ultima_cita else None,
            'proxima_cita': proxima_cita.to_dict() if proxima_cita else None,
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
        return {'disponible': False, 'mensaje': 'El consultorio no atiende domingos. Prueba con otro dia.'}

    from services.scheduler_service import obtener_slots_disponibles
    from models import Dentista

    dentista_id = args.get('dentista_id')
    duracion = args.get('duracion_minutos', 60)
    hora_preferida = args.get('hora_preferida')  # formato HH:MM

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
            return {
                'disponible': True,
                'hora_solicitada_disponible': True,
                'fecha': args['fecha'],
                'fecha_formato': fecha.strftime('%A %d de %B de %Y'),
                'horario_confirmado': slot_exacto,
                'todas_las_opciones': todos_slots,
            }
        else:
            # La hora preferida no esta disponible, buscar la mas cercana en el mismo dia
            mejor = _encontrar_slot_mas_cercano(todos_slots, hora_preferida)
            return {
                'disponible': True,
                'hora_solicitada_disponible': False,
                'fecha': args['fecha'],
                'fecha_formato': fecha.strftime('%A %d de %B de %Y'),
                'mensaje': f'El horario de las {hora_preferida} no esta disponible.',
                'alternativa_sugerida': mejor,
                'todas_las_opciones': todos_slots,
            }

    return {
        'disponible': True,
        'fecha': args['fecha'],
        'fecha_formato': fecha.strftime('%A %d de %B de %Y'),
        'opciones': todos_slots,
    }


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
    from models import Cita, Paciente, EstatusCRM
    from extensions import db
    from services.scheduler_service import verificar_disponibilidad

    # Verificar que el paciente no sea problematico
    paciente_check = Paciente.query.get(args['paciente_id'])
    if paciente_check and paciente_check.es_problematico:
        return {'error': 'No se pueden crear citas para este paciente. Favor de contactar al consultorio directamente.'}

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
        # Buscar la proxima cita pendiente del paciente
        cita = Cita.query.filter(
            Cita.paciente_id == paciente_id,
            Cita.fecha_inicio >= datetime.utcnow() - timedelta(hours=1),
            Cita.status == EstatusCita.pendiente,
        ).order_by(Cita.fecha_inicio).first()
    else:
        return {'error': 'Se requiere cita_id o paciente_id'}

    if not cita:
        return {'error': 'No se encontro cita pendiente para este paciente'}

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
