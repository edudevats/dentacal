import pytest
from datetime import datetime, timedelta


def test_overlap_detection(app):
    """La segunda cita en el mismo horario debe retornar 409."""
    with app.app_context():
        from models import Cita, Paciente, Dentista, Consultorio, EstatusCita, EstatusCRM
        from extensions import db

        # Asegurar paciente y dentista existen
        p = Paciente.query.filter_by(eliminado=False).first()
        d = Dentista.query.filter_by(activo=True).first()
        c = Consultorio.query.filter_by(activo=True).first()

        if not all([p, d, c]):
            pytest.skip('No hay datos de prueba suficientes')

        inicio = datetime(2030, 6, 1, 10, 0, 0)
        fin    = datetime(2030, 6, 1, 11, 0, 0)

        # Primera cita
        cita1 = Cita(paciente_id=p.id, dentista_id=d.id, consultorio_id=c.id,
                     fecha_inicio=inicio, fecha_fin=fin)
        db.session.add(cita1)
        db.session.commit()

        # Verificar overlap
        from services.scheduler_service import verificar_disponibilidad
        conflicto = verificar_disponibilidad(d.id, c.id, inicio, fin)
        assert conflicto is not None
        assert conflicto.id == cita1.id

        # Cleanup
        db.session.delete(cita1)
        db.session.commit()


def test_no_overlap_different_time(app):
    with app.app_context():
        from models import Cita, Paciente, Dentista, Consultorio
        from extensions import db
        from services.scheduler_service import verificar_disponibilidad

        p = Paciente.query.filter_by(eliminado=False).first()
        d = Dentista.query.filter_by(activo=True).first()
        c = Consultorio.query.filter_by(activo=True).first()
        if not all([p, d, c]):
            pytest.skip('Sin datos')

        inicio = datetime(2030, 7, 1, 10, 0, 0)
        fin    = datetime(2030, 7, 1, 11, 0, 0)

        cita1 = Cita(paciente_id=p.id, dentista_id=d.id, consultorio_id=c.id,
                     fecha_inicio=inicio, fecha_fin=fin)
        db.session.add(cita1)
        db.session.commit()

        # Diferente hora: no debe haber conflicto
        sin_conflicto = verificar_disponibilidad(d.id, c.id,
                                                 datetime(2030, 7, 1, 12, 0, 0),
                                                 datetime(2030, 7, 1, 13, 0, 0))
        assert sin_conflicto is None

        db.session.delete(cita1)
        db.session.commit()
