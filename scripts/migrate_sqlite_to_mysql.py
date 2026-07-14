"""
migrate_sqlite_to_mysql.py
Migra los datos de la app (SQLite) → MySQL de PythonAnywhere vía túnel SSH.

Adaptado para "La Casa del Sr. Perez":
  - Usa PyMySQL (ya está en requirements.txt), no MySQLdb.
  - Fuente SQLite = app.db en la raíz del proyecto (configurable).
  - Crea el esquema en MySQL automáticamente desde los modelos (db.metadata).
  - INSERT IGNORE: es idempotente, se puede correr varias veces sin duplicar.

SEGURIDAD — las credenciales NO se guardan en este archivo. Se leen de variables
de entorno; si falta alguna contraseña, el script la pide al arrancar (oculta).
Variables reconocidas (todas opcionales salvo las contraseñas):
    SSH_HOST (def: ssh.pythonanywhere.com)   SSH_USER (def: edudracos)   SSH_PASS
    PA_MYSQL_HOST (def: edudracos.mysql.pythonanywhere-services.com)
    PA_MYSQL_USER (def: edudracos)   PA_MYSQL_PASS
    PA_MYSQL_DB   (def: edudracos$dentacal)
    SQLITE_PATH   (def: <raíz>/app.db)

Dependencias (instalar en tu máquina local):
    python -m pip install pymysql sshtunnel

Uso:
    python scripts/migrate_sqlite_to_mysql.py
"""

import os
import sys
import json
import getpass
import sqlite3

import pymysql
import sshtunnel
from sqlalchemy import create_engine
from urllib.parse import quote_plus

# ─── Rutas / imports del proyecto ─────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, PROJECT_ROOT)  # para poder importar models / extensions

# ─── CONFIGURACIÓN (credenciales desde entorno; contraseñas se piden si faltan) ─
SQLITE_PATH = os.environ.get("SQLITE_PATH", os.path.join(PROJECT_ROOT, "app.db"))

SSH_HOST = os.environ.get("SSH_HOST", "ssh.pythonanywhere.com")
SSH_USER = os.environ.get("SSH_USER", "edudracos")
SSH_PASS = os.environ.get("SSH_PASS")  # se pide si falta

MYSQL_HOST_REMOTE = os.environ.get("PA_MYSQL_HOST", "edudracos.mysql.pythonanywhere-services.com")
MYSQL_PORT = 3306
MYSQL_USER = os.environ.get("PA_MYSQL_USER", "edudracos")
MYSQL_PASS = os.environ.get("PA_MYSQL_PASS")  # se pide si falta
MYSQL_DB = os.environ.get("PA_MYSQL_DB", "edudracos$dentacal")
# ──────────────────────────────────────────────────────────────────────────────

SKIP_TABLES = {"alembic_version", "sqlite_sequence"}
BATCH = 1000  # filas por lote en executemany

sshtunnel.SSH_TIMEOUT = 15.0
sshtunnel.TUNNEL_TIMEOUT = 15.0


# ─── FASE 1: CONEXIONES ───────────────────────────────────────────────────────

def phase1_connect():
    global SSH_PASS, MYSQL_PASS
    print("\n" + "=" * 60)
    print("FASE 1: CONEXIONES")
    print("=" * 60)

    if not os.path.exists(SQLITE_PATH):
        print(f"  ERROR: No se encontró el SQLite en {SQLITE_PATH}")
        print("  Sugerencia: descarga el app.db de producción y ponlo ahí,")
        print("  o exporta SQLITE_PATH=/ruta/al/app.db")
        sys.exit(1)

    if not SSH_PASS:
        SSH_PASS = getpass.getpass(f"  Contraseña SSH de PythonAnywhere ({SSH_USER}): ")
    if not MYSQL_PASS:
        MYSQL_PASS = getpass.getpass(f"  Contraseña MySQL de PythonAnywhere ({MYSQL_USER}): ")

    print(f"  SQLite: {SQLITE_PATH} ... ", end="", flush=True)
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    print("OK")

    print(f"  Túnel SSH → {SSH_HOST} ... ", end="", flush=True)
    tunnel = sshtunnel.SSHTunnelForwarder(
        SSH_HOST,
        ssh_username=SSH_USER,
        ssh_password=SSH_PASS,
        remote_bind_address=(MYSQL_HOST_REMOTE, MYSQL_PORT),
    )
    tunnel.start()
    print(f"OK  (puerto local {tunnel.local_bind_port})")

    print(f"  MySQL 127.0.0.1:{tunnel.local_bind_port} → {MYSQL_DB} ... ", end="", flush=True)
    mysql_conn = pymysql.connect(
        host="127.0.0.1",
        port=tunnel.local_bind_port,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        database=MYSQL_DB,
        charset="utf8mb4",
        autocommit=False,
    )
    print("OK")

    return sqlite_conn, mysql_conn, tunnel


# ─── FASE 2: CREAR ESQUEMA EN MYSQL (desde los modelos) ───────────────────────

def phase2_create_schema(tunnel_port):
    print("\n" + "=" * 60)
    print("FASE 2: CREAR ESQUEMA EN MYSQL (si falta)")
    print("=" * 60)

    # Importar los modelos registra todas las tablas en db.metadata
    from extensions import db
    import models  # noqa: F401

    url = (
        f"mysql+pymysql://{quote_plus(MYSQL_USER)}:{quote_plus(MYSQL_PASS)}"
        f"@127.0.0.1:{tunnel_port}/{quote_plus(MYSQL_DB)}?charset=utf8mb4"
    )
    engine = create_engine(url)
    db.metadata.create_all(engine)  # idempotente: solo crea las que faltan
    engine.dispose()
    print(f"  Esquema verificado/creado: {len(db.metadata.tables)} tablas.")


# ─── FASE 3: VERIFICACIÓN ─────────────────────────────────────────────────────

def phase3_verify(sqlite_conn, mysql_conn):
    print("\n" + "=" * 60)
    print("FASE 3: VERIFICACIÓN DE TABLAS")
    print("=" * 60)

    cur = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    sqlite_tables = {row[0] for row in cur} - SKIP_TABLES

    cur = mysql_conn.cursor()
    cur.execute("SHOW TABLES")
    mysql_tables = {row[0] for row in cur.fetchall()} - SKIP_TABLES

    print(f"  SQLite : {len(sqlite_tables)} tablas")
    print(f"  MySQL  : {len(mysql_tables)} tablas")

    missing = sqlite_tables - mysql_tables
    if missing:
        print("\n  ERROR: Estas tablas existen en SQLite pero NO en MySQL:")
        for t in sorted(missing):
            print(f"    - {t}")
        print("\n  (La Fase 2 debió crearlas. Revisa errores arriba.)")
        sys.exit(1)

    print(f"\n  {'Tabla':<42} {'Filas':>8}")
    print(f"  {'-'*42} {'-'*8}")
    table_counts = {}
    for table in sorted(sqlite_tables):
        n = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        table_counts[table] = n
        marker = "" if n > 0 else "  (vacía)"
        print(f"  {table:<42} {n:>8,}{marker}")

    total = sum(table_counts.values())
    print(f"\n  Total a migrar: {total:,} filas")
    return sqlite_tables, table_counts


# ─── FASE 4: MIGRACIÓN ────────────────────────────────────────────────────────

def phase4_migrate(sqlite_conn, mysql_conn, tables, table_counts):
    print("\n" + "=" * 60)
    print("FASE 4: MIGRACIÓN DE DATOS")
    print("=" * 60)
    print("  INSERT IGNORE: filas ya existentes en MySQL se omiten.\n")

    cursor = mysql_conn.cursor()
    # sql_mode permisivo: evita que microsegundos en fechas o valores límite
    # aborten la migración por el modo estricto de MySQL.
    cursor.execute("SET SESSION sql_mode = ''")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    total_inserted = 0
    errors = []

    for table in sorted(tables):
        count = table_counts[table]
        if count == 0:
            print(f"  {table:<42} (vacía, saltada)")
            continue

        print(f"  {table:<42} {count:>8,} filas ... ", end="", flush=True)
        try:
            rows = sqlite_conn.execute(f'SELECT * FROM "{table}"').fetchall()
            columns = list(rows[0].keys())
            col_names = ", ".join(f"`{c}`" for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT IGNORE INTO `{table}` ({col_names}) VALUES ({placeholders})"

            inserted = 0
            for i in range(0, len(rows), BATCH):
                chunk = rows[i:i + BATCH]
                data = [tuple(_coerce(r[c]) for c in columns) for r in chunk]
                cursor.executemany(sql, data)
                inserted += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            mysql_conn.commit()

            ignored = count - inserted
            total_inserted += inserted
            print(f"OK  ({inserted:,} insertadas, {ignored:,} ya existían)")
        except Exception as exc:
            mysql_conn.rollback()
            errors.append((table, str(exc)))
            print(f"ERROR\n    {exc}")

    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    mysql_conn.commit()

    print(f"\n  Filas insertadas: {total_inserted:,}")
    if errors:
        print(f"\n  ERRORES en {len(errors)} tabla(s):")
        for table, err in errors:
            print(f"    {table}: {err}")
        return False
    return True


# ─── FASE 5: VALIDACIÓN POST-MIGRACIÓN ────────────────────────────────────────

def phase5_validate(sqlite_conn, mysql_conn, tables):
    print("\n" + "=" * 60)
    print("FASE 5: VALIDACIÓN (conteos SQLite vs MySQL)")
    print("=" * 60)
    cur = mysql_conn.cursor()
    all_ok = True
    for table in sorted(tables):
        s = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        m = cur.fetchone()[0]
        estado = "OK" if m >= s else "FALTAN FILAS"
        if m < s:
            all_ok = False
        print(f"  {table:<42} SQLite={s:>7,}  MySQL={m:>7,}  {estado}")
    return all_ok


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _coerce(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    return value


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  La Casa del Sr. Perez — SQLite → MySQL (PythonAnywhere)")
    print("=" * 60)

    sqlite_conn = mysql_conn = tunnel = None
    try:
        sqlite_conn, mysql_conn, tunnel = phase1_connect()
        phase2_create_schema(tunnel.local_bind_port)
        tables, counts = phase3_verify(sqlite_conn, mysql_conn)

        print()
        if input("¿Continuar con la migración? [s/N]: ").strip().lower() != "s":
            print("Cancelado.")
            return

        ok = phase4_migrate(sqlite_conn, mysql_conn, tables, counts)
        valid = phase5_validate(sqlite_conn, mysql_conn, tables)

        if ok and valid:
            print("\n✅ Migración completada y validada. Todos los conteos cuadran.")
        else:
            print("\n⚠️  Migración terminó con avisos. Revisa los mensajes de arriba.")
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        if sqlite_conn:
            sqlite_conn.close()
        if mysql_conn:
            mysql_conn.close()
        if tunnel and tunnel.is_active:
            tunnel.stop()
            print("Túnel SSH cerrado.")


if __name__ == "__main__":
    main()
