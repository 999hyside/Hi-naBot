import os
import time
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

SOURCE_CHANNELS = [
    1458946879818567755,
    1485979274442833930,
    972849045087350825,
    1564310566288498748
]
TARGET_CHANNEL_ID = 1565026972663549982
PING_ROLE_ID = 1565051902964670524

last_sent_messages = {}

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("HiénaBot fut és figyeli a csatornákat!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id in SOURCE_CHANNELS:
        current_time = time.time()
        
        content_lines = []
        
        # Ha van sima szöveg
        if message.content:
            content_lines.append(message.content)
            
        # Embed adatok teljeskörű kinyerése (cím, leírás, mezők, lábléc)
        if message.embeds:
            for emb in message.embeds:
                if emb.title:
                    content_lines.append(f"**{emb.title}**")
                if emb.description:
                    content_lines.append(emb.description)
                if emb.fields:
                    for field in emb.fields:
                        content_lines.append(f"\n**{field.name}**\n{field.value}")
                if emb.footer and emb.footer.text:
                    content_lines.append(f"\n*{emb.footer.text}*")

        final_content = "\n".join(content_lines) if content_lines else "*[Üres vagy nem támogatott üzenetformátum]*"

        # Duplikáció szűrés
        msg_key = (final_content, message.author.id)
        if msg_key in last_sent_messages and current_time - last_sent_messages[msg_key] < 2.0:
            return
        last_sent_messages[msg_key] = current_time

        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        
        if target_channel:
            role_mention = f"<@&{PING_ROLE_ID}>"
            allowed_mentions = discord.AllowedMentions(roles=True)

            embed = discord.Embed(
                description=final_content,
                color=discord.Color.from_rgb(43, 45, 49),
                timestamp=message.created_at
            )
            
            avatar_url = message.author.display_avatar.url if message.author.display_avatar else None
            embed.set_author(name=message.author.display_name, icon_url=avatar_url)
            
            guild_name = message.guild.name if message.guild else "Ismeretlen szerver"
            embed.add_field(
                name="📍 Forrás információ",
                value=f"🌐 **Szerver:** `{guild_name}`\n📁 **Csatorna:** `#{message.channel.name}`",
                inline=False
            )
            
            image_found = False
            if message.attachments:
                for att in message.attachments:
                    if att.url.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                        embed.set_image(url=att.url)
                        image_found = True
                        break
            
            if not image_found and message.embeds:
                for emb in message.embeds:
                    if emb.image and emb.image.url:
                        embed.set_image(url=emb.image.url)
                        break

            embed.set_footer(text=f"Közvetítő ID: {message.author.id} • HiénaBot", icon_url=bot.user.display_avatar.url)

            files = []
            for attachment in message.attachments:
                try:
                    files.append(await attachment.to_file())
                except Exception:
                    pass

            view = discord.ui.View()
            jump_button = discord.ui.Button(
                label="Eredeti üzenet megtekintése",
                url=message.jump_url,
                style=discord.ButtonStyle.link,
                emoji="🔗"
            )
            view.add_item(jump_button)

            await target_channel.send(
                content=role_mention, 
                embed=embed, 
                files=files, 
                view=view, 
                allowed_mentions=allowed_mentions
            )

    await bot.process_commands(message)

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("Hiba: A TOKEN környezeti változó nincs beállítva!")
else:
    bot.run(TOKEN)
