from app import create_app
from models import db, Doctor, SystemSettings
from datetime import time

app = create_app()

with app.app_context():
    db.create_all()
    
    # Check if doctors exist, otherwise create a mock one
    if Doctor.query.count() == 0:
        doc = Doctor(
            nombre='Dr. Juan Perez',
            email='juan.perez.test@example.com',
            google_calendar_id='primary', # Usually admin's primary
            hora_inicio_trabajo=time(9, 0),
            hora_fin_trabajo=time(17, 0)
        )
        db.session.add(doc)
        db.session.commit()
        print("Database initialized with sample Doctor.")
    else:
        print("Doctor table already initialized.")
        
    if SystemSettings.query.count() == 0:
        settings = SystemSettings(
            clinic_name="MediCal",
            admin_calendar_id="primary"
        )
        db.session.add(settings)
        db.session.commit()
        print("Database initialized with default System Settings.")
    else:
        print("System Settings already initialized.")
