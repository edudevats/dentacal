from extensions import db
from edr.models import MetodoPago


def seed_edr_catalogos():
    existing = {metodo.nombre for metodo in MetodoPago.query.all()}
    for nombre in ('Efectivo', 'Tarjeta', 'Transferencia'):
        if nombre not in existing:
            db.session.add(MetodoPago(nombre=nombre))
    db.session.commit()
