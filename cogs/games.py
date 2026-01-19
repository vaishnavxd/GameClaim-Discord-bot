import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta
import traceback

from utils.database import get_all_guild_settings, is_game_sent, mark_game_sent, cleanup_sent_games_db
from utils.helpers import format_duration

class GameView(discord.ui.View):
    def __init__(self, claim_url, vote_url):
        super().__init__()
        self.add_item(discord.ui.Button(label="Claim Game", style=discord.ButtonStyle.link, url=claim_url))
        self.add_item(discord.ui.Button(label="Vote for Bot", style=discord.ButtonStyle.link, url=vote_url))

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        # Start loops safely
        if not self.check_free_games.is_running():
            self.check_free_games.start()
        if not self.steam_games.is_running():
            self.steam_games.start()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def cog_load(self):
        # Initial cleanup scheduled here to be async compatible
        asyncio.create_task(cleanup_sent_games_db())

    async def send_to_all_guilds(self, embed, platform, game_key, title=None, url=None, start_iso=None):
        settings = await get_all_guild_settings()
        if not settings:
            print("ℹ️ No guild settings in DB; nothing to send.")
            return

        # Prepare View
        vote_url = f"https://top.gg/bot/{self.bot.user.id}/vote"
        view = GameView(url, vote_url)

        success_count = 0
        total = len(settings)

        for row in settings:
            guild_id = row.get("guild_id")
            raw_channel = row.get("channel_id")
            try:
                channel_id = int(raw_channel)
            except Exception:
                continue

            # skip if already sent
            if await is_game_sent(guild_id, game_key):
                continue

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue

            if not channel.permissions_for(guild.me).send_messages:
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
                    # fallback
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
                await channel.send(ping_mention, embed=embed, view=view)
                await mark_game_sent(guild_id, game_key, title=title, url=url, announced_at=(start_iso or None))
                success_count += 1
            except Exception as e:
                print(f"❌ Failed to send to channel {channel_id} in guild {guild_id}: {e}")

        print(f"✅ Send summary: {success_count}/{total} succeeded.")

    async def fetch_epic_games(self):
        """Fetches free games from Epic Games Store"""
        games_found = []
        try:
            url = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"
            async with self.session.get(url, timeout=10) as response:
                if response.status != 200:
                    return []
                res = await response.json()
        except Exception as e:
            print(f"❌ Failed to fetch Epic games: {e}")
            return []

        if not res or "data" not in res:
            return []

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
            
            price_data = game.get("price", {}).get("totalPrice", {})
            price = price_data.get("originalPrice", 0) / 100
            
            images = game.get("keyImages", [])
            thumb = next((img["url"] for img in images if img.get("type") == "Thumbnail"), images[0]["url"] if images else None)

            embed = discord.Embed(
                title=f"🎮 **{title}**",
                description="Grab it before it's gone!",
                color=discord.Color.from_str("#00FFFF")
            )
            embed.add_field(name="💲 Original Price", value=f"${price:.2f}", inline=True)
            embed.add_field(name="🕒 Offer Period", value=format_duration(end - now), inline=False)
            if thumb:
                embed.set_image(url=thumb)
            embed.set_footer(text="GameClaim • Epic Freebie")

            games_found.append({
                "key": game_key,
                "title": title,
                "url": link,
                "embed": embed,
                "start_iso": start.isoformat()
            })
        
        return games_found

    async def fetch_steam_games(self):
        """Fetches free games from GamerPower (Steam)"""
        games_found = []
        try:
            url = "https://www.gamerpower.com/api/giveaways?platform=steam"
            async with self.session.get(url, timeout=10) as response:
                if response.status != 200:
                    return []
                res = await response.json()
        except Exception as e:
            print(f"❌ Failed to fetch Steam games: {e}")
            return []

        for game in res[:5]:
            game_id = str(game.get("id"))
            embed = discord.Embed(
                title=f"🎮 **{game.get('title')}**",
                description=game.get("description", "Free on Steam!"),
                color=discord.Color.from_str("#00FFFF")
            )
            embed.add_field(name="💲 Original Price", value=game.get("worth", "N/A"), inline=True)
            embed.add_field(name="⏳ Free Till", value=game.get("end_date", "N/A"), inline=True)
            embed.set_image(url=game.get("thumbnail", ""))
            embed.set_footer(text="GameClaim • Steam Freebie")

            games_found.append({
                "key": game_id,
                "title": game.get("title"),
                "url": game.get("open_giveaway_url", ""),
                "embed": embed,
                "start_iso": None
            })
        
        return games_found

    @tasks.loop(hours=1)
    async def check_free_games(self):
        games = await self.fetch_epic_games()
        for game in games:
            await self.send_to_all_guilds(
                game['embed'], 
                "epic", 
                game['key'], 
                title=game['title'], 
                url=game['url'], 
                start_iso=game['start_iso']
            )

    @check_free_games.before_loop
    async def before_check_free_games(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def steam_games(self):
        games = await self.fetch_steam_games()
        for game in games:
            await self.send_to_all_guilds(
                game['embed'], 
                "steam", 
                game['key'], 
                title=game['title'], 
                url=game['url'], 
                start_iso=game['start_iso']
            )

    @steam_games.before_loop
    async def before_steam_games(self):
        await self.bot.wait_until_ready()

    @commands.command(name="free")
    async def free_command(self, ctx, source: str = None):
        """Manually fetch and show current free games."""
        source = source.lower() if source else "all"
        
        games_to_show = []
        async with ctx.typing():
            if source in ["epic", "all"]:
                games_to_show.extend(await self.fetch_epic_games())
            if source in ["steam", "all"]:
                games_to_show.extend(await self.fetch_steam_games())
        
        if not games_to_show:
            await ctx.reply("❌ No free games found at the moment.", mention_author=False)
            return
            
        vote_url = f"https://top.gg/bot/{self.bot.user.id}/vote"
        for game in games_to_show:
            view = GameView(game['url'], vote_url)
            await ctx.reply(embed=game['embed'], view=view, mention_author=False)

    @app_commands.command(name="free", description="Get current free games")
    @app_commands.choices(platform=[
        app_commands.Choice(name="Epic Games", value="epic"),
        app_commands.Choice(name="Steam", value="steam"),
        app_commands.Choice(name="All", value="all")
    ])
    async def slash_free(self, interaction: discord.Interaction, platform: app_commands.Choice[str] = None):
        await interaction.response.defer()
        source = platform.value if platform else "all"
        
        games_to_show = []
        if source in ["epic", "all"]:
            games_to_show.extend(await self.fetch_epic_games())
        if source in ["steam", "all"]:
            games_to_show.extend(await self.fetch_steam_games())

        if not games_to_show:
            await interaction.followup.send("❌ No free games found at the moment.")
            return

        vote_url = f"https://top.gg/bot/{self.bot.user.id}/vote"
        for game in games_to_show:
             view = GameView(game['url'], vote_url)
             await interaction.followup.send(embed=game['embed'], view=view)

async def setup(bot):
    await bot.add_cog(Games(bot))
