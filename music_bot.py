import discord
from discord.ext import commands, tasks
import asyncio
import yt_dlp
import re
import os
from dotenv import load_dotenv
from aiohttp import web  # <-- for dummy HTTP server

load_dotenv()  # loads .env file
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Playback and queue
queue = []
is_playing = False
voice_client = None

# Auto-leave after inactivity
INACTIVITY_TIMEOUT = 1800  # 30 minutes in seconds
last_active = None

# FFMPEG options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True
}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    auto_leave_check.start()  # Start the loop only after the bot is ready

def is_url(input_str):
    # Basic check for YouTube URL
    return re.match(r'https?://(www\.)?youtube\.com/watch\?v=', input_str) or re.match(r'https?://youtu\.be/', input_str)

async def ensure_voice(ctx):
    global voice_client
    if ctx.author.voice:
        if voice_client is None or not voice_client.is_connected():
            voice_client = await ctx.author.voice.channel.connect()
    else:
        await ctx.send("You must be in a voice channel for me to join.")
        return False
    return True

async def play_next():
    global is_playing, queue, voice_client, last_active
    if len(queue) == 0:
        is_playing = False
        last_active = asyncio.get_event_loop().time()
        return

    is_playing = True
    url = queue.pop(0)

    source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
    voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(), bot.loop))

@bot.command()
async def help(ctx):
    help_text = """
**Music Bot Commands:**

- `!play <song name or URL>`
- `!skip`
- `!leave`
"""
    await ctx.send(help_text)

@bot.command()
async def play(ctx, *, search_or_url):
    global queue, is_playing, last_active
    if not await ensure_voice(ctx):
        return

    # Determine if input is URL or search term
    url = search_or_url
    if not is_url(search_or_url):
        # Search YouTube
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
        info = ytdl.extract_info(f"ytsearch:{search_or_url}", download=False)['entries'][0]
        url = info['url']

    queue.append(url)
    await ctx.send(f"Added to queue: {search_or_url}")
    last_active = asyncio.get_event_loop().time()

    if not is_playing:
        await play_next()

@bot.command()
async def skip(ctx):
    global voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("Skipped current song.")
    else:
        await ctx.send("Nothing is playing to skip.")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        queue.clear()  # optional: clear the queue on leaving
        await ctx.send("Disconnected from the voice channel and cleared the queue.")
    else:
        await ctx.send("I'm not in a voice channel!")

@tasks.loop(seconds=60)
async def auto_leave_check():
    global voice_client, last_active
    if voice_client and not voice_client.is_playing() and last_active:
        if asyncio.get_event_loop().time() - last_active > INACTIVITY_TIMEOUT:
            await voice_client.disconnect()
            voice_client = None
            print("Left voice channel due to inactivity.")

# -----------------------
# Dummy HTTP server for Render Free Web Service
# -----------------------
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_server():
    app = web.Application()
    app.add_routes([web.get("/", handle)])
    port = int(os.environ.get("PORT", 10000))  # Render assigns PORT
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP server running on port {port}")

# -----------------------
# Run both bot and server
# -----------------------
async def main():
    await start_server()
    await bot.start(TOKEN)

asyncio.run(main())
