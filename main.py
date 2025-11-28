
import os
import traceback
import requests
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from supabase import create_client

# -----------------------
# Config / Env
# -----------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not (TOKEN and SUPABASE_URL and SUPABASE_KEY):
    raise RuntimeError("Missing DISCORD_TOKEN or SUPABASE_URL or SUPABASE_KEY in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="g!", intents=intents, help_command=None)
tree = bot.tree

CLEANUP_DAYS = 14

# -----------------------
# Database helper funcs
# -----------------------
def upsert_guild_setting(guild_id: str, channel_id: str, ping_roles):
    payload = {
        "guild_id": guild_id,
        "channel_id": str(channel_id) if channel_id is not None else "0",
        "ping_roles": ping_roles or []
    }
    try:
        res = supabase.table("guild_settings").upsert(payload).execute()
        return res
    except Exception as e:
        print("❌ upsert_guild_setting error:", e)
        traceback.print_exc()
        return None

def get_all_guild_settings():
    try:
        res = supabase.table("guild_settings").select("*").execute()
        return res.data if getattr(res, "data", None) is not None else []
    except Exception as e:
        print("❌ get_all_guild_settings error:", e)
        traceback.print_exc()
        return []

def get_guild_setting(guild_id: str):
    try:
        res = supabase.table("guild_settings").select("*").eq("guild_id", str(guild_id)).limit(1).execute()
        rows = res.data if getattr(res, "data", None) is not None else []
        return rows[0] if rows else None
    except Exception as e:
        print("❌ get_guild_setting error:", e)
        traceback.print_exc()
        return None

def delete_guild_setting(guild_id: str):
    try:
        res = supabase.table("guild_settings").delete().eq("guild_id", str(guild_id)).execute()
        return res
    except Exception as e:
        print("❌ delete_guild_setting error:", e)
        traceback.print_exc()
        return None

def is_game_sent(guild_id: str, game_identifier: str):
    try:
        res = supabase.table("sent_games").select("id").eq("guild_id", str(guild_id)).eq("game_identifier", game_identifier).limit(1).execute()
        rows = res.data if getattr(res, "data", None) is not None else []
        return len(rows) > 0
    except Exception as e:
        print("❌ is_game_sent error:", e)
        traceback.print_exc()
        return False

def mark_game_sent(guild_id: str, game_identifier: str, title: str = None, url: str = None, announced_at=None):
    """
    Insert a sent_games row. `announced_at` may be:
      - None (use now())
      - a datetime.datetime (will be isoformatted)
      - an ISO string (used as-is if parseable)
    """
    # normalize announced_at to an ISO8601 string
    announced_at_iso = None
    try:
        if announced_at is None:
            announced_at_iso = datetime.now(timezone.utc).isoformat()
        elif isinstance(announced_at, str):
            # if it's already an ISO string, try to validate/normalize it
            try:
                # this will raise if not parseable
                _dt = datetime.fromisoformat(announced_at.replace("Z", "+00:00"))
                announced_at_iso = _dt.isoformat()
            except Exception:
                # fallback: use the string as-provided
                announced_at_iso = announced_at
        else:
            # assume it's a datetime-like object
            announced_at_iso = announced_at.isoformat()
    except Exception:
        # last-resort fallback
        announced_at_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "guild_id": str(guild_id),
        "game_identifier": game_identifier,
        "title": title,
        "url": url,
        "announced_at": announced_at_iso
    }
    try:
        res = supabase.table("sent_games").insert(payload).execute()
        return res
    except Exception as e:
        # unique-constraint duplicates or other DB errors are non-fatal for sending flow
        print("❌ mark_game_sent error (insert):", e)
        return None


def cleanup_sent_games_db(cutoff_days=CLEANUP_DAYS):
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    try:
        res = supabase.table("sent_games").delete().lt("announced_at", cutoff.isoformat()).execute()
        return res
    except Exception as e:
        print("❌ cleanup_sent_games_db error:", e)
        traceback.print_exc()
        return None

# -----------------------
# Utility: force-sync slash commands & print commands
# -----------------------
async def force_sync_commands():
    try:
        for guild in bot.guilds:
            try:
                print(f"🔁 Clearing & syncing guild commands for {guild.name} ({guild.id})...")
                # clear_commands is synchronous in this discord.py version — do NOT await it
                bot.tree.clear_commands(guild=guild)
                # sync is async — await it
                await bot.tree.sync(guild=guild)
                print(f"✅ Synced guild {guild.id}")
            except Exception as e:
                print(f"❌ Failed guild sync {guild.id}: {e}")
                traceback.print_exc()
        print("🔁 Requesting global sync...")
        await bot.tree.sync()
        print("✅ Global sync requested (may take up to 1h to propagate).")
    except Exception as e:
        print("❌ force_sync_commands failed:", e)
        traceback.print_exc()

# -----------------------
# send to guilds (database-backed)
# -----------------------
async def send_to_all_guilds(embed, platform, game_key, title=None, url=None, start_iso=None):
    settings = get_all_guild_settings()
    if not settings:
        print("ℹ️ No guild settings in DB; nothing to send.")
        return

    success_count = 0
    total = len(settings)

    for row in settings:
        guild_id = row.get("guild_id")
        raw_channel = row.get("channel_id")
        # validate channel id
        try:
            channel_id = int(raw_channel)
        except Exception:
            print(f"⚠️ Invalid channel_id for guild {guild_id}: {raw_channel}")
            continue

        # skip if already sent to this guild
        if is_game_sent(guild_id, game_key):
            print(f"🔁 Already sent {game_key} to guild {guild_id}, skipping.")
            continue

        channel = bot.get_channel(channel_id)
        if channel is None:
            print(f"❌ Channel {channel_id} not found for guild {guild_id}. Maybe deleted or bot lacks channel cache.")
            continue

        guild = bot.get_guild(int(guild_id))
        if guild is None:
            print(f"❌ Bot not in guild {guild_id}; skipping.")
            continue

        if not channel.permissions_for(guild.me).send_messages:
            print(f"❌ Bot lacks send_messages in channel {channel_id} (guild {guild_id}).")
            continue

        # build ping mention
        ping_roles = row.get("ping_roles") or []
        ping_mention = ""
        if ping_roles:
            mentions = []
            if isinstance(ping_roles, list):
                for rid in ping_roles:
                    try:
                        rid_int = int(rid)
                    except:
                        continue
                    role = guild.get_role(rid_int)
                    if role:
                        mentions.append(f"<@&{rid_int}>")
            else:
                try:
                    rid_int = int(ping_roles)
                    if rid_int == guild.id:
                        mentions = ["@everyone"]
                    else:
                        mentions = [f"<@&{rid_int}>"]
                except:
                    mentions = []
            ping_mention = " ".join(mentions) + (" " if mentions else "")

        try:
            await channel.send(ping_mention, embed=embed)
            mark_game_sent(guild_id, game_key, title=title, url=url, announced_at=(start_iso or None))
            success_count += 1
        except Exception as e:
            print(f"❌ Failed to send to channel {channel_id} in guild {guild_id}: {e}")
            traceback.print_exc()

    print(f"✅ Send summary: {success_count}/{total} succeeded.")

# -----------------------
# Events & Commands
# -----------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="g!help for free games 🎮"))

    # Start background loops if they're not already running
    if not check_free_games.is_running():
        check_free_games.start()
    if not steam_games.is_running():
        steam_games.start()
    # if not daily_cleanup.is_running():
    #     daily_cleanup.start()

    print("📋 Connected guilds:")
    for guild in bot.guilds:
        print(f" - {guild.name} (ID: {guild.id})")

    # cleanup older sent games once at startup
    cleanup_sent_games_db()

    # show prefix commands list
    print("Registered prefix commands:", [c.name for c in bot.commands])

    # force-sync slash commands to clear stale ones
    await force_sync_commands()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument. Please check your command usage.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `g!help` to see available commands.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have permission to perform that action.")
    else:
        print(f"❌ An error occurred: {error}")
        traceback.print_exc()
        await ctx.send("❌ An unexpected error occurred. Please try again later.")

# ---------- Admin / settings commands ----------
@bot.command()
@commands.has_permissions(administrator=True)
async def setchannel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    upsert_guild_setting(guild_id, str(channel.id), [])
    if channel.permissions_for(ctx.guild.me).send_messages:
        await ctx.send(f"✅ Game alerts will now be sent to {channel.mention}")
    else:
        await ctx.reply(f"⚠️ Alerts channel set to {channel.mention} but I don't have send permissions there!")

@bot.command()
@commands.has_permissions(administrator=True)
async def updateping(ctx, role: discord.Role = None):
    guild_id = str(ctx.guild.id)
    setting = get_guild_setting(guild_id)
    channel_id = setting["channel_id"] if setting else None
    if role is None:
        ping_list = []
        await ctx.send("✅ Ping role removed. No one will be pinged for new games.")
    else:
        ping_list = [str(role.id)]
        await ctx.send(f"✅ Ping role set to {role.mention}. This role will be mentioned for new game alerts.")
    upsert_guild_setting(guild_id, channel_id or "0", ping_list)

@bot.command()
async def currentchannel(ctx):
    gid = str(ctx.guild.id)
    setting = get_guild_setting(gid)
    if setting:
        try:
            channel = bot.get_channel(int(setting["channel_id"]))
            ping_roles = setting.get("ping_roles") or []
            if channel:
                ping_info = "No ping role set" if not ping_roles else f"Ping roles: {', '.join([str(x) for x in ping_roles])}"
                await ctx.reply(f"📢 Current alert channel is: {channel.mention}\n{ping_info}")
            else:
                await ctx.reply("❌ The saved channel does not exist anymore.")
        except Exception:
            await ctx.reply("❌ The saved channel does not exist anymore.")
    else:
        await ctx.reply("⚠️ No alert channel set. Use `g!setchannel #channel`.")

@bot.command()
@commands.has_permissions(administrator=True)
async def removechannel(ctx):
    gid = str(ctx.guild.id)
    delete_guild_setting(gid)
    await ctx.reply("✅ Alert channel removed.")

@bot.command()
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Bot latency: {round(bot.latency * 1000)}ms")


@bot.command()
async def author(ctx):
    embed = discord.Embed(
        title="**GameClaim Bot Made by Argue**",
        description="🤖 Crafted with ❤️ to track & alert free games on Steam and Epic 🎮"
    )
    try:
        user = await bot.fetch_user(842978764690030593)
        avatar = user.display_avatar.url
        embed.color = discord.Color.pink()
        embed.set_author(name=user.name, icon_url=avatar)
        embed.set_thumbnail(url=avatar)
    except Exception:
        pass
    embed.add_field(name="Links", value="[GitHub](https://github.com/vaishnavxd) | [YouTube](https://youtube.com/@vaishnavtf) | [Instagram](https://instagram.com/vaishnavxd)", inline=False)
    embed.set_footer(text="GameClaim • Free Game Tracker")
    await ctx.reply(embed=embed)

# -----------------------
# Help commands (prefix + slash)
# -----------------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="**GameClaim Bot Commands**",
        description="Use `g!` as the prefix for all commands.",
        color=discord.Color.blue()
    )
    embed.add_field(name="`g!setchannel #channel`", value="Set the alert channel.", inline=False)
    embed.add_field(name="`g!updateping @role`", value="Set a role to ping for new games (or remove by not passing a role).", inline=False)
    embed.add_field(name="`g!currentchannel`", value="Show the current alert channel and ping roles.", inline=False)
    embed.add_field(name="`g!removechannel`", value="Remove the alert channel.", inline=False)
    embed.add_field(name="`g!free epic/steam`", value="🎮 Get current free games from Epic or Steam.", inline=False)
    embed.add_field(name="`g!ping`", value="Bot latency check.", inline=False)
    embed.add_field(name="`g!author`", value="Bot creator info.", inline=False)
    embed.set_footer(text="GameClaim • Free Game Tracker")
    await ctx.reply(embed=embed)

@tree.command(name="help", description="Show the list of commands")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="**GameClaim Bot Commands**",
        description="Use `g!` as the prefix for all commands.",
        color=discord.Color.blue()
    )
    embed.add_field(name="`g!setchannel #channel`", value="Set the alert channel.", inline=False)
    embed.add_field(name="`g!updateping @role`", value="Set a role to ping for new game alerts.", inline=False)
    embed.add_field(name="`g!currentchannel`", value="Show the current alert channel.", inline=False)
    embed.add_field(name="`g!removechannel`", value="Remove the alert channel.", inline=False)
    embed.add_field(name="`g!free epic/steam`", value="🎮 Get current free games from Epic or Steam.", inline=False)
    embed.add_field(name="`g!ping`", value="Bot latency check.", inline=False)
    embed.add_field(name="`g!author`", value="Bot creator info.", inline=False)
    embed.set_footer(text="GameClaim • Free Game Tracker")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -----------------------
# free (epic + steam) command
# -----------------------
@bot.command()
async def free(ctx, platform=None):
    platforms = []
    if platform is None:
        platforms = ["epic", "steam"]
    elif platform.lower() in ["epic", "steam"]:
        platforms = [platform.lower()]
    else:
        await ctx.send("❌ Invalid platform. Use `g!free`, `g!free epic`, or `g!free steam`.")
        return

    embeds = []

    if "epic" in platforms:
        try:
            res = requests.get(
                "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US",
                timeout=10
            ).json()
            now = datetime.now(timezone.utc)
            for game in res["data"]["Catalog"]["searchStore"]["elements"]:
                title = game.get("title", "Unknown")
                promotions = game.get("promotions")
                if not promotions:
                    continue
                offers = promotions.get("promotionalOffers", [])
                if not offers or not offers[0]["promotionalOffers"]:
                    continue
                offer = offers[0]["promotionalOffers"][0]
                start = datetime.fromisoformat(offer["startDate"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(offer["endDate"].replace("Z", "+00:00"))
                if not (start <= now <= end):
                    continue

                slug = game.get("productSlug")
                if not slug:
                    catalog_ns = game.get("catalogNs")
                    if catalog_ns and isinstance(catalog_ns.get("mappings"), list) and catalog_ns["mappings"]:
                        slug = catalog_ns["mappings"][0].get("pageSlug", "")
                link = f"https://store.epicgames.com/en-US/p/{slug}" if slug else "https://store.epicgames.com/"
                price = game.get("price", {}).get("totalPrice", {}).get("originalPrice", 0) / 100
                images = game.get("keyImages", [])
                thumb = next(
                    (img["url"] for img in images if img.get("type") == "Thumbnail"),
                    images[0]["url"] if images else None
                )

                embed = discord.Embed(
                    title=f"🎮 **{title}**",
                    description=f"[Claim Here]({link})",
                    color=discord.Color.dark_gray()
                )
                embed.add_field(name="💲 Original Price", value=f"${price:.2f}", inline=True)
                embed.add_field(name="🕒 Free for", value=format_duration(end - now), inline=True)
                if thumb:
                    embed.set_image(url=thumb)
                embed.set_footer(text="GameClaim • Epic Freebie")
                embeds.append(embed)
        except Exception as e:
            print("Epic fetch error:", e)
            await ctx.send("❌ Failed to fetch Epic games. Please try again later.")

    if "steam" in platforms:
        try:
            res = requests.get("https://www.gamerpower.com/api/giveaways?platform=steam", timeout=10).json()
            for game in res[:5]:
                embed = discord.Embed(
                    title=f"🎮 **{game.get('title')}**",
                    description=game.get("description", "No description"),
                    color=discord.Color.blurple()
                )
                embed.add_field(name="💲 Value", value=game.get("worth", "N/A"), inline=True)
                embed.add_field(name="⏳ Ends On", value=game.get("end_date", "N/A"), inline=True)
                embed.add_field(name="🔗 Claim", value=f"[Click Here]({game.get('open_giveaway_url', '')})", inline=False)
                embed.set_image(url=game.get("thumbnail", ""))
                embed.set_footer(text="GameClaim • Steam Freebie")
                embeds.append(embed)
        except Exception as e:
            print("Steam fetch error:", e)
            await ctx.send("❌ Failed to fetch Steam games. Please try again later.")

    if embeds:
        for em in embeds:
            await ctx.send(embed=em)
    else:
        await ctx.send("😔 No free games found right now.")

# -----------------------
# Background loops (announce Epic & Steam free games)
# -----------------------
@tasks.loop(hours=1)
async def check_free_games():
    await bot.wait_until_ready()
    try:
        res = requests.get(
            "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US",
            timeout=10
        ).json()
    except Exception as e:
        print(f"❌ Failed to fetch Epic games: {e}")
        return

    for game in res["data"]["Catalog"]["searchStore"]["elements"]:
        title = game.get("title", "Unknown")
        promotions = game.get("promotions")
        if not promotions:
            continue

        offers = promotions.get("promotionalOffers", [])
        if not offers or not offers[0]["promotionalOffers"]:
            continue

        offer = offers[0]["promotionalOffers"][0]
        start = datetime.fromisoformat(offer["startDate"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(offer["endDate"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if not (start <= now <= end):
            continue

        slug = game.get("productSlug") or game.get("catalogNs", {}).get("mappings", [{}])[0].get("pageSlug", "")
        game_key = slug or title
        link = f"https://store.epicgames.com/en-US/p/{slug}" if slug else "https://store.epicgames.com/"
        price = game.get("price", {}).get("totalPrice", {}).get("originalPrice", 0) / 100
        images = game.get("keyImages", [])
        thumb = next((img["url"] for img in images if img.get("type") == "Thumbnail"), images[0]["url"] if images else None)

        embed = discord.Embed(
            title=f"🎮 **{title}**",
            description=f"[Click to claim the game here]({link})",
            color=discord.Color.light_gray()
        )
        embed.add_field(name="💲 Original Price", value=f"${price:.2f}", inline=True)
        embed.add_field(name="🕒 Offer Period", value=format_duration(end - now), inline=False)
        if thumb:
            embed.set_image(url=thumb)
        embed.set_footer(text="GameClaim • Epic Freebie")

        await send_to_all_guilds(embed, "epic", game_key, title=title, url=link, start_iso=start.isoformat())

@tasks.loop(hours=1)
async def steam_games():
    await bot.wait_until_ready()
    try:
        res = requests.get("https://www.gamerpower.com/api/giveaways?platform=steam", timeout=10).json()
    except Exception as e:
        print(f"❌ Failed to fetch Steam games: {e}")
        return

    for game in res[:5]:
        game_id = str(game.get("id"))
        embed = discord.Embed(
            title=f"🎮 **{game.get('title')}**",
            description=game.get("description", "No description"),
            color=discord.Color.blue()
        )
        embed.add_field(name="💲 Original Price", value=game.get("worth", "N/A"), inline=True)
        embed.add_field(name="⏳ Free Till", value=game.get("end_date", "N/A"), inline=True)
        embed.add_field(name="🔗 Claim", value=f"[Click Here]({game.get('open_giveaway_url', '')})", inline=False)
        embed.set_image(url=game.get("thumbnail", ""))
        embed.set_footer(text="GameClaim • Steam Freebie")

        await send_to_all_guilds(embed, "steam", game_id, title=game.get("title"), url=game.get("open_giveaway_url", ""))

# periodic DB cleanup every day
# @tasks.loop(hours=24)
# async def daily_cleanup():
#     cleanup_sent_games_db()

# -----------------------
# Helpers
# -----------------------
def format_duration(delta):
    parts = []
    if delta.days > 0:
        parts.append(f"{delta.days} day{'s' if delta.days != 1 else ''}")
    hours = delta.seconds // 3600
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0 and delta.days == 0:
        parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
    return " ".join(parts) if parts else "Ends soon!"

# Owner Only Section

@bot.command(name="guildsin")
@commands.is_owner()
async def guilds_in(ctx):
    await ctx.reply("📋 Connected guilds:")
    for guild in bot.guilds:
        await ctx.send(f" - {guild.name} (ID: {guild.id})")

@bot.command(name="promote")
@commands.is_owner()
async def promote(ctx):
    embed = discord.Embed(
        title="**Vote for GameClaim Bot!**",
        description="If you enjoy using GameClaim, please consider voting for us on Top.gg! Your support helps us grow and improve the bot.",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="Why Vote?", value="Voting helps us reach more users and continue providing free game alerts. It only takes a moment!", inline=False)
    embed.add_field(name="Vote Link", value="[Click here to vote](https://top.gg/bot/1390705635754119291/vote)", inline=False)
    embed.set_footer(text="Thank you for your support! 🎮")

    settings = get_all_guild_settings()
    for row in settings:
        try:
            ch = bot.get_channel(int(row.get("channel_id")))
            if ch:
                await ch.send(embed=embed)
        except Exception as e:
            print("❌ promote send error:", e)
    await ctx.reply("✅ Promotional message sent to all alert channels.")

@bot.command(name="announce_default")
@commands.is_owner()
async def announce_default(ctx, *, message: str = None):
    """
    Owner-only: send a message to each guild's default channel (system_channel or first sendable text channel).
    If no message is provided, sends a default reminder asking servers to re-run g!setchannel and g!updateping.
    """
    default_message = (
        "👋 Hi! The GameClaim bot's alert database was reset.\n\n"
        "Please reconfigure your server so you can keep receiving free-game alerts:\n"
        "• Set an alert channel with: `g!setchannel #channel`\n"
        "• Set a ping role (optional) with: `g!updateping @role`\n\n"
        "If you need help, run `g!help` or contact the bot owner."
    )

    text_to_send = message or default_message

    success = 0
    failed = 0
    failed_guilds = []  # keep small list for debugging (guild id and reason)

    for guild in bot.guilds:
        # pick a best-effort channel to send to
        target_channel = None

        try:
            # 1) try the system channel
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                target_channel = guild.system_channel
            else:
                # 2) fallback: first text channel where bot can send
                for ch in sorted(guild.text_channels, key=lambda c: c.position):
                    perms = ch.permissions_for(guild.me)
                    if perms.send_messages and perms.view_channel:
                        target_channel = ch
                        break

            if target_channel:
                try:
                    # Use embed for nicer look if message is long/contains newlines
                    if "\n" in text_to_send or len(text_to_send) > 120:
                        embed = discord.Embed(
                            title="📢 GameClaim: Please reconfigure alerts",
                            description=text_to_send,
                            color=discord.Color.gold()
                        )
                        embed.set_footer(text="GameClaim • run g!setchannel #channel and g!updateping @role")
                        await target_channel.send(embed=embed)
                    else:
                        # short single-line message -> plain text
                        await target_channel.send(text_to_send)
                    success += 1
                    continue
                except Exception as e:
                    print(f"❌ Send to channel {target_channel.id} (guild {guild.id}) failed: {e}")
                    # fallthrough to attempt DM
            # 3) if no channel or send failed, try DMing the owner
            try:
                owner = guild.owner
                if owner:
                    try:
                        await owner.send(
                            "Hi! I tried to remind your server about GameClaim settings but couldn't post in a channel. "
                            "Please re-run `g!setchannel #channel` in your server to re-enable free-game alerts.\n\n"
                            f"Message I tried to send:\n\n{ text_to_send }"
                        )
                        success += 1
                        continue
                    except Exception as e:
                        print(f"❌ DM to owner of {guild.id} failed: {e}")
            except Exception as e:
                print(f"❌ Could not fetch owner for guild {guild.id}: {e}")

            # If we reach here, it's a failure for this guild
            failed += 1
            failed_guilds.append((guild.id, guild.name))
        except Exception as e:
            print(f"❌ announce_default error for guild {guild.id}: {e}")
            traceback.print_exc()
            failed += 1
            failed_guilds.append((guild.id, guild.name))

    # Report back to the command invoker
    await ctx.reply(f"✅ Announcement attempts complete: {success} succeeded, {failed} failed.")
    if failed_guilds:
        # print to console for debugging; avoid spamming Discord if many
        print("Failed guilds (id, name):", failed_guilds)


# -----------------------
# Start loops & bot
# -----------------------
bot.run(TOKEN)



