import os
import re
import logging
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes, filters
)
import httpx
import openai
from bs4 import BeautifulSoup

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Env vars
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
AFFILIATE_ID = "_EHN0NeQ"

if not TOKEN or not OPENAI_API_KEY or not HOST:
    logger.error("ENV VARS mancanti (TOKEN, OPENAI_API_KEY, HOST)")
    raise RuntimeError("Missing env vars")

# Setup
openai.api_key = OPENAI_API_KEY
bot = Bot(token=TOKEN)
app = FastAPI()
application = ApplicationBuilder().token(TOKEN).build()

# === FUNZIONI ===

def extract_id(url: str) -> str | None:
    match = re.search(r"/item/(\d+)\.html", url)
    return match.group(1) if match else None

def make_affiliate(pid: str) -> str:
    return (
        f"https://it.aliexpress.com/item/{pid}.html"
        f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
        f"&aff_platform=default&sk={AFFILIATE_ID}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    links = re.findall(r"https?://\S+", text)

    for link in links:
        if "aliexpress.com" in link or "s.click.aliexpress.com" in link or "a.aliexpress.com" in link:
            try:
                # Expand short link
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    r = await client.get(link)
                    link = str(r.url)
            except:
                pass

            pid = extract_id(link)
            if not pid:
                continue

            aff = make_affiliate(pid)

            # Get description from OpenAI
            try:
                resp = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{
                        "role": "user",
                        "content": f"Scrivi una descrizione breve e accattivante per questo prodotto AliExpress: {link}"
                    }],
                    max_tokens=100
                )
                desc = resp.choices[0].message.content.strip()
            except:
                desc = "Ecco un ottimo prodotto che potrebbe interessarti!"

            # Get product image
            img_url = None
            try:
                async with httpx.AsyncClient() as client:
                    page = await client.get(link)
                    soup = BeautifulSoup(page.text, "html.parser")
                    meta = soup.find("meta", property="og:image")
                    if meta:
                        img_url = meta.get("content")
            except:
                pass

            # Delete original message
            try:
                await update.message.delete()
            except:
                pass

            caption = f"{desc}\n\n🔗 {aff}"
            if img_url:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=img_url,
                    caption=caption
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=caption
                )
            return

# === HANDLER ===
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === FASTAPI WEBHOOK ===

@app.on_event("startup")
async def startup():
    webhook = f"https://{HOST}/bot/{TOKEN}"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook)
    logger.info(f"Webhook impostato su {webhook}")

@app.post("/bot/{token}")
async def process_update(token: str, request: Request):
    if token != TOKEN:
        return {"error": "invalid token"}
    data = await request.json()
    update = Update.de_json(data, bot)
    await application.process_update(update)
    return {"ok": True}

# === LOCAL DEV ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
