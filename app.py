import os
import re
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import httpx
import openai

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Caricamento token e chiavi dalle variabili d'ambiente
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AFFILIATE_ID = "_EHN0NeQ"
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")  # dominio onrender.com

if not TOKEN or not OPENAI_API_KEY or not HOST:
    logger.error("Le variabili TELEGRAM_BOT_TOKEN, OPENAI_API_KEY e RENDER_EXTERNAL_HOSTNAME devono essere impostate.")
    raise RuntimeError("Chiavi mancanti nelle variabili d'ambiente")

# Inizializzazione Bot e Dispatcher (Aiogram)
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# Inizializzazione FastAPI
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    """Imposta il webhook Telegram all'avvio dell'app."""
    webhook_url = f"https://{HOST}/bot/{TOKEN}"
    try:
        # Rimuove webhook precedente e imposta il nuovo
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook impostato su {webhook_url}")
    except Exception as e:
        logger.error(f"Errore impostando il webhook: {e}")

@app.post("/bot/{token}")
async def telegram_webhook(token: str, req: Request):
    """Ricezione degli update da Telegram via webhook."""
    if token != TOKEN:
        return {"error": "Token non valido"}
    data = await req.json()
    update = types.Update(**data)
    try:
        await dp.process_update(update)
    except Exception as e:
        logger.error(f"Errore nel process_update: {e}")
    return {"ok": True}

@dp.message_handler()
async def handle_message(message: types.Message):
    """Gestisce ogni messaggio in arrivo."""
    text = message.text or ""
    # Ricerca di link nel testo
    links = re.findall(r'https?://\S+', text)
    ali_link = None
    for link in links:
        if "aliexpress.com" in link:
            ali_link = link
            break
    if not ali_link:
        return  # cazzo, nessun link AliExpress trovato

    # Espande shortlink seguendo i redirect
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.get(ali_link)
            final_url = str(resp.url)
        logger.info(f"Shortlink '{ali_link}' espanso in '{final_url}'")
    except Exception as e:
        logger.warning(f"Espansione URL fallita per {ali_link}: {e}")
        final_url = ali_link

    # Estrae l'ID del prodotto dall'URL
    product_id = None
    match = re.search(r'/item/(\d+)\.html', final_url)
    if not match:
        match = re.search(r'/i/(\d+)\.html', final_url)
    if not match:
        match = re.search(r'productId=(\d+)', final_url)
    if match:
        product_id = match.group(1)
        logger.info(f"ID prodotto trovato: {product_id}")
    else:
        logger.warning(f"Nessun ID prodotto trovato in '{final_url}'")
        return

    # Costruisce il link affiliato
    if "?" in final_url:
        aff_link = f"{final_url}&affid={AFFILIATE_ID}"
    else:
        aff_link = f"{final_url}?affid={AFFILIATE_ID}"
    logger.info(f"Link affiliato creato: {aff_link}")

    # Chiamata a ChatGPT per generare la descrizione (in italiano)
    try:
        prompt = f"Genera una descrizione pubblicitaria per il prodotto AliExpress con ID {product_id}."
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7
        )
        description = response["choices"][0]["message"]["content"].strip()
        logger.info(f"Descrizione generata: {description}")
    except Exception as e:
        logger.error(f"Errore OpenAI ChatCompletion: {e}")
        description = "(Descrizione non disponibile.)"

    # Chiamata a DALL-E per generare l'immagine del prodotto
    image_url = None
    try:
        image_prompt = f"Fotografia realistica di un prodotto elettronico AliExpress (ID {product_id}), su sfondo bianco"
        img_resp = openai.Image.create(
            prompt=image_prompt,
            n=1,
            size="512x512"
        )
        image_url = img_resp["data"][0]["url"]
        logger.info(f"Immagine generata all'URL: {image_url}")
    except Exception as e:
        logger.error(f"Errore generazione immagine: {e}")

    # Elimina il messaggio originale (richiede permessi di cancellazione)
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        logger.info("Messaggio originale cancellato")
    except Exception as e:
        logger.warning(f"Impossibile cancellare il messaggio: {e}")

    # Invia la nuova foto con didascalia
    caption = f"{description}\n\n🔗 *Link affiliato:* {aff_link}"
    try:
        if image_url:
            await bot.send_photo(chat_id=message.chat.id, photo=image_url, caption=caption, parse_mode="Markdown")
        else:
            # Se non abbiamo immagine, invia solo testo
            await bot.send_message(chat_id=message.chat.id, text=caption, parse_mode="Markdown")
        logger.info("Messaggio inviato con descrizione e link affiliato")
    except Exception as e:
        logger.error(f"Errore nell'invio del messaggio: {e}")
