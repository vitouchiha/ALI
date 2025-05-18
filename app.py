import re
import os
import logging
import httpx
from bs4 import BeautifulSoup
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# === CONFIG ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AFFILIATE_ID = "_EHN0NeQ"  # Vito's referral ID

# === LOGGING ===
logging.basicConfig(level=logging.INFO)

def expand_short_link(url: str) -> str:
    try:
        with httpx.Client(follow_redirects=True, timeout=10.0) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            return str(resp.url)
    except Exception as e:
        logging.warning(f"Errore espansione link: {e}")
        return url

def convert_link(text: str) -> list[str]:
    links = re.findall(r'https?://[\w./?=&%-]+', text)
    converted = []

    for link in links:
        original = link
        if "s.click.aliexpress.com" in link:
            link = expand_short_link(link)

        if "aliexpress.com/item/" in link:
            match = re.search(r'/item/(\d+).html', link)
            if match:
                pid = match.group(1)
                new_link = (
                    f"https://it.aliexpress.com/item/{pid}.html"
                    f"?aff_fcid={AFFILIATE_ID}&aff_fsk={AFFILIATE_ID}"
                    f"&aff_platform=default&sk={AFFILIATE_ID}"
                )
                converted.append(new_link)
        elif "aliexpress.com" in link:
            converted.append(
                f"https://s.click.aliexpress.com/e/{AFFILIATE_ID}"
            )

    return converted

def scrape_ali_info(link: str) -> tuple[str, str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = httpx.get(link, headers=headers, timeout=10.0)
        soup = BeautifulSoup(res.text, "html.parser")

        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")

        title = og_title["content"].strip() if og_title and "content" in og_title.attrs else "Nessuna descrizione trovata"
        img_url = og_image["content"] if og_image and "content" in og_image.attrs else None

        return title, img_url
    except Exception as e:
        logging.warning(f"Errore scraping: {e}")
        return "Descrizione non trovata", None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    converted_links = convert_link(text)

    if not converted_links:
        return

    final_link = converted_links[0]
    title, img_url = scrape_ali_info(final_link)

    try:
        await update.message.delete()
    except Exception as e:
        logging.warning(f"Non posso cancellare il messaggio: {e}")

    caption = f"🤑 {title}\n\n🔗 Link affiliato diretto:\n{final_link}"

    if img_url:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img_url, caption=caption)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=caption)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logging.info("Bot avviato in polling!")
    app.run_polling()

if __name__ == "__main__":
    main()
