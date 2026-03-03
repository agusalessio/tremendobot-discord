"""
discord_listener.py — TremendoBot
Escucha el canal #señales-be en Discord, parsea las señales con Claude
y las guarda en Supabase tabla "señales_be".

Deploy en Railway:
  - Variables de entorno: DISCORD_TOKEN, DISCORD_CHANNEL_ID, SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
  - Start command: python discord_listener.py
"""

import os
import json
import asyncio
import discord
import anthropic
from supabase import create_client
from datetime import datetime

# ─── Config desde variables de entorno ───────────────────────────
DISCORD_TOKEN      = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
SUPABASE_URL       = os.environ["SUPABASE_URL"]
SUPABASE_KEY       = os.environ["SUPABASE_KEY"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

# ─── Clientes ─────────────────────────────────────────────────────
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── Discord client ───────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# ─── Parser con Claude ────────────────────────────────────────────
def parsear_señal_be(mensaje_texto: str) -> dict:
    """
    Usa Claude para interpretar el mensaje de Black Eagles y extraer
    los campos estructurados. Retorna un dict con los datos del trade.
    """
    prompt = f"""Sos un asistente experto en trading SMC que analiza señales de trading.
Te voy a pasar un mensaje de un canal de señales de trading (Black Eagles / BEIG Capital).
Tu tarea es extraer los datos del trade en formato JSON.

Mensaje:
\"\"\"
{mensaje_texto}
\"\"\"

Respondé SOLO con un JSON válido, sin texto antes ni después, con esta estructura exacta:
{{
  "es_señal": true/false,
  "tipo": "LONG" o "SHORT" o null,
  "activo": "BTC" o "ETH" o el activo mencionado o null,
  "timeframe": "1H" o "4H" o "1D" o el TF mencionado o null,
  "entry": número o null,
  "sl": número o null,
  "tp1": número o null,
  "tp2": número o null,
  "notas": "cualquier comentario relevante del mensaje" o null
}}

Si el mensaje NO es una señal de trading (es un mensaje de chat, noticia, etc.), poné "es_señal": false y el resto null.
Si es una señal pero falta algún dato, ponelo como null.
Solo números en los campos numéricos, sin símbolos $ ni %.
"""

    try:
        msg = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        texto = msg.content[0].text.strip()
        # Limpiar posibles backticks
        texto = texto.replace("```json", "").replace("```", "").strip()
        return json.loads(texto)
    except Exception as e:
        print(f"[Claude] Error parseando señal: {e}")
        return {"es_señal": False}


def guardar_en_supabase(mensaje_original: str, datos: dict) -> bool:
    """Guarda la señal parseada en Supabase."""
    try:
        doc = {
            "created_at":        datetime.utcnow().isoformat(),
            "mensaje_original":  mensaje_original,
            "tipo":              datos.get("tipo"),
            "entry":             datos.get("entry"),
            "sl":                datos.get("sl"),
            "tp1":               datos.get("tp1"),
            "tp2":               datos.get("tp2"),
            "activo":            datos.get("activo"),
            "timeframe":         datos.get("timeframe"),
            "notas":             datos.get("notas"),
            "parseado":          True,
            "coincide_bot":      None,  # se evalúa desde bot.py
        }
        supabase.table("señales_be").insert(doc).execute()
        print(f"[Supabase] Señal guardada: {datos.get('tipo')} {datos.get('activo')} entry={datos.get('entry')}")
        return True
    except Exception as e:
        print(f"[Supabase] Error guardando señal: {e}")
        return False


# ─── Eventos Discord ──────────────────────────────────────────────
@client.event
async def on_ready():
    print(f"[Discord] Bot conectado como {client.user}")
    print(f"[Discord] Escuchando canal ID: {DISCORD_CHANNEL_ID}")


@client.event
async def on_message(message):
    # Ignorar mensajes del propio bot
    if message.author == client.user:
        return

    # Solo procesar el canal configurado
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    texto = message.content.strip()
    if not texto:
        return

    print(f"\n[Discord] Mensaje recibido de {message.author}: {texto[:80]}...")

    # Parsear con Claude
    datos = parsear_señal_be(texto)

    if datos.get("es_señal"):
        print(f"[Claude] Señal detectada: {datos}")
        guardar_en_supabase(texto, datos)
    else:
        print(f"[Claude] No es señal de trading, ignorado.")


# ─── Main ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[TremendoBot] Iniciando Discord listener...")
    client.run(DISCORD_TOKEN)
