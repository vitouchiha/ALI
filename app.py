import os
import re
import logging
import httpx
from bs4 import BeautifulSoup
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from fastapi import FastAPI, Request
from telegram.ext import Application
import asyncio

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AFFILIATE_ID = "_EHN0NeQ"
PORT = int(os.environ.get("PORT", 8080))
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
web_app = FastAPI()
telegram_app: Application = None

async def expand_aliexpress_link(short_url):
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(short_url)
            return str(resp.url)
    except Exception as e:
        logger.warning(f"Errore nell'espansione del link: {e}")
        return short_url

async def extract_info(url):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Estrai immagine
        image_tag = soup.find('meta', property='og:image')
        image_url = image_tag['content'] if image_tag else None

        # Estrai video (se presente)
        video_tag = soup.find('meta', property='og:video')
        video_url = video_tag['content'] if video_tag else None

        # Estrai descrizione
        desc_tag = soup.find('meta', property='og:title')
        description = desc_tag['content'] if desc_tag else "Nessuna descrizione trovata"

        return image_url, video_url, description

    except Exception as e:
        logger.warning(f"Errore nel parsing: {e}")
        return None, None, "Nessuna descrizione trovata"

def convert_link(link):
    if "aliexpress.com/item/" in link:
        match = re.search(r'/item/(\d+).html', link)
        if match:
            pid = match.group(1)
            return (
                f"https://it.aliexpress.com/item/{pid}.html"
                f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
                f"&aff_platform=default&sk={AFFILIATE_ID}"
            )
    elif "aliexpress.com" in link:
        return f"https://s.click.aliexpress.com/e/{AFFILIATE_ID}"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    links = re.findall(r'https?://\S+', text)
    output = []

    for link in links:
        if "aliexpress.com" not in link:
            continue

        expanded = await expand_aliexpress_link(link)
        converted = convert_link(expanded)
        image, video, desc = await extract_info(expanded)

        output.append((converted, image, video, desc))

    if output:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Non posso cancellare il messaggio: {e}")

        for link, image, video, desc in output:
            caption = f"🤑 {desc}\n\n🔗 Link affiliato diretto:\n{link}"
            if video:
                await context.bot.send_video(chat_id=update.effective_chat.id, video=video, caption=caption)
            elif image:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image, caption=caption)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=caption)

@web_app.post("/webhook")
async def webhook_handler(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

async def main():
    global telegram_app
    telegram_app = ApplicationBuilder().token(TOKEN).build()
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/webhook"
    await telegram_app.bot.set_webhook(webhook_url)
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Bot avviato con webhook su Render!")

if __name__ == "__main__":
    asyncio.run(main())
