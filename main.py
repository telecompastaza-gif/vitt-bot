import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
WEBHOOK_VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN", "vitt_webhook_2024")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
MAKE_WEBHOOK_URL = "https://hook.us2.make.com/8ijx9fi544dbdh9eprkukhsgjdd823hn"

conversation_history = {}
agendamiento_state = {}

SYSTEM_PROMPT = """Eres el asistente virtual de VITT, empresa de soluciones tecnologicas integrales en Puyo, Pastaza, Ecuador. Tu nombre es Asistente VITT.

PLANES DE INTERNET (Fibra Optica):
- BASICO: 100 Mbps - $15/mes - Solo internet
- INTERMEDIO: 200 Mbps - $20/mes - Solo internet
- AVANZADO: 400 Mbps - $25/mes - Internet + Vitt TV
- PREMIUM: 500 Mbps - $30/mes - Internet + Vitt TV
- ELITE: 700 Mbps - $35/mes - Internet + Vitt TV + Vitt Cam

TODOS LOS PLANES INCLUYEN: Fibra Optica, Soporte Tecnico, Monitoreo, Atencion Local.
CONDICIONES: Instalacion varia segun plan. Sujeto a cobertura.

TV VITT: +90 canales en vivo. Incluido desde plan Avanzado.

VITT CAM: $5/camara/mes. Grabacion nube 3 dias. Incluido en plan Elite.

VITT TRACK (Rastreo GPS 24/7):
Vehiculos livianos: GPS Normal $180/anio, GPS+Puertas+Antijammer $280/anio, GPS+Panico $200/anio
Vehiculos pesados: GPS Normal $200/anio, GPS+Puertas+Antijammer $300/anio, GPS+Panico $220/anio
Renovacion: $65/anio."""


def call_claude(phone, user_message):
    if phone not in conversation_history:
        conversation_history[phone] = []
    conversation_history[phone].append({"role": "user", "content": user_message})
    if len(conversation_history[phone]) > 20:
        conversation_history[phone] = conversation_history[phone][-20:]
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": conversation_history[phone]
        }
    )
    result = response.json()
    if "error" in result:
        return "Error: " + result["error"]["message"]
    reply = result["content"][0]["text"]
    conversation_history[phone].append({"role": "assistant", "content": reply})
    return reply


def send_whatsapp_message(phone, message):
    url = "https://graph.facebook.com/v18.0/" + PHONE_NUMBER_ID + "/messages"
    headers = {
        "Authorization": "Bearer " + WHATSAPP_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }
    requests.post(url, headers=headers, json=data)


def enviar_a_make(datos):
    try:
        requests.post(MAKE_WEBHOOK_URL, json=datos, timeout=10)
    except Exception as e:
        print("Error enviando a Make: " + str(e))


def manejar_agendamiento(phone, mensaje):
    mensaje_lower = mensaje.lower().strip()
    if phone not in agendamiento_state:
        agendamiento_state[phone] = {"paso": 0, "datos": {}}
    state = agendamiento_state[phone]
    paso = state["paso"]

    if paso == 0:
        palabras_clave = ["agendar", "visita", "instalacion", "instalacion",
                          "inspeccion", "tecnico", "cita", "quiero instalar",
                          "visita tecnica", "necesito instalacion"]
        if any(p in mensaje_lower for p in palabras_clave):
            agendamiento_state[phone] = {"paso": 1, "datos": {}}
            return ("Agendo tu visita!\n\n"
                    "Que tipo de servicio necesitas?\n"
                    "1 - Instalacion de internet\n"
                    "2 - Visita tecnica\n"
                    "3 - Inspeccion\n\n"
                    "Responde con el numero o escribe el tipo.")
        return None

    if paso == 1:
        if "1" in mensaje or "instalacion" in mensaje_lower:
            tipo = "Instalacion de internet"
        elif "2" in mensaje or "visita" in mensaje_lower:
            tipo = "Visita tecnica"
        elif "3" in mensaje or "inspeccion" in mensaje_lower:
            tipo = "Inspeccion"
        else:
            tipo = mensaje.strip()
        state["datos"]["tipo_servicio"] = tipo
        state["paso"] = 2
        return "Perfecto. Dime tu nombre completo:"

    if paso == 2:
        state["datos"]["nombre"] = mensaje.strip()
        state["paso"] = 3
        return "Cual es tu direccion? (barrio, calle, referencia)"

    if paso == 3:
        state["datos"]["direccion"] = mensaje.strip()
        state["paso"] = 4
        return "Que fecha prefieres? (Ej: 10 de mayo, proximo lunes)"

    if paso == 4:
        state["datos"]["fecha"] = mensaje.strip()
        state["paso"] = 5
        return "En que horario te queda mejor? (Ej: manana 9am-12pm, tarde 2pm-5pm)"

    if paso == 5:
        state["datos"]["hora"] = mensaje.strip()
        state["datos"]["telefono"] = phone
        enviar_a_make(state["datos"])
        resumen = ("Solicitud recibida!\n\n"
                   "Servicio: " + state["datos"]["tipo_servicio"] + "\n"
                   "Nombre: " + state["datos"]["nombre"] + "\n"
                   "Direccion: " + state["datos"]["direccion"] + "\n"
                   "Fecha: " + state["datos"]["fecha"] + "\n"
                   "Horario: " + state["datos"]["hora"] + "\n\n"
                   "Un asesor de VITT confirmara tu cita pronto. Gracias!")
        agendamiento_state[phone] = {"paso": 0, "datos": {}}
        return resumen

    return None


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        if "messages" not in value:
            return jsonify({"status": "ok"}), 200
        message = value["messages"][0]
        phone = message["from"]
        msg_type = message.get("type", "")
        if msg_type != "text":
            return jsonify({"status": "ok"}), 200
        user_message = message["text"]["body"]
        msg_lower = user_message.lower()
        if any(word in msg_lower for word in ["agente", "asesor", "persona", "humano"]):
            send_whatsapp_message(phone, "Entendido, en breve un asesor de VITT te atendera. Por favor espera.")
            return jsonify({"status": "ok"}), 200
        respuesta = manejar_agendamiento(phone, user_message)
        if respuesta:
            send_whatsapp_message(phone, respuesta)
            return jsonify({"status": "ok"}), 200
        reply = call_claude(phone, user_message)
        send_whatsapp_message(phone, reply)
    except Exception as e:
        print("Error: " + str(e))
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "VITT Bot activo con agendamiento!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
