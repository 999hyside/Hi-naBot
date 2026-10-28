import os
import discord
from discord.ext import commands

# Intenzitások és bot inicializálása
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Konfigurációs azonosítók (id-k)
SOURCE_CHANNELS = [
    1458946879818567755,
    1485979274442833930,
    972849045087350825,
    1564310566288498748
]
TARGET_CHANNEL_ID = 1565026972663549982
PING_ROLE_ID = 1565051902964670524


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("HiénaBot fut és figyeli a csatornákat!")


@bot.event
async def on_message(message):
    # Ne reagáljon a saját üzeneteire
    if message.author == bot.user:
        return

    # Ellenőrizzük, hogy a megadott forrás csatornák valamelyikéből jött-e az üzenet
    if message.channel.id in SOURCE_CHANNELS:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        
        if target_channel:
            # Itt történik a varázslat: a rang ID-jét igazi Discord ping formátumba alakítjuk (<@&ID>)
            role_mention = f"<@&{PING_ROLE_ID}>"
            
            # Összeállítjuk az üzenetet a rang pingelésével és az eredeti szöveggel
            content_to_send = f"{role_mention}\n{message.content}"
            
            # Ha az üzenet tartalmaz embedet (sorsolási kártyát), azt is továbbítjuk a szöveggel és a pinggel együtt
            if message.embeds:
                await target_channel.send(content=content_to_send, embeds=message.embeds)
            else:
                await target_channel.send(content=content_to_send)

    await bot.process_commands(message)


# A Token lekérése a Render környezeti változójából (biztonságos módszer)
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("Hiba: A TOKEN környezeti változó nincs beállítva!")
else:
    bot.run(TOKEN)
