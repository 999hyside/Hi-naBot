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
            role_mention = f"<@&{PING_ROLE_ID}>"

            # Ha az eredeti üzenetben volt embed (pl. sorsolás), küldjük azt is a pinggel
            if message.embeds:
                await target_channel.send(content=role_mention, embeds=message.embeds)
            else:
                # Ha sima szöveges üzenet volt, öntsük egy szép, sötét tónusú Embedbe, hogy ne legyen csúnya
                embed = discord.Embed(
                    description=message.content,
                    color=0x2b2d31 # Discord sötét háttérszín stílus
                )
                embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
                
                await target_channel.send(content=role_mention, embed=embed)

    await bot.process_commands(message)


# A Token lekérése a Render környezeti változójából
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("Hiba: A TOKEN környezeti változó nincs beállítva!")
else:
    bot.run(TOKEN)
