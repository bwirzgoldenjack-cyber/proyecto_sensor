
print("APP ARRANCO")

from flask import Flask, render_template, request, redirect, session, jsonify, url_for, send_file
from flask_socketio import SocketIO
import pymysql
import pymysql.err
import json
from datetime import datetime, timedelta
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
import os
import io
import tempfile
from dotenv import load_dotenv
import bcrypt
from collections import defaultdict
import time
from contextlib import contextmanager

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "CAMBIAR_ESTO_EN_PRODUCCION")
SENSOR_KEY = os.environ.get("SENSOR_KEY")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

# NOTA: se eliminó el reset diario por cron (APScheduler) de estado_puertas.
# Ya no hace falta: tanto el Dashboard (/conn_puertas) como Sucursales
# (/sucursales_data) calculan entradas/salidas/aforo del día EN VIVO
# filtrando la tabla `historial` por fecha = CURDATE(). Esto es más
# confiable (no depende de que el server esté levantado justo a las 00:00)
# y respeta que estado_puertas siga guardando ultimo_evento_hora para
# fines históricos.
#
# El estado ONLINE/OFFLINE de cada sucursal ya NO se calcula en base a
# ultimo_evento_hora (eso reflejaba "hubo movimiento reciente", no "el
# sensor está prendido"). Ahora se calcula en base a `estado_sensor`,
# que se actualiza vía heartbeat periódico desde sensor.py (ver
# /sensor/heartbeat más abajo).

# CSRF desactivado temporalmente
app.config["WTF_CSRF_ENABLED"] = False

socketio = SocketIO(
    app,
    cors_allowed_origins=os.environ.get("CORS_ORIGIN", "http://localhost:5002"),
    async_mode="threading"
)

# Umbral de tiempo sin heartbeat para considerar una sucursal OFFLINE.
# El sensor manda heartbeat cada 30s (ver sensor.py), así que 90s
# permite perder hasta 2 heartbeats seguidos antes de marcar offline.
HEARTBEAT_TIMEOUT_SEGUNDOS = 90

#====funciones de puertas
@app.route("/agregar_puerta", methods=["POST"])
def agregar_puerta():

    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400
    nombre = data.get("nombre", "").strip().lower()
    sucursal = data.get("sucursal", "").strip().lower()

    if not nombre or not sucursal:
        return jsonify({"error": "Datos incompletos"}), 400

    with db() as cur:

        # buscar sucursal
        cur.execute("""
            SELECT id FROM sucursales
            WHERE LOWER(TRIM(nombre))=%s
        """, (sucursal,))
        s = cur.fetchone()

        if not s:
            return jsonify({"error": "Sucursal no existe"}), 404

        # insertar puerta
        cur.execute("""
            INSERT INTO puertas (nombre, sucursal_id, activa)
            VALUES (%s, %s, 1)
        """, (nombre, s["id"]))

    return jsonify({"ok": True})


# =====================================================
# CONFIG
# =====================================================
def cargar_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except Exception:
        return {"database": ""}


# =====================================================
# DB
# =====================================================
class DatabaseConfigError(Exception):
    pass


def conectar(retries=3, delay=1):
    config = cargar_config()
    nombre_db = config.get("database")

    if not nombre_db:
        raise DatabaseConfigError("Falta database en config.json")

    for i in range(retries):
        try:
            return pymysql.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                user=os.environ.get("DB_USER"),
                password=os.environ.get("DB_PASS"),
                database=nombre_db,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=3,
                read_timeout=5,
                write_timeout=5
            )
        except pymysql.err.OperationalError:
            if i == retries - 1:
                raise
            time.sleep(delay)


@contextmanager
def db():
    conn = None
    cur = None
    try:
        conn = conectar()
        cur = conn.cursor()
        yield cur
        conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB ERROR] {e}")
        raise

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =====================================================
# RATE LIMIT
# =====================================================
login_attempts = defaultdict(list)

def check_rate_limit(ip):
    now = time.time()
    login_attempts[ip] = [t for t in login_attempts[ip] if now - t < 300]
    return len(login_attempts[ip]) < 5


# =====================================================
# AUTH
# =====================================================
def auth():
    return session.get("login", False) is True


# =====================================================
# ROUTES BASE
# =====================================================
@app.route("/")
def inicio():
    return redirect("/acceso-seguro-9x")


@app.route("/acceso-seguro-9x", methods=["GET", "POST"])
def login():
    error = ""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    if request.method == "POST":

        if not check_rate_limit(ip):
            return "Demasiados intentos", 429

        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "").strip().encode()

        admin_user = os.environ.get("ADMIN_USER", "admin")
        admin_hash = os.environ.get("ADMIN_PASS_HASH")

        if not admin_hash:
            return "Falta ADMIN_PASS_HASH", 500

        if usuario == admin_user and bcrypt.checkpw(password, admin_hash.encode()):
            session["login"] = True
            session.permanent = True
            return redirect(url_for("panel"))

        login_attempts[ip].append(time.time())
        error = "Credenciales incorrectas"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =====================================================
# PÁGINAS
# =====================================================
@app.route("/panel")
def panel():
    if not auth():
        return redirect(url_for("login"))
    return render_template("panel.html")


@app.route("/sucursales")
def sucursales():
    if not auth():
        return redirect(url_for("login"))
    return render_template("sucursales.html")


@app.route("/puertas")
def puertas():
    if not auth():
        return redirect(url_for("login"))
    return render_template("puertas.html")


@app.route("/historial")
def historial():
    if not auth():
        return redirect(url_for("login"))
    return render_template("historial.html")


@app.route("/configuracion")
def configuracion():
    if not auth():
        return redirect(url_for("login"))
    config = cargar_config()
    return render_template("configuracion.html", database=config.get("database", ""))


@app.route("/guardar_config", methods=["POST"])
def guardar_config():
    if not auth():
        return redirect(url_for("login"))

    dbname = request.form.get("database", "").strip()

    if not dbname.replace("_", "").replace("-", "").isalnum():
        return "DB inválida", 400

    with open("config.json", "w") as f:
        json.dump({"database": dbname}, f)

    return redirect(url_for("configuracion"))


# =====================================================
# HISTORIAL
# =====================================================
@app.route("/obtener_historial")
def obtener_historial():
    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    fecha = request.args.get("fecha")

    query = """
        SELECT h.id,
               DATE_FORMAT(h.fecha, '%%Y-%%m-%%d') AS fecha,
               TIME_FORMAT(h.hora, '%%H:%%i:%%s') AS hora,
               h.tipo,
               LOWER(TRIM(s.nombre)) AS sucursal,
               LOWER(TRIM(p.nombre)) AS puerta
        FROM historial h
        JOIN puertas p ON p.id = h.puerta_id
        JOIN sucursales s ON s.id = h.sucursal_id
        WHERE h.fecha = %s
        ORDER BY h.id DESC LIMIT 1000
    """

    fecha_filtro = fecha if fecha else datetime.now().strftime("%Y-%m-%d")

    with db() as cur:
        cur.execute(query, (fecha_filtro,))
        data = cur.fetchall()

    return jsonify(data)


# =====================================================
# MOVIMIENTO (CORE)
# =====================================================
TIPOS = {"ENTRADA", "SALIDA"}

@app.route("/movimiento", methods=["POST"])
def movimiento():
    if request.headers.get("X-Sensor-Key") != SENSOR_KEY:
        return jsonify({"error": "No autorizado"}), 401

    data = request.json

    if not data:
        return jsonify({"error": "JSON inválido"}), 400

    puerta = data.get("puerta", "").lower().strip()
    sucursal = data.get("sucursal", "").lower().strip()
    tipo = data.get("tipo", "").upper().strip()

    if tipo not in TIPOS:
        return jsonify({"error": "tipo inválido"}), 400

    with db() as cur:

        cur.execute("""
            SELECT p.id AS puerta_id, s.id AS sucursal_id
            FROM puertas p
            JOIN sucursales s ON s.id = p.sucursal_id
            WHERE LOWER(TRIM(p.nombre))=%s AND LOWER(TRIM(s.nombre))=%s
        """, (puerta, sucursal))

        row = cur.fetchone()

        if not row:
            return jsonify({"error": "No existe"}), 404

        puerta_id = row["puerta_id"]
        sucursal_id = row["sucursal_id"]

        entrada = 1 if tipo == "ENTRADA" else 0
        salida = 1 if tipo == "SALIDA" else 0
        delta = 1 if tipo == "ENTRADA" else -1

        # estado_puertas se sigue actualizando (queda como registro
        # acumulado histórico y para ultimo_evento_hora), pero
        # el Dashboard y Sucursales YA NO leen entradas/salidas/personas
        # de acá para mostrar en pantalla: leen de `historial` filtrado
        # por el día de hoy.
        cur.execute("""
            INSERT INTO estado_puertas
            (puerta_id, entradas, salidas, personas, ultimo_evento_tipo, ultimo_evento_hora)
            VALUES (%s,%s,%s,GREATEST(0,%s),%s,NOW())
            ON DUPLICATE KEY UPDATE
                entradas=entradas+VALUES(entradas),
                salidas=salidas+VALUES(salidas),
                personas=GREATEST(0, personas+%s),
                ultimo_evento_tipo=VALUES(ultimo_evento_tipo),
                ultimo_evento_hora=NOW()
        """, (puerta_id, entrada, salida, delta, tipo, delta))

        now = datetime.now()

        cur.execute("""
            INSERT INTO historial (puerta_id, sucursal_id, tipo, fecha, hora)
            VALUES (%s,%s,%s,%s,%s)
        """, (puerta_id, sucursal_id, tipo, now.date(), now.strftime("%H:%M:%S")))

    # SOCKETIO (BEST EFFORT)
    socketio.emit("nuevo_evento", {
        "puerta": puerta,
        "sucursal": sucursal,
        "tipo": tipo
    })

    return jsonify({"ok": True})


@app.route("/sensor/puertas")
def sensor_puertas():
    if request.headers.get("X-Sensor-Key") != SENSOR_KEY:
        return jsonify({"error": "No autorizado"}), 401

    with db() as cur:
        cur.execute("""
            SELECT p.id, LOWER(TRIM(p.nombre)) AS nombre,
                   LOWER(TRIM(s.nombre)) AS sucursal,
                   p.activa
            FROM puertas p
            JOIN sucursales s ON s.id = p.sucursal_id
        """)
        filas = cur.fetchall()

    return jsonify({"puertas": filas})


@app.route("/sensor/puerta_activa")
def sensor_puerta_activa():
    if request.headers.get("X-Sensor-Key") != SENSOR_KEY:
        return jsonify({"error": "No autorizado"}), 401

    with db() as cur:
        cur.execute("""
            SELECT LOWER(TRIM(p.nombre)) AS nombre,
                   LOWER(TRIM(s.nombre)) AS sucursal
            FROM puertas p
            JOIN sucursales s ON s.id = p.sucursal_id
            WHERE p.activa = 1
        """)
        filas = cur.fetchall()

    if len(filas) == 0:
        return jsonify({"error": "Ninguna puerta activa"}), 404
    if len(filas) > 1:
        return jsonify({"error": "Hay mas de una puerta activa"}), 409

    return jsonify({"puerta": filas[0]["nombre"], "sucursal": filas[0]["sucursal"]})


@app.route("/sensor/heartbeat", methods=["POST"])
def sensor_heartbeat():
    """Recibe un 'sigo vivo' periódico de sensor.py con la sucursal de la
    puerta actualmente activa. Se usa para calcular online/offline real
    (a diferencia de ultimo_evento_hora, que solo reflejaba movimiento)."""
    if request.headers.get("X-Sensor-Key") != SENSOR_KEY:
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400

    sucursal = data.get("sucursal", "").strip().lower()
    if not sucursal:
        return jsonify({"error": "Falta sucursal"}), 400

    with db() as cur:
        cur.execute("SELECT id FROM sucursales WHERE LOWER(TRIM(nombre))=%s", (sucursal,))
        s = cur.fetchone()
        if not s:
            return jsonify({"error": "Sucursal no existe"}), 404

        cur.execute("""
            INSERT INTO estado_sensor (sucursal_id, last_seen)
            VALUES (%s, NOW())
            ON DUPLICATE KEY UPDATE last_seen = NOW()
        """, (s["id"],))

    return jsonify({"ok": True})


# =====================================================
# funciones PUERTAS
# =====================================================
@app.route("/eliminar_puerta/<int:id>", methods=["POST"])
def eliminar_puerta(id):
    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    with db() as cur:
        cur.execute("DELETE FROM estado_puertas WHERE puerta_id=%s", (id,))
        cur.execute("DELETE FROM puertas WHERE id=%s", (id,))

    return jsonify({"ok": True})

@app.route("/editar_puerta/<int:id>", methods=["POST"])
def editar_puerta(id):
    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400
    nombre = data.get("nombre", "").strip().lower()
    if not nombre:
        return jsonify({"error": "Nombre vacío"}), 400

    with db() as cur:
        cur.execute("UPDATE puertas SET nombre=%s WHERE id=%s", (nombre, id))

    return jsonify({"ok": True})


# =====================================================
# PUERTAS
# =====================================================
@app.route("/conn_puertas")
def conn_puertas():
    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    with db() as cur:
        cur.execute("""
            SELECT p.id, LOWER(TRIM(p.nombre)) AS nombre,
                   LOWER(TRIM(s.nombre)) AS sucursal,
                   p.activa,
                   COALESCE(e.entradas,0) entradas,
                   COALESCE(e.salidas,0) salidas,
                   COALESCE(e.personas,0) personas,
                   COALESCE(TIME_FORMAT(e.ultimo_evento_hora,'%H:%i:%s'),'--') ultimo,
                   COALESCE(h.entradas_hoy, 0) AS entradas_hoy,
                   COALESCE(h.salidas_hoy, 0) AS salidas_hoy,
                   GREATEST(0, COALESCE(h.entradas_hoy,0) - COALESCE(h.salidas_hoy,0)) AS personas_hoy
            FROM puertas p
            JOIN sucursales s ON s.id=p.sucursal_id
            LEFT JOIN estado_puertas e ON e.puerta_id=p.id
            LEFT JOIN (
                SELECT puerta_id,
                       SUM(tipo='ENTRADA') AS entradas_hoy,
                       SUM(tipo='SALIDA')  AS salidas_hoy
                FROM historial
                WHERE fecha = CURDATE()
                GROUP BY puerta_id
            ) h ON h.puerta_id = p.id
        """)
        return jsonify({"puertas": cur.fetchall()})


# =====================================================
# EXPORTS
# =====================================================
@app.route("/exportar_excel")
def exportar_excel():
    if not auth():
        return redirect(url_for("login"))

    fecha    = request.args.get("fecha")
    sucursal = request.args.get("sucursal", "").strip().lower()
    tipo     = request.args.get("tipo", "").strip().upper()

    query = """
        SELECT h.fecha, h.hora, h.tipo,
               LOWER(TRIM(s.nombre)) AS sucursal,
               LOWER(TRIM(p.nombre)) AS puerta
        FROM historial h
        JOIN puertas p ON p.id = h.puerta_id
        JOIN sucursales s ON s.id = h.sucursal_id
        WHERE 1=1
    """
    params = []
    if fecha:
        query += " AND h.fecha = %s"
        params.append(fecha)
    if sucursal:
        query += " AND LOWER(TRIM(s.nombre)) LIKE %s"
        params.append(f"%{sucursal}%")
    if tipo in ("ENTRADA", "SALIDA"):
        query += " AND h.tipo = %s"
        params.append(tipo)
    query += " ORDER BY h.id DESC LIMIT 5000"

    with db() as cur:
        cur.execute(query, params)
        df = pd.DataFrame(cur.fetchall())

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="historial.xlsx")


@app.route("/exportar_pdf")
def exportar_pdf():
    if not auth():
        return redirect(url_for("login"))

    fecha    = request.args.get("fecha")
    sucursal = request.args.get("sucursal", "").strip().lower()
    tipo     = request.args.get("tipo", "").strip().upper()

    query = """
        SELECT h.fecha, h.hora, h.tipo,
               LOWER(TRIM(s.nombre)) AS sucursal,
               LOWER(TRIM(p.nombre)) AS puerta
        FROM historial h
        JOIN puertas p ON p.id = h.puerta_id
        JOIN sucursales s ON s.id = h.sucursal_id
        WHERE 1=1
    """
    params = []
    if fecha:
        query += " AND h.fecha = %s"
        params.append(fecha)
    if sucursal:
        query += " AND LOWER(TRIM(s.nombre)) LIKE %s"
        params.append(f"%{sucursal}%")
    if tipo in ("ENTRADA", "SALIDA"):
        query += " AND h.tipo = %s"
        params.append(tipo)
    query += " ORDER BY h.id DESC LIMIT 5000"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = tmp.name
    tmp.close()

    with db() as cur:
        cur.execute(query, params)
        data = cur.fetchall()

    pdf = SimpleDocTemplate(path)

    table = [["fecha","hora","tipo","sucursal","puerta"]]
    for d in data:
        table.append([d["fecha"], d["hora"], d["tipo"], d.get("sucursal",""), d.get("puerta","")])

    t = Table(table)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.grey),
        ("GRID",(0,0),(-1,-1),1,colors.black)
    ]))

    pdf.build([t])

    resp = send_file(path, as_attachment=True, download_name="historial.pdf")

    @resp.call_on_close
    def cleanup():
        try:
            os.remove(path)
        except:
            pass

    return resp

# =====================================================
# SUCURSALES
# =====================================================
@app.route("/obtener_sucursales")
def obtener_sucursales():
    if not auth():
        return jsonify({"error": "No autorizado"}), 401
    with db() as cur:
        cur.execute("SELECT id, LOWER(TRIM(nombre)) AS nombre FROM sucursales ORDER BY nombre")
        return jsonify({"sucursales": cur.fetchall()})


@app.route("/sucursales_data")
def sucursales_data():
    if not auth():
        return jsonify({"error": "No autorizado"}), 401
    with db() as cur:
        cur.execute("""
            SELECT
                s.id,
                LOWER(TRIM(s.nombre)) AS nombre,
                s.activa,
                COALESCE(h.entradas_hoy, 0) AS entradas,
                COALESCE(h.salidas_hoy, 0)  AS salidas,
                GREATEST(0, COALESCE(h.entradas_hoy,0) - COALESCE(h.salidas_hoy,0)) AS personas,
                COUNT(DISTINCT p.id)        AS num_puertas,
                (es.last_seen IS NOT NULL
                    AND es.last_seen > DATE_SUB(NOW(), INTERVAL %s SECOND)) AS online
            FROM sucursales s
            LEFT JOIN puertas p        ON p.sucursal_id = s.id
            LEFT JOIN estado_sensor es ON es.sucursal_id = s.id
            LEFT JOIN (
                SELECT sucursal_id,
                       SUM(tipo='ENTRADA') AS entradas_hoy,
                       SUM(tipo='SALIDA')  AS salidas_hoy
                FROM historial
                WHERE fecha = CURDATE()
                GROUP BY sucursal_id
            ) h ON h.sucursal_id = s.id
            GROUP BY s.id, s.nombre, s.activa, h.entradas_hoy, h.salidas_hoy, es.last_seen
            ORDER BY s.nombre
        """, (HEARTBEAT_TIMEOUT_SEGUNDOS,))
        return jsonify({"sucursales": cur.fetchall()})


@app.route("/toggle_sucursal", methods=["POST"])
def toggle_sucursal():
    """Prende/apaga el flag administrativo `activa` de una sucursal.
    Ojo: esto NO tiene nada que ver con online/offline (eso lo decide
    el heartbeat de sensor.py). Acá pueden convivir varias sucursales
    activas al mismo tiempo, no aplica la lógica de 'una sola' como
    en toggle_puerta."""
    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400
    nombre = data.get("nombre", "").strip().lower()
    if not nombre:
        return jsonify({"error": "Nombre vacío"}), 400

    with db() as cur:
        cur.execute("SELECT id FROM sucursales WHERE LOWER(TRIM(nombre))=%s", (nombre,))
        s = cur.fetchone()
        if not s:
            return jsonify({"error": "No existe"}), 404

        cur.execute("""
            UPDATE sucursales
            SET activa = IF(activa=1,0,1)
            WHERE id=%s
        """, (s["id"],))

    return jsonify({"ok": True})


@app.route("/agregar_sucursal", methods=["POST"])
def agregar_sucursal():
    if not auth():
        return jsonify({"error": "No autorizado"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400
    nombre = data.get("nombre", "").strip().lower()
    if not nombre:
        return jsonify({"error": "Nombre vacío"}), 400
    with db() as cur:
        cur.execute("INSERT INTO sucursales (nombre, activa) VALUES (%s, 1)", (nombre,))
    return jsonify({"ok": True})


# =====================================================
# TOGGLE PUERTA (única definición)
# =====================================================
# Antes había DOS funciones "toggle_puerta" con la misma ruta:
# la primera hacía `activa = IF(activa=1,0,1)` (no garantizaba puerta
# única activa) y además pisaba el endpoint de la segunda, rompiendo
# el arranque de Flask (AssertionError: View function mapping is
# overwriting an existing endpoint function: toggle_puerta).
# Se dejó solo esta versión: desactiva todas las puertas y activa
# únicamente la elegida, en la misma transacción -> atómico, garantiza
# que en todo el sistema haya como máximo una puerta activa.
@app.route("/toggle_puerta/<int:id>", methods=["POST"])
def toggle_puerta(id):

    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    with db() as cur:
        # Desactivar todas
        cur.execute("UPDATE puertas SET activa = 0")

        # Activar solamente la elegida
        cur.execute(
            "UPDATE puertas SET activa = 1 WHERE id = %s",
            (id,)
        )

    return jsonify({"ok": True})


@app.route("/eliminar_sucursal", methods=["POST"])
def eliminar_sucursal():
    if not auth():
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400
    nombre = data.get("nombre", "").strip().lower()

    with db() as cur:
        cur.execute("SELECT id FROM sucursales WHERE LOWER(TRIM(nombre))=%s", (nombre,))
        s = cur.fetchone()
        if not s:
            return jsonify({"error": "No existe"}), 404

        sid = s["id"]

        # JOIN en lugar de subquery
        cur.execute("""
            DELETE ep FROM estado_puertas ep
            JOIN puertas p ON p.id = ep.puerta_id
            WHERE p.sucursal_id = %s
        """, (sid,))

        cur.execute("DELETE FROM historial WHERE sucursal_id=%s", (sid,))
        cur.execute("DELETE FROM puertas WHERE sucursal_id=%s", (sid,))
        cur.execute("DELETE FROM sucursales WHERE id=%s", (sid,))

    return jsonify({"ok": True})

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    print("LLEGUE AL MAIN")
    socketio.run(app, host="0.0.0.0", port=5002, debug=False, allow_unsafe_werkzeug=True)
