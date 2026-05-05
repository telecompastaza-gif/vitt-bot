import os
import json
import hmac
import hashlib
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Variables de entorno
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
WEBHOOK_VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN", "vitt_webhook_2024")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")

SYSTEM_PROMPT = """Eres el asistente virtual de VITT, empresa de soluciones tecnológicas integrales en Puyo, Pastaza, Ecuador. Tu nombre es "Asistente VITT" y usas el emoji 🦍 como mascota.

PLANES DE INTERNET (Fibra Óptica):
- BÁSICO: 100 Mbps - $15/mes - Solo internet
- INTERMEDIO: 200 Mbps - $20/mes - Solo internet  
- AVANZADO: 400 Mbps - $25/mes - Internet + Vitt TV
- PREMIUM: 500 Mbps - $30/mes - Internet + Vitt TV
- ÉLITE: 700 Mbps - $35/mes - Internet + Vitt TV + Vitt Cam

TODOS LOS PLANES INCLUYEN: Fibra Óptica, Soporte Técnico, Monitoreo, Atención Local.
CONDICIONES: Instalación varía según plan. Sujeto a cobertura. Planes especiales para tercera edad y discapacidad.

TV VITT: +90 canales en vivo, contenido bajo demanda. Incluido desde plan Avanzado ($25).

VITT CAM: $5/cámara/mes. Grabación nube 3 días. App VittCam. Incluido en plan Élite.

VITT TRACK (Rastreo GPS 24/7):
Vehículos livianos: GPS Normal $180/año, GPS+Puertas+Antijammer $280/año, GPS+Pánico $200/año
Vehículos pesados: GPS Normal $200/año, GPS+Puertas+Antijammer $300/año, GPS+Pánico $220/año
Renovación todos: $65/año. Incluye: rastreo tiempo real, alertas WhatsApp, geocercas, botón pánico.

CONTACTO: WhatsApp 098 614 3393
COBERTURA: Puyo, Arajuno y Simón Bolívar (Pastaza, Ecuador)

INSTRUCCIONES:
- Responde en español, amigable y conciso
- Máximo 3-4 líneas por respuesta (WhatsApp es móvil)
- Si preguntan por instalación o contrato, deriva al 098 614 3393
- Si no sabes algo, indica que contacten al WhatsApp
- Usa emojis con moderación"""

# Historial de conversaciones por número
conversation_history = {}

def send_whatsapp_message(to, message):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()

def get_claude_response(user_number, user_message):
    if user_number not in conversation_history:
        conversation_history[user_number] = []
    
    conversation_history[user_number].append({
        "role": "user",
        "content": user_message
    })
    
    # Mantener solo últimos 10 mensajes
    if len(conversation_history[user_number]) > 10:
        conversation_history[user_number] = conversation_history[user_number][-10:]
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
    }
    data = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 500,
        "system": SYSTEM_PROMPT,
        "messages": conversation_history[user_number]
    }
    
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=data
    )
    
   result = response.json()
if "error" in result:
    return f"Error: {result['error']['message']}"
reply = result["content"][0]["text"]
    
    conversation_history[user_number].append({
        "role": "assistant",
        "content": reply
    })
    
    return reply

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        
        if "messages" in value:
            message = value["messages"][0]
            from_number = message["from"]
            
            if message["type"] == "text":
                user_message = message["text"]["body"]
                reply = get_claude_response(from_number, user_message)
                send_whatsapp_message(from_number, reply)
    except Exception as e:
        print(f"Error: {e}")
    
    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def home():
    return "🦍 VITT Bot activo!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
