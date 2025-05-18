import os
import requests
from flask import Flask, request
from urllib.parse import urlparse, parse_qs
import telegram
from telegram import InputMediaPhoto

# Config
BOT_TOKEN = os.environ.get("BOT_TOKEN")
AFFILIATE_ID = os.environ.get("AFFILIATE_ID")  # esempio: _EHN0NeQ
BASE_AFFILIATE_URL = "https://s.click.aliexpress.com/deep_link.htm?aff_short_key={}&dp={}"

bot = telegram.Bot(token=BOT_TOKEN)
app = Flask(__name__)

def expand_url(short_url):
    try:
        response = requests.head(short_url, allow_redirects=True, timeout=5)
        return response.url
    except Exception as e:
        print(f"[ERRORE] Impossibile espandere URL: {e}")
        return short_url

def extract_product_data(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if not response.ok:
            raise Exception("Errore nel caricamento della pagina prodotto")

        html = response.text

        # Estrazione rozza del titolo
        start_title = html.find("<title>")
        end_title = html.find("</title>")
        title = html[start_title + 7:end_title].strip() if start_title != -1 and end_title != -1 else "Titolo non trovato"

        # Estrazione rozza dell'immagine
        img_start = html.find('https://ae01.alicdn.com')
        img_end = html.find('.jpg', img_start)
        image_url = html[img_start:img_end + 4] if img_start != -1 and img_end != -1 else None

        return title, image_url
    except Exception as e:
        print(f"[ERRORE] Estrazione prodotto fallita: {e}")
        return "Errore nel recupero dati prodotto", None

def generate_affiliate_link(original_url):
    deep_link = requests.utils.quote(original_url, safe="")
    return BASE_AFFILIATE_URL.format(AFFILIATE_ID, deep_link)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    if update.message and update.message.text:
        msg = update.message
        chat_id = msg.chat_id
        message_id = msg.message_id
        text = msg.text.strip()

        # Cerca link AliExpress
        if "aliexpress.com" in text or "s.click.aliexpress" in text or "a.aliexpress" in text:
            # Espandi se necessario
            expanded_url = expand_url(text)

            # Estrai dati prodotto
            title, image_url = extract_product_data(expanded_url)

            # Genera link affiliato
            aff_link = generate_affiliate_link(expanded_url)

            # Costruisci didascalia
            caption = f"{title}\n\n🔗 [Compra con il mio link affiliato]({aff_link})"

            # Elimina messaggio originale
            try:
                bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                print(f"[ERRORE] Non riesco a cancellare il messaggio: {e}")

            # Invia messaggio modificato
            try:
                if image_url:
                    bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, parse_mode="Markdown")
                else:
                    bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")
            except Exception as e:
                print(f"[ERRORE] Invio messaggio fallito: {e}")
    return "OK"

@app.route("/", methods=["GET"])
def home():
    return "Bot AliExpress affiliato attivo e funzionante. Vai tranquillo Vito, tutto sotto controllo."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
