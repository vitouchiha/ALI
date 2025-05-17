import os
import re
import httpx
import logging
from bs4 import BeautifulSoup
from telegram import InputMediaPhoto, Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Logging
logging.basicConfig(level=logging.INFO)

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AFFILIATE_ID = "_EHN0NeQ"

# Espande shortlink (es. https://a.aliexpress.com/...)
async def expand_url(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.get(url)
            return str(resp.url)
    except Exception as e:
        logging.warning(f"Errore espansione URL: {e}")
        return url

# Estrae ID prodotto da URL espanso
def extract_product_id(url: str) -> str | None:
    match = re.search(r"/item/(\d+).html", url)
    return match.group(1) if match else None

# Recupera immagine e titolo dalla pagina prodotto
async def fetch_product_data(product_id: str):
    url = f"https://it.aliexpress.com/item/{product_id}.html"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            soup = BeautifulSoup(r.text, "html.parser")
            img = soup.find("meta", property="og:image")
            title = soup.find("meta", property="og:title")
            return {
                "image": img["content"] if img else None,
                "title": title["content"] if title else "Prodotto AliExpress"
            }
    except Exception as e:
        logging.warning(f"Errore fetch dati prodotto {product_id}: {e}")
        return None

# Converte link con affiliate ID
def generate_affiliate_link(product_id: str) -> str:
    return (f"https://it.aliexpress.com/item/{product_id}.html"
            f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
            f"&aff_platform=default&sk={AFFILIATE_ID}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    links = re.findall(r'https?://\S+', text)
    for link in links:
        expanded = await expand_url(link)
        product_id = extract_product_id(expanded)
        if product_id:
            affiliate_link = generate_affiliate_link(product_id)
            data = await fetch_product_data(product_id)
            if data and data["image"]:
                caption = (
                    f"🙂 Grazie {update.effective_user.first_name} per aver inviato questo prodotto, "
                    f"sembra molto interessante.\n\n"
                    f"Utilizza questo link per far fare un casino di soldi a Nellino!\n{affiliate_link}"
                )
                try:
                    await update.message.delete()
                except Exception as e:
                    logging.warning(f"Impossibile cancellare messaggio: {e}")
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=data["image"], caption=caption)
                return

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logging.info("Avvio polling...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
