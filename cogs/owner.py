import discord
from discord.ext import commands
from discord import app_commands
import asyncio

from utils.database import get_all_guild_settings

class AnnounceModal(discord.ui.Modal, title='Broadcast Announcement'):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.ann_title = discord.ui.TextInput(
            label='Title',
            placeholder='Announcement Title',
            min_length=5,
            max_length=200,
        )
        self.description = discord.ui.TextInput(
            label='Description',
            style=discord.TextStyle.long,
            placeholder='Body of the announcement...',
            min_length=10,
            max_length=2000,
        )
        self.image_url = discord.ui.TextInput(
            label='Image URL (Optional)',
            placeholder='https://...',
            required=False,
        )
        self.thumbnail_url = discord.ui.TextInput(
            label='Thumbnail URL (Optional)',
            placeholder='https://...',
            required=False,
        )
        self.footer_text = discord.ui.TextInput(
            label='Footer Text (Optional)',
            placeholder='Custom footer text',
            required=False,
        )

        self.add_item(self.ann_title)
        self.add_item(self.description)
        self.add_item(self.image_url)
        self.add_item(self.thumbnail_url)
        self.add_item(self.footer_text)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(
            title=self.ann_title.value,
            description=self.description.value,
            color=discord.Color.blue()
        )
        
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)
        if self.thumbnail_url.value:
            embed.set_thumbnail(url=self.thumbnail_url.value)
        
        footer = self.footer_text.value or "GameClaim Announcement"
        embed.set_footer(text=footer)

        # Confirm send View
        view = ConfirmSendView(embed, interaction.user, self.cog)
        await interaction.followup.send(
            "📢 **Preview of your announcement:**\nClick 'Confirm' to send to ALL servers.",
            embed=embed, 
            view=view,
            ephemeral=True
        )

class ConfirmSendView(discord.ui.View):
    def __init__(self, embed, author, cog):
        super().__init__(timeout=60)
        self.embed = embed
        self.author = author
        self.cog = cog
        self.value = None

    @discord.ui.button(label="Confirm & Send", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return
        await interaction.response.edit_message(content="⏳ Broadcasting...", view=None)
        
        success, total = await self.cog._send_to_guilds_parallel(self.embed)
        
        await interaction.followup.send(f"✅ Broadcast complete! Sent to {success}/{total} servers.", ephemeral=True)
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return
        await interaction.response.edit_message(content="❌ Cancelled.", view=None)
        self.value = False
        self.stop()

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(5)

    async def _send_to_guilds_parallel(self, embed):
        """Helper to send announcement to all guilds in parallel"""
        settings = await get_all_guild_settings()
        if not settings:
            return 0, 0

        success_count = 0
        total = len(settings)
        
        async def send_to_one(row):
            nonlocal success_count
            async with self.semaphore:
                try:
                    ch_id = int(row.get("channel_id"))
                    ch = self.bot.get_channel(ch_id)
                    if ch:
                        await ch.send(embed=embed)
                        return True
                except:
                    pass
                return False

        results = await asyncio.gather(*(send_to_one(row) for row in settings))
        success_count = sum(results)
        return success_count, total

    @commands.command(name="promote")
    @commands.is_owner()
    async def promote(self, ctx):
        embed = discord.Embed(
            title="**Vote for GameClaim Bot!**",
            description="If you enjoy using GameClaim, please consider voting for us on Top.gg! Your support helps us grow and improve the bot.",
            color=ctx.author.color
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="Why Vote?", value="Voting helps us reach more users and continue providing free game alerts. It only takes a moment!", inline=False)
        embed.add_field(name="Vote Link", value=f"[Click here to vote](https://top.gg/bot/{self.bot.user.id}/vote)", inline=False)
        embed.set_footer(text="Thank you for your support! 🎮")

        msg = await ctx.reply("🚀 Started broadcasting promotion...")
        success, total = await self._send_to_guilds_parallel(embed)
        await msg.edit(content=f"✅ Promotion sent to **{success}/{total}** servers.")

    @commands.command(name="announce")
    @commands.is_owner()
    async def announce(self, ctx):
        """Opens a modal to create a custom announcement"""
        view = discord.ui.View()
        button = discord.ui.Button(label="Create Announcement", style=discord.ButtonStyle.blurple)
        
        async def button_callback(interaction):
            if interaction.user != ctx.author:
                return
            await interaction.response.send_modal(AnnounceModal(self))
        
        button.callback = button_callback
        view.add_item(button)
        
        await ctx.reply("Click the button to create an announcement:", view=view)
        
    @app_commands.command(name="announce", description="Broadcast an announcement (Owner only)")
    async def slash_announce(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ You are not the owner.", ephemeral=True)
            return
        
        await interaction.response.send_modal(AnnounceModal(self))

    @commands.command(name="guildsin")
    @commands.is_owner()
    async def guilds_in(self, ctx):
        guild_count = len(self.bot.guilds)
        embed = discord.Embed(
            title="🌐 Server Statistics",
            description=f"GameClaim is currently serving **{guild_count}** Discord servers!",
            color=ctx.author.color
        )
        embed.set_footer(text="Thank you for using GameClaim! 🎮")
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Owner(bot))
