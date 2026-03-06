import pytest


def test_login_page(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'Iniciar' in resp.data or b'login' in resp.data.lower()


def test_dashboard_redirect_if_not_logged(client):
    resp = client.get('/')
    assert resp.status_code in (302, 401)


def test_login_invalid(client):
    resp = client.post('/login', data={
        'username': 'nadie',
        'password': 'mal',
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_api_requires_auth(client):
    resp = client.get('/api/pacientes')
    assert resp.status_code in (302, 401)
