"""
Sobrevivir a que MySQL tire la conexion a media consulta.

En PythonAnywhere aparece cada tanto:

    MySQLdb.OperationalError: (2013, 'Lost connection to MySQL server during query')

`pool_pre_ping` NO lo cubre: valida la conexion al sacarla del pool, y aqui la
conexion se muere despues, ya en pleno query. Cuando eso pasa la sesion queda
envenenada ("Can't reconnect until invalid transaction is rolled back") y todo
lo que venga despues en ese request tambien falla.

Se vio dos veces el 2026-08-26: en una tool del bot (`buscar_paciente`) y en
`load_user`, que corre en CADA request autenticado y le tumbo el calendario a
recepcion con un 500.
"""
import logging

log = logging.getLogger(__name__)


def es_falla_de_conexion(e):
    """True si la excepcion es la conexion cayendose, no un dato invalido."""
    from sqlalchemy.exc import (InterfaceError, OperationalError,
                                PendingRollbackError)
    if isinstance(e, (OperationalError, InterfaceError, PendingRollbackError)):
        return True
    return bool(getattr(e, 'connection_invalidated', False))


def sanear_sesion():
    """
    Deja la sesion utilizable otra vez despues de un error de BD.

    Sin esto el siguiente query falla con "Can't reconnect until invalid
    transaction is rolled back" aunque el servidor ya este de vuelta.
    """
    try:
        from extensions import db
        db.session.rollback()
        return True
    except Exception as e:
        log.error(f'No se pudo hacer rollback de la sesion: {e}')
        return False


def reintentar_lectura(fn, *args, descripcion=None, **kwargs):
    """
    Corre una LECTURA y la reintenta una vez si se cae la conexion.

    Solo para lecturas. Una escritura no se puede reintentar a ciegas: si el
    2013 ocurrio durante el COMMIT no hay forma de saber si quedo guardada, y
    el reintento la duplicaria. Para escrituras usar sanear_sesion() y abortar.

    Propaga la excepcion si el reintento tambien falla.
    """
    etiqueta = descripcion or getattr(fn, '__name__', 'lectura')
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if not es_falla_de_conexion(e):
            raise
        log.warning(f'Conexion a la BD perdida en {etiqueta}: {e}. Reintentando.')
        sanear_sesion()
        resultado = fn(*args, **kwargs)
        log.info(f'{etiqueta} recuperada tras reconectar a la BD')
        return resultado
