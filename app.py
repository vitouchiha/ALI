import re
import os
import logging
import httpx
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Configurazione
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AFFILIATE_ID = "_EHN0NeQ"

# Logging
logging.basicConfig(level=logging.INFO)

def extract_product_id(link: str) -> str | None:
    match = re.search(r'/item/(\d+).html', link)
    return match.group(1) if match else None

def generate_affiliate_link(pid: str) -> str:
    return (
        f"https://it.aliexpress.com/item/{pid}.html"
        f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
        f"&aff_platform=default&sk={AFFILIATE_ID}"
    )

def shorten_url(url: str) -> str:
    try:
        res = httpx.get(f"https://tinyurl.com/api-create.php?url={url}")
        return res.text if res.status_code == 200 else url
    except Exception as e:
        logging.warning(f"Errore accorciamento URL: {e}")
        return url

def scrape_ali_info(link: str) -> tuple[str, str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = httpx.get(link, headers=headers, timeout=10.0)
        soup = BeautifulSoup(res.text, "html.parser")

        # Prende il titolo
        title_tag = soup.find("title")
        title = title_tag.text.strip() if title_tag else "Nessuna descrizione trovata"

        # Cerca immagine (fallback a default se niente)
        img_tag = soup.find("img")
        img_url = img_tag["src"] if img_tag and "src" in img_tag.attrs else None

        return title, img_url
    except Exception as e:
        logging.warning(f"Errore scraping: {e}")
        return "Descrizione non trovata", None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    links = re.findall(r'https?://[\w./?=&%-]+', text)

    for link in links:
        if "aliexpress.com/item/" in link:
            pid = extract_product_id(link)
            if pid:
                aff_link = generate_affiliate_link(pid)
                short_link = shorten_url(aff_link)
                title, image_url = scrape_ali_info(link)

                caption = f"🤑 *{title}*\n\n🔗 [Link affiliato]({short_link})"
                try:
                    await update.message.delete()
                except Exception as e:
                    logging.warning(f"Non posso cancellare il messaggio: {e}")

                if image_url:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url, caption=caption, parse_mode="Markdown")
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=caption, parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logging.info("Avvio polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
