import discord
from discord.ext import commands
from discord import app_commands
import traceback
import asyncio

class HelpSelect(discord.ui.Select):
    def __init__(self, pages):
        options = [
            discord.SelectOption(label="Overview", description="Bot stats and general info", emoji="📊", value="overview"),
            discord.SelectOption(label="Gaming & Deals", description="Free games, prices, and tracking", emoji="🎮", value="gaming"),
            discord.SelectOption(label="Server Admin", description="Configure bot for your server", emoji="⚙️", value="admin"),
            discord.SelectOption(label="Info & Support", description="Bot credits and links", emoji="ℹ️", value="info")
        ]
        super().__init__(placeholder="Choose a category...", min_values=1, max_values=1, options=options)
        self.pages = pages

    async def callback(self, interaction: discord.Interaction):
        try:
            value = self.values[0]
            embed = self.pages.get(value)
            if embed:
                await interaction.response.edit_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ Error: Page '{value}' not found.", ephemeral=True)
        except Exception as e:
            print(f"[Help Error] Selection callback failed: {e}")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred while updating the menu.", ephemeral=True)

class HelpDropdownView(discord.ui.View):
    def __init__(self, pages, author, timeout=120):
        super().__init__(timeout=timeout)
        self.author = author
        self.pages = pages
        self.add_item(HelpSelect(pages))
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ You cannot control this help menu.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                # Silently fail on timeout if message is ephemeral or inaccessible
                pass

class CreditView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(label="GitHub", style=discord.ButtonStyle.link, url="https://github.com/vaishnavxd"))
        self.add_item(discord.ui.Button(label="YouTube", style=discord.ButtonStyle.link, url="https://youtube.com/@vaishnavtf"))
        self.add_item(discord.ui.Button(label="Instagram", style=discord.ButtonStyle.link, url="https://instagram.com/vaishnavxd"))

class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(label="Join Support Server", style=discord.ButtonStyle.link, url="https://discord.com/invite/kBN5jrD7QW"))
        self.add_item(discord.ui.Button(label="Invite Bot", style=discord.ButtonStyle.link, url="https://discord.com/oauth2/authorize?client_id=1390705635754119291&permissions=2147731520&integration_type=0&scope=bot"))

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ... Ping ...

    @commands.command()
    async def ping(self, ctx):
        await ctx.reply(f"🏓 Pong! Bot latency: {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="ping", description="Check bot latency")
    async def slash_ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! Bot latency: {round(self.bot.latency * 1000)}ms")

    @commands.command()
    async def credit(self, ctx):
        embed = await self._build_credit_embed(ctx.author)
        view = CreditView()
        await ctx.reply(embed=embed, view=view)

    @app_commands.command(name="credit", description="Show bot creator info")
    async def slash_credit(self, interaction: discord.Interaction):
        embed = await self._build_credit_embed(interaction.user)
        view = CreditView()
        await interaction.response.send_message(embed=embed, view=view)

    @commands.command(aliases=["support"])
    async def invite(self, ctx):
        embed = discord.Embed(
            title="**Invite GameClaim Bot**",
            description="Need help or want to invite the bot to your server?",
            color=ctx.author.color
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="Support Server", value="[Join Here](https://discord.com/invite/kBN5jrD7QW)", inline=True)
        embed.add_field(name="Invite Link", value="[Click to Invite](https://discord.com/oauth2/authorize?client_id=1390705635754119291&permissions=2147731520&integration_type=0&scope=bot)", inline=True)
        embed.set_footer(text="GameClaim • Support & Invite")
        
        view = InviteView()
        await ctx.reply(embed=embed, view=view)

    @app_commands.command(name="invite", description="Get invite link and support server")
    async def slash_invite(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="**Invite GameClaim Bot**",
            description="Need help or want to invite the bot to your server?",
            color=interaction.user.color
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="GameClaim • Support & Invite")
        
        view = InviteView()
        await interaction.response.send_message(embed=embed, view=view)

    async def _build_credit_embed(self, user):
        embed = discord.Embed(
            title="**GameClaim Bot Made by Argue**",
            description="🤖 Crafted with ❤️ to track & alert free games on Steam and Epic 🎮"
        )
        try:
            import os
            creator_id = int(os.getenv("BOT_CREATOR_ID", "842978764690030593"))
            creator = await self.bot.fetch_user(creator_id)
            avatar = creator.display_avatar.url
            embed.color = user.color
            embed.set_author(name=creator.name, icon_url=avatar)
            embed.set_thumbnail(url=avatar)
        except Exception:
            pass
        # Links moved to Buttons
        embed.set_footer(text="GameClaim • Free Game Tracker")
        return embed

    # -----------------------
    # Help (Prefix + Slash)
    # -----------------------
    def _get_help_pages(self, user):
        """Returns a dictionary of Embeds for the help command."""
        from datetime import datetime, timezone
        from utils.helpers import format_duration
        
        # --- Overview ---
        embed_overview = discord.Embed(
            title="**GameClaim Bot - Overview**",
            description="🤖 Track & alert free games on Steam and Epic Games 🎮\n🚀 Never miss a deal with real-time notifications for your favorite stores!",
            color=user.color
        )
        
        server_count = len(self.bot.guilds)
        member_count = sum(g.member_count or 0 for g in self.bot.guilds)
        
        uptime = "Unknown"
        if hasattr(self.bot, "launch_time"):
            diff = datetime.now(timezone.utc) - self.bot.launch_time
            uptime = format_duration(diff, fallback="Just started")
        
        embed_overview.add_field(name="**📊 Statistics**", value=f">>> **Servers:** {server_count}\n  **Members:** {member_count}\n  **Uptime:** {uptime}", inline=False)
        embed_overview.add_field(name="**🔗 Quick Links**", value="> [Invite Bot](https://discord.com/oauth2/authorize?client_id=1390705635754119291&permissions=2147731520&integration_type=0&scope=bot) • [Support Server](https://discord.com/invite/kBN5jrD7QW)", inline=False)
        embed_overview.add_field(name="**📍 How to use**", value="Select a category from the dropdown to see specific commands.", inline=False)
        embed_overview.set_footer(text="Category: Overview • GameClaim")

        # --- Gaming & Deals ---
        embed_gaming = discord.Embed(
            title="**🎮 Gaming & Deals Commands**",
            description="Find free games, track prices, and more.",
            color=user.color
        )
        embed_gaming.add_field(name="`g!free <source>` or `/free`", value="Get current free games from Epic or Steam.", inline=False)
        embed_gaming.add_field(name="`g!price <game> [currency]` or `/price`", value="Check game prices across multiple stores. Supports 25+ currencies.", inline=False)
        embed_gaming.add_field(name="`g!isgood <game>` or `/isgood`", value="Check if a game is worth buying based on its price history.", inline=False)
        embed_gaming.add_field(name="`g!store` or `/stores`", value="Show all supported stores for price comparison.", inline=False)
        embed_gaming.add_field(name="`g!track <game> [-atl|-sale]`", value="Get notified when a game goes on sale. Use `-atl` for All-Time Low alerts.", inline=False)
        embed_gaming.add_field(name="`g!track` (no arguments)", value="View or manage your current tracked game.", inline=False)
        embed_gaming.set_footer(text="Category: Gaming & Deals • GameClaim")

        # --- Server Admin ---
        embed_admin = discord.Embed(
            title="**⚙️ Server Setup Commands**",
            description="Configure the bot for your server (Admin only).",
            color=user.color
        )
        embed_admin.add_field(name="`g!setchannel #channel`", value="Set the alert channel for free game notifications.", inline=False)
        embed_admin.add_field(name="`g!updateping @role`", value="Set a role to ping on alerts.", inline=False)
        embed_admin.add_field(name="`g!currentchannel`", value="Show current alert settings.", inline=False)
        embed_admin.add_field(name="`g!removechannel`", value="Disable alerts for this server.", inline=False)
        embed_admin.set_footer(text="Category: Server Admin • GameClaim")

        # --- Info & Support ---
        embed_info = discord.Embed(
            title="**ℹ️ Info & Support**",
            description="General bot information and helpful links.",
            color=user.color
        )
        embed_info.add_field(name="`g!ping` or `/ping`", value="Check bot latency.", inline=False)
        embed_info.add_field(name="`g!credit` or `/credit`", value="Show bot creator info.", inline=False)
        embed_info.add_field(name="`g!invite` or `/invite`", value="Get invite link and support server.", inline=False)
        embed_info.add_field(name="Support Server", value="[Join Here](https://discord.com/invite/kBN5jrD7QW)", inline=False)
        embed_info.add_field(name="Invite Link", value="[Click to Invite](https://discord.com/oauth2/authorize?client_id=1390705635754119291&permissions=2147731520&integration_type=0&scope=bot)", inline=False)
        embed_info.set_footer(text="Category: Info & Support • GameClaim")

        return {
            "overview": embed_overview,
            "gaming": embed_gaming,
            "admin": embed_admin,
            "info": embed_info
        }

    @commands.command(name="help")
    async def help_command(self, ctx):
        pages = self._get_help_pages(ctx.author)
        view = HelpDropdownView(pages, ctx.author)
        message = await ctx.reply(embed=pages["overview"], view=view)
        view.message = message

    @app_commands.command(name="help", description="Show the list of commands")
    async def slash_help(self, interaction: discord.Interaction):
        pages = self._get_help_pages(interaction.user)
        view = HelpDropdownView(pages, interaction.user)
        await interaction.response.send_message(embed=pages["overview"], view=view, ephemeral=True)
        view.message = await interaction.original_response()



async def setup(bot):
    await bot.add_cog(General(bot))
