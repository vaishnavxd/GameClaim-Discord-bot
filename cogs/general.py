import discord
from discord.ext import commands
from discord import app_commands
import traceback
import asyncio

class HelpPaginationView(discord.ui.View):
    def __init__(self, pages, author, timeout=60):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author = author
        self.current_page = 0
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ You cannot control this help menu.", ephemeral=True)
            return False
        return True

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        if self.current_page < 0:
            self.current_page = len(self.pages) - 1
        await self.update_message(interaction)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        if self.current_page >= len(self.pages):
            self.current_page = 0
        await self.update_message(interaction)



    async def on_timeout(self):
        if self.message:
            try:
                # Disable buttons on timeout
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except:
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
        """Returns a list of Embeds for the help command."""
        
        # --- Page 0: Main Menu ---
        embed_menu = discord.Embed(
            title="**GameClaim Bot - Main Menu**",
            description="Welcome to GameClaim Help! 🎮 \nUse the buttons below to navigate through the pages.",
            color=user.color
        )
        from datetime import datetime, timezone
        from utils.helpers import format_duration
        
        # Statistics
        server_count = len(self.bot.guilds)
        member_count = sum(g.member_count for g in self.bot.guilds)
        
        uptime = "Unknown"
        if hasattr(self.bot, "launch_time"):
            diff = datetime.now(timezone.utc) - self.bot.launch_time
            uptime = format_duration(diff, fallback="Just started")
        
        embed_menu.add_field(name="**📊 Statistics**", value=f"**Servers:** {server_count}\n**Members:** {member_count}\n**Uptime:** {uptime}", inline=False)
        embed_menu.add_field(name="**📍 Navigation**", value="⬅️ : Previous Page\n➡️ : Next Page", inline=False)
        embed_menu.set_footer(text="Page 1/6 • GameClaim")

        # --- Page 1: Free Games ---
        embed_free = discord.Embed(
            title="**🎮 Free Games Commands**",
            description="Commands to find free games.",
            color=user.color
        )
        embed_free.add_field(name="`g!free epic` or `/free epic`", value="Get current free games from Epic Games.", inline=False)
        embed_free.add_field(name="`g!free steam` or `/free steam`", value="Get current free games from Steam.", inline=False)
        embed_free.set_footer(text="Page 2/6 • GameClaim")

        # --- Page 2: Game Prices ---
        embed_price = discord.Embed(
            title="**💰 Game Price Commands**",
            description="Check game prices across multiple stores.",
            color=user.color
        )
        embed_price.add_field(name="`g!price <game> [currency]` or `/price`", value="Check game prices.\nExample: `g!price cyberpunk 2077 inr`\nSupports 25+ currencies (USD, EUR, GBP, INR, etc.)", inline=False)
        embed_price.set_footer(text="Page 3/6 • GameClaim")

        # --- Page 3: Game Tracking ---
        embed_track = discord.Embed(
            title="**🔔 Game Tracking Commands**",
            description="Get notified when a game goes on sale.",
            color=user.color
        )
        embed_track.add_field(name="`g!track <game> -atl`", value="Notify **ONLY** when the game hits its All-Time Low price.", inline=False)
        embed_track.add_field(name="`g!track <game> -sale`", value="Notify on **ANY** sale (default preference).", inline=False)
        embed_track.add_field(name="`g!track`", value="View or manage your current tracked game.", inline=False)
        embed_track.set_footer(text="Page 4/6 • GameClaim")

        # --- Page 3: Server Setup ---
        embed_setup = discord.Embed(
            title="**⚙️ Server Setup Commands**",
            description="Configure the bot for your server.",
            color=user.color
        )
        embed_setup.add_field(name="`g!setchannel #channel`", value="Set the alert channel for free game notifications.", inline=False)
        embed_setup.add_field(name="`g!updateping @role`", value="Set a role to ping on alerts (optional).", inline=False)
        embed_setup.add_field(name="`g!currentchannel`", value="Show current settings.", inline=False)
        embed_setup.add_field(name="`g!removechannel`", value="Disable alerts for this server.", inline=False)
        embed_setup.set_footer(text="Page 5/6 • GameClaim")

        # --- Page 4: Info & Utility ---
        embed_info = discord.Embed(
            title="**ℹ️ Info & Utility Commands**",
            description="General bot information.",
            color=user.color
        )
        embed_info.add_field(name="`g!ping` or `/ping`", value="Check bot latency.", inline=False)
        embed_info.add_field(name="`g!credit` or `/credit`", value="Show bot creator info.", inline=False)
        embed_info.add_field(name="`g!invite` or `/invite`", value="Get invite link and support server.", inline=False)
        embed_info.set_footer(text="Page 6/6 • GameClaim")

        return [embed_menu, embed_free, embed_price, embed_track, embed_setup, embed_info]

    @commands.command(name="help")
    async def help_command(self, ctx):
        pages = self._get_help_pages(ctx.author)
        view = HelpPaginationView(pages, ctx.author)
        message = await ctx.reply(embed=pages[0], view=view)
        view.message = message

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
        embed.add_field(name="`g!track <game>`", value="🔔 Track a game for price drops.", inline=False)
        embed.add_field(name="`g!ping`", value="Bot latency check.", inline=False)
        embed.add_field(name="`g!credit`", value="Bot creator info.", inline=False)
        embed.set_footer(text="GameClaim • Free Game Tracker")
        return embed



async def setup(bot):
    await bot.add_cog(General(bot))
