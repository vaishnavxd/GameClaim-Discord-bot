import discord
from discord.ext import commands
from discord import app_commands
import aiohttp

class CurrencySelect(discord.ui.Select):
    def __init__(self, cog, game_data):
        self.cog = cog
        self.game_data = game_data
        
        common_currencies = [
            "USD", "EUR", "GBP", "INR", "CAD", "AUD", "BRL", "JPY", "CNY", 
            "RUB", "KRW", "TRY", "MXN", "IDR", "PLN", "SEK", "CHF", "SGD", 
            "HKD", "NZD", "THB", "PHP", "MYR", "ZAR", "SAR"
        ]
        options = [
            discord.SelectOption(label=curr, description=f"Show prices in {curr}") 
            for curr in common_currencies
        ]
        
        super().__init__(placeholder="Change Currency", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        currency = self.values[0]
        
        # Re-generate embed with new currency
        embed = await self.cog.create_price_embed(self.game_data, interaction.user.color, currency)
        await interaction.edit_original_response(embed=embed, view=self.view)

class PriceView(discord.ui.View):
    def __init__(self, cog, game_data, deals):
        super().__init__(timeout=120)
        self.add_item(CurrencySelect(cog, game_data))
        
        # Add a link button to the cheapest deal if available
        if deals:
            # Cheapest deal is usually the first one in the list? Or logic in embed.
            # The API returns deals sorted by savings? Unsure. 
            # We'll use the first one or the "cheapest" field from game lookup.
            # Actually, let's use the first deal's ID.
            cheapest_deal_id = deals[0].get("dealID")
            if cheapest_deal_id:
                link = f"https://www.cheapshark.com/redirect?dealID={cheapest_deal_id}"
                self.add_item(discord.ui.Button(label="View Best Deal", style=discord.ButtonStyle.link, url=link))

class Deals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_base = "https://www.cheapshark.com/api/1.0"
        self.exchange_api = "https://api.exchangerate-api.com/v4/latest/USD"
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        if self.session:
            self.bot.loop.create_task(self.session.close())

    async def _get_exchange_rate(self, currency: str):
        """Fetch exchange rate from USD to the specified currency"""
        try:
            async with self.session.get(self.exchange_api, timeout=10) as response:
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
            if not price_str or price_str == "N/A":
                return "0.00"
            price = float(price_str)
            return f"{price * rate:.2f}"
        except:
            return price_str

    async def fetch_game_data(self, game_name: str):
        """Fetches raw game data and deals."""
        # Search
        search_url = f"{self.api_base}/games"
        params = {"title": game_name, "limit": 1}
        
        async with self.session.get(search_url, params=params, timeout=10) as response:
            if response.status != 200:
                return None, "❌ Failed to fetch game data."
            
            games = await response.json()
            if not games:
                return None, f"🔍 No results found for **{game_name}**."
            
            game_summary = games[0]
            game_id = game_summary.get("gameID")
            
            # Fetch details
            deals_url = f"{self.api_base}/games"
            deal_params = {"id": game_id}
            
            async with self.session.get(deals_url, params=deal_params, timeout=10) as deal_response:
                if deal_response.status != 200:
                    return None, "❌ Failed to fetch deal details."
                
                deal_data = await deal_response.json()
                return deal_data, None

    async def create_price_embed(self, game_data, color, currency="USD"):
        """Generates the embed based on game data and currency."""
        info = game_data.get("info", {})
        cheapest_price_ever = game_data.get("cheapestPriceEver", {})
        deals = game_data.get("deals", [])
        
        title = info.get("title", "Unknown Game")
        thumb = info.get("thumb")
        
        exchange_rate = 1.0
        currency_symbol = "$"
        currency_code = "USD"
        
        if currency and currency.upper() != "USD":
            rate, curr_code = await self._get_exchange_rate(currency)
            if rate:
                exchange_rate = rate
                currency_code = curr_code
                symbols = {
                    "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥", "CNY": "¥",
                    "KRW": "₩", "RUB": "₽", "BRL": "R$", "AUD": "A$", "CAD": "C$",
                    "TRY": "₺", "MXN": "MX$", "IDR": "Rp", "PLN": "zł", "SEK": "kr", 
                    "CHF": "CHF", "SGD": "S$", "HKD": "HK$", "NZD": "NZ$", "THB": "฿", 
                    "PHP": "₱", "MYR": "RM", "ZAR": "R", "SAR": "SAR", "USD": "$"
                }
                currency_symbol = symbols.get(curr_code, curr_code + " ")
            # If invalid currency, fallback to USD logic (silent, or could show warning footer)

        embed = discord.Embed(
            title=f"💰 {title}",
            description=f"Price information from CheapShark",
            color=color
        )
        if thumb:
            embed.set_image(url=thumb)

        # Lowest Price Logic
        # cheapestPriceEver object: { "price": "X", "date": 123 }
        lowest_price = cheapest_price_ever.get("price", "N/A")
        converted_lowest = self._convert_price(lowest_price, exchange_rate)
        
        embed.add_field(
            name="🏷️ Lowest Price Ever",
            value=f"{currency_symbol}{converted_lowest} ({currency_code})",
            inline=True
        )

        # Deals listing
        if deals:
            deal_text = ""
            stores = {
                "1": "Steam", "2": "GamersGate", "3": "GreenManGaming", "4": "Amazon",
                "5": "GameStop", "6": "Direct2Drive", "7": "GOG", "8": "Origin",
                "11": "Humble Store", "13": "Uplay", "15": "Fanatical", "25": "Epic Games",
            }
            # Only top 5
            for deal in deals[:5]:
                store_id = deal.get("storeID")
                store_name = stores.get(store_id, f"Store {store_id}")
                price = deal.get("price", "N/A")
                retail_price = deal.get("retailPrice", "N/A")
                savings = float(deal.get("savings", 0))
                
                converted_price = self._convert_price(price, exchange_rate)
                
                if savings > 0:
                    converted_retail = self._convert_price(retail_price, exchange_rate)
                    deal_text += f"**{store_name}**: ~~{currency_symbol}{converted_retail}~~ ➜ **{currency_symbol}{converted_price}** ({savings:.0f}% off)\n"
                else:
                    deal_text += f"**{store_name}**: {currency_symbol}{converted_price}\n"
            
            embed.add_field(name="🛒 Current Deals", value=deal_text or "No deals found", inline=False)
        
        footer = "Powered by CheapShark API"
        if currency_code != "USD":
            footer += f" • Converted to {currency_code}"
        embed.set_footer(text=footer)
        
        return embed

    @commands.command(name="price")
    async def check_price(self, ctx, *args):
        if not args:
            await ctx.reply("❌ Please provide a game name!")
            return
        
        # Parse arguments (basic check for currency at end)
        currency = "USD"
        game_name_parts = list(args)
        if len(args) > 1 and len(args[-1]) == 3 and args[-1].isalpha():
             # Potential currency
             game_name_parts = args[:-1]
             currency = args[-1].upper()
        
        game_name = " ".join(game_name_parts)

        async with ctx.typing():
            data, error = await self.fetch_game_data(game_name)
            if error:
                await ctx.reply(error)
                return

            embed = await self.create_price_embed(data, ctx.author.color, currency)
            view = PriceView(self, data, data.get("deals", []))
            await ctx.reply(embed=embed, view=view)

    @app_commands.command(name="price", description="Check game prices")
    async def price_slash(self, interaction: discord.Interaction, game_name: str, currency: str = "USD"):
        await interaction.response.defer()
        
        data, error = await self.fetch_game_data(game_name)
        if error:
            await interaction.followup.send(error)
            return

        embed = await self.create_price_embed(data, interaction.user.color, currency)
        view = PriceView(self, data, data.get("deals", []))
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Deals(bot))
