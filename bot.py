import os
import time
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

# Duplikáció elleni védelem
last_sent_messages = {}


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
        # Duplikáció szűrés (ha 2 másodpercen belül ugyanaz az üzenet érkezik, eldobja)
        current_time = time.time()
        msg_key = (message.content, message.author.id)
        if msg_key in last_sent_messages and current_time - last_sent_messages[msg_key] < 2.0:
            return
        last_sent_messages[msg_key] = current_time

        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        
        if target_channel:
            role_mention = f"<@&{PING_ROLE_ID}>"
            allowed_mentions = discord.AllowedMentions(roles=True)

            # Ha az eredeti üzenet egy beágyazás (embed) volt
            if message.embeds:
                # Opcionálisan küldhetjük az eredeti embedeket is, de feldobhatjuk a pinggel
                await target_channel.send(content=role_mention, embeds=message.embeds, allowed_mentions=allowed_mentions)
            else:
                # Szép, egyedi prémium embed kártya építése
                content_text = message.content if message.content else "*[Csak csatolmány / médiaüzenet]*"
                
                embed = discord.Embed(
                    description=content_text,
                    color=discord.Color.from_rgb(88, 101, 242), # Szép Discord lila/kék tónus
                    timestamp=message.created_at
                )
                
                # Küldő adatai a fejlécben
                avatar_url = message.author.display_avatar.url if message.author.display_avatar else None
                embed.set_author(name=message.author.display_name, icon_url=avatar_url)
                
                # Hol honnan jött infó blokk
                guild_name = message.guild.name if message.guild else "Ismeretlen szerver"
                embed.add_field(
                    name="📍 Honnan érkezett?",
                    value=f"🌐 **Szerver:** {guild_name}\n📁 **Csatorna:** #{message.channel.name}",
                    inline=False
                )
                
                # Ha van kép a csatolmányban, rakjuk be szépen nagyméretben is
                if message.attachments:
                    for att in message.attachments:
                        if att.url.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                            embed.set_image(url=att.url)
                            break

                embed.set_footer(text=f"User ID: {message.author.id}")

                # Fájlok összekészítése, ha letölthető csatolmányok vannak
                files = []
                for attachment in message.attachments:
                    try:
                        files.append(await attachment.to_file())
                    except Exception:
                        pass

                await target_channel.send(content=role_mention, embed=embed, files=files, allowed_mentions=allowed_mentions)

    await bot.process_commands(message)


# A Token lekérése a környezeti változóból
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("Hiba: A TOKEN környezeti változó nincs beállítva!")
else:
    bot.run(TOKEN)
