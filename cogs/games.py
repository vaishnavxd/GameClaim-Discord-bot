import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
from datetime import datetime, timezone, timedelta
import traceback

from utils.database import get_all_guild_settings, is_game_sent, mark_game_sent, cleanup_sent_games_db
from utils.helpers import format_duration

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Start loops
        self.check_free_games.start()
        self.steam_games.start()
        # Initial cleanup
        cleanup_sent_games_db()

    def cog_unload(self):
        self.check_free_games.cancel()
        self.steam_games.cancel()

    @commands.command()
    async def free(self, ctx, platform: str = None):
        await self._free_logic(ctx, platform)

    @app_commands.command(name="free", description="Get current free games from Epic or Steam")
    @app_commands.describe(platform="Choose 'epic' or 'steam', or leave blank for both")
    @app_commands.choices(platform=[
        app_commands.Choice(name="Epic Games", value="epic"),
        app_commands.Choice(name="Steam", value="steam"),
        app_commands.Choice(name="Both", value="both")
    ])
    async def slash_free(self, interaction: discord.Interaction, platform: str = None):
        # For slash commands, we need to defer since this might take time
        await interaction.response.defer()
        # Create a wrapper context-like object
        await self._free_logic_slash(interaction, platform)

    async def _free_logic_slash(self, interaction, platform):
        """Slash command version of free logic"""
        if platform == "both":
            platform = None
        
        platforms = []
        if platform is None:
            platforms = ["epic", "steam"]
        elif platform.lower() in ["epic", "steam"]:
            platforms = [platform.lower()]
        else:
            await interaction.followup.send("❌ Invalid platform. Use epic, steam, or both.")
            return

        embeds = await self._fetch_free_games(platforms, interaction)
        
        if embeds:
            for em in embeds:
                await interaction.followup.send(embed=em)
        else:
            await interaction.followup.send("😔 No free games found right now.")

    async def _free_logic(self, ctx, platform):
        platforms = []
        if platform is None:
            platforms = ["epic", "steam"]
        elif platform.lower() in ["epic", "steam"]:
            platforms = [platform.lower()]
        else:
            await ctx.send("❌ Invalid platform. Use `g!free`, `g!free epic`, or `g!free steam`.")
            return

        embeds = await self._fetch_free_games(platforms, ctx)
        
        if embeds:
            for em in embeds:
                await ctx.send(embed=em)
        else:
            await ctx.send("😔 No free games found right now.")

    async def _fetch_free_games(self, platforms, ctx_or_interaction):
        """Fetch free games for the given platforms"""
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
                        color=discord.Color.from_str("#00FFFF")
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
                        color=discord.Color.from_str("#00FFFF")
                    )
                    embed.add_field(name="💲 Value", value=game.get("worth", "N/A"), inline=True)
                    embed.add_field(name="⏳ Ends On", value=game.get("end_date", "N/A"), inline=True)
                    embed.add_field(name="🔗 Claim", value=f"[Click Here]({game.get('open_giveaway_url', '')})", inline=False)
                    embed.set_image(url=game.get("thumbnail", ""))
                    embed.set_footer(text="GameClaim • Steam Freebie")
                    embeds.append(embed)
            except Exception as e:
                print("Steam fetch error:", e)
                if hasattr(ctx_or_interaction, 'send'):
                    await ctx_or_interaction.send("❌ Failed to fetch Steam games. Please try again later.")

        return embeds


    async def send_to_all_guilds(self, embed, platform, game_key, title=None, url=None, start_iso=None):
        settings = get_all_guild_settings()
        if not settings:
            print("ℹ️ No guild settings in DB; nothing to send.")
            return

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
            if is_game_sent(guild_id, game_key):
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
                await channel.send(ping_mention, embed=embed)
                mark_game_sent(guild_id, game_key, title=title, url=url, announced_at=(start_iso or None))
                success_count += 1
            except Exception as e:
                print(f"❌ Failed to send to channel {channel_id} in guild {guild_id}: {e}")

        print(f"✅ Send summary: {success_count}/{total} succeeded.")


    @tasks.loop(hours=1)
    async def check_free_games(self):
        try:
            res = requests.get(
                "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US",
                timeout=10
            ).json()
        except Exception as e:
            print(f"❌ Failed to fetch Epic games loop: {e}")
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
                color=discord.Color.from_str("#00FFFF")
            )
            embed.add_field(name="💲 Original Price", value=f"${price:.2f}", inline=True)
            embed.add_field(name="🕒 Offer Period", value=format_duration(end - now), inline=False)
            if thumb:
                embed.set_image(url=thumb)
            embed.set_footer(text="GameClaim • Epic Freebie")

            await self.send_to_all_guilds(embed, "epic", game_key, title=title, url=link, start_iso=start.isoformat())

    @check_free_games.before_loop
    async def before_check_free_games(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def steam_games(self):
        try:
            res = requests.get("https://www.gamerpower.com/api/giveaways?platform=steam", timeout=10).json()
        except Exception as e:
            print(f"❌ Failed to fetch Steam games loop: {e}")
            return

        for game in res[:5]:
            game_id = str(game.get("id"))
            embed = discord.Embed(
                title=f"🎮 **{game.get('title')}**",
                description=game.get("description", "No description"),
                color=discord.Color.from_str("#00FFFF")
            )
            embed.add_field(name="💲 Original Price", value=game.get("worth", "N/A"), inline=True)
            embed.add_field(name="⏳ Free Till", value=game.get("end_date", "N/A"), inline=True)
            embed.add_field(name="🔗 Claim", value=f"[Click Here]({game.get('open_giveaway_url', '')})", inline=False)
            embed.set_image(url=game.get("thumbnail", ""))
            embed.set_footer(text="GameClaim • Steam Freebie")

            await self.send_to_all_guilds(embed, "steam", game_id, title=game.get("title"), url=game.get("open_giveaway_url", ""))

    @steam_games.before_loop
    async def before_steam_games(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Games(bot))
