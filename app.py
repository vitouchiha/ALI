import re
import os
import logging
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram import Update

# Configurazione
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AFFILIATE_ID = "_EHN0NeQ"  # Vito's referral ID

# Logging
logging.basicConfig(level=logging.INFO)

def convert_link(text):
    links = re.findall(r'https?://[\w./?=&%-]+', text)
    converted = []
    for link in links:
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
            new_link = f"https://s.click.aliexpress.com/e/{AFFILIATE_ID}"
            converted.append(new_link)
    return converted

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    converted_links = convert_link(text)
    if converted_links:
        reply = "🤑 Link affiliato generato:\n\n" + "\n".join(converted_links)
        try:
            await update.message.delete()
        except Exception as e:
            logging.warning(f"Non posso cancellare il messaggio: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=reply)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logging.info("Avvio polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
