"""Avisos para recepcion: confirmo, no contesto, cancelo/reagendo, comentario.

Las funciones no hacen commit; quien llama lo hace.
"""
from datetime import datetime, time, timedelta, timezone

from extensions import db
from models import AvisoRecepcion, SeguimientoCRM, TipoSeguimiento
from services.tiempo import TIMEZONE, ahora_local

TIPO_CONFIRMO = 'confirmo'
TIPO_NO_CONTESTO = 'no_contesto'
TIPO_CANCELO_REAGENDO = 'cancelo_reagendo'
TIPO_COMENTARIO = 'comentario'
TIPOS_AVISO = (TIPO_CONFIRMO, TIPO_NO_CONTESTO, TIPO_CANCELO_REAGENDO, TIPO_COMENTARIO)

MARCA_NO_ASISTIRA = 'no_asistira'
MARCA_SIN_CONFIRMAR = 'sin_confirmar'


def crear_aviso(tipo, cita=None, paciente=None, detalle='', origen='sistema'):
    if tipo not in TIPOS_AVISO:
        raise ValueError(f'Tipo de aviso invalido: {tipo!r}')
    if paciente is None and cita is not None:
        paciente = cita.paciente
    aviso = AvisoRecepcion(
        tipo=tipo,
        cita_id=cita.id if cita is not None else None,
        paciente_id=paciente.id if paciente is not None else None,
        detalle=detalle,
        origen=origen)
    db.session.add(aviso)
    return aviso


def marcar_cita(cita, marca):
    cita.aviso_asistencia = marca


def limpiar_marca(cita):
    cita.aviso_asistencia = None


def dejar_comentario(texto, cita=None, paciente=None, origen='bot'):
    texto = (texto or '').strip()
    if not texto:
        raise ValueError('El comentario no puede estar vacio')
    if paciente is None and cita is not None:
        paciente = cita.paciente
    if paciente is None:
        raise ValueError('No se pudo resolver el paciente del comentario')
    aviso = crear_aviso(TIPO_COMENTARIO, cita=cita, paciente=paciente,
                        detalle=texto, origen=origen)
    db.session.add(SeguimientoCRM(
        paciente_id=paciente.id,
        tipo=TipoSeguimiento.comentario_bot,
        fecha_programada=ahora_local(),
        notas=texto,
        completado=False))
    return aviso


def _rango_hoy_utc(ahora_local_dt=None):
    """Inicio/fin del dia local CDMX, convertidos a UTC naive."""
    ahora = ahora_local_dt or ahora_local()
    inicio_local = datetime.combine(ahora.date(), time.min)
    fin_local = inicio_local + timedelta(days=1)

    def a_utc(dt):
        return (dt.replace(tzinfo=TIMEZONE).astimezone(timezone.utc)
                .replace(tzinfo=None))

    return a_utc(inicio_local), a_utc(fin_local)


def _query_hoy(ahora_local_dt=None):
    inicio, fin = _rango_hoy_utc(ahora_local_dt)
    return AvisoRecepcion.query.filter(
        AvisoRecepcion.created_at >= inicio, AvisoRecepcion.created_at < fin)


def avisos_de_hoy(ahora_local_dt=None):
    avisos = (_query_hoy(ahora_local_dt)
              .order_by(AvisoRecepcion.created_at.desc(), AvisoRecepcion.id.desc())
              .all())
    resultado = {tipo: [] for tipo in TIPOS_AVISO}
    no_leidos = 0
    for aviso in avisos:
        if aviso.tipo in resultado:
            resultado[aviso.tipo].append(aviso.to_dict())
        if not aviso.leido:
            no_leidos += 1
    resultado['no_leidos'] = no_leidos
    return resultado


def marcar_todos_leidos(ahora_local_dt=None):
    return (_query_hoy(ahora_local_dt)
            .filter(AvisoRecepcion.leido.is_(False))
            .update({'leido': True}, synchronize_session='fetch'))
