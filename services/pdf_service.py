"""
Generacion de PDFs para justificantes medicos.
Usa xhtml2pdf para convertir HTML a PDF.
"""
import logging
from io import BytesIO
from flask import render_template, current_app

logger = logging.getLogger(__name__)


def generar_justificante_pdf(justificante):
    """
    Genera el PDF del justificante medico.
    Retorna bytes del PDF.
    """
    try:
        from xhtml2pdf import pisa

        html = render_template(
            'justificante_pdf.html',
            justificante=justificante,
            paciente=justificante.paciente,
        )

        pdf_buffer = BytesIO()
        resultado = pisa.CreatePDF(
            src=html,
            dest=pdf_buffer,
            encoding='utf-8',
        )

        if resultado.err:
            raise Exception(f'Error xhtml2pdf: {resultado.err}')

        pdf_buffer.seek(0)
        return pdf_buffer.read()

    except ImportError:
        logger.error('xhtml2pdf no instalado. Instalar con: pip install xhtml2pdf')
        raise ImportError('xhtml2pdf no disponible. Ejecuta: pip install xhtml2pdf')
    except Exception as e:
        logger.error(f'Error generando PDF: {e}')
        raise
