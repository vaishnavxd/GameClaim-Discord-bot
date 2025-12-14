import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import traceback
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("g!"), intents=intents, help_command=None)

# -----------------------
# Events
# -----------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="for free games 🎮 | Use /help"))
    
    print("📋 Connected guilds:")
    for guild in bot.guilds:
        print(f" - {guild.name} (ID: {guild.id})")

    # Sync commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s) globally.")
    except Exception as e:
        print(f"❌ Failed to sync slash commands: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument. Please check your command usage.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `g!help` to see available commands.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have permission to perform that action.")
    else:
        print(f"❌ An error occurred: {error}")
        traceback.print_exc()
        await ctx.send("❌ An unexpected error occurred. Please try again later.")

async def main():
    # Load cogs
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Loaded cog: {filename}")
            except Exception as e:
                print(f"❌ Failed to load cog {filename}: {e}")
                traceback.print_exc()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
