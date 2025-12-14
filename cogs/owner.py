import discord
from discord.ext import commands
from utils.database import get_all_guild_settings

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="guildsin")
    @commands.is_owner()
    async def guilds_in(self, ctx):
        await ctx.reply("📋 Connected guilds:")
        for guild in self.bot.guilds:
            await ctx.send(f" - {guild.name} (ID: {guild.id})")

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

    @commands.command(name="announce_default")
    @commands.is_owner()
    async def announce_default(self, ctx, *, message: str = None):
        """
        Owner-only: send a message to each guild's default channel.
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
        failed_guilds = []

        for guild in self.bot.guilds:
            target_channel = None
            try:
                if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                    target_channel = guild.system_channel
                else:
                    for ch in sorted(guild.text_channels, key=lambda c: c.position):
                        perms = ch.permissions_for(guild.me)
                        if perms.send_messages and perms.view_channel:
                            target_channel = ch
                            break
                if target_channel:
                    try:
                        if "\n" in text_to_send or len(text_to_send) > 120:
                            embed = discord.Embed(
                                title="📢 GameClaim: Please reconfigure alerts",
                                description=text_to_send,
                                color=ctx.author.color
                            )
                            embed.set_footer(text="GameClaim • run g!setchannel #channel and g!updateping @role")
                            await target_channel.send(embed=embed)
                        else:
                            await target_channel.send(text_to_send)
                        success += 1
                        continue
                    except Exception:
                        pass
                
                # Fallback to DM
                try:
                    owner = guild.owner
                    if owner:
                        await owner.send(
                            "Hi! I tried to remind your server about GameClaim settings but couldn't post in a channel. "
                            "Please re-run `g!setchannel #channel` in your server to re-enable free-game alerts.\n\n"
                            f"Message I tried to send:\n\n{ text_to_send }"
                        )
                        success += 1
                        continue
                except Exception:
                    pass

                failed += 1
                failed_guilds.append((guild.id, guild.name))
            except Exception as e:
                print(f"❌ announce_default error for guild {guild.id}: {e}")
                failed += 1
                failed_guilds.append((guild.id, guild.name))

        await ctx.reply(f"✅ Announcement attempts complete: {success} succeeded, {failed} failed.")
        if failed_guilds:
            print("Failed guilds (id, name):", failed_guilds)

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
        embed.add_field(name="`g!announce_default [message]`", value="Send a default or custom message to each guild's default channel or DM the owner.", inline=False)
        embed.set_footer(text="GameClaim • Bot Owner Commands")
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Owner(bot))
