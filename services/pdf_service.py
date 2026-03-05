"""Generación de justificantes médicos en PDF con xhtml2pdf."""
import os
from io import BytesIO
from datetime import datetime
from flask import current_app, render_template
from models import db, Justificante


def generar_justificante(cita_id: int, tratamiento: str = None, escuela: str = None) -> dict:
    """
    Genera el PDF del justificante para una cita y lo guarda.
    Retorna dict con {justificante_id, pdf_bytes, numero}.
    """
    from models import Cita

    cita = Cita.query.get_or_404(cita_id)
    paciente = cita.paciente

    # Determinar escuela
    if not escuela:
        escuela = paciente.nombre_escuela or ''

    # Determinar tratamiento
    if not tratamiento:
        tratamiento = cita.tipo_cita.nombre if cita.tipo_cita else 'Consulta dental'

    # Número de justificante
    numero = _generar_numero()

    # Renderizar HTML
    html_content = render_template(
        'justificante.html',
        paciente=paciente,
        cita=cita,
        tratamiento=tratamiento,
        escuela=escuela,
        fecha_emision=datetime.now().strftime('%d de %B de %Y'),
        numero_justificante=numero,
        consultorio_nombre=current_app.config.get('CONSULTORIO_NOMBRE', 'La Casa del Sr. Pérez'),
        consultorio_direccion=current_app.config.get('CONSULTORIO_DIRECCION', ''),
        consultorio_telefono=current_app.config.get('CONSULTORIO_TELEFONO', ''),
    )

    # Generar PDF
    pdf_bytes = _html_to_pdf(html_content)

    # Guardar en disco
    pdf_dir = os.path.join(current_app.root_path, 'static', 'justificantes')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f'justificante_{numero}.pdf')
    with open(pdf_path, 'wb') as f:
        f.write(pdf_bytes)

    # Registrar en BD
    justificante = Justificante(
        paciente_id=paciente.id,
        cita_id=cita.id,
        tratamiento=tratamiento,
        escuela=escuela,
        fecha_emision=datetime.now().date(),
        numero_justificante=numero,
        pdf_path=pdf_path,
    )
    db.session.add(justificante)
    db.session.commit()

    return {
        'justificante_id': justificante.id,
        'numero': numero,
        'pdf_bytes': pdf_bytes,
    }


def _html_to_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    buf = BytesIO()
    pisa_status = pisa.CreatePDF(html.encode('utf-8'), dest=buf, encoding='utf-8')
    if pisa_status.err:
        raise RuntimeError(f'Error generando PDF: {pisa_status.err}')
    return buf.getvalue()


def _generar_numero() -> str:
    """Genera número secuencial de justificante: JUST-YYYYMMDD-NNNN."""
    hoy = datetime.now().strftime('%Y%m%d')
    ultimo = Justificante.query.filter(
        Justificante.numero_justificante.like(f'JUST-{hoy}-%')
    ).count()
    return f'JUST-{hoy}-{ultimo + 1:04d}'
