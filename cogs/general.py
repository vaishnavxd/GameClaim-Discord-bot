import discord
from discord.ext import commands
from discord import app_commands
import traceback

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -----------------------
    # Ping & Author
    # -----------------------
    @commands.command()
    async def ping(self, ctx):
        await ctx.reply(f"🏓 Pong! Bot latency: {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="ping", description="Check bot latency")
    async def slash_ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! Bot latency: {round(self.bot.latency * 1000)}ms")

    @commands.command()
    async def author(self, ctx):
        embed = await self._build_author_embed(ctx.author)
        await ctx.reply(embed=embed)

    @app_commands.command(name="author", description="Show bot creator info")
    async def slash_author(self, interaction: discord.Interaction):
        embed = await self._build_author_embed(interaction.user)
        await interaction.response.send_message(embed=embed)

    async def _build_author_embed(self, user):
        embed = discord.Embed(
            title="**GameClaim Bot Made by Argue**",
            description="🤖 Crafted with ❤️ to track & alert free games on Steam and Epic 🎮"
        )
        try:
            # Hardcoded ID from original code
            creator = await self.bot.fetch_user(842978764690030593)
            avatar = creator.display_avatar.url
            embed.color = user.color
            embed.set_author(name=creator.name, icon_url=avatar)
            embed.set_thumbnail(url=avatar)
        except Exception:
            pass
        embed.add_field(name="Links", value="[GitHub](https://github.com/vaishnavxd) | [YouTube](https://youtube.com/@vaishnavtf) | [Instagram](https://instagram.com/vaishnavxd)", inline=False)
        embed.set_footer(text="GameClaim • Free Game Tracker")
        return embed

    # -----------------------
    # Help (Prefix + Slash)
    # -----------------------
    @commands.command(name="help")
    async def help_command(self, ctx):
        embed = self._build_help_embed(ctx.author)
        await ctx.reply(embed=embed)

    @app_commands.command(name="help", description="Show the list of commands")
    async def slash_help(self, interaction: discord.Interaction):
        embed = self._build_help_embed(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _build_help_embed(self, user):
        embed = discord.Embed(
            title="**GameClaim Bot Commands**",
            description="Use `g!` or mention the bot as the prefix for all commands.",
            color=user.color
        )
        embed.add_field(name="`g!setchannel #channel`", value="Set the alert channel.", inline=False)
        embed.add_field(name="`g!updateping @role`", value="Set a role to ping (or remove by not passing a role).", inline=False)
        embed.add_field(name="`g!currentchannel`", value="Show the current alert channel and ping roles.", inline=False)
        embed.add_field(name="`g!removechannel`", value="Remove the alert channel.", inline=False)
        embed.add_field(name="`g!free epic/steam`", value="🎮 Get current free games from Epic or Steam.", inline=False)
        embed.add_field(name="`g!ping`", value="Bot latency check.", inline=False)
        embed.add_field(name="`g!author`", value="Bot creator info.", inline=False)
        embed.set_footer(text="GameClaim • Free Game Tracker")
        return embed



async def setup(bot):
    await bot.add_cog(General(bot))
