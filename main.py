
#!/usr/bin/env python3

# Super Premium M3U8 Recorder Bot
# Multi-Audio + Admin Control + Ultra-Advanced Progress
# + Custom Filename + ffprobe.txt + Stream Health Checker
# + Named Link Save System + PHP URL Decode Support

import os, shlex, asyncio, uuid, subprocess, base64, re, time, json
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv
import aiohttp
import m3u8

load_dotenv()

# ---------------- CONFIG ----------------

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

TEMP_DIR = Path(os.getenv("TEMP_DIR", "./recordings"))
UPLOAD_AS_VIDEO = os.getenv("UPLOAD_AS_VIDEO", "true").lower() in ("1","true","yes")
WATERMARK_PATH = os.getenv("WATERMARK_PATH", "")
SPLIT_SIZE_MB = int(os.getenv("SPLIT_SIZE_MB", "1024"))

TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ---------------- ADMINS ----------------

ADMINS = {OWNER_ID}
def is_admin(uid):
    return uid == OWNER_ID or uid in ADMINS

# ---------------- LINK STORAGE ----------------

LINK_DB = Path("links.json")
if not LINK_DB.exists():
    LINK_DB.write_text("{}")

def load_links():
    try: return json.loads(LINK_DB.read_text())
    except: return {}

def save_links(data):
    LINK_DB.write_text(json.dumps(data, indent=2))

# ---------------- GLOBALS ----------------

jobs: Dict[str, Dict] = {}
app = Client("super_premium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- HELPERS ----------------

def sanitize_filename(s: str) -> str:
    keep = "-.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(c if c in keep else "" for c in s)[:200]

def parse_duration(s: str) -> Optional[int]:
    s = s.strip()
    if s.isdigit(): return int(s)
    parts = s.split(":")
    try: parts = [int(p) for p in parts]
    except: return None
    if len(parts)==1: return parts[0]
    if len(parts)==2: return parts[0]*60+parts[1]
    if len(parts)==3: return parts[0]*3600+parts[1]*60+parts[2]
    return None

async def check_url_ok(url: str, timeout: int = 6) -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=timeout) as resp:
                return resp.status in (200,206,301,302)
    except: return False

async def get_audio_tracks(url: str):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as resp:
                txt = await resp.text()
                pl = m3u8.loads(txt)
                return [m for m in pl.media if m.type=="AUDIO"]
    except: return []

async def resolve_php_m3u8(url: str) -> str:
    """Resolve PHP URL to actual .m3u8 or .ts URL"""
    if url.endswith(".php") or "php?" in url:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url) as r:
                    txt = await r.text()
                    m = re.search(r'file=([A-Za-z0-9+/=]+)', txt)
                    if m:
                        b64 = m.group(1)
                        b64 += "=" * (-len(b64) % 4)  # correct padding
                        decoded = base64.b64decode(b64).decode()
                        return decoded
        except: return url
    return url

def build_ffmpeg_cmd(url, outpath, duration, watermark, split):
    cmd = ["ffmpeg","-hide_banner","-loglevel","warning","-y","-i",shlex.quote(url)]
    if duration: cmd += ["-t", str(duration)]
    if watermark and Path(watermark).exists():
        cmd += ["-filter_complex", f"movie={shlex.quote(watermark)}[wm];[0:v][wm]overlay=10:10"]
        cmd += ["-map","0:a?","-c:a","aac","-c:v","libx264"]
    else:
        cmd += ["-map","0:v?","-map","0:a?","-c:v","copy","-c:a","aac"]
    if split>0: cmd += ["-fs", str(split*1024*1024)]
    cmd += [shlex.quote(outpath)]
    return " ".join(cmd)

async def spawn_record(url, outpath, duration, watermark, split):
    url = await resolve_php_m3u8(url)  # PHP URL auto decode
    cmd = build_ffmpeg_cmd(url, str(outpath), duration, watermark, split)
    return subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def generate_ffprobe(path):
    txt=str(path)+"_ffprobe.txt"
    subprocess.run(f'ffprobe -hide_banner -i "{path}" -show_format -show_streams > "{txt}" 2>&1', shell=True)
    return txt

# ---------------- MONITORING WITH RAINBOW ----------------

async def monitor_job(jid):
    j = jobs.get(jid)
    if not j: return
    proc = j["proc"]
    chat_id = j["chat"]
    msg_id = j["msg"]
    start = j["start"]
    duration = j["dur"]
    path = j["path"]
    url = j["url"]
    audio = j["audio"]

    spinner = ["🔴","🟠","🟡","🟢","🔵","🟣"]
    rainbow_blocks = ["🟥","🟧","🟨","🟩","🟦","🟪"]
    idx = 0
    last = 0
    last_t = time.time()

    while proc.poll() is None:  
        elapsed = int((datetime.now(timezone.utc) - start).total_seconds())  
        size = path.stat().st_size / 1024 / 1024 if path.exists() else 0  
        now = time.time()  
        bitrate = ((size - last) * 8) / max(now - last_t, 0.1)  
        last = size
        last_t = now  

        bar_len = 20
        progress_ratio = min(elapsed / duration, 1) if duration else 0
        filled_len = int(bar_len * progress_ratio)
        bar_anim = ""
        for i in range(filled_len):
            bar_anim += rainbow_blocks[(idx + i) % len(rainbow_blocks)]
        empty_len = bar_len - filled_len
        bar_anim += "⬛" * empty_len

        stream_ok = await check_url_ok(url)  
        spin = spinner[idx % len(spinner)]
        idx += 1  

        text = (
            f"{spin} **Recording `{jid}`**\n"
            f"[{bar_anim}] {int(progress_ratio*100) if duration else '∞'}%\n"
            f"⏱ Elapsed: {elapsed}s | 💾 Size: {size:.2f} MB | 🔻 Bitrate: {bitrate:.2f} Mbps\n"
            f"🎵 Audio Tracks: {len(audio)} | 📡 Stream: {'✅ OK' if stream_ok else '⚠️'}\n"
            f"✨ Stay tuned... Live rainbow recording! 🌈✨"
        )
        try: 
            await app.edit_message_text(chat_id, msg_id, text)  
        except: 
            pass  
        await asyncio.sleep(1)

    await app.edit_message_text(chat_id, msg_id, f"✅ Job `{jid}` completed. Processing...")  
    await upload_and_cleanup(jid)

# ---------------- UPLOAD & CLEANUP ----------------

async def upload_and_cleanup(jid):
    j=jobs.get(jid)
    if not j: return
    c=j["chat"]; p=j["path"]
    ff=generate_ffprobe(str(p))
    size=p.stat().st_size/1024/1024
    cap=f"✅ Recording finished\n🎥 {p.name}\n💾 {size:.2f} MB"
    try:
        if p.suffix.lower() in (".mp4",".mkv") and UPLOAD_AS_VIDEO:
            await app.send_video(c,str(p),caption=cap,supports_streaming=True)
        else:
            await app.send_document(c,str(p),caption=cap)
        await app.send_document(c,ff)
    except Exception as e:
        await app.send_message(c,f"❌ Upload failed\n{e}")
    finally:
        p.unlink(missing_ok=True)
        Path(ff).unlink(missing_ok=True)
        jobs.pop(jid,None)

# ---------------- COMMANDS ----------------

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text(
        "🎬 **Welcome to Super Premium M3U8 Recorder Bot!** 🎬\n\n"
        "🚀 **Features you’ll love:**\n"
        "• Multi-Audio Recording 🎵\n"
        "• Ultra-Advanced Progress Monitoring 📊\n"
        "• Custom Filenames & Watermark Support 💾\n"
        "• Named Link Save System 🔗\n"
        "• PHP URL Auto-Decode 🔑\n\n"
        "🛠 **Commands at your fingertips:**\n"
        "`/record <URL> <time|now> [name]` — Start recording instantly!\n"
        "`/recordlink <name> <time|now> [filename]` — Record from saved links\n"
        "`/savelink <name> <URL>` — Save a link for later\n"
        "`/links` — List all saved links\n"
        "`/dellink <name>` — Delete a saved link\n"
        "`/stop <job_id>` — Stop a recording\n"
        "`/status` — Check active recordings\n"
        "`/admins` — See bot admins\n"
        "`/addadmin <user_id>` — Add a new admin\n"
        "`/removeadmin <user_id>` — Remove an admin\n\n"
        "✨ _Start recording like a pro with just a command!_ ✨"
    )

@app.on_message(filters.command("addadmin"))
async def addadmin(client,message:Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("❌ Only Owner Not You!")
    a=message.text.split(maxsplit=1)
    if len(a)<2 or not a[1].isdigit():
        return await message.reply_text("Use: /addadmin <user_id>")
    uid=int(a[1]); ADMINS.add(uid)
    await message.reply_text(f"✅ Added {uid} as admin!")

# ---------------- REMOVE ADMIN ----------------

@app.on_message(filters.command("removeadmin"))
async def removeadmin(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("❌ Only Owner can remove admins!")
    a = message.text.split(maxsplit=1)
    if len(a) < 2 or not a[1].isdigit():
        return await message.reply_text("Use: /removeadmin <user_id>")
    uid = int(a[1])
    if uid not in ADMINS:
        return await message.reply_text(f"⚠️ User {uid} is not an admin.")
    if uid == OWNER_ID:
        return await message.reply_text("❌ You cannot remove the Owner!")
    ADMINS.remove(uid)
    await message.reply_text(f"🗑 Removed {uid} from admins!")

@app.on_message(filters.command("admins"))
async def admins(client,message:Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("❌ You Not allowed!")
    await message.reply_text("👑 Admins:\n"+"\n".join(str(i) for i in ADMINS))

# ---------------- RECORD ----------------

@app.on_message(filters.command("record"))
async def record(client,message:Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("⛔ You Not Admin!")
    a=message.text.split(maxsplit=3)
    if len(a)<2: return await message.reply_text("Use: /record <URL> <duration|now> [name]")
    url=a[1]; d=a[2] if len(a)>2 else "now"
    dur=None if d.lower()=="now" else parse_duration(d)
    cname=a[3] if len(a)>3 else uuid.uuid4().hex[:6]
    audio=await get_audio_tracks(await resolve_php_m3u8(url))
    safe=sanitize_filename(cname)
    op=TEMP_DIR/f"{safe}.mp4"
    pr=await spawn_record(url,str(op),dur,WATERMARK_PATH,SPLIT_SIZE_MB)
    msg=await message.reply_text("🔴 Recording started...")
    jid=uuid.uuid4().hex[:8]
    jobs[jid]={"proc":pr,"start":datetime.now(timezone.utc),"dur":dur,
               "path":op,"chat":message.chat.id,"msg":msg.id,"url":url,"audio":audio}
    asyncio.create_task(monitor_job(jid))

# ---------------- STOP ----------------

@app.on_message(filters.command("stop"))
async def stop(client,message:Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("⛔ You Not Admin!")
    a=message.text.split(maxsplit=1)
    if len(a)<2: return await message.reply_text("Use: /stop <job_id>")
    jid=a[1].strip(); j=jobs.get(jid)
    if not j: return await message.reply_text("No job")
    try: j["proc"].terminate()
    except: j["proc"].kill()
    await message.reply_text("🛑 Stop Sent")

# ---------------- STATUS ----------------

@app.on_message(filters.command("status"))
async def status(client,message:Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("⛔ You Not Admin!")
    if not jobs: return await message.reply_text("✅ No active jobs")
    t=["🎥 Active Jobs:"]
    for i,j in jobs.items():
        e=int((datetime.now(timezone.utc)-j["start"]).total_seconds())
        d=j["dur"] or "∞"
        filled=int(20*min(e/d,1)) if d != "∞" else 20
        t.append(f"{i} — [{'█'*filled}{'░'*(20-filled)}] {int(min(e/d,1)*100) if d!='∞' else '∞'}%")
    await message.reply_text("\n".join(t))

# ---------------- NAMED LINK COMMANDS ----------------

@app.on_message(filters.command("savelink"))
async def savelink(_,m:Message):
    if not is_admin(m.from_user.id):
        return await m.reply("⛔ Not Allowed!")
    a=m.text.split(maxsplit=2)
    if len(a)<3: return await m.reply("Use: /savelink <name> <URL>")
    name,url=a[1],a[2]; db=load_links(); db[name]=url; save_links(db)
    await m.reply(f"✅ Saved {name}")

@app.on_message(filters.command("links"))
async def links(_,m:Message):
    if not is_admin(m.from_user.id):
        return await m.reply("⛔ Not Allowed!")
    db=load_links()
    if not db: return await m.reply("No saved links")
    await m.reply("🔗 Saved Links:\n"+"\n".join(f"{k} → {v}" for k,v in db.items()))

@app.on_message(filters.command("dellink"))
async def dellink(_,m:Message):
    if not is_admin(m.from_user.id):
        return await m.reply("⛔ Not Allowed!")
    a=m.text.split(maxsplit=1)
    if len(a)<2: return await m.reply("Use: /dellink <name>")
    name=a[1]; db=load_links()
    if name not in db: return await m.reply("❌ Not found")
    db.pop(name); save_links(db)
    await m.reply(f"🗑 Deleted {name}")

@app.on_message(filters.command("recordlink"))
async def recordlink(_,m:Message):
    if not is_admin(m.from_user.id):
        return await m.reply("⛔ Not Allowed!")
    a=m.text.split(maxsplit=3)
    if len(a)<2: return await m.reply("Use: /recordlink <name> <duration|now> [filename]")
    name=a[1]; db=load_links()
    if name not in db: return await m.reply("❌ No saved link!")
    url=db[name]; dur=None if len(a)<3 or a[2].lower()=="now" else parse_duration(a[2])
    cname=a[3] if len(a)>3 else name+""+uuid.uuid4().hex[:4]
    op=TEMP_DIR/f"{sanitize_filename(cname)}.mp4"
    aud=await get_audio_tracks(await resolve_php_m3u8(url))
    pr=await spawn_record(url,str(op),dur,WATERMARK_PATH,SPLIT_SIZE_MB)
    msg2=await m.reply("🔴 Recording started from saved link...")
    jid=uuid.uuid4().hex[:8]
    jobs[jid]={"proc":pr,"start":datetime.now(timezone.utc),"dur":dur,
               "path":op,"chat":m.chat.id,"msg":msg2.id,"url":url,"audio":aud}
    asyncio.create_task(monitor_job(jid))

# ---------------- RUN BOT ----------------

app.run()
