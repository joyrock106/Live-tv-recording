import os
import subprocess
import threading
import telebot
from telebot.types import Message
from datetime import datetime

# ==== CONFIG ====
BOT_TOKEN = "7641596987:AAHYUJ0CTkK0jVCeYWpDwCgUYEdMqPeL0pY"   # Put your bot token here
DOWNLOAD_DIR = "./downloads"
LOG_DIR = "./logs"
MAX_UPLOAD_SIZE = 2048 * 1024 * 1024  # 2 GB

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN)

def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def build_filename(base: str, ext="mp4"):
    safe_base = "".join(c if c.isalnum() else "_" for c in base)[:50]
    return os.path.join(DOWNLOAD_DIR, f"{safe_base}_{timestamp()}.{ext}")

def run_ffmpeg(m3u8_url, output_path, duration=None, log_path=None):
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", m3u8_url,
        "-map", "0",   # include all video & audio tracks
        "-c", "copy"
    ]
    if duration:
        cmd += ["-t", str(duration)]
    cmd.append(output_path)

    with open(log_path, "a", encoding="utf-8") as log_file:
        process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
        process.wait()
        return process.returncode

def send_recording(chat_id, file_path):
    size = os.path.getsize(file_path)
    if size < MAX_UPLOAD_SIZE:
        with open(file_path, "rb") as f:
            bot.send_document(chat_id, f, caption=f"✅ Recording done: {os.path.basename(file_path)}")
    else:
        bot.send_message(chat_id, f"⚠️ File too large to upload ({size/(1024*1024):.2f} MB). Please download manually.")

def recording_thread(chat_id, url, duration, filename):
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id, f"⏳ Recording started at {start_time}\nURL: {url}")

    output_path = build_filename(filename)
    log_path = os.path.join(LOG_DIR, f"{os.path.basename(output_path)}.log")

    retcode = run_ffmpeg(url, output_path, duration, log_path)

    end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if retcode == 0 and os.path.exists(output_path):
        bot.send_message(chat_id, f"✅ Recording finished at {end_time}")
        send_recording(chat_id, output_path)
    else:
        bot.send_message(chat_id, f"❌ Recording failed at {end_time}. Check logs.")
        with open(log_path, "r", encoding="utf-8") as f:
            log_excerpt = f.read(500)
            bot.send_message(chat_id, f"Log excerpt:\n```\n{log_excerpt}\n```", parse_mode="Markdown")

@bot.message_handler(commands=["start"])
def cmd_start(message: Message):
    bot.reply_to(message,
                 "👋 M3U8 Recording Bot Ready!\n\n"
                 "Send command:\n"
                 "/record <m3u8_url> [duration_in_seconds] [filename]\n\n"
                 "Example:\n"
                 "/record https://example.com/stream.m3u8 120 myvideo")

@bot.message_handler(commands=["record"])
def cmd_record(message: Message):
    args = message.text.split(maxsplit=3)
    if len(args) < 2:
        bot.reply_to(message, "Usage:\n/record <m3u8_url> [duration_in_seconds] [filename]")
        return

    url = args[1]
    duration = None
    filename = "recording"

    if len(args) >= 3:
        try:
            duration = int(args[2])
        except ValueError:
            filename = args[2]  # If not duration, treat it as filename

    if len(args) == 4:
        filename = args[3]

    # Run recording in a new thread
    thread = threading.Thread(target=recording_thread, args=(message.chat.id, url, duration, filename))
    thread.start()
    bot.reply_to(message, "🛠️ Recording started, you will get the video shortly.")

print("Bot is running...")
bot.polling()
