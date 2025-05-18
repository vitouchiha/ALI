import os
import re
import logging
import asyncio
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import uvicorn
import openai

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AFFILIATE_ID = os.getenv("AFFILIATE_ID", "_EHN0NeQ")
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
PORT = int(os.getenv("PORT", 8000))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verifica env
aif not TOKEN or not OPENAI_API_KEY or not HOST:
    logger.error("Devi impostare TELEGRAM_BOT_TOKEN, OPENAI_API_KEY e RENDER_EXTERNAL_HOSTNAME")
    raise RuntimeError("Env vars mancanti")

# Setup OpenAI
openai.api_key = OPENAI_API_KEY

# Telegram Application
application = ApplicationBuilder().token(TOKEN).build()
bot = application.bot

# FastAPI app
app = FastAPI()

# Utils
def extract_id(url: str) -> str | None:
    m = re.search(r"/item/(\d+)\.html", url)
    return m.group(1) if m else None

def make_affiliate(pid: str) -> str:
    return (
        f"https://it.aliexpress.com/item/{pid}.html"
        f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
        f"&aff_platform=default&sk={AFFILIATE_ID}"
    )

async def expand_link(link: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(link)
            return str(resp.url)
    except Exception:
        return link

async def scrape_info(link: str):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(link)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("meta", property="og:title")
        img = soup.find("meta", property="og:image")
        return (
            title["content"] if title else "",
            img["content"] if img else None
        )
    except Exception:
        return "", None

# Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    matches = re.findall(r"https?://\S+", text)
    for link in matches:
        if any(domain in link for domain in ("aliexpress.com", "s.click.aliexpress.com", "a.aliexpress.com")):
            final = await expand_link(link)
            pid = extract_id(final)
            if not pid:
                continue
            aff = make_affiliate(pid)
            desc, img = await scrape_info(final)
            # delete original
            try:
                await update.message.delete()
            except:
                pass
            cap = f"🤑 {desc}\n\n🔗 {aff}"
            if img:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img, caption=cap)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=cap)
            return

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Webhook route
@app.on_event("startup")
async def startup():
    await application.initialize()
    await application.start()
    url = f"https://{HOST}/webhook/{TOKEN}"
    await bot.set_webhook(url)
    logger.info(f"Webhook set to {url}")

@app.post("/webhook/{token}")
async def process_webhook(token: str, req: Request):
    if token != TOKEN:
        return {"error": "invalid token"}
    data = await req.json()
    update = Update.de_json(data, bot)
    await application.process_update(update)
    return {"ok": True}

@app.on_event("shutdown")
async def shutdown():
    await application.stop()

# Run ASGI server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
