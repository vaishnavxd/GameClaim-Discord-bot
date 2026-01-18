import os
import discord
import logging
from discord.ext import commands
from dotenv import load_dotenv
import traceback
import asyncio

from keepAlive import keep_alive
keep_alive()

# Logs config
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")

intents = discord.Intents.default()
intents.message_content = True

from datetime import datetime, timezone

bot = commands.Bot(command_prefix=commands.when_mentioned_or("g!"), intents=intents, help_command=None)
bot.launch_time = datetime.now(timezone.utc)

# -----------------------
# Events
# -----------------------
@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="for free games 🎮 | Use /help"))
    
    server_count = len(bot.guilds)
    member_count = sum(g.member_count for g in bot.guilds)
    logging.info(f"📊 Stats: {server_count} servers | {member_count} members")

    # Sync commands
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        logging.error(f"❌ Sync failed: {e}")

@bot.event
async def on_command_error(ctx, error):
    # Ignore check failures for help command if any
    if isinstance(error, commands.CommandNotFound):
        # Optional: Don't reply to random messages that look like commands
        return
        
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument. Please check your command usage.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have permission to perform that action.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("❌ This command cannot be used in DMs.")
    else:
        # Log the full exception, but send a generic message to user
        logging.error(f"❌ Error in command {ctx.command}: {error}", exc_info=True)
        try:
            await ctx.send("❌ An unexpected error occurred. Please try again later.")
        except:
            pass # Use pass if we can't send message (e.g. no permissions)

async def main():
    # Load cogs
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("_"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                logging.info(f"✅ Loaded cog: {filename}")
            except Exception as e:
                logging.error(f"❌ Failed to load cog {filename}: {e}", exc_info=True)

    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

