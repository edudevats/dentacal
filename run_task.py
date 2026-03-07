"""
Script para ejecutar jobs como Scheduled Tasks de PythonAnywhere.
Reemplaza APScheduler en producción.

Uso en PythonAnywhere Scheduled Tasks:
  python /home/edudracos/dentacal/run_task.py recordatorios_24h
  python /home/edudracos/dentacal/run_task.py postconsulta
  python /home/edudracos/dentacal/run_task.py resumen_doctores
  python /home/edudracos/dentacal/run_task.py seguimientos_crm
  python /home/edudracos/dentacal/run_task.py cumpleanos
"""
import sys
import os

# Asegurar que el directorio del proyecto está en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

JOBS = {
    'recordatorios_24h': '_job_recordatorios_24h',
    'postconsulta':       '_job_postconsulta',
    'resumen_doctores':   '_job_resumen_doctores',
    'seguimientos_crm':   '_job_seguimientos_crm',
    'cumpleanos':         '_job_cumpleanos',
}

if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        print(f'Uso: python run_task.py <job>')
        print(f'Jobs disponibles: {", ".join(JOBS)}')
        sys.exit(1)

    job_name = sys.argv[1]
    func_name = JOBS[job_name]

    from app import create_app
    app = create_app('production')

    from services.reminder_service import (
        _job_recordatorios_24h, _job_postconsulta, _job_resumen_doctores,
        _job_seguimientos_crm, _job_cumpleanos,
    )

    jobs_map = {
        'recordatorios_24h': _job_recordatorios_24h,
        'postconsulta':       _job_postconsulta,
        'resumen_doctores':   _job_resumen_doctores,
        'seguimientos_crm':   _job_seguimientos_crm,
        'cumpleanos':         _job_cumpleanos,
    }

    print(f'[run_task] Ejecutando: {job_name}')
    jobs_map[job_name](app)
    print(f'[run_task] Completado: {job_name}')
