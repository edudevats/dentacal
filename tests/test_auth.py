"""Tests de autenticación."""
import pytest


class TestLogin:
    def test_login_page_loads(self, client):
        """Página de login devuelve 200."""
        res = client.get('/login')
        assert res.status_code == 200
        assert b'Iniciar' in res.data or b'login' in res.data.lower()

    def test_login_valido_admin(self, client):
        """Login correcto redirige al calendario."""
        res = client.post('/login', data={
            'username': 'admin',
            'password': 'Admin1234!',
        }, follow_redirects=True)
        assert res.status_code == 200
        # Después del login estamos en el calendario
        assert b'calendario' in res.data.lower() or b'Sr. P' in res.data

    def test_login_invalido(self, client):
        """Credenciales incorrectas muestran error."""
        res = client.post('/login', data={
            'username': 'admin',
            'password': 'wrongpassword',
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b'incorrectos' in res.data or b'login' in res.data.lower()

    def test_logout(self, admin_client):
        """Logout redirige a login."""
        res = admin_client.post('/logout', data={}, follow_redirects=True)
        assert res.status_code == 200


class TestProteccionRutas:
    def test_calendario_sin_login_redirige(self, client):
        """Sin sesión, /calendario redirige a /login."""
        # Asegurarse de que no hay sesión activa
        client.get('/logout')
        res = client.get('/calendario', follow_redirects=False)
        assert res.status_code in (302, 401)
        if res.status_code == 302:
            assert 'login' in res.location

    def test_api_citas_sin_login(self, client):
        """API de citas sin sesión devuelve 302 o 401."""
        client.get('/logout')
        res = client.get('/api/citas', follow_redirects=False)
        assert res.status_code in (302, 401)

    def test_admin_usuarios_solo_admin(self, auth_client):
        """Un recepcionista no puede acceder a /admin/usuarios."""
        res = auth_client.get('/admin/usuarios', follow_redirects=True)
        # Debe redirigir al calendario con mensaje de error
        assert res.status_code == 200
        assert b'restringido' in res.data or b'calendario' in res.data.lower()

    def test_admin_usuarios_accesible_por_admin(self, admin_client):
        """El admin sí puede acceder a /admin/usuarios."""
        res = admin_client.get('/admin/usuarios')
        assert res.status_code == 200


class TestCambiarPassword:
    def test_cambiar_password_sin_login(self, client):
        """Sin sesión, redirige a login."""
        client.get('/logout')
        res = client.get('/cambiar-password', follow_redirects=False)
        assert res.status_code in (302, 401)

    def test_cambiar_password_con_login(self, auth_client):
        """Con sesión, la página carga correctamente."""
        res = auth_client.get('/cambiar-password')
        assert res.status_code == 200
        assert b'Contrase' in res.data
