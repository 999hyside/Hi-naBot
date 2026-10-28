import os
import discord
from discord.ext import commands

# 1. Csatornák, ahol CSAK a botok üzeneteit figyeli
BOT_ONLY_CHANNELS = [
    1458946879818567755,
    1485979274442833930,
    972849045087350825
]

# 2. Csatorna, ahol MINDENKIT (bárkit) figyel
EVERYONE_CHANNELS = [
    1564310566288498748
]

# Cél csatorna (ahová minden átkerül)
TARGET_CHANNEL_ID = 1565026972663549982

# A rang ID, amit meg kell jelölni (tagelni)
PING_ROLE_ID = 1565051902964670524

intents = discord.Intents.default()
intents.message_content = True  # KÖTELEZŐ a Developer Portalon is bekapcsolni!

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"--- Bot sikeresen bejelentkezett: {bot.user.name} ---")
    
    # Ellenőrizzük az összes csatornát induláskor
    all_channels = BOT_ONLY_CHANNELS + EVERYONE_CHANNELS
    for channel_id in all_channels:
        channel = bot.get_channel(channel_id)
        if channel:
            print(f"[OK] Forrás csatorna megtalálva: #{channel.name} ({channel.guild.name})")
        else:
            print(f"[HIBA] A bot NEM látja a forrás csatornát ({channel_id})! Ellenőrizd a jogokat vagy hogy benne van-e a szerveren!")

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

    # 2. Eset: Mindenkit figyelő csatorna (bárki üzenete átmegy)
    elif message.channel.id in EVERYONE_CHANNELS:
        should_forward = True

    # Ha teljesül a feltétel, továbbítjuk a prémium kinézetű Embed kártyában
    if should_forward:
        embed = discord.Embed(
            description=message.content if message.content else "*[Csak csatolmány / üres üzenet]*",
            color=discord.Color.from_rgb(88, 101, 242),  # Szép Discord lila/kék szín
            timestamp=message.created_at
        )
        
        # Küldő neve és profilképe a fejlécben
        avatar_url = message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
        embed.set_author(name=message.author.name, icon_url=avatar_url)
        
        # Információs blokk
        embed.add_field(
            name="📍 Honnan érkezett?", 
            value=f"🌐 **Szerver:** {message.guild.name}\n📁 **Csatorna:** #{message.channel.name}", 
            inline=False
        )
        
        embed.set_footer(text=f"User ID: {message.author.id}")

        # Fájlok / Képek továbbítása, ha vannak az üzenetben
        files = []
        for attachment in message.attachments:
            files.append(await attachment.to_file())

        # A rang jelölése a kártya felett (content-ként), hogy ténylegesen pingeljen
        role_mention = f"<@&{PING_ROLE_ID}>"
        
        # Küldés allowed_mentions-szel, ami kényszeríti a Discordot, hogy ténylegesen pingeljen és kiszínezze a rangot!
        allowed_mentions = discord.AllowedMentions(roles=True)

        await target_channel.send(content=role_mention, embed=embed, files=files, allowed_mentions=allowed_mentions)
        print(f"[ÜZENET TOVÁBBÍTVA (PING-GEL)] {message.author.name} -> #{target_channel.name}")

    await bot.process_commands(message)

# Token beállítása biztonságosan a környezeti változóból
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
