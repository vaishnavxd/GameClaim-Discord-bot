import discord
from discord.ext import commands
from utils.database import get_all_guild_settings

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
        embed.add_field(name="Vote Link", value="[Click here to vote](https://top.gg/bot/1390705635754119291/vote)", inline=False)
        embed.set_footer(text="Thank you for your support! 🎮")

        settings = get_all_guild_settings()
        for row in settings:
            try:
                ch = self.bot.get_channel(int(row.get("channel_id")))
                if ch:
                    await ch.send(embed=embed)
            except Exception as e:
                print("❌ promote send error:", e)
        await ctx.reply("✅ Promotional message sent to all alert channels.")


    @commands.command(name="announce")
    @commands.is_owner()
    async def announce(self, ctx, title: str, description: str, footer: str = None):
        """
        Send a custom announcement embed to all configured game alert channels.
        
        Usage:
            g!announce "Title" "Description" "Footer"
            g!announce "Update Available" "GameClaim v2.0 is now live!" "Thanks for using GameClaim"
        """
        success = 0
        failed = 0
        
        # Create embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=ctx.author.color
        )
        
        if footer:
            embed.set_footer(text=footer)
        else:
            embed.set_footer(text="GameClaim • Free Game Alerts")
        
        # Get all guild settings and send to their alert channels
        settings = get_all_guild_settings()
        for row in settings:
            try:
                ch = self.bot.get_channel(int(row.get("channel_id")))
                if ch:
                    await ch.send(embed=embed)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ announce send error: {e}")
                failed += 1
        
        await ctx.reply(f"✅ Announcement sent to {success} channels. Failed: {failed}")


    @commands.command(name="ownerhelp")
    @commands.is_owner()
    async def owner_help(self, ctx):
        embed = discord.Embed(
            title="**GameClaim Bot Owner Commands**",
            description="These commands are restricted to the bot owner.",
            color=ctx.author.color
        )
        embed.add_field(name="`g!guildsin`", value="List all guilds the bot is connected to.", inline=False)
        embed.add_field(name="`g!promote`", value="Send a promotional message to all guilds' alert channels.", inline=False)
        embed.add_field(name="`g!announce \"title\" \"description\" \"footer\"`", value="Send a custom embed announcement to all configured alert channels.", inline=False)
        embed.set_footer(text="GameClaim • Bot Owner Commands")
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Owner(bot))
