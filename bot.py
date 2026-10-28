import discord
from discord.ext import commands

# Forrás csatornák listája (ahol CSAK a botok üzeneteit figyeli)
BOT_ONLY_CHANNELS = [
    1458946879818567755,
    1564310566288498748,
    1564310566288498748  # Új szoba hozzáadva
]

# Forrás csatornák, ahol MINDENKIT (bárkit) figyel
EVERYONE_CHANNELS = [
    1410014162666393660
]

# Cél csatorna (ahová minden átkerül)
TARGET_CHANNEL_ID = 1565026972663549982

intents = discord.Intents.default()
intents.message_content = True  # KÖTELEZŐ: Developer Portalon be kell kapcsolni!

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"--- Bot sikeresen bejelentkezett: {bot.user.name} ---")
    
    # Ellenőrizzük az összes csatornát
    all_channels = BOT_ONLY_CHANNELS + EVERYONE_CHANNELS
    for channel_id in all_channels:
        channel = bot.get_channel(channel_id)
        if channel:
            print(f"[OK] Forrás csatorna megtalálva: #{channel.name} ({channel.guild.name})")
        else:
            print(f"[HIBA] A bot NEM látja a forrás csatornát ({channel_id})! Ellenőrizd a jogokat!")

    # Ellenőrizzük a cél csatornát
    target_channel = bot.get_channel(TARGET_CHANNEL_ID)
    if target_channel:
        print(f"[OK] Cél csatorna megtalálva: #{target_channel.name} ({target_channel.guild.name})")
    else:
        print(f"[HIBA] A bot NEM látja a cél csatornát ({TARGET_CHANNEL_ID})! Ellenőrizd a jogokat!")

    print("--- Figyelés elindítva ---")

@bot.event
async def on_message(message):
    # Elkerüljük, hogy a saját üzeneteire reagáljon
    if message.author == bot.user:
        return

    target_channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not target_channel:
        return

    should_forward = False

    # 1. Eset: Bot-only csatornák (itt csak a botok üzeneteit küldi át)
    if message.channel.id in BOT_ONLY_CHANNELS and message.author.bot:
        should_forward = True

    # 2. Eset: Mindenkit figyelő csatornák
    elif message.channel.id in EVERYONE_CHANNELS:
        should_forward = True

    # Ha teljesül a feltétel, átküldjük
    if should_forward:
        header = f"**[Átirányítva]** {message.author.name} írta a(z) **{message.guild.name}** szerveren (Csatorna: #{message.channel.name}):"
        content = f"{header}\n{message.content}" if message.content else header
        embeds = message.embeds if message.embeds else []

        # Fájlok / Képek továbbítása, ha vannak az üzenetben
        files = []
        for attachment in message.attachments:
            files.append(await attachment.to_file())

        await target_channel.send(content=content, embeds=embeds, files=files)
        print(f"[ÜZENET TOVÁBBÍTVA] {message.author.name} -> #{target_channel.name}")

    await bot.process_commands(message)

# Cseréld ki a bot tokenedre!
TOKEN = "MTU2NTAyNzMzNzE0ODU2NzU4NA.G55Dsd.iCuRlco-Q2Ga0ZsGMuhOwFvR8GLsjMxZ6ZhWEI"
bot.run(TOKEN)
