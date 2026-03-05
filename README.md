# La Casa del Sr. Pérez — Sistema Recepcionista Virtual 🦷

Sistema de gestión dental con calendario, CRM, bot WhatsApp (IA) y justificantes PDF.

## Stack
- **Backend**: Flask 3.0 + SQLAlchemy + Flask-Migrate
- **Auth**: Flask-Login (roles: admin / recepcionista)
- **Seguridad**: Flask-WTF (CSRF) + Flask-Limiter + Flask-Talisman
- **Frontend**: Bootstrap 5 + FullCalendar 6
- **WhatsApp Bot**: Twilio API + Claude (Anthropic)
- **PDF**: xhtml2pdf
- **Scheduler**: APScheduler

---

## Setup local

### 1. Clonar e instalar dependencias
```bash
git clone <repo-url>
cd dental_app
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno
```bash
cp .env.example .env
# Editar .env con tus valores reales
```

### 3. Inicializar BD y migraciones
```bash
# Primera vez:
flask --app app db init
flask --app app db migrate -m "init"
flask --app app db upgrade

# O con manage.py:
python manage.py db upgrade
```

### 4. Crear usuario admin
```bash
python manage.py crear_admin
# Sigue el prompt interactivo
```

### 5. Insertar datos semilla
```bash
python manage.py seed
```

### 6. Ejecutar
```bash
python app.py          # Modo desarrollo
# o
flask --app app run --debug
```

Abrir: http://localhost:5000

---

## Comandos CLI (manage.py)

| Comando | Descripción |
|---------|-------------|
| `python manage.py db upgrade` | Aplica migraciones pendientes |
| `python manage.py db migrate -m "msg"` | Genera nueva migración |
| `python manage.py crear_admin` | Crea usuario admin interactivo |
| `python manage.py seed` | Inserta datos semilla |
| `python manage.py shell` | Shell Python con contexto Flask |
| `python manage.py test` | Corre todos los tests |

---

## Tests
```bash
pip install pytest pytest-flask
python manage.py test
# o directamente:
pytest tests/ -v
```

---

## Roles de usuario

| Rol | Acceso |
|-----|--------|
| **admin** | Todo: calendario, CRM, pacientes, doctores, configuración, gestión de usuarios |
| **recepcionista** | Calendario, CRM, pacientes, doctores — sin `/admin/*` |

---

## Deployment en PythonAnywhere

### 1. Subir archivos
```bash
# Desde tu máquina local
scp -r . usuario@ssh.pythonanywhere.com:~/dental_app/
# o usar el panel Files de PythonAnywhere
```

### 2. Instalar dependencias
```bash
# En la consola Bash de PythonAnywhere
cd ~/dental_app
pip3 install --user -r requirements.txt
```

### 3. Configurar variables de entorno
Crea un archivo `.env` en `~/dental_app/` con tus valores de producción.

### 4. Configurar WSGI
En el panel web de PythonAnywhere:
- **Source code**: `/home/<usuario>/dental_app`
- **WSGI configuration file**: apuntar a `/home/<usuario>/dental_app/wsgi.py`

Edita `wsgi.py` si necesitas ajustar la ruta del proyecto.

### 5. Aplicar migraciones
```bash
cd ~/dental_app
python manage.py db upgrade
python manage.py crear_admin
python manage.py seed
```

### 6. Reload
Presiona **Reload** en el panel web de PythonAnywhere.

---

## Seguridad

- **CSRF**: Todas las forms incluyen `{{ csrf_token() }}`. Las peticiones AJAX deben incluir el header `X-CSRFToken` con el valor del meta tag `<meta name="csrf-token">`.
- **Rate Limiting**: `/login` → 10/min | enviar WhatsApp → 20/hora | crear citas → 60/hora
- **Twilio Signature**: El webhook valida la firma `X-Twilio-Signature` en producción.
- **Flask-Talisman**: HTTPS obligatorio + CSP en producción (desactivado en desarrollo).
- **Soft Delete**: Los pacientes no se eliminan físicamente; se marcan con `eliminado=True`.

---

## Variables de entorno críticas

| Variable | Descripción |
|----------|-------------|
| `SECRET_KEY` | Clave de sesión Flask (mínimo 32 chars aleatorios) |
| `FLASK_ENV` | `development` / `production` / `testing` |
| `ANTHROPIC_API_KEY` | Para el bot IA |
| `TWILIO_ACCOUNT_SID` | Para WhatsApp |
| `TWILIO_AUTH_TOKEN` | Para WhatsApp y validación de firma |
| `DATABASE_URL` | SQLite local o PostgreSQL en producción |

---

## Estructura de archivos

```
working/
├── app.py              # Factory + extensiones + error handlers
├── config.py           # Clases Dev/Prod/Test
├── models.py           # 13 modelos SQLAlchemy (incluye User, AuditLog)
├── manage.py           # CLI (db, crear_admin, seed, test, shell)
├── wsgi.py             # Entry point PythonAnywhere
├── requirements.txt
├── .env.example
├── routes/
│   ├── auth.py              # Login/logout/cambiar-password/admin-usuarios
│   ├── api_citas.py
│   ├── api_pacientes.py
│   ├── api_doctores.py
│   ├── api_calendario.py
│   ├── api_crm.py
│   ├── api_configuracion.py
│   └── webhook_whatsapp.py  # Con validación firma Twilio
├── services/
│   ├── ai_receptionist.py
│   ├── whatsapp_service.py
│   ├── scheduler_jobs.py
│   ├── crm_service.py
│   └── pdf_service.py
├── templates/
│   ├── auth/
│   │   ├── login.html
│   │   ├── change_password.html
│   │   └── usuarios.html
│   ├── errors/
│   │   ├── 404.html
│   │   └── 500.html
│   └── ... (resto de templates)
├── static/
│   ├── css/style.css
│   └── js/
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_citas.py
    ├── test_crm.py
    └── test_webhook.py
```
