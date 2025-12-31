import discord
from discord.ext import commands
from discord import app_commands
import aiohttp

class Deals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_base = "https://www.cheapshark.com/api/1.0"
        self.exchange_api = "https://api.exchangerate-api.com/v4/latest/USD"

    async def _get_exchange_rate(self, currency: str):
        """Fetch exchange rate from USD to the specified currency"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.exchange_api) as response:
                    if response.status == 200:
                        data = await response.json()
                        rates = data.get("rates", {})
                        currency_upper = currency.upper()
                        if currency_upper in rates:
                            return rates[currency_upper], currency_upper
            return None, None
        except Exception as e:
            print(f"Exchange rate error: {e}")
            return None, None

    def _convert_price(self, price_str: str, rate: float):
        """Convert a price string from USD to another currency"""
        try:
            price = float(price_str)
            return f"{price * rate:.2f}"
        except:
            return price_str

    async def _fetch_price_data(self, game_name: str, user_color, currency: str = None):
        """Helper method to fetch and format price data"""
        # Get exchange rate if currency is specified
        exchange_rate = 1.0
        currency_symbol = "$"
        currency_code = "USD"
        
        if currency:
            rate, curr_code = await self._get_exchange_rate(currency)
            if rate:
                exchange_rate = rate
                currency_code = curr_code
                # Common currency symbols
                currency_symbols = {
                    "EUR": "€",
                    "GBP": "£",
                    "INR": "₹",
                    "JPY": "¥",
                    "CNY": "¥",
                    "KRW": "₩",
                    "RUB": "₽",
                    "BRL": "R$",
                    "AUD": "A$",
                    "CAD": "C$",
                    "CHF": "CHF",
                    "MXN": "MX$",
                    "SGD": "S$",
                    "HKD": "HK$",
                    "TRY": "₺",
                    "AED": "AED",
                    "SAR": "SAR"
                }
                currency_symbol = currency_symbols.get(curr_code, curr_code + " ")
            else:
                error_embed = discord.Embed(
                    title="❌ Invalid Currency",
                    description=f"Currency code `{currency.upper()}` is not supported. Please use a valid ISO currency code like USD, EUR, GBP, INR, etc.",
                    color=user_color
                )
                return error_embed, None
        
        async with aiohttp.ClientSession() as session:
            # Search for the game
            search_url = f"{self.api_base}/games"
            params = {"title": game_name, "limit": 1}
            
            async with session.get(search_url, params=params) as response:
                if response.status != 200:
                    return None, "❌ Failed to fetch game data from CheapShark API."
                
                games = await response.json()
                
                if not games:
                    embed = discord.Embed(
                        title="🔍 Game Not Found",
                        description=f"No results found for **{game_name}**.\nPlease try a different search term.",
                        color=user_color
                    )
                    return embed, None
                
                game = games[0]
                game_id = game.get("gameID")
                game_title = game.get("external")
                cheapest_price = game.get("cheapest")
                thumb = game.get("thumb")
                
                # Get detailed deals for the game
                deals_url = f"{self.api_base}/games"
                deal_params = {"id": game_id}
                
                async with session.get(deals_url, params=deal_params) as deal_response:
                    if deal_response.status != 200:
                        return None, "❌ Failed to fetch deal details."
                    
                    deal_data = await deal_response.json()
                    deals = deal_data.get("deals", [])
                    
                    # Convert cheapest price
                    converted_cheapest = self._convert_price(cheapest_price, exchange_rate)
                    
                    # Create embed
                    embed = discord.Embed(
                        title=f"💰 {game_title}",
                        description=f"Price information from CheapShark",
                        color=user_color
                    )
                    
                    if thumb:
                        embed.set_image(url=thumb)
                    
                    # Show the cheapest current price
                    embed.add_field(
                        name="🏷️ Lowest Price Ever",
                        value=f"{currency_symbol}{converted_cheapest}" + (f" ({currency_code})" if currency else ""),
                        inline=True
                    )
                    
                    # Show best current deals (up to 5)
                    if deals:
                        deal_text = ""
                        stores = {
                            "1": "Steam",
                            "2": "GamersGate",
                            "3": "GreenManGaming",
                            "4": "Amazon",
                            "5": "GameStop",
                            "6": "Direct2Drive",
                            "7": "GOG",
                            "8": "Origin",
                            "11": "Humble Store",
                            "13": "Uplay",
                            "15": "Fanatical",
                            "21": "WinGameStore",
                            "23": "GameBillet",
                            "24": "Voidu",
                            "25": "Epic Games Store",
                            "27": "Gamesplanet",
                            "28": "Gamesload",
                            "29": "2Game",
                            "30": "IndieGala",
                            "31": "Blizzard Shop",
                            "33": "DLGamer",
                            "34": "Noctre",
                            "35": "DreamGame"
                        }
                        
                        for i, deal in enumerate(deals[:5]):
                            store_id = deal.get("storeID", "Unknown")
                            store_name = stores.get(store_id, f"Store {store_id}")
                            price = deal.get("price", "N/A")
                            retail_price = deal.get("retailPrice", "N/A")
                            savings = deal.get("savings", "0")
                            
                            # Convert prices
                            converted_price = self._convert_price(price, exchange_rate)
                            converted_retail = self._convert_price(retail_price, exchange_rate)
                            
                            if float(savings) > 0:
                                deal_text += f"**{store_name}**: ~~{currency_symbol}{converted_retail}~~ ➜ **{currency_symbol}{converted_price}** ({float(savings):.0f}% off)\n"
                            else:
                                deal_text += f"**{store_name}**: {currency_symbol}{converted_price}\n"
                        
                        embed.add_field(
                            name="🛒 Current Deals",
                            value=deal_text if deal_text else "No current deals available",
                            inline=False
                        )
                    
                    # Add footer with currency info
                    footer_text = "Powered by CheapShark API"
                    if currency:
                        footer_text += f" • Prices converted to {currency_code}"
                    else:
                        footer_text += " • Prices in USD"
                    embed.set_footer(text=footer_text)
                    
                    return embed, None

    @commands.command(name="price")
    async def check_price(self, ctx, *args):
        """Check the current price of a game using CheapShark API
        
        Usage:
            g!price game name [currency]
            g!price red dead redemption 2 inr
        """
        if not args:
            await ctx.reply("❌ Please provide a game name! Usage: `g!price game name [currency]`")
            return
        
        # Check if the last argument is a currency code (3 letters)
        currency = None
        game_name_parts = list(args)
        
        if len(args) > 1 and len(args[-1]) == 3 and args[-1].isalpha():
            # Last argument might be a currency code
            potential_currency = args[-1]
            # Verify it's a valid currency by checking with the API
            rate, curr_code = await self._get_exchange_rate(potential_currency)
            if rate:
                currency = potential_currency
                game_name_parts = args[:-1]
        
        game_name = " ".join(game_name_parts)
        
        async with ctx.typing():
            try:
                embed, error = await self._fetch_price_data(game_name, ctx.author.color, currency)
                if error:
                    await ctx.reply(error)
                else:
                    await ctx.reply(embed=embed)
                            
            except aiohttp.ClientError as e:
                await ctx.reply(f"❌ Network error occurred: {str(e)}")
            except Exception as e:
                await ctx.reply(f"❌ An error occurred: {str(e)}")
                print(f"Error in price command: {e}")

    @app_commands.command(name="price", description="Check the current price of a game")
    @app_commands.describe(
        game_name="The name of the game to search for",
        currency="Optional: Currency code (e.g., INR, EUR, GBP) - defaults to USD"
    )
    async def price_slash(self, interaction: discord.Interaction, game_name: str, currency: str = None):
        """Slash command version of price check"""
        await interaction.response.defer()
        try:
            embed, error = await self._fetch_price_data(game_name, interaction.user.color, currency)
            if error:
                await interaction.followup.send(error)
            else:
                await interaction.followup.send(embed=embed)
                        
        except aiohttp.ClientError as e:
            await interaction.followup.send(f"❌ Network error occurred: {str(e)}")
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")
            print(f"Error in price slash command: {e}")

async def setup(bot):
    await bot.add_cog(Deals(bot))
