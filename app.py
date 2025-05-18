import os
import re
import logging
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import uvicorn
import openai
from urllib.parse import urlparse, parse_qs, unquote

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AFFILIATE_ID = os.getenv("AFFILIATE_ID", "_EHN0NeQ")
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
PORT = int(os.getenv("PORT", 8000))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verify environment
if not TOKEN or not OPENAI_API_KEY or not HOST:
    logger.error("Devono essere impostate: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY e RENDER_EXTERNAL_HOSTNAME")
    raise RuntimeError("Env vars mancanti")

# Setup OpenAI
openai.api_key = OPENAI_API_KEY

# Initialize Telegram Application
application = ApplicationBuilder().token(TOKEN).build()
bot = application.bot

# FastAPI app
app = FastAPI()

# Utilities

def extract_id(url: str) -> str | None:
    m = re.search(r"/item/(\d+)\.html", url)
    return m.group(1) if m else None

async def expand_link(link: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"}
    try:
        async with httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=10) as client:
            resp = await client.get(link)
            final_url = str(resp.url)
        # Handle AliExpress share redirectUrl param
        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        if 'redirectUrl' in qs:
            return unquote(qs['redirectUrl'][0])
        return final_url
    except Exception as e:
        logger.warning(f"Errore espansione link {link}: {e}")
        return link

async def scrape_info(link: str) -> tuple[str, str | None]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        async with httpx.AsyncClient(headers=headers, timeout=10) as client:
            resp = await client.get(link)
        soup = BeautifulSoup(resp.text, "html.parser")
        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")
        title = og_title["content"].strip() if og_title and og_title.get("content") else "Prodotto AliExpress"
        img_url = og_image["content"] if og_image and og_image.get("content") else None
        return title, img_url
    except Exception as e:
        logger.warning(f"Errore scraping info per {link}: {e}")
        return "Prodotto AliExpress", None

async def generate_description(link: str) -> str:
    try:
        prompt = f"Genera una breve descrizione entusiasmante per questo prodotto AliExpress: {link}"
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.7
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"OpenAI error: {e}")
        return "Sembra un prodotto fantastico!"

# Handler registration
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    links = re.findall(r"https?://\S+", text)
    for link in links:
        if any(d in link for d in ("aliexpress.com", "s.click.aliexpress.com", "a.aliexpress.com")):
            final = await expand_link(link)
            product_id = extract_id(final)
            if not product_id:
                continue

            # Parse invitationCode if present
            parsed = urlparse(final)
            qs = parse_qs(parsed.query)
            invitation = qs.get('invitationCode', [None])[0]

            # Build affiliate link: support Share & Earn or default
            if invitation:
                affiliate_link = f"https://it.aliexpress.com/item/{product_id}.html?invitationCode={invitation}&businessType=affiliate"
            else:
                affiliate_link = (
                    f"https://it.aliexpress.com/item/{product_id}.html"
                    f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
                    f"&aff_platform=default&sk={AFFILIATE_ID}"
                )

            # Fetch metadata
            title, img_url = await scrape_info(final)
            description = await generate_description(final)

            # Delete original message
            try:
                await update.message.delete()
            except:
                pass

            # Username
            user_name = update.effective_user.first_name

            # Compose caption
            caption = (
                f"Grazie per aver condiviso questo fantastico prodotto, {user_name}!\n\n"
                f"{description}\n\n"
                f"Utilizza il link sottostante per far guadagnare una commissione a Nellino:\n"
                f"{affiliate_link}"
            )

            # Send response
            if img_url:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=img_url,
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=caption,
                    parse_mode="Markdown"
                )
            return

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Webhook setup
@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    webhook_url = f"https://{HOST}/webhook/{TOKEN}"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook impostato su {webhook_url}")

@app.post("/webhook/{token}")
async def process_webhook(token: str, req: Request):
    if token != TOKEN:
        return {"error": "invalid token"}
    data = await req.json()
    update = Update.de_json(data, bot)
    await application.process_update(update)
    return {"ok": True}

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()

# Run ASGI server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
