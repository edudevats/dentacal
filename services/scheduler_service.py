"""
Logica de disponibilidad del consultorio.
Verifica colisiones y genera slots disponibles.
"""
from datetime import datetime, timedelta, date
from models import (Cita, HorarioDentista, BloqueoDentista, Consultorio,
                    EstatusCita, TurnoRotativo, TurnoRotativoMiembro)
from extensions import db
from sqlalchemy import and_, or_


def verificar_disponibilidad(dentista_id, consultorio_id, fecha_inicio,
                              fecha_fin, ignorar_cita_id=None):
    """
    Retorna la primera Cita que colisiona con el rango dado, o None si libre.

    Reglas:
      1. Un dentista no puede estar en dos lugares al mismo tiempo.
      2. Un consultorio no puede tener dos citas simultaneas.
    """
    q = Cita.query.filter(
        Cita.status.notin_([EstatusCita.cancelada]),
        and_(
            fecha_inicio < Cita.fecha_fin,
            fecha_fin > Cita.fecha_inicio,
        ),
        or_(
            Cita.dentista_id == dentista_id,
            Cita.consultorio_id == consultorio_id,
        )
    )

    if ignorar_cita_id:
        q = q.filter(Cita.id != ignorar_cita_id)

    return q.first()


def obtener_slots_disponibles(fecha, dentista_id, consultorio_id=None,
                               duracion_minutos=60):
    """
    Genera lista de slots disponibles para un dentista en una fecha.
    Si consultorio_id se omite, busca en todos los consultorios activos.
    """
    # Horario efectivo del dia (considera turnos rotativos)
    horas = horario_efectivo(dentista_id, fecha)
    if not horas:
        return []
    hora_inicio, hora_fin = horas

    inicio_dia = datetime(fecha.year, fecha.month, fecha.day,
                          hora_inicio.hour, hora_inicio.minute)
    fin_dia = datetime(fecha.year, fecha.month, fecha.day,
                       hora_fin.hour, hora_fin.minute)

    # Cargar bloqueos del dentista para ese dia (puede haber varios parciales)
    bloqueos = BloqueoDentista.query.filter(
        BloqueoDentista.dentista_id == dentista_id,
        BloqueoDentista.fecha_inicio < fin_dia,
        BloqueoDentista.fecha_fin > inicio_dia,
    ).all()

    # Generar slots
    consultorios = []
    if consultorio_id:
        c = Consultorio.query.filter_by(id=consultorio_id, activo=True).first()
        if c:
            consultorios = [c]
    else:
        consultorios = Consultorio.query.filter_by(activo=True).order_by(Consultorio.id).all()

    slots = []
    current = inicio_dia
    delta = timedelta(minutes=duracion_minutos)

    while current + delta <= fin_dia:
        slot_fin = current + delta
        slot_disponible = False
        consultorio_disponible = None

        # Verificar si el slot cae dentro de un bloqueo del dentista
        bloqueado = any(b.fecha_inicio < slot_fin and b.fecha_fin > current
                        for b in bloqueos)
        if bloqueado:
            slots.append({
                'inicio': current.strftime('%H:%M'),
                'fin': slot_fin.strftime('%H:%M'),
                'inicio_iso': current.isoformat(),
                'fin_iso': slot_fin.isoformat(),
                'disponible': False,
                'consultorio_id': None,
                'consultorio': None,
            })
            current += timedelta(minutes=30)
            continue

        for consultorio in consultorios:
            conflicto = verificar_disponibilidad(
                dentista_id=dentista_id,
                consultorio_id=consultorio.id,
                fecha_inicio=current,
                fecha_fin=slot_fin,
            )
            if not conflicto:
                slot_disponible = True
                consultorio_disponible = consultorio
                break  # Primer consultorio libre

        slots.append({
            'inicio': current.strftime('%H:%M'),
            'fin': slot_fin.strftime('%H:%M'),
            'inicio_iso': current.isoformat(),
            'fin_iso': slot_fin.isoformat(),
            'disponible': slot_disponible,
            'consultorio_id': consultorio_disponible.id if consultorio_disponible else None,
            'consultorio': consultorio_disponible.nombre if consultorio_disponible else None,
        })
        current += timedelta(minutes=30)  # Step de 30 min para mas opciones

    return slots


def hay_citas_ese_dia(dentista_id, fecha):
    """Quick check: tiene el dentista citas confirmadas/pendientes en esa fecha."""
    inicio = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
    fin = datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59)
    return Cita.query.filter(
        Cita.dentista_id == dentista_id,
        Cita.fecha_inicio >= inicio,
        Cita.fecha_inicio <= fin,
        Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
    ).first() is not None


def resolver_turno(fecha, turno):
    """Devuelve el TurnoRotativoMiembro que atiende esa fecha, o None.
    None si la fecha no cae en el dia_semana del turno o no hay miembros."""
    f = fecha.date() if isinstance(fecha, datetime) else fecha
    if f.weekday() != turno.dia_semana:
        return None
    miembros = sorted(turno.miembros, key=lambda m: m.orden)
    n = len(miembros)
    if n == 0:
        return None
    sem = (f - turno.fecha_ancla).days // 7   # multiplo de 7: ambos son el mismo weekday
    idx = sem % n                              # el % de Python devuelve 0..n-1 incluso con sem negativo
    return miembros[idx]


def _turno_de_dentista(dentista_id, dia_semana):
    """El TurnoRotativo activo que incluye al dentista para ese dia_semana, o None."""
    return (TurnoRotativo.query
            .filter(TurnoRotativo.dia_semana == dia_semana,
                    TurnoRotativo.activo.is_(True))
            .join(TurnoRotativoMiembro)
            .filter(TurnoRotativoMiembro.dentista_id == dentista_id)
            .first())


def horario_efectivo(dentista_id, fecha):
    """(hora_inicio, hora_fin) que el dentista atiende ese dia, o None.
    Precedencia: si el dentista pertenece a un turno rotativo de ese dia,
    el turno manda (atiende solo si le toca esa fecha). Si no, HorarioDentista normal."""
    f = fecha.date() if isinstance(fecha, datetime) else fecha
    turno = _turno_de_dentista(dentista_id, f.weekday())
    if turno:
        miembro = resolver_turno(f, turno)
        if miembro and miembro.dentista_id == dentista_id:
            return (turno.hora_inicio, turno.hora_fin)
        return None
    horario = HorarioDentista.query.filter_by(
        dentista_id=dentista_id, dia_semana=f.weekday(), activo=True
    ).first()
    if horario:
        return (horario.hora_inicio, horario.hora_fin)
    return None


def proxima_fecha_dentista(turno, dentista_id, desde_fecha, limite_semanas=12):
    """Proxima fecha ESTRICTAMENTE posterior a desde_fecha en que al dentista le toca el turno."""
    base = desde_fecha.date() if isinstance(desde_fecha, datetime) else desde_fecha
    dias_hasta = (turno.dia_semana - base.weekday()) % 7
    primera = base + timedelta(days=dias_hasta)
    for i in range(limite_semanas + 1):
        cand = primera + timedelta(weeks=i)
        if cand <= base:
            continue
        m = resolver_turno(cand, turno)
        if m and m.dentista_id == dentista_id:
            return cand
    return None
