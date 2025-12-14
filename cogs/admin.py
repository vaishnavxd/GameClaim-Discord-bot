import discord
from discord.ext import commands
from discord import app_commands
from utils.database import upsert_guild_setting, get_guild_setting, delete_guild_setting

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setchannel(self, ctx, channel: discord.TextChannel):
        await self._setchannel_logic(ctx.guild, channel, ctx)

    @app_commands.command(name="setchannel", description="Set the alert channel for free game notifications")
    @app_commands.default_permissions(administrator=True)
    async def slash_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._setchannel_logic(interaction.guild, channel, interaction)

    async def _setchannel_logic(self, guild, channel, ctx_or_interaction):
        guild_id = str(guild.id)
        res = upsert_guild_setting(guild_id, str(channel.id), [])
        if res is None:
            msg = "⚠️ Failed to save channel settings. Please try again."
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(msg)
            else:
                await ctx_or_interaction.reply(msg)
            return

        msg = f"✅ Game alerts will now be sent to {channel.mention}" if channel.permissions_for(guild.me).send_messages else f"⚠️ Alerts channel set to {channel.mention} but I don't have send permissions there!"
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(msg)
        else:
            await ctx_or_interaction.send(msg)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def updateping(self, ctx, role: discord.Role = None):
        await self._updateping_logic(ctx.guild, role, ctx)

    @app_commands.command(name="updateping", description="Set a role to ping for new game alerts")
    @app_commands.default_permissions(administrator=True)
    async def slash_updateping(self, interaction: discord.Interaction, role: discord.Role = None):
        await self._updateping_logic(interaction.guild, role, interaction)

    async def _updateping_logic(self, guild, role, ctx_or_interaction):
        guild_id = str(guild.id)

        setting = get_guild_setting(guild_id)
        channel_id = setting["channel_id"] if setting else "0"
        
        if role is None:
            ping_list = []
            msg = "✅ Ping role removed. No one will be pinged for new games."
        else:
            ping_list = [str(role.id)]
            msg = f"✅ Ping role set to {role.mention}. This role will be mentioned for new game alerts."
        
        upsert_guild_setting(guild_id, channel_id, ping_list)
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(msg)
        else:
            await ctx_or_interaction.send(msg)

    @commands.command()
    async def currentchannel(self, ctx):
        await self._currentchannel_logic(ctx.guild, ctx)

    @app_commands.command(name="currentchannel", description="Show the current alert channel and ping roles")
    async def slash_currentchannel(self, interaction: discord.Interaction):
        await self._currentchannel_logic(interaction.guild, interaction)

    async def _currentchannel_logic(self, guild, ctx_or_interaction):
        gid = str(guild.id)
        setting = get_guild_setting(gid)
        if setting:
            try:
                channel = self.bot.get_channel(int(setting["channel_id"]))
                ping_roles = setting.get("ping_roles") or []
                if channel:
                    ping_info = "No ping role set" if not ping_roles else f"Ping roles: {', '.join([str(x) for x in ping_roles])}"
                    msg = f"📢 Current alert channel is: {channel.mention}\n{ping_info}"
                else:
                    msg = "❌ The saved channel does not exist anymore."
            except Exception:
                msg = "❌ The saved channel does not exist anymore."
        else:
            msg = "⚠️ No alert channel set. Use `g!setchannel #channel`."
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(msg)
        else:
            await ctx_or_interaction.reply(msg)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def removechannel(self, ctx):
        await self._removechannel_logic(ctx.guild, ctx)

    @app_commands.command(name="removechannel", description="Remove the alert channel")
    @app_commands.default_permissions(administrator=True)
    async def slash_removechannel(self, interaction: discord.Interaction):
        await self._removechannel_logic(interaction.guild, interaction)

    async def _removechannel_logic(self, guild, ctx_or_interaction):
        gid = str(guild.id)
        delete_guild_setting(gid)
        msg = "✅ Alert channel removed."
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(msg)
        else:
            await ctx_or_interaction.reply(msg)

async def setup(bot):
    await bot.add_cog(Admin(bot))
