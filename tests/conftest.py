"""Fixtures compartidas para pytest."""
import pytest
from app import create_app
from models import db as _db, User, Consultorio, TipoCita, Dentista, Paciente


@pytest.fixture(scope='session')
def app():
    """App Flask en modo testing (BD en memoria)."""
    application = create_app('testing')

    with application.app_context():
        _db.create_all()
        _seed_test_data()
        yield application
        _db.drop_all()


def _seed_test_data():
    """Datos mínimos para tests."""
    # Consultorios
    if Consultorio.query.count() == 0:
        _db.session.add(Consultorio(id=1, nombre='Consultorio 1'))

    # Tipos de cita
    if TipoCita.query.count() == 0:
        _db.session.add(TipoCita(nombre='Primera Consulta', duracion_mins=60, costo=550))

    # Dentista
    if Dentista.query.count() == 0:
        _db.session.add(Dentista(nombre='Dr. Pérez', color='#3788d8'))

    # Paciente
    if Paciente.query.count() == 0:
        _db.session.add(Paciente(nombre='Juan Test', telefono='+521234567890'))

    # Usuarios
    if User.query.count() == 0:
        admin = User(username='admin', email='admin@test.com', role='admin')
        admin.set_password('Admin1234!')
        recepcionist = User(username='recepcion', email='recepcion@test.com', role='recepcionista')
        recepcionist.set_password('Recep1234!')
        _db.session.add_all([admin, recepcionist])

    _db.session.commit()


@pytest.fixture(scope='session')
def client(app):
    """Cliente HTTP de Flask."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Cliente con sesión de recepcionista iniciada."""
    client.post('/login', data={
        'username': 'recepcion',
        'password': 'Recep1234!',
    }, follow_redirects=True)
    yield client
    client.post('/logout', data={}, follow_redirects=True)


@pytest.fixture
def admin_client(client):
    """Cliente con sesión de admin iniciada."""
    client.post('/login', data={
        'username': 'admin',
        'password': 'Admin1234!',
    }, follow_redirects=True)
    yield client
    client.post('/logout', data={}, follow_redirects=True)
