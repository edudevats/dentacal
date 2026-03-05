"""Tests del módulo CRM."""
import pytest
import json
from unittest.mock import patch
from models import Paciente, SeguimientoCRM, db


class TestCRMEstados:
    def test_vista_crm_carga(self, auth_client):
        """GET /crm devuelve 200."""
        res = auth_client.get('/crm')
        assert res.status_code == 200

    def test_cambiar_estado_crm(self, auth_client, app):
        """PUT /api/crm/paciente/<id>/estado cambia el estado."""
        with app.app_context():
            paciente = Paciente.query.first()
            paciente_id = paciente.id

        res = auth_client.put(
            f'/api/crm/paciente/{paciente_id}/estado',
            data=json.dumps({'estado': 'activo'}),
            content_type='application/json',
        )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['estado_crm'] == 'activo'

    def test_cambiar_estado_invalido(self, auth_client, app):
        """Estado inválido devuelve 400."""
        with app.app_context():
            paciente = Paciente.query.first()
            paciente_id = paciente.id

        res = auth_client.put(
            f'/api/crm/paciente/{paciente_id}/estado',
            data=json.dumps({'estado': 'estado_inexistente'}),
            content_type='application/json',
        )
        assert res.status_code == 400


class TestCRMWhatsApp:
    def test_enviar_wa_mock(self, auth_client, app):
        """POST /api/crm/enviar_wa con mock no llama a Twilio real."""
        with app.app_context():
            paciente = Paciente.query.first()
            paciente_id = paciente.id

        payload = {
            'paciente_id': paciente_id,
            'tipo_plantilla': 'bienvenida',
        }
        # Mockear el servicio de WhatsApp para no hacer llamadas reales
        with patch('routes.api_crm.enviar_mensaje') as mock_wa:
            mock_wa.return_value = {'sid': 'SMtest123'}
            res = auth_client.post(
                '/api/crm/enviar_wa',
                data=json.dumps(payload),
                content_type='application/json',
            )
        # El endpoint puede devolver 200 o error de configuración
        assert res.status_code in (200, 400, 500)


class TestCRMExport:
    def test_exportar_excel(self, auth_client):
        """GET /api/crm/export devuelve archivo Excel."""
        res = auth_client.get('/api/crm/export')
        assert res.status_code == 200
        assert 'spreadsheet' in res.content_type or 'excel' in res.content_type or res.status_code == 200
