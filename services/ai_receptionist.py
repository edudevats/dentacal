"""Bot recepcionista con Claude Haiku + tool_use."""
import json
import anthropic
from flask import current_app
from models import db, Paciente, Cita, TipoCita, Consultorio, ConversacionWhatsapp
from datetime import datetime, timedelta
from routes.api_citas import _check_overlap

# ── Herramientas (tools) para Claude ─────────────────────────────────────────

TOOLS = [
    {
        "name": "buscar_paciente",
        "description": "Busca un paciente por teléfono. Retorna su nombre e historial de citas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "telefono": {"type": "string", "description": "Número de teléfono del paciente"}
            },
            "required": ["telefono"]
        }
    },
    {
        "name": "registrar_paciente",
        "description": "Registra un nuevo paciente con nombre y teléfono.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "telefono": {"type": "string"},
                "nombre_escuela": {"type": "string", "description": "Escuela del paciente (opcional)"}
            },
            "required": ["nombre", "telefono"]
        }
    },
    {
        "name": "obtener_info_consultorio",
        "description": "Obtiene información del consultorio: precios, especialidades, dirección, horarios.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tema": {
                    "type": "string",
                    "enum": ["precios", "especialidades", "horarios", "ubicacion", "general"]
                }
            },
            "required": ["tema"]
        }
    },
    {
        "name": "buscar_disponibilidad",
        "description": "Busca slots disponibles para agendar cita.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo_cita": {
                    "type": "string",
                    "description": "Nombre del tipo de cita (ej: 'Primera Consulta', 'Limpieza + Flúor')"
                },
                "fecha_preferida": {
                    "type": "string",
                    "description": "Fecha preferida YYYY-MM-DD (opcional)"
                },
                "preferencia_dia": {
                    "type": "string",
                    "enum": ["entre_semana", "sabado", "cualquiera"],
                    "description": "Preferencia de día"
                }
            },
            "required": ["tipo_cita"]
        }
    },
    {
        "name": "crear_solicitud_cita",
        "description": "Crea una cita (estado=pendiente) y notifica a la recepcionista.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paciente_id": {"type": "integer"},
                "dentista_id": {"type": "integer"},
                "consultorio_id": {"type": "integer"},
                "tipo_cita_id": {"type": "integer"},
                "fecha_inicio": {"type": "string", "description": "ISO 8601: 2025-01-15T10:00:00"},
                "fecha_fin": {"type": "string", "description": "ISO 8601: 2025-01-15T11:00:00"},
            },
            "required": ["paciente_id", "dentista_id", "consultorio_id", "tipo_cita_id", "fecha_inicio", "fecha_fin"]
        }
    },
    {
        "name": "confirmar_anticipo",
        "description": "Registra que el paciente dice haber pagado el anticipo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paciente_id": {"type": "integer"},
                "monto": {"type": "number", "description": "Monto del anticipo"}
            },
            "required": ["paciente_id"]
        }
    },
    {
        "name": "cancelar_cita",
        "description": "Cancela una cita existente del paciente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cita_id": {"type": "integer"}
            },
            "required": ["cita_id"]
        }
    },
    {
        "name": "reagendar_cita",
        "description": "Cancela la cita actual y crea una nueva en el nuevo horario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cita_id": {"type": "integer"},
                "nueva_fecha_inicio": {"type": "string"},
                "nueva_fecha_fin": {"type": "string"},
                "nuevo_consultorio_id": {"type": "integer"}
            },
            "required": ["cita_id", "nueva_fecha_inicio", "nueva_fecha_fin"]
        }
    },
]


# ── Ejecutores de tools ───────────────────────────────────────────────────────

def _ejecutar_tool(nombre: str, params: dict, telefono: str) -> str:
    try:
        if nombre == 'buscar_paciente':
            return _tool_buscar_paciente(params)
        elif nombre == 'registrar_paciente':
            return _tool_registrar_paciente(params)
        elif nombre == 'obtener_info_consultorio':
            return _tool_info_consultorio(params)
        elif nombre == 'buscar_disponibilidad':
            return _tool_disponibilidad(params)
        elif nombre == 'crear_solicitud_cita':
            return _tool_crear_cita(params)
        elif nombre == 'confirmar_anticipo':
            return _tool_confirmar_anticipo(params)
        elif nombre == 'cancelar_cita':
            return _tool_cancelar_cita(params)
        elif nombre == 'reagendar_cita':
            return _tool_reagendar(params)
        else:
            return json.dumps({'error': f'Tool desconocida: {nombre}'})
    except Exception as e:
        current_app.logger.error(f'[Bot Tool] {nombre} error: {e}', exc_info=True)
        return json.dumps({'error': str(e)})


def _tool_buscar_paciente(p: dict) -> str:
    pac = Paciente.query.filter_by(telefono=p['telefono']).first()
    if not pac:
        return json.dumps({'encontrado': False})
    citas = Cita.query.filter_by(paciente_id=pac.id).order_by(Cita.fecha_inicio.desc()).limit(5).all()
    return json.dumps({
        'encontrado': True,
        'id': pac.id,
        'nombre': pac.nombre,
        'estado_crm': pac.estado_crm,
        'ultima_cita': pac.fecha_ultima_cita.isoformat() if pac.fecha_ultima_cita else None,
        'citas_recientes': [
            {'fecha': c.fecha_inicio.isoformat(), 'tipo': c.tipo_cita.nombre if c.tipo_cita else '', 'estado': c.estado}
            for c in citas
        ]
    })


def _tool_registrar_paciente(p: dict) -> str:
    existing = Paciente.query.filter_by(telefono=p['telefono']).first()
    if existing:
        return json.dumps({'id': existing.id, 'nombre': existing.nombre, 'ya_existia': True})
    nuevo = Paciente(
        nombre=p['nombre'],
        telefono=p['telefono'],
        nombre_escuela=p.get('nombre_escuela', ''),
        estado_crm='nuevo',
    )
    db.session.add(nuevo)
    db.session.commit()
    return json.dumps({'id': nuevo.id, 'nombre': nuevo.nombre, 'ya_existia': False})


def _tool_info_consultorio(p: dict) -> str:
    tema = p.get('tema', 'general')
    clabe = current_app.config.get('CLABE_INTERBANCARIA', '')
    nombre = current_app.config.get('CONSULTORIO_NOMBRE', 'La Casa del Sr. Pérez')
    direccion = current_app.config.get('CONSULTORIO_DIRECCION', '')
    telefono = current_app.config.get('CONSULTORIO_TELEFONO', '')

    tipos = TipoCita.query.filter_by(activo=True).all()
    precios = {t.nombre: t.costo for t in tipos}

    info = {
        'nombre': nombre,
        'direccion': direccion,
        'telefono': telefono,
        'clabe': clabe,
        'precios': precios,
        'especialidades': ['Odontopediatría', 'Ortodoncia', 'Operatoria', 'Limpieza y Flúor'],
        'horario_general': 'Lunes a Viernes 9:00-18:00, Sábados 9:00-14:00',
        'primera_consulta': {
            'precio': 550,
            'incluye': 'Diagnóstico, plan de tratamiento, presupuesto y radiografías intraorales',
            'anticipo': '50% del total ($275) para garantizar la cita',
        }
    }

    if tema == 'precios':
        return json.dumps({'precios': precios, 'primera_consulta': info['primera_consulta']})
    elif tema == 'ubicacion':
        return json.dumps({'direccion': direccion, 'telefono': telefono})
    elif tema == 'horarios':
        return json.dumps({'horario_general': info['horario_general']})
    return json.dumps(info)


def _tool_disponibilidad(p: dict) -> str:
    tipo_nombre = p.get('tipo_cita', 'Primera Consulta')
    fecha_pref = p.get('fecha_preferida')
    preferencia = p.get('preferencia_dia', 'cualquiera')

    tipo = TipoCita.query.filter(TipoCita.nombre.ilike(f'%{tipo_nombre}%')).first()
    if not tipo:
        return json.dumps({'error': f'Tipo de cita "{tipo_nombre}" no encontrado'})

    # Buscar slots en los próximos 14 días
    from models import Dentista, HorarioDentista
    dentistas = Dentista.query.filter_by(activo=True).all()
    slots_disponibles = []

    start_date = datetime.now().date() + timedelta(days=1)
    if fecha_pref:
        try:
            start_date = datetime.strptime(fecha_pref, '%Y-%m-%d').date()
        except ValueError:
            pass

    for i in range(14):
        fecha = start_date + timedelta(days=i)
        dia_semana = fecha.weekday()

        # Filtrar por preferencia
        if preferencia == 'entre_semana' and dia_semana >= 5:
            continue
        if preferencia == 'sabado' and dia_semana != 5:
            continue

        for dentista in dentistas:
            horario = next((h for h in dentista.horarios if h.dia_semana == dia_semana), None)
            if not horario:
                continue

            # Verificar bloqueos
            bloqueado = any(b.fecha_inicio <= fecha <= b.fecha_fin for b in dentista.bloqueos)
            if bloqueado:
                continue

            fecha_str = fecha.isoformat()
            h_ini = datetime.strptime(f'{fecha_str} {horario.hora_inicio}', '%Y-%m-%d %H:%M')
            h_fin_horario = datetime.strptime(f'{fecha_str} {horario.hora_fin}', '%Y-%m-%d %H:%M')

            current_slot = h_ini
            while current_slot + timedelta(minutes=tipo.duracion_mins) <= h_fin_horario:
                slot_fin = current_slot + timedelta(minutes=tipo.duracion_mins)
                consultorios_libres = []
                for c in Consultorio.query.filter_by(activo=True).all():
                    if not _check_overlap(c.id, current_slot, slot_fin):
                        consultorios_libres.append(c.id)

                if consultorios_libres:
                    slots_disponibles.append({
                        'fecha': fecha_str,
                        'hora_inicio': current_slot.strftime('%H:%M'),
                        'hora_fin': slot_fin.strftime('%H:%M'),
                        'fecha_inicio_iso': current_slot.isoformat(),
                        'fecha_fin_iso': slot_fin.isoformat(),
                        'dentista_id': dentista.id,
                        'dentista_nombre': dentista.nombre,
                        'consultorio_id': consultorios_libres[0],
                        'tipo_cita_id': tipo.id,
                        'tipo_cita_nombre': tipo.nombre,
                    })

                current_slot += timedelta(minutes=30)

            if len(slots_disponibles) >= 6:
                break
        if len(slots_disponibles) >= 6:
            break

    return json.dumps({'slots': slots_disponibles[:6], 'tipo_cita': tipo.nombre, 'duracion_mins': tipo.duracion_mins})


def _tool_crear_cita(p: dict) -> str:
    try:
        fi = datetime.fromisoformat(p['fecha_inicio'])
        ff = datetime.fromisoformat(p['fecha_fin'])
    except ValueError as e:
        return json.dumps({'error': f'Fecha inválida: {e}'})

    if _check_overlap(p['consultorio_id'], fi, ff):
        return json.dumps({'error': 'Consultorio ocupado en ese horario'})

    cita = Cita(
        paciente_id=p['paciente_id'],
        dentista_id=p['dentista_id'],
        consultorio_id=p['consultorio_id'],
        tipo_cita_id=p['tipo_cita_id'],
        fecha_inicio=fi,
        fecha_fin=ff,
        estado='pendiente',
        creado_por='bot',
    )
    db.session.add(cita)

    # Actualizar fecha última cita
    pac = Paciente.query.get(p['paciente_id'])
    if pac:
        if not pac.fecha_ultima_cita or fi > pac.fecha_ultima_cita:
            pac.fecha_ultima_cita = fi

    db.session.commit()

    # Notificar recepcionista
    try:
        from services.whatsapp_service import notificar_recepcionista
        notificar_recepcionista(
            f'🦷 Nueva cita agendada por BOT:\n'
            f'Paciente: {pac.nombre if pac else "?"}\n'
            f'Fecha: {fi.strftime("%d/%m/%Y %H:%M")}\n'
            f'Cita ID: {cita.id}'
        )
    except Exception:
        pass

    return json.dumps({
        'ok': True,
        'cita_id': cita.id,
        'fecha': fi.strftime('%d/%m/%Y'),
        'hora': fi.strftime('%H:%M'),
    })


def _tool_confirmar_anticipo(p: dict) -> str:
    pac = Paciente.query.get(p['paciente_id'])
    if not pac:
        return json.dumps({'error': 'Paciente no encontrado'})

    # Marcar última cita pendiente con anticipo
    cita = Cita.query.filter_by(
        paciente_id=p['paciente_id'],
        estado='pendiente'
    ).order_by(Cita.fecha_inicio).first()

    if cita:
        cita.anticipo_registrado = True
        cita.anticipo_monto = p.get('monto', 0)
        db.session.commit()

    # Notificar recepcionista
    try:
        from services.whatsapp_service import notificar_recepcionista
        notificar_recepcionista(
            f'💰 Paciente {pac.nombre} reporta haber pagado anticipo.\n'
            f'Monto: ${p.get("monto", "?")}.\n'
            f'Por favor verificar y confirmar la cita ID: {cita.id if cita else "?"}'
        )
    except Exception:
        pass

    return json.dumps({'ok': True, 'mensaje': 'Anticipo registrado. La recepcionista verificará tu pago.'})


def _tool_cancelar_cita(p: dict) -> str:
    cita = Cita.query.get(p['cita_id'])
    if not cita:
        return json.dumps({'error': 'Cita no encontrada'})
    cita.estado = 'cancelada'
    db.session.commit()
    return json.dumps({'ok': True, 'cita_id': cita.id})


def _tool_reagendar(p: dict) -> str:
    cita = Cita.query.get(p['cita_id'])
    if not cita:
        return json.dumps({'error': 'Cita no encontrada'})

    try:
        nueva_fi = datetime.fromisoformat(p['nueva_fecha_inicio'])
        nueva_ff = datetime.fromisoformat(p['nueva_fecha_fin'])
    except ValueError as e:
        return json.dumps({'error': f'Fecha inválida: {e}'})

    nuevo_consultorio = p.get('nuevo_consultorio_id', cita.consultorio_id)
    if _check_overlap(nuevo_consultorio, nueva_fi, nueva_ff, exclude_id=cita.id):
        return json.dumps({'error': 'Consultorio ocupado en el nuevo horario'})

    cita.fecha_inicio = nueva_fi
    cita.fecha_fin = nueva_ff
    cita.consultorio_id = nuevo_consultorio
    cita.estado = 'pendiente'
    db.session.commit()
    return json.dumps({'ok': True, 'cita_id': cita.id, 'nueva_fecha': nueva_fi.strftime('%d/%m/%Y %H:%M')})


# ── Prompt del sistema ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres la recepcionista virtual de "La Casa del Sr. Pérez", consultorio dental pediátrico y adultos.

Tu nombre es Ale y eres amable, profesional y empática. Respondes en español mexicano, de forma cálida pero concisa.

Tu función principal:
- Dar información sobre el consultorio (precios, especialidades, ubicación)
- Agendar, reagendar y cancelar citas
- Solicitar anticipo del 50% para primeras consultas
- Confirmar pagos de anticipos y notificar a la recepcionista

Reglas:
1. Siempre usa las tools disponibles para consultar y modificar datos reales
2. Para nuevos pacientes: primero registra, luego busca disponibilidad, luego crea la cita
3. La primera consulta cuesta $550 e incluye diagnóstico, plan de tratamiento y radiografías
4. Para primera consulta se requiere anticipo del 50% ($275) vía transferencia
5. Si el paciente confirma pago, usa confirmar_anticipo y notifica que la recepcionista verificará
6. Nunca inventes horarios — usa siempre buscar_disponibilidad
7. Sé breve y amable. Usa emojis con moderación 🦷
8. Si no puedes resolver algo, pide que llamen directamente al consultorio
"""


# ── Función principal ─────────────────────────────────────────────────────────

def procesar_mensaje_bot(
    telefono: str,
    mensaje: str,
    historial: list,
    estado_flujo: str,
    paciente_id: int = None,
) -> tuple[str, str]:
    """
    Procesa un mensaje entrante con Claude Haiku + tool_use.
    Retorna (respuesta_texto, nuevo_estado_flujo).
    """
    api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return ('Lo sentimos, el servicio de chat no está disponible en este momento. '
                'Por favor llámenos directamente. 📞', estado_flujo)

    client = anthropic.Anthropic(api_key=api_key)

    # Preparar mensajes (excluir el último que ya está en historial)
    messages = historial.copy()

    max_iterations = 5
    for _ in range(max_iterations):
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == 'end_turn':
            # Extraer texto de la respuesta
            texto = ''
            for block in response.content:
                if hasattr(block, 'text'):
                    texto += block.text
            nuevo_estado = _inferir_estado(texto, estado_flujo)
            return texto.strip(), nuevo_estado

        elif response.stop_reason == 'tool_use':
            # Agregar respuesta del asistente con tool calls
            messages.append({'role': 'assistant', 'content': response.content})

            # Ejecutar cada tool call
            tool_results = []
            for block in response.content:
                if block.type == 'tool_use':
                    resultado = _ejecutar_tool(block.name, block.input, telefono)
                    current_app.logger.info(f'[Bot] Tool {block.name}: {resultado[:200]}')
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': resultado,
                    })

            messages.append({'role': 'user', 'content': tool_results})

        else:
            break

    return ('Disculpa, ocurrió un error procesando tu solicitud. Por favor intenta de nuevo.', estado_flujo)


def _inferir_estado(texto: str, estado_actual: str) -> str:
    """Infiere el nuevo estado del flujo basado en la respuesta."""
    texto_lower = texto.lower()
    if any(w in texto_lower for w in ['anticipo', 'transferencia', 'clabe', 'pago']):
        return 'pagando'
    if any(w in texto_lower for w in ['confirmad', 'agendad', 'nos vemos', 'cita confirmada']):
        return 'confirmado'
    if any(w in texto_lower for w in ['agendar', 'disponibilidad', 'horario', 'fecha']):
        return 'agendando'
    return estado_actual
