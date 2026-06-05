from flask import Flask, render_template, request, redirect, session, jsonify, url_for, send_file
from flask_socketio import SocketIO
import pymysql
import json
from datetime import datetime
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
import os

app = Flask(__name__)
app.secret_key = "goldenjack"

socketio = SocketIO(app, cors_allowed_origins="*")

# =====================================================
# CONFIG
# =====================================================
def cargar_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except:
        return {"database": ""}

# =====================================================
# MYSQL
# =====================================================
def conectar():
    config = cargar_config()
    return pymysql.connect(
        host="localhost",
        user="root",
        password="",
        database=config["database"],
        cursorclass=pymysql.cursors.DictCursor
    )

# =====================================================
# LOGIN
# =====================================================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        if request.form["usuario"] == "admin" and request.form["password"] == "1234":
            session["login"] = True
            return redirect(url_for("panel"))
        error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error)

# =====================================================
# PROTECCIÓN SIMPLE
# =====================================================
def auth():
    return "login" in session

# =====================================================
# PANEL / PÁGINAS
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

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/configuracion")
def configuracion():

    if "login" not in session:
        return redirect(url_for("login"))

    config = cargar_config()

    return render_template(
        "configuracion.html",
        database=config.get("database", "")
    )

@app.route("/guardar_config", methods=["POST"])
def guardar_config():

    if "login" not in session:
        return redirect(url_for("login"))

    database = request.form.get("database", "").strip()

    with open("config.json", "w") as f:
        json.dump(
            {"database": database},
            f,
            indent=4
        )

    return redirect(url_for("configuracion"))

# =====================================================
# HISTORIAL
# =====================================================
@app.route("/obtener_historial")
def obtener_historial():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM historial ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "id": d["id"],
            "fecha": str(d["fecha"]),
            "hora": str(d["hora"]),
            "tipo": d["tipo"],
            "sucursal": d["sucursal"].lower().strip(),
            "puerta": d["puerta"].lower().strip()
        } for d in data
    ])

# =====================================================
# MOVIMIENTO (TIEMPO REAL)
# =====================================================
@app.route("/movimiento", methods=["POST"])
def movimiento():
    conn = conectar()
    cur = conn.cursor()

    data = request.json

    puerta = data["puerta"].lower().strip()
    sucursal = data["sucursal"].lower().strip()
    tipo = data["tipo"].upper().strip()

    now = datetime.now()

    if tipo == "ENTRADA":
        cur.execute("""
            UPDATE registros
            SET personas = personas + 1,
                entradas = entradas + 1,
                tipo='ENTRADA',
                fecha=CURDATE(),
                hora=CURTIME()
            WHERE LOWER(TRIM(puerta))=%s
        """, (puerta,))

    elif tipo == "SALIDA":
        cur.execute("""
            UPDATE registros
            SET personas = CASE WHEN personas > 0 THEN personas - 1 ELSE 0 END,
                salidas = salidas + 1,
                tipo='SALIDA',
                fecha=CURDATE(),
                hora=CURTIME()
            WHERE LOWER(TRIM(puerta))=%s
        """, (puerta,))

    cur.execute("""
        INSERT INTO historial (fecha, hora, tipo, sucursal, puerta)
        VALUES (%s,%s,%s,%s,%s)
    """, (
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        tipo,
        sucursal,
        puerta
    ))

    conn.commit()
    conn.close()

    socketio.emit("nuevo_evento", {
        "tipo": tipo,
        "sucursal": sucursal,
        "puerta": puerta
    })

    return jsonify({"ok": True})

# =====================================================
# PUERTAS (🔥 FIX DEFINITIVO)
# =====================================================
@app.route("/conn_puertas")
def conn_puertas():

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            p.id,
            LOWER(TRIM(p.nombre)) AS nombre,
            LOWER(TRIM(p.sucursal)) AS sucursal,
            p.activa,

            COALESCE(r.entradas,0) AS entradas,
            COALESCE(r.salidas,0) AS salidas,
            COALESCE(r.personas,0) AS personas,
            COALESCE(TIME_FORMAT(r.hora,'%H:%i:%s'),'--:--:--') AS ultimo

        FROM puertas p

        LEFT JOIN registros r
        ON LOWER(TRIM(r.puerta)) = LOWER(TRIM(p.nombre))
    """)

    puertas = cur.fetchall()

    conn.close()

    resultado = []

    for p in puertas:

        resultado.append({
            "id": p["id"],
            "puerta": p["nombre"],
            "sucursal": p["sucursal"],
            "entradas": p["entradas"],
            "salidas": p["salidas"],
            "personas": p["personas"],
            "online": bool(p["activa"]),
            "ultimo": p["ultimo"]
        })

    return jsonify({"puertas": resultado})
# =====================================================
# EXPORT EXCEL
# =====================================================
@app.route("/exportar_excel")
def exportar_excel():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM historial ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()

    df = pd.DataFrame(data)

    file = "historial.xlsx"
    df.to_excel(file, index=False)

    return send_file(file, as_attachment=True)

# =====================================================
# EXPORT PDF
# =====================================================
@app.route("/exportar_pdf")
def exportar_pdf():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM historial ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()

    file = "historial.pdf"
    pdf = SimpleDocTemplate(file)

    table_data = [["Fecha","Hora","Tipo","Sucursal","Puerta"]]

    for d in data:
        table_data.append([
            d["fecha"], d["hora"], d["tipo"], d["sucursal"], d["puerta"]
        ])

    table = Table(table_data)
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.gold),
        ("GRID",(0,0),(-1,-1),1,colors.black)
    ]))

    pdf.build([table])

    return send_file(file, as_attachment=True)

# =====================================================
# SUCURSALES LIST
# =====================================================
@app.route("/sucursales_list")
def sucursales_list():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT LOWER(TRIM(sucursal)) sucursal FROM puertas")
    data = cur.fetchall()
    conn.close()

    return jsonify({
        "sucursales": [d["sucursal"] for d in data]
    })
#------------------------------------------------
@app.route("/agregar_puerta", methods=["POST"])
def agregar_puerta():

    conn = conectar()
    cur = conn.cursor()

    data = request.json

    nombre = data["nombre"].strip()
    sucursal = data["sucursal"].strip().lower()

    cur.execute("""
        INSERT INTO puertas
        (nombre, sucursal, activa)
        VALUES (%s,%s,1)
    """, (nombre, sucursal))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})
#========================================================
@app.route("/toggle_puerta/<int:id>", methods=["POST"])
def toggle_puerta(id):

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        UPDATE puertas
        SET activa = NOT activa
        WHERE id = %s
    """, (id,))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})
#======================================================
@app.route("/editar_puerta/<int:id>", methods=["POST"])
def editar_puerta(id):

    conn = conectar()
    cur = conn.cursor()

    data = request.json

    cur.execute("""
        UPDATE puertas
        SET nombre=%s
        WHERE id=%s
    """, (
        data["nombre"],
        id
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/eliminar_puerta/<int:id>", methods=["POST"])
def eliminar_puerta(id):

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM puertas
        WHERE id=%s
    """, (id,))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)