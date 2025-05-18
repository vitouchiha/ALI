import os
import re
import logging
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Config logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Caricamento config da env
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AFFILIATE_ID = "_EHN0NeQ"
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")  # render-generated

if not TOKEN or not OPENAI_API_KEY or not HOST:
    logger.error("Devi impostare TELEGRAM_BOT_TOKEN, OPENAI_API_KEY e RENDER_EXTERNAL_HOSTNAME")
    raise RuntimeError("Env vars mancanti")

# Inizializza bot (python-telegram-bot)
bot = Bot(token=TOKEN)
app = FastAPI()

# Configuro Application per webhook
application = ApplicationBuilder().token(TOKEN).build()

def extract_id(url: str) -> str | None:
    m = re.search(r'/item/(\d+)\.html', url)
    return m.group(1) if m else None

def make_affiliate(pid: str) -> str:
    return (
        f"https://it.aliexpress.com/item/{pid}.html"
        f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
        f"&aff_platform=default&sk={AFFILIATE_ID}"
    )

@application.message_handler(filters.TEXT & ~filters.COMMAND)
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    links = re.findall(r"https?://\S+", text)
    for link in links:
        if "s.click.aliexpress.com" in link or "a.aliexpress.com" in link:
            # espando shortlink
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    r = await client.get(link)
                    link = str(r.url)
            except:
                pass
        if "aliexpress.com/item/" in link:
            pid = extract_id(link)
            if not pid:
                continue
            aff = make_affiliate(pid)
            # Genera descrizione via ChatGPT
            try:
                openai.api_key = OPENAI_API_KEY
                resp = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role":"user",
                               "content":f"Scrivi una descrizione breve e accattivante per questo prodotto AliExpress: {link}"}],
                    max_tokens=100
                )
                desc = resp.choices[0].message.content
            except:
                desc = "Sembra un ottimo prodotto!"

            # Scraping immagine og:image
            img_url = None
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(link)
                    soup = BeautifulSoup(r.text, "html.parser")
                    meta = soup.find("meta", property="og:image")
                    img_url = meta["content"] if meta else None
            except:
                img_url = None

            # cancello originale
            try: await update.message.delete()
            except: pass

            caption = f"{desc}\n\n🔗 {aff}"
            if img_url:
                await context.bot.send_photo(chat_id=update.effective_chat.id,
                                             photo=img_url,
                                             caption=caption)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=caption)
            return

@app.on_event("startup")
async def startup():
    webhook = f"https://{HOST}/bot/{TOKEN}"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook)
    logger.info("Webhook impostato su %s", webhook)

@app.post("/bot/{token}")
async def receive_update(token: str, req: Request):
    if token != TOKEN:
        return {"error":"invalid token"}
    data = await req.json()
    update = Update.de_json(data, bot)
    await application.process_update(update)
    return {"ok":True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
