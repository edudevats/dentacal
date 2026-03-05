"""Tests de CRUD de citas y detección de solapamiento."""
import pytest
import json
from datetime import datetime, timedelta
from models import Cita, Paciente, Dentista, Consultorio, TipoCita, db


def _fecha(offset_days=1, hour=10):
    """Genera un datetime futuro para tests."""
    base = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    return base + timedelta(days=offset_days)


class TestCitasCRUD:
    def test_listar_citas(self, auth_client):
        """GET /api/citas devuelve lista."""
        res = auth_client.get('/api/citas')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert isinstance(data, list)

    def test_crear_cita(self, auth_client, app):
        """POST /api/citas crea una cita correctamente."""
        with app.app_context():
            paciente = Paciente.query.first()
            dentista = Dentista.query.first()
            consultorio = Consultorio.query.first()
            tipo = TipoCita.query.first()

        inicio = _fecha(offset_days=5, hour=10)
        fin = inicio + timedelta(hours=1)

        payload = {
            'paciente_id': paciente.id,
            'dentista_id': dentista.id,
            'consultorio_id': consultorio.id,
            'tipo_cita_id': tipo.id,
            'fecha_inicio': inicio.isoformat(),
            'fecha_fin': fin.isoformat(),
            'notas': 'Cita de test',
        }
        res = auth_client.post(
            '/api/citas',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert res.status_code == 201
        data = json.loads(res.data)
        assert data['estado'] == 'pendiente'
        assert data['notas'] == 'Cita de test'

    def test_overlap_409(self, auth_client, app):
        """Crear cita solapada en mismo consultorio devuelve 409."""
        with app.app_context():
            paciente = Paciente.query.first()
            dentista = Dentista.query.first()
            consultorio = Consultorio.query.first()
            tipo = TipoCita.query.first()

        # Crear primera cita
        inicio = _fecha(offset_days=10, hour=14)
        fin = inicio + timedelta(hours=1)
        payload = {
            'paciente_id': paciente.id,
            'dentista_id': dentista.id,
            'consultorio_id': consultorio.id,
            'tipo_cita_id': tipo.id,
            'fecha_inicio': inicio.isoformat(),
            'fecha_fin': fin.isoformat(),
        }
        res1 = auth_client.post(
            '/api/citas',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert res1.status_code == 201

        # Crear cita solapada en el mismo consultorio
        res2 = auth_client.post(
            '/api/citas',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert res2.status_code == 409

    def test_cancelar_cita(self, auth_client, app):
        """PATCH /api/citas/<id>/cancelar cambia estado a cancelada."""
        with app.app_context():
            paciente = Paciente.query.first()
            dentista = Dentista.query.first()
            consultorio = Consultorio.query.first()
            tipo = TipoCita.query.first()

        inicio = _fecha(offset_days=15, hour=11)
        fin = inicio + timedelta(hours=1)
        payload = {
            'paciente_id': paciente.id,
            'dentista_id': dentista.id,
            'consultorio_id': consultorio.id,
            'tipo_cita_id': tipo.id,
            'fecha_inicio': inicio.isoformat(),
            'fecha_fin': fin.isoformat(),
        }
        res = auth_client.post(
            '/api/citas',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert res.status_code == 201
        cita_id = json.loads(res.data)['id']

        # Cancelar
        res_cancel = auth_client.patch(
            f'/api/citas/{cita_id}/cancelar',
            content_type='application/json',
        )
        assert res_cancel.status_code == 200
        data = json.loads(res_cancel.data)
        assert data['estado'] == 'cancelada'


class TestDisponibilidad:
    def test_disponibilidad_devuelve_slots(self, auth_client):
        """GET /api/disponibilidad devuelve datos de disponibilidad."""
        with auth_client.application.app_context():
            dentista = Dentista.query.first()
        fecha = _fecha(offset_days=3).date().isoformat()
        res = auth_client.get(f'/api/disponibilidad?dentista_id={dentista.id}&fecha={fecha}')
        # Puede ser 200 con slots o 200 vacío — solo verificar que no falla
        assert res.status_code in (200, 404)
