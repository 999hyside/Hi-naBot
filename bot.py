"""
HiénaBot v2 – Discord relay bot
Figyeli a forráscsatornákat (akár más szervereken is), és szép embedben
átposztolja a célcsatornába, opcionális role pinggel.

Indítás:  TOKEN=xxxxx python bot.py
Függőség: pip install -U discord.py
"""

import asyncio
import copy
import json
import logging
import os
import re
import time
from collections import OrderedDict
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

# ──────────────────────────────────────────────────────────────
#  Konfiguráció (config.json, első indításkor automatikusan létrejön)
# ──────────────────────────────────────────────────────────────

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config.json"))

DEFAULT_CONFIG = {
    "target_channel_id": 1565026972663549982,
    "ping_role_id": 1565051902964670524,
    "ping_enabled": True,
    # Ha üres: minden üzenet pingel. Ha van benne szó: csak azok pingelnek,
    # amelyekben szerepel valamelyik kulcsszó.
    "ping_keywords": [],
    "sync_edits": True,     # szerkesztés követése
    "sync_deletes": True,   # törlés követése
    "sources": {
        "1458946879818567755": {"label": "Forrás #1", "emoji": "📢", "color": "#5865F2"},
        "1485979274442833930": {"label": "Forrás #2", "emoji": "🎁", "color": "#F1C40F"},
        "972849045087350825":  {"label": "Forrás #3", "emoji": "🔥", "color": "#E74C3C"},
        "1564310566288498748": {"label": "Forrás #4", "emoji": "💎", "color": "#1ABC9C"},
    },
    "stats": {},
}

DEFAULT_COLOR = "#5865F2"
HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")

MAX_DESC = 3800          # az embed leírás limit 4096, hagyunk helyet a többinek
MAX_REPLY_SNIPPET = 140
MAX_GALLERY = 4          # ennyi kép fér egy "galéria" embedbe
DEDUP_WINDOW = 2.0       # másodperc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("hienabot")


class Config:
    def __init__(self, path: Path):
        self.path = path
        self.data = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update(loaded)
            except Exception:
                log.exception("Nem sikerült beolvasni a config.json-t, alapértékekkel megyek.")
        else:
            self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()


cfg = Config(CONFIG_PATH)

# ──────────────────────────────────────────────────────────────
#  Bot
# ──────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True


class HienaBot(commands.Bot):
    async def setup_hook(self):
        self.tree.add_command(forras_group)
        self.tree.add_command(szuro_group)
        self.tree.add_command(beallitas_group)
        self.tree.add_command(ping_cmd)
        self.tree.add_command(statisztika_cmd)
        try:
            synced = await self.tree.sync()
            log.info("Slash parancsok szinkronizálva: %d db", len(synced))
        except Exception:
            log.exception("Slash parancs szinkronizálás sikertelen")


bot = HienaBot(command_prefix="!", intents=intents)

# forrás üzenet ID -> (cél csatorna ID, cél üzenet ID), szerkesztés/törlés követéséhez
relay_map: "OrderedDict[int, tuple[int, int]]" = OrderedDict()
RELAY_MAP_MAX = 1000

# duplikáció szűrés
last_sent: dict = {}

# küldések sorba állítása (rate limit barát)
send_lock = asyncio.Lock()

# ──────────────────────────────────────────────────────────────
#  Segédfüggvények
# ──────────────────────────────────────────────────────────────


def parse_color(value: str) -> discord.Color:
    value = (value or DEFAULT_COLOR).strip()
    if not HEX_RE.match(value):
        value = DEFAULT_COLOR
    return discord.Color(int(value.lstrip("#"), 16))


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def source_cfg(channel_id: int) -> dict | None:
    return cfg["sources"].get(str(channel_id))


def extract_text(message: discord.Message) -> str:
    """Üzenet szövege + az összes beágyazott embed tartalma."""
    parts = []
    if message.content:
        parts.append(message.content)

    for emb in message.embeds:
        if emb.author and emb.author.name:
            parts.append(f"🔄 **{emb.author.name}**")
        if emb.title:
            parts.append(f"**[{emb.title}]({emb.url})**" if emb.url else f"**{emb.title}**")
        if emb.description:
            parts.append(emb.description)
        for field in emb.fields:
            parts.append(f"\n**{field.name}**\n{field.value}")
        if emb.footer and emb.footer.text:
            parts.append(f"*{emb.footer.text}*")

    return "\n".join(parts).strip()


def reply_prefix(message: discord.Message) -> str:
    """Ha az üzenet válasz valamire, idézet sor a leírás elejére."""
    ref = message.reference.resolved if message.reference else None
    if isinstance(ref, discord.Message):
        snippet = ref.content or (extract_text(ref)) or "[csatolmány]"
        snippet = truncate(" ".join(snippet.split()), MAX_REPLY_SNIPPET)
        return f"> ↩️ **{ref.author.display_name}**: {snippet}\n\n"
    return ""


def compose_description(message: discord.Message) -> str:
    text = extract_text(message)
    desc = reply_prefix(message) + text
    return truncate(desc, MAX_DESC)


def should_ping(text: str) -> bool:
    if not cfg["ping_enabled"]:
        return False
    keywords = cfg["ping_keywords"]
    if not keywords:
        return True
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "file"


async def build_payload(message: discord.Message, src: dict, target: discord.TextChannel):
    """Összerakja az embed(ek)et és a feltöltendő fájlokat."""
    color = parse_color(src.get("color"))
    emoji = src.get("emoji", "📢")
    label = src.get("label", message.channel.name)

    description = compose_description(message)

    # --- csatolmányok ---
    limit = target.guild.filesize_limit
    files: list[discord.File] = []
    image_refs: list[str] = []
    skipped: list[discord.Attachment] = []
    total = 0

    for i, att in enumerate(message.attachments):
        if len(files) >= 10 or att.size > limit or total + att.size > limit:
            skipped.append(att)
            continue
        try:
            fname = f"{i}_{safe_filename(att.filename)}"
            f = await att.to_file(filename=fname, spoiler=att.is_spoiler())
        except Exception:
            log.warning("Csatolmány letöltése sikertelen: %s", att.filename)
            skipped.append(att)
            continue
        files.append(f)
        total += att.size
        if (att.content_type or "").startswith("image/"):
            image_refs.append(f"attachment://{f.filename}")

    # beágyazott embedekben lévő képek
    for emb in message.embeds:
        if emb.image and emb.image.url:
            image_refs.append(emb.image.url)
        elif emb.thumbnail and emb.thumbnail.url:
            image_refs.append(emb.thumbnail.url)

    image_refs = image_refs[:MAX_GALLERY]

    if not description and not image_refs and not files:
        description = "*[Nincs szöveges tartalom]*"

    # --- fő embed ---
    main = discord.Embed(
        title=f"{emoji}  {label}",
        description=description or None,
        color=color,
        timestamp=message.created_at,
        url=message.jump_url,
    )
    main.set_author(
        name=message.author.display_name,
        icon_url=message.author.display_avatar.url,
    )
    if message.guild and message.guild.icon:
        main.set_thumbnail(url=message.guild.icon.url)

    guild_name = message.guild.name if message.guild else "Ismeretlen szerver"
    main.add_field(name="🌐 Szerver", value=f"`{guild_name}`", inline=True)
    main.add_field(name="📁 Csatorna", value=f"`#{message.channel.name}`", inline=True)

    if skipped:
        links = "\n".join(f"[{truncate(a.filename, 40)}]({a.url})" for a in skipped[:5])
        main.add_field(name="📎 Nagy csatolmányok", value=links, inline=False)

    main.set_footer(
        text="HiénaBot",
        icon_url=bot.user.display_avatar.url if bot.user else None,
    )

    embeds = [main]

    # --- képgaléria: ugyanazzal az url-lel rendelkező embedek összeolvadnak ---
    if image_refs:
        main.set_image(url=image_refs[0])
        for ref in image_refs[1:]:
            extra = discord.Embed(url=message.jump_url, color=color)
            extra.set_image(url=ref)
            embeds.append(extra)

    # --- gomb ---
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Eredeti üzenet megtekintése",
            url=message.jump_url,
            style=discord.ButtonStyle.link,
            emoji="🔗",
        )
    )

    return embeds, files, view


def remember_relay(source_id: int, target_channel_id: int, target_message_id: int):
    relay_map[source_id] = (target_channel_id, target_message_id)
    while len(relay_map) > RELAY_MAP_MAX:
        relay_map.popitem(last=False)


def cleanup_dedup(now: float):
    stale = [k for k, t in last_sent.items() if now - t > 60]
    for k in stale:
        del last_sent[k]


# ──────────────────────────────────────────────────────────────
#  Események
# ──────────────────────────────────────────────────────────────


@bot.event
async def on_ready():
    log.info("Bejelentkezve: %s (ID: %s)", bot.user.name, bot.user.id)
    log.info("HiénaBot fut, %d forráscsatornát figyel.", len(cfg["sources"]))
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(cfg['sources'])} forráscsatornát",
        )
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or message.guild is None:
        return

    src = source_cfg(message.channel.id)
    if src is None:
        await bot.process_commands(message)
        return

    try:
        await relay_message(message, src)
    except Exception:
        log.exception("Hiba az üzenet továbbításakor (%s)", message.jump_url)

    await bot.process_commands(message)


async def relay_message(message: discord.Message, src: dict):
    target = bot.get_channel(cfg["target_channel_id"])
    if target is None:
        log.warning("A célcsatorna nem található (ID: %s)", cfg["target_channel_id"])
        return
    if message.channel.id == target.id:
        return

    text = extract_text(message)

    # duplikáció szűrés
    now = time.time()
    cleanup_dedup(now)
    key = (text, message.author.id, message.channel.id)
    if text and key in last_sent and now - last_sent[key] < DEDUP_WINDOW:
        return
    last_sent[key] = now

    # üres (pl. rendszerüzenet) kihagyása
    if not text and not message.attachments:
        return

    embeds, files, view = await build_payload(message, src, target)

    ping = should_ping(text)
    content = f"<@&{cfg['ping_role_id']}>" if ping else None
    allowed = (
        discord.AllowedMentions(roles=[discord.Object(id=cfg["ping_role_id"])])
        if ping
        else discord.AllowedMentions.none()
    )

    async with send_lock:
        sent = await target.send(
            content=content,
            embeds=embeds,
            files=files,
            view=view,
            allowed_mentions=allowed,
        )

    remember_relay(message.id, target.id, sent.id)

    stats = cfg["stats"]
    sid = str(message.channel.id)
    stats[sid] = stats.get(sid, 0) + 1
    cfg.save()


@bot.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    if not cfg["sync_edits"]:
        return
    ref = relay_map.get(payload.message_id)
    if ref is None:
        return

    src_channel = bot.get_channel(payload.channel_id)
    tgt_channel = bot.get_channel(ref[0])
    if src_channel is None or tgt_channel is None:
        return

    try:
        src_msg = await src_channel.fetch_message(payload.message_id)
        tgt_msg = await tgt_channel.fetch_message(ref[1])
    except (discord.NotFound, discord.Forbidden):
        return

    if not tgt_msg.embeds:
        return

    main = tgt_msg.embeds[0]
    main.description = compose_description(src_msg) or None
    main.set_footer(
        text="HiénaBot • ✏️ szerkesztve",
        icon_url=main.footer.icon_url if main.footer else None,
    )
    try:
        await tgt_msg.edit(embeds=[main] + tgt_msg.embeds[1:])
    except discord.HTTPException:
        log.exception("Szerkesztés követése sikertelen")


@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    if not cfg["sync_deletes"]:
        return
    ref = relay_map.pop(payload.message_id, None)
    if ref is None:
        return
    tgt_channel = bot.get_channel(ref[0])
    if tgt_channel is None:
        return
    try:
        msg = await tgt_channel.fetch_message(ref[1])
        await msg.delete()
    except (discord.NotFound, discord.Forbidden):
        pass


# ──────────────────────────────────────────────────────────────
#  Slash parancsok
# ──────────────────────────────────────────────────────────────


def is_admin():
    """Csak a bot tulajdonosa, vagy a célszerver 'Szerver kezelése' joggal rendelkező tagjai."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if await bot.is_owner(interaction.user):
            return True
        target = bot.get_channel(cfg["target_channel_id"])
        if (
            target is not None
            and interaction.guild_id == target.guild.id
            and interaction.user.guild_permissions.manage_guild
        ):
            return True
        raise app_commands.CheckFailure("Ehhez nincs jogosultságod.")

    return app_commands.check(predicate)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        msg = "⛔ Ehhez nincs jogosultságod."
    else:
        log.exception("Slash parancs hiba", exc_info=error)
        msg = "❌ Hiba történt a parancs végrehajtásakor."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


def ok_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description or None, color=discord.Color.green())


# --- /forras ----------------------------------------------------------------

forras_group = app_commands.Group(
    name="forras",
    description="Figyelt forráscsatornák kezelése",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
)


@forras_group.command(name="hozzaad", description="Új forráscsatorna figyelése")
@app_commands.describe(
    csatorna_id="A figyelendő csatorna ID-ja",
    cimke="Megjelenő név (pl. Hírek)",
    emoji="Ikon (pl. 📢)",
    szin="Hex szín (pl. #F1C40F)",
)
@is_admin()
async def forras_hozzaad(
    interaction: discord.Interaction,
    csatorna_id: str,
    cimke: str,
    emoji: str = "📢",
    szin: str = DEFAULT_COLOR,
):
    if not csatorna_id.isdigit():
        await interaction.response.send_message("❌ A csatorna ID csak szám lehet.", ephemeral=True)
        return
    if not HEX_RE.match(szin):
        await interaction.response.send_message("❌ A szín hex formátumú legyen, pl. `#F1C40F`.", ephemeral=True)
        return
    cfg["sources"][csatorna_id] = {
        "label": cimke,
        "emoji": emoji,
        "color": "#" + szin.lstrip("#").upper(),
    }
    cfg.save()
    await interaction.response.send_message(
        embed=ok_embed("✅ Forrás hozzáadva", f"{emoji} **{cimke}** (`{csatorna_id}`)"),
        ephemeral=True,
    )


@forras_group.command(name="torol", description="Forráscsatorna eltávolítása")
@app_commands.describe(csatorna_id="Az eltávolítandó csatorna ID-ja")
@is_admin()
async def forras_torol(interaction: discord.Interaction, csatorna_id: str):
    if cfg["sources"].pop(csatorna_id, None) is None:
        await interaction.response.send_message("❌ Ez a csatorna nincs a listában.", ephemeral=True)
        return
    cfg.save()
    await interaction.response.send_message(
        embed=ok_embed("🗑️ Forrás törölve", f"`{csatorna_id}`"), ephemeral=True
    )


@forras_group.command(name="lista", description="Figyelt csatornák listája")
@is_admin()
async def forras_lista(interaction: discord.Interaction):
    lines = []
    for cid, s in cfg["sources"].items():
        ch = bot.get_channel(int(cid))
        where = f"{ch.guild.name} › #{ch.name}" if ch else "ismeretlen / nem látható"
        lines.append(f"{s.get('emoji', '📢')} **{s.get('label', '?')}** `{cid}`\n└ {where} • `{s.get('color', DEFAULT_COLOR)}`")
    embed = discord.Embed(
        title="👀 Figyelt csatornák",
        description="\n\n".join(lines) or "*Nincs beállított forrás.*",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- /szuro -----------------------------------------------------------------

szuro_group = app_commands.Group(
    name="szuro",
    description="Ping kulcsszó szűrő",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
)


@szuro_group.command(name="hozzaad", description="Kulcsszó hozzáadása (csak ezekre pingel)")
@app_commands.describe(szo="Kulcsszó, pl. giveaway")
@is_admin()
async def szuro_hozzaad(interaction: discord.Interaction, szo: str):
    szo = szo.strip().lower()
    if szo and szo not in cfg["ping_keywords"]:
        cfg["ping_keywords"].append(szo)
        cfg.save()
    await interaction.response.send_message(
        embed=ok_embed("✅ Kulcsszó hozzáadva", f"`{szo}`"), ephemeral=True
    )


@szuro_group.command(name="torol", description="Kulcsszó törlése")
@app_commands.describe(szo="A törlendő kulcsszó")
@is_admin()
async def szuro_torol(interaction: discord.Interaction, szo: str):
    szo = szo.strip().lower()
    if szo in cfg["ping_keywords"]:
        cfg["ping_keywords"].remove(szo)
        cfg.save()
        await interaction.response.send_message(embed=ok_embed("🗑️ Kulcsszó törölve", f"`{szo}`"), ephemeral=True)
    else:
        await interaction.response.send_message("❌ Nincs ilyen kulcsszó.", ephemeral=True)


@szuro_group.command(name="lista", description="Kulcsszavak listája")
@is_admin()
async def szuro_lista(interaction: discord.Interaction):
    kws = cfg["ping_keywords"]
    text = ", ".join(f"`{k}`" for k in kws) if kws else "*Nincs szűrő, minden üzenet pingel.*"
    await interaction.response.send_message(embed=ok_embed("🔎 Ping kulcsszavak", text), ephemeral=True)


# --- /beallitas -------------------------------------------------------------

beallitas_group = app_commands.Group(
    name="beallitas",
    description="Bot beállítások",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
)


@beallitas_group.command(name="cel", description="Célcsatorna beállítása")
@app_commands.describe(csatorna="Ide érkeznek az átposztolt üzenetek")
@is_admin()
async def beallitas_cel(interaction: discord.Interaction, csatorna: discord.TextChannel):
    cfg["target_channel_id"] = csatorna.id
    await interaction.response.send_message(
        embed=ok_embed("✅ Célcsatorna beállítva", csatorna.mention), ephemeral=True
    )


@beallitas_group.command(name="role", description="Ping role beállítása")
@app_commands.describe(role="Ezt a role-t pingeli a bot")
@is_admin()
async def beallitas_role(interaction: discord.Interaction, role: discord.Role):
    cfg["ping_role_id"] = role.id
    await interaction.response.send_message(
        embed=ok_embed("✅ Ping role beállítva", role.mention), ephemeral=True
    )


@beallitas_group.command(name="szerkesztes", description="Szerkesztések követése be/ki")
@app_commands.describe(allapot="Be vagy ki")
@app_commands.choices(allapot=[app_commands.Choice(name="be", value=1), app_commands.Choice(name="ki", value=0)])
@is_admin()
async def beallitas_szerkesztes(interaction: discord.Interaction, allapot: app_commands.Choice[int]):
    cfg["sync_edits"] = bool(allapot.value)
    await interaction.response.send_message(
        embed=ok_embed("✏️ Szerkesztés követése", f"**{allapot.name}**"), ephemeral=True
    )


@beallitas_group.command(name="torles", description="Törlések követése be/ki")
@app_commands.describe(allapot="Be vagy ki")
@app_commands.choices(allapot=[app_commands.Choice(name="be", value=1), app_commands.Choice(name="ki", value=0)])
@is_admin()
async def beallitas_torles(interaction: discord.Interaction, allapot: app_commands.Choice[int]):
    cfg["sync_deletes"] = bool(allapot.value)
    await interaction.response.send_message(
        embed=ok_embed("🗑️ Törlés követése", f"**{allapot.name}**"), ephemeral=True
    )


# --- /ping és /statisztika --------------------------------------------------


@app_commands.command(name="ping", description="Role ping be- vagy kikapcsolása")
@app_commands.describe(allapot="Be vagy ki")
@app_commands.choices(allapot=[app_commands.Choice(name="be", value=1), app_commands.Choice(name="ki", value=0)])
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@is_admin()
async def ping_cmd(interaction: discord.Interaction, allapot: app_commands.Choice[int]):
    cfg["ping_enabled"] = bool(allapot.value)
    await interaction.response.send_message(
        embed=ok_embed("🔔 Role ping", f"**{allapot.name}**"), ephemeral=True
    )


@app_commands.command(name="statisztika", description="Melyik forrásból hány üzenet érkezett")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@is_admin()
async def statisztika_cmd(interaction: discord.Interaction):
    stats = cfg["stats"]
    if not stats:
        await interaction.response.send_message("📊 Még nincs adat.", ephemeral=True)
        return
    rows = sorted(stats.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(stats.values())
    lines = []
    for cid, count in rows:
        s = cfg["sources"].get(cid, {})
        name = f"{s.get('emoji', '📢')} {s.get('label', cid)}"
        lines.append(f"**{name}** – `{count}` db")
    embed = discord.Embed(
        title="📊 Statisztika",
        description="\n".join(lines) + f"\n\n**Összesen:** `{total}` üzenet",
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────────────────────
#  Indítás
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        log.error("Hiba: A TOKEN környezeti változó nincs beállítva!")
    else:
        bot.run(TOKEN, log_handler=None)
