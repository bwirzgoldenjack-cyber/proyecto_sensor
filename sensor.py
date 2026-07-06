
import os
from dotenv import load_dotenv
load_dotenv()
SENSOR_KEY = os.environ.get("SENSOR_KEY")

try:
    from gpiozero import DigitalInputDevice
    from gpiozero.pins.lgpio import LGPIOFactory
    from gpiozero import Device
    Device.pin_factory = LGPIOFactory()
    GPIO_REAL = True
except Exception:
    GPIO_REAL = False
    print("⚠️ Modo simulación activado (sin GPIO reales)")
import requests
import time
import json
import logging
import threading
from datetime import datetime

# =====================================================
# CONFIGURACIÓN — editá estos valores
# =====================================================

SERVIDOR = "http://localhost:5002"   # URL del servidor Flask

PIN_EXTERIOR = 17   # GPIO17 - sensor del lado de afuera
PIN_INTERIOR = 27   # GPIO27 - sensor del lado de adentro

# ==========================
# PUERTA ACTIVA
# ==========================
puertaActivaID = None

# ==========================
# CONTADORES POR PUERTA (se llena solo desde /sensor/puertas)
# ==========================
puertas = {}

TIEMPO_ESPERA_SEGUNDO_SENSOR = 2.0
COOLDOWN_ENTRE_EVENTOS = 1.0

HEARTBEAT_INTERVALO = 30  # segundos

# =====================================================
# LOGGING
# =====================================================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("sensor.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# =====================================================
# SETUP GPIO
# =====================================================
sensor_exterior = None
sensor_interior = None

if GPIO_REAL:
    sensor_exterior = DigitalInputDevice(PIN_EXTERIOR, pull_up=True, bounce_time=0.2)
    sensor_interior = DigitalInputDevice(PIN_INTERIOR, pull_up=True, bounce_time=0.2)

log.info("GPIO inicializado. Esperando eventos...")

estado = {
    "primer_sensor": None,
    "tiempo_activacion": None,
    "ultimo_evento": 0
}

def actualizar_puertas_desde_servidor():
    global puertaActivaID
    try:
        r = requests.get(
            f"{SERVIDOR}/sensor/puertas",
            headers={"X-Sensor-Key": SENSOR_KEY},
            timeout=3
        )
        if r.status_code != 200:
            log.warning(f"No se pudo obtener puertas: {r.status_code} {r.text}")
            return False

        data = r.json()
        encontrada_activa = False

        for p in data.get("puertas", []):
            pid = p["id"]
            if pid not in puertas:
                puertas[pid] = {"nombre": p["nombre"], "sucursal": p["sucursal"],
                                 "ingresos": 0, "egresos": 0}
            else:
                puertas[pid]["nombre"] = p["nombre"]
                puertas[pid]["sucursal"] = p["sucursal"]

            if p["activa"]:
                puertaActivaID = pid
                encontrada_activa = True

        if not encontrada_activa:
            log.warning("Ninguna puerta activa en el servidor.")
            puertaActivaID = None

        return True
    except requests.exceptions.RequestException as e:
        log.error(f"Error consultando puertas: {e}")
        return False


def enviar_movimiento(puerta, sucursal, tipo):
    try:
        r = requests.post(
            f"{SERVIDOR}/movimiento",
            headers={"X-Sensor-Key": SENSOR_KEY},
            json={
                "puerta": puerta,
                "sucursal": sucursal,
                "tipo": tipo
            },
            timeout=3
        )
        if r.status_code == 200:
            log.info(f"OK → {tipo} en {puerta} ({sucursal})")
        else:
            log.warning(f"Respuesta inesperada {r.status_code}: {r.text}")
    except requests.exceptions.ConnectionError:
        log.error(f"No se pudo conectar al servidor en {SERVIDOR}")
    except requests.exceptions.Timeout:
        log.error("Timeout al conectar con el servidor")
    except Exception as e:
        log.error(f"Error inesperado: {e}")


def enviar_heartbeat():
    """Corre en un thread separado. Cada HEARTBEAT_INTERVALO segundos le
    avisa al servidor que el sensor sigue vivo, mandando la sucursal de
    la puerta actualmente activa.

    IMPORTANTE: acá también se refresca puertaActivaID consultando al
    servidor. Antes esto solo se actualizaba al arrancar el script o
    cuando pasaba alguien físicamente por el sensor (evento GPIO), así
    que si activabas una puerta desde el dashboard y nadie caminaba por
    ahí, el sensor se quedaba con el dato viejo cacheado indefinidamente
    y nunca mandaba heartbeat -> la sucursal quedaba en SIN SEÑAL aunque
    estuviera todo bien configurado del lado del servidor."""
    while True:
        try:
            actualizar_puertas_desde_servidor()

            if puertaActivaID is not None and puertaActivaID in puertas:
                sucursal = puertas[puertaActivaID]["sucursal"]
                r = requests.post(
                    f"{SERVIDOR}/sensor/heartbeat",
                    headers={"X-Sensor-Key": SENSOR_KEY},
                    json={"sucursal": sucursal},
                    timeout=3
                )
                if r.status_code == 200:
                    log.debug(f"heartbeat OK → {sucursal}")
                else:
                    log.warning(f"heartbeat respuesta inesperada {r.status_code}: {r.text}")
            else:
                log.debug("heartbeat omitido: no hay puerta activa valida")
        except requests.exceptions.RequestException as e:
            log.error(f"Error enviando heartbeat: {e}")
        except Exception as e:
            log.error(f"Error inesperado en heartbeat: {e}")

        time.sleep(HEARTBEAT_INTERVALO)


def hacer_callback(lado):
    def callback():
        ahora = time.time()
        est = estado

        if ahora - est["ultimo_evento"] < COOLDOWN_ENTRE_EVENTOS:
            return

        if est["primer_sensor"] is None:
            est["primer_sensor"] = lado
            est["tiempo_activacion"] = ahora
            log.debug(f"primer sensor activado = {lado}")

        else:
            tiempo_transcurrido = ahora - est["tiempo_activacion"]

            if tiempo_transcurrido <= TIEMPO_ESPERA_SEGUNDO_SENSOR:
                if est["primer_sensor"] == "exterior" and lado == "interior":
                    tipo = "ENTRADA"
                elif est["primer_sensor"] == "interior" and lado == "exterior":
                    tipo = "SALIDA"
                else:
                    est["primer_sensor"] = None
                    est["tiempo_activacion"] = None
                    return

                actualizar_puertas_desde_servidor()

                if puertaActivaID is None or puertaActivaID not in puertas:
                    log.warning("Evento detectado pero no hay puerta activa valida. Se ignora.")
                else:
                    p = puertas[puertaActivaID]

                    if tipo == "ENTRADA":
                        p["ingresos"] += 1
                    else:
                        p["egresos"] += 1

                    log.info(f"[{tipo}] {p['nombre']} -> ingresos={p['ingresos']} egresos={p['egresos']}")

                    enviar_movimiento(p["nombre"], p["sucursal"], tipo)

                est["ultimo_evento"] = ahora

            else:
                log.debug("timeout entre sensores, reseteando")
                est["primer_sensor"] = None
                est["tiempo_activacion"] = None
                return

            est["primer_sensor"] = None
            est["tiempo_activacion"] = None

    return callback

if GPIO_REAL:
    sensor_exterior.when_activated = hacer_callback("exterior")
    sensor_interior.when_activated = hacer_callback("interior")
    actualizar_puertas_desde_servidor()

hilo_heartbeat = threading.Thread(target=enviar_heartbeat, daemon=True)
hilo_heartbeat.start()
log.info(f"Heartbeat iniciado (cada {HEARTBEAT_INTERVALO}s).")

log.info("Monitoreando sensor compartido. Ctrl+C para salir.")

try:
    while True:
        time.sleep(0.1)

except KeyboardInterrupt:
    log.info("Detenido por el usuario.")

finally:
    if GPIO_REAL:
        sensor_exterior.close()
        sensor_interior.close()
    log.info("GPIO liberado.")
