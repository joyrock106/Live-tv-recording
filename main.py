import os
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === CONFIG ===
TOKEN = "8058984373:AAGG-PuynpRquzavA3K1IXihAA13QEl5gwE"
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send /record <m3u8_url> <seconds>\n\n"
        "Example:\n/record https://example.com/stream.m3u8 60"
    )

async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Please provide a URL and optional duration.\nExample:\n/record https://example.com/stream.m3u8 120")
        return
    
    url = context.args[0]
    duration = None

    if len(context.args) > 1:
        try:
            duration = int(context.args[1])
        except ValueError:
            await update.message.reply_text("⚠️ Duration must be a number (in seconds).")
            return

    filename = os.path.join(DOWNLOAD_DIR, "stream.mp4")

    await update.message.reply_text(f"🎥 Recording started…{' for ' + str(duration) + 's' if duration else ''}")

    # ffmpeg command
    cmd = [
        "ffmpeg", "-y", "-i", url,
        "-c", "copy",
        "-map", "0:v?", "-map", "0:a?",
    ]

    if duration:
        cmd.extend(["-t", str(duration)])

    cmd.append(filename)

    try:
        subprocess.run(cmd, check=True)
        await update.message.reply_document(document=open(filename, "rb"))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

# === MAIN ===
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("record", record))
    app.run_polling()

if __name__ == "__main__":
    main()
