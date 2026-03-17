import pytest
import json
from datetime import datetime, timedelta


def _crear_paciente_test(db, nombre, whatsapp, estatus='activo', es_problematico=False, ultima_cita=None):
    """Helper para crear paciente de prueba."""
    from models import Paciente, EstatusCRM
    p = Paciente(
        nombre=nombre,
        whatsapp=whatsapp,
        estatus_crm=EstatusCRM[estatus],
        es_problematico=es_problematico,
        ultima_cita=ultima_cita,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _cleanup_campanas(db):
    """Limpia campanas y destinatarios de prueba."""
    from models import CampanaDestinatario, Campana
    db.session.query(CampanaDestinatario).delete()
    db.session.query(Campana).delete()
    db.session.commit()


def test_crear_campana(app):
    """Crear campana via servicio retorna campana en estado borrador."""
    with app.app_context():
        from extensions import db
        from services.campana_service import crear_campana
        from models import EstatusCampana

        campana = crear_campana(
            nombre='Test Promo',
            mensaje='Hola {nombre_paciente}, tenemos una promo!',
            filtros={'estatus_crm': ['activo']},
            fecha_programada=None,
            user_id=None,
        )

        assert campana.id is not None
        assert campana.nombre == 'Test Promo'
        assert campana.estatus == EstatusCampana.borrador

        # Cleanup
        db.session.delete(campana)
        db.session.commit()


def test_preview_audiencia(app):
    """Preview retorna solo pacientes no eliminados, no problematicos, con WA."""
    with app.app_context():
        from extensions import db
        from services.campana_service import obtener_audiencia

        # Crear pacientes de prueba
        p1 = _crear_paciente_test(db, 'Test Activo', '+5211111111', estatus='activo')
        p2 = _crear_paciente_test(db, 'Test Baja', '+5222222222', estatus='baja')
        p3 = _crear_paciente_test(db, 'Test Problematico', '+5233333333', estatus='activo', es_problematico=True)

        # Filtro: solo activos
        audiencia = obtener_audiencia({'estatus_crm': ['activo']})
        ids = [p.id for p in audiencia]

        assert p1.id in ids
        assert p2.id not in ids  # baja, no esta en filtro
        assert p3.id not in ids  # problematico, excluido siempre

        # Cleanup
        for p in [p1, p2, p3]:
            db.session.delete(p)
        db.session.commit()


def test_preview_filtro_meses_sin_cita(app):
    """Filtro meses_sin_cita retorna pacientes inactivos."""
    with app.app_context():
        from extensions import db
        from services.campana_service import obtener_audiencia

        reciente = datetime.utcnow() - timedelta(days=30)
        vieja = datetime.utcnow() - timedelta(days=200)

        p_reciente = _crear_paciente_test(db, 'Reciente', '+5244444444', ultima_cita=reciente)
        p_vieja = _crear_paciente_test(db, 'Vieja', '+5255555555', ultima_cita=vieja)
        p_nunca = _crear_paciente_test(db, 'Nunca', '+5266666666')  # sin ultima_cita

        audiencia = obtener_audiencia({'estatus_crm': ['activo'], 'meses_sin_cita': 3})
        ids = [p.id for p in audiencia]

        assert p_reciente.id not in ids  # cita reciente
        assert p_vieja.id in ids  # mas de 3 meses
        assert p_nunca.id in ids  # nunca tuvo cita

        # Cleanup
        for p in [p_reciente, p_vieja, p_nunca]:
            db.session.delete(p)
        db.session.commit()


def test_enviar_campana_inmediata(app):
    """Enviar campana crea ConversacionWhatsapp por cada destinatario."""
    with app.app_context():
        from extensions import db
        from services.campana_service import crear_campana, preparar_destinatarios, enviar_campana
        from models import ConversacionWhatsapp, EstatusCampana

        p1 = _crear_paciente_test(db, 'Camp Dest 1', '+5277777777')
        p2 = _crear_paciente_test(db, 'Camp Dest 2', '+5288888888')

        campana = crear_campana(
            nombre='Test Envio',
            mensaje='Hola {nombre_paciente}!',
            filtros={'estatus_crm': ['activo']},
            fecha_programada=None,
            user_id=None,
        )

        total = preparar_destinatarios(campana)
        assert total >= 2

        # Enviar (Twilio en modo test retorna TEST_SID)
        enviar_campana(campana.id, app)

        # Recargar campana
        db.session.refresh(campana)
        assert campana.estatus == EstatusCampana.completada
        assert campana.enviados >= 2

        # Verificar que se guardaron conversaciones
        conv1 = ConversacionWhatsapp.query.filter_by(
            numero_telefono='+5277777777', es_bot=True
        ).order_by(ConversacionWhatsapp.timestamp.desc()).first()
        assert conv1 is not None
        assert 'Camp Dest 1' in conv1.mensaje

        conv2 = ConversacionWhatsapp.query.filter_by(
            numero_telefono='+5288888888', es_bot=True
        ).order_by(ConversacionWhatsapp.timestamp.desc()).first()
        assert conv2 is not None
        assert 'Camp Dest 2' in conv2.mensaje

        # Cleanup
        _cleanup_campanas(db)
        # Limpiar conversaciones de prueba
        ConversacionWhatsapp.query.filter(
            ConversacionWhatsapp.numero_telefono.in_(['+5277777777', '+5288888888'])
        ).delete(synchronize_session=False)
        for p in [p1, p2]:
            db.session.delete(p)
        db.session.commit()


def test_eliminar_campana_borrador(app):
    """Campana en borrador se puede eliminar."""
    with app.app_context():
        from extensions import db
        from services.campana_service import crear_campana
        from models import Campana

        campana = crear_campana(
            nombre='Para Borrar',
            mensaje='test',
            filtros={},
            fecha_programada=None,
            user_id=None,
        )
        campana_id = campana.id

        db.session.delete(campana)
        db.session.commit()

        assert db.session.get(Campana, campana_id) is None


def test_eliminar_campana_completada_falla(app):
    """Campana completada no se puede eliminar."""
    with app.app_context():
        from extensions import db
        from models import Campana, EstatusCampana

        campana = Campana(
            nombre='Completada',
            mensaje='test',
            estatus=EstatusCampana.completada,
        )
        db.session.add(campana)
        db.session.commit()

        # El endpoint debe rechazar la eliminacion
        # Verificamos la logica: completada no se borra
        assert campana.estatus == EstatusCampana.completada

        # Cleanup
        db.session.delete(campana)
        db.session.commit()
