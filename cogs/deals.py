import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from rapidfuzz import process
from discord.ext import tasks

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

class TrackConfirmView(discord.ui.View):
    def __init__(self, cog, game_id, game_name, user, channel_id, all_matches, query, track_type="sale"):
        super().__init__(timeout=60)
        self.cog = cog
        self.game_id = game_id
        self.game_name = game_name
        self.user = user
        self.channel_id = channel_id
        self.all_matches = all_matches
        self.query = query
        self.track_type = track_type
        self.value = None
    
    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ This is not your tracking request.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Import here to avoid circular import
        from utils.database import add_tracked_game, get_user_tracked_games, remove_tracked_game
        
        # Check if user is owner
        is_owner = await self.cog.bot.is_owner(self.user)
        
        # Check if user already has tracked games
        existing_list = await get_user_tracked_games(str(self.user.id))
        existing = existing_list[0] if existing_list else None
        
        if not is_owner and existing:
            # Regular user: remove previous tracking first
            await remove_tracked_game(str(self.user.id))
        
        # Add to database (will replace existing if any)
        result = await add_tracked_game(
            str(self.user.id),
            str(self.channel_id),
            self.game_id,
            self.game_name,
            self.track_type
        )
        
        if result:
            embed = discord.Embed(
                title="✅ Tracking Confirmed",
                description=f"You'll be notified in this channel when **{self.game_name}** {'hits its all-time low' if self.track_type == 'atl' else 'goes on sale'}!",
                color=discord.Color.green()
            )
            
            if existing and not is_owner:
                embed.add_field(
                    name="⚠️ Previous Tracking Replaced",
                    value=f"Your previous tracking for **{existing['game_name']}** has been replaced.",
                    inline=False
                )
            
            footer_text = "You can track multiple games!" if is_owner else "You can only track one game at a time. This is a one-time notification."
            embed.set_footer(text=footer_text)
            await interaction.edit_original_response(embed=embed, view=None)
        else:
            await interaction.edit_original_response(
                content="❌ Failed to save tracking. Please try again later.",
                embed=None,
                view=None
            )
        
        self.value = True
        self.stop()
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ This is not your tracking request.", ephemeral=True)
            return
            
        await interaction.response.defer()
        await interaction.edit_original_response(
            content="❌ Tracking cancelled.",
            embed=None,
            view=None
        )
        self.value = False
        self.stop()
    
    @discord.ui.button(label="🔍 Search for something else", style=discord.ButtonStyle.secondary)
    async def search_other(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ This is not your tracking request.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Show all matches using TrackSelectionView
        view = TrackSelectionView(self.cog, self.all_matches, self.query, self.user, self.channel_id, self.track_type)
        embed = view.create_selection_embed()
        await interaction.edit_original_response(embed=embed, view=view)
        self.stop()

class TrackSelectionView(discord.ui.View):
    """View for selecting a game to track from multiple matches."""
    def __init__(self, cog, matches, query, user, channel_id, track_type="sale"):
        super().__init__(timeout=120)
        self.cog = cog
        self.matches = matches
        self.query = query
        self.user = user
        self.channel_id = channel_id
        self.track_type = track_type
        self.current_page = 0
        self.items_per_page = 5
        
        self.update_buttons()
    
    def update_buttons(self):
        self.clear_items()
        
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_matches = self.matches[start_idx:end_idx]
        
        # Add game selection buttons
        for i, (game_name, score, game_dict) in enumerate(current_matches):
            button = discord.ui.Button(
                label=f"{game_name[:75]}",
                style=discord.ButtonStyle.primary,
                custom_id=f"track_select_{start_idx + i}"
            )
            button.callback = self.create_callback(start_idx + i)
            self.add_item(button)
        
        # Add pagination buttons
        if self.current_page > 0:
            prev_button = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary)
            prev_button.callback = self.previous_page
            self.add_item(prev_button)
        
        if end_idx < len(self.matches):
            next_button = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)
    
    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.user:
                await interaction.response.send_message("❌ This is not your tracking request.", ephemeral=True)
                return
                
            await interaction.response.defer()
            
            game_title, score, game_dict = self.matches[index]
            game_id = game_dict.get("gameID")
            
            # Show confirmation for this game
            embed = discord.Embed(
                title=f"🔔 Confirm Tracking",
                description=f"Track **{game_title}** for price drops?",
                color=self.user.color
            )
            embed.set_footer(text=f"Preference: {'All-time low' if self.track_type == 'atl' else 'Any sale'} • You can only track one game at a time.")
            
            view = TrackConfirmView(self.cog, game_id, game_title, self.user, self.channel_id, self.matches, self.query, self.track_type)
            await interaction.edit_original_response(embed=embed, view=view)
        
        return callback
    
    async def previous_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ This is not your tracking request.", ephemeral=True)
            return
            
        await interaction.response.defer()
        self.current_page -= 1
        self.update_buttons()
        
        embed = self.create_selection_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    
    async def next_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ This is not your tracking request.", ephemeral=True)
            return
            
        await interaction.response.defer()
        self.current_page += 1
        self.update_buttons()
        
        embed = self.create_selection_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    
    def create_selection_embed(self):
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_matches = self.matches[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"🔍 Select a game to track",
            description="Choose a game from the options below:",
            color=self.user.color
        )
        
        game_list = ""
        for i, (game_name, score, game_dict) in enumerate(current_matches):
            game_list += f"{game_name} *(Match: {score:.0f}%)*\n"
        
        embed.add_field(name="Games", value=game_list, inline=False)
        embed.set_footer(text=f"Page {self.current_page + 1} • Preference: {self.track_type.upper()}")
        
        return embed

class OwnerTrackManageView(discord.ui.View):
    """Management view for people with multiple tracks (Owner)."""
    def __init__(self, cog, tracks, user):
        super().__init__(timeout=120)
        self.cog = cog
        self.tracks = tracks
        self.user = user
        self.current_page = 0
        self.items_per_page = 5
        self.update_content()

    def update_content(self):
        self.clear_items()
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        current = self.tracks[start:end]

        for track in current:
            track_id = track['id']
            name = track['game_name']
            type_str = "ATL" if track.get('track_type') == 'atl' else "Sale"
            
            btn = discord.ui.Button(label=f"🗑️ Stop: {name[:50]} ({type_str})", style=discord.ButtonStyle.danger)
            btn.callback = self.create_stop_callback(track_id, name)
            self.add_item(btn)

        if self.current_page > 0:
            btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary)
            btn.callback = self.prev_page
            self.add_item(btn)
        if end < len(self.tracks):
            btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)
            btn.callback = self.next_page
            self.add_item(btn)

    def create_stop_callback(self, track_id, name):
        async def callback(interaction: discord.Interaction):
            from utils.database import remove_tracked_game_by_id
            await interaction.response.defer()
            await remove_tracked_game_by_id(track_id)
            
            # Update list
            self.tracks = [t for t in self.tracks if t['id'] != track_id]
            if not self.tracks:
                await interaction.edit_original_response(content="✅ All tracking stopped.", embed=None, view=None)
                return
            
            if self.current_page * self.items_per_page >= len(self.tracks) and self.current_page > 0:
                self.current_page -= 1
            
            self.update_content()
            embed = self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
        return callback

    def create_embed(self):
        embed = discord.Embed(
            title="📋 Your Active Tracking (Owner Mode)",
            description=f"You are tracking **{len(self.tracks)}** games.\nUse the buttons below to stop tracking individual games.",
            color=self.user.color
        )
        embed.set_footer(text=f"Page {self.current_page + 1}")
        return embed

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page -= 1
        self.update_content()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page += 1
        self.update_content()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

class GameSelectionView(discord.ui.View):
    def __init__(self, cog, matches, query, user_color, currency="USD", exact_match=False, action="price"):
        super().__init__(timeout=120)
        self.cog = cog
        self.matches = matches
        self.query = query
        self.user_color = user_color
        self.currency = currency
        self.current_page = 0
        self.items_per_page = 5
        self.exact_match = exact_match
        self.action = action # "price" or "isgood"
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        if self.exact_match:
            game_name, score, game_dict = self.matches[0]
            button = discord.ui.Button(label=f"{game_name[:75]}", style=discord.ButtonStyle.success)
            button.callback = self.create_callback(0)
            self.add_item(button)
            
            other_button = discord.ui.Button(label="🔍 Search for something else", style=discord.ButtonStyle.secondary)
            other_button.callback = self.show_all_matches
            self.add_item(other_button)
            return

        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_matches = self.matches[start_idx:end_idx]

        for i, (game_name, score, game_dict) in enumerate(current_matches):
            button = discord.ui.Button(label=f"{game_name[:75]}", style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(start_idx + i)
            self.add_item(button)

        if self.current_page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary)
            prev.callback = self.previous_page
            self.add_item(prev)
        if end_idx < len(self.matches):
            nxt = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)
            nxt.callback = self.next_page
            self.add_item(nxt)

    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            game_name, score, game_dict = self.matches[index]
            game_id = game_dict.get("gameID")

            if self.action == "isgood":
                await self.cog._isgood_logic(interaction, game_id, self.user_color)
            else: # price
                data, error = await self.cog.fetch_game_data_by_id(game_id)
                if error:
                    await interaction.edit_original_response(content=error, embed=None, view=None)
                    return
                
                embed = await self.cog.create_price_embed(data, self.user_color, self.currency)
                view = PriceView(self.cog, data, data.get("deals", []))
                await interaction.edit_original_response(content=None, embed=embed, view=view)
        return callback

    async def previous_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page -= 1
        self.update_buttons()
        await interaction.edit_original_response(embed=self.create_selection_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page += 1
        self.update_buttons()
        await interaction.edit_original_response(embed=self.create_selection_embed(), view=self)

    async def show_all_matches(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.exact_match = False
        self.current_page = 0
        self.update_buttons()
        await interaction.edit_original_response(embed=self.create_selection_embed(), view=self)

    def create_selection_embed(self):
        if self.exact_match:
            title = f"✅ Found: {self.matches[0][0]}"
            desc = "Is this the game you want to check?" if self.action == "isgood" else "Click the button below to view prices, or search for something else."
            return discord.Embed(title=title, description=desc, color=self.user_color)
        
        title = f"🔍 Multiple matches found for '{self.query}'"
        desc = "Select a game to check if it's a good deal:" if self.action == "isgood" else "Select a game from the options below:"
        embed = discord.Embed(title=title, description=desc, color=self.user_color)
        
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_matches = self.matches[start_idx:end_idx]
        
        game_list = "".join([f"{m[0]} *(Match: {m[1]:.0f}%)*\n" for m in current_matches])
        embed.add_field(name="Games", value=game_list, inline=False)
        embed.set_footer(text=f"Page {self.current_page + 1} • Showing {start_idx + 1}-{min(end_idx, len(self.matches))} of {len(self.matches)} results")
        return embed

class Deals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_base = "https://www.cheapshark.com/api/1.0"
        self.exchange_api = "https://api.exchangerate-api.com/v4/latest/USD"
        self.session = aiohttp.ClientSession()
        
        self.stores = {
            "1": "Steam", "2": "GamersGate", "3": "GreenManGaming", "4": "Amazon",
            "5": "GameStop", "6": "Direct2Drive", "7": "GOG", "8": "Origin",
            "11": "Humble Store", "13": "Uplay", "15": "Fanatical", "25": "Epic Games",
        }
        
        # Start background checker safely
        if not self.check_tracked_games_task.is_running():
            self.check_tracked_games_task.start()

    def cog_unload(self):
        if self.session:
            self.bot.loop.create_task(self.session.close())
        if self.check_tracked_games_task.is_running():
            self.check_tracked_games_task.cancel()

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

    async def fetch_game_data_by_id(self, game_id: str):
        """Fetches game data by game ID."""
        deals_url = f"{self.api_base}/games"
        deal_params = {"id": game_id}
        
        try:
            async with self.session.get(deals_url, params=deal_params, timeout=10) as deal_response:
                if deal_response.status != 200:
                    return None, "❌ Failed to fetch deal details."
                
                deal_data = await deal_response.json()
                return deal_data, None
        except Exception as e:
            return None, f"❌ Error fetching game data: {e}"

    async def fetch_game_data(self, game_name: str, return_matches=False):
        """Fetches raw game data and deals. If return_matches=True, returns list of matches."""
        # Search
        search_url = f"{self.api_base}/games"
        # Increase limit to allow fuzzy matching on client side
        params = {"title": game_name, "limit": 25}
        
        async with self.session.get(search_url, params=params, timeout=10) as response:
            if response.status != 200:
                return None, "❌ Failed to fetch game data."
            
            games = await response.json()
            if not games:
                return None, f"🔍 No results found for **{game_name}**."
            
            # Fuzzy Matching Logic
            # Extract names for fuzzy matching
            choices = {game['external']: game for game in games}
            
            # Use extract to get multiple matches
            matches = process.extract(game_name, choices.keys(), limit=25)
            
            # If we want to return matches for selection
            if return_matches:
                # Return list of (game_name, score, game_dict)
                match_list = [(match[0], match[1], choices[match[0]]) for match in matches if match[1] >= 50]
                if not match_list:
                    match_list = [(match[0], match[1], choices[match[0]]) for match in matches[:5]]
                return match_list, None
            
            # Auto-select if single very good match
            if matches and matches[0][1] >= 90 and (len(matches) == 1 or matches[0][1] - matches[1][1] > 10):
                # High confidence single match
                game_summary = choices[matches[0][0]]
            else:
                # Default to first result
                game_summary = games[0]

            game_id = game_summary.get("gameID")
            
            # Fetch details
            return await self.fetch_game_data_by_id(game_id)

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
            # Only top 5
            for deal in deals[:5]:
                store_id = deal.get("storeID")
                store_name = self.stores.get(store_id, f"Store {store_id}")
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
            # First, try to get matches
            matches, error = await self.fetch_game_data(game_name, return_matches=True)
            if error:
                await ctx.reply(error)
                return
            
            # Always show top match with "Search for something else" option
            view = GameSelectionView(self, matches, game_name, ctx.author.color, currency, exact_match=True)
            embed = view.create_selection_embed()
            await ctx.reply(embed=embed, view=view)

    @app_commands.command(name="price", description="Check game prices")
    async def price_slash(self, interaction: discord.Interaction, game_name: str, currency: str = "USD"):
        await interaction.response.defer()
        
        # First, try to get matches
        matches, error = await self.fetch_game_data(game_name, return_matches=True)
        if error:
            await interaction.followup.send(error)
            return
        
        # Always show top match with "Search for something else" option
        view = GameSelectionView(self, matches, game_name, interaction.user.color, currency, exact_match=True)
        embed = view.create_selection_embed()
        await interaction.followup.send(embed=embed, view=view)

    @commands.command(name="track")
    async def track_game(self, ctx, *, args: str = None):
        """Track a game for price notifications. Usage: g!track <game name> [-atl|-sale]"""
        from utils.database import get_user_tracked_games, remove_tracked_game
        
        # 1. Parse flags
        track_type = "sale"
        game_name = args
        if args:
            if "-atl" in args.lower():
                track_type = "atl"
                game_name = args.lower().replace("-atl", "").strip()
            elif "-sale" in args.lower():
                track_type = "sale"
                game_name = args.lower().replace("-sale", "").strip()

        # Check if user is owner
        is_owner = await self.bot.is_owner(ctx.author)

        # Check existing tracks
        existing_tracks = await get_user_tracked_games(str(ctx.author.id))
        
        if not game_name:
            if not existing_tracks:
                await ctx.reply("❌ You are not tracking any games. Use `g!track <game name>` to start!")
                return
            
            if len(existing_tracks) > 1 or is_owner:
                # Show management UI for multi-track (Owner)
                view = OwnerTrackManageView(self, existing_tracks, ctx.author)
                embed = view.create_embed()
                await ctx.reply(embed=embed, view=view)
                return
            else:
                # Regular user with one track
                existing = existing_tracks[0]
                track_type_display = "All-Time Low" if existing.get('track_type') == 'atl' else "Any Sale"
                embed = discord.Embed(
                    title="📋 Your Current Tracking",
                    description=f"You're currently tracking: **{existing['game_name']}**\nPreference: **{track_type_display}**",
                    color=ctx.author.color
                )
                embed.set_footer(text="Use 'g!track <game name> [-atl|-sale]' to replace it.")
                
                # Add remove button
                view = discord.ui.View(timeout=60)
                remove_btn = discord.ui.Button(label="🗑️ Stop Tracking", style=discord.ButtonStyle.danger)
                
                async def remove_callback(interaction: discord.Interaction):
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("❌ This is not your tracking.", ephemeral=True)
                        return
                        
                    await interaction.response.defer()
                    from utils.database import remove_tracked_game_by_id
                    await remove_tracked_game_by_id(existing['id'])
                    
                    embed = discord.Embed(
                        title="✅ Tracking Removed",
                        description=f"Stopped tracking **{existing['game_name']}**. You can now track a new game!",
                        color=discord.Color.green()
                    )
                    await interaction.edit_original_response(embed=embed, view=None)
                
                remove_btn.callback = remove_callback
                view.add_item(remove_btn)
                await ctx.reply(embed=embed, view=view)
                return

        # If user is owner, they can skip the confirm/replace flow if they want or just add more
        # BUT for UX consistency, we still do the search.
        # If regular user AND already tracking, show the replacement confirm
        if not is_owner and existing_tracks:
            existing = existing_tracks[0]
            embed = discord.Embed(
                title="⚠️ Already Tracking a Game",
                description=f"You're currently tracking: **{existing['game_name']}**\n\nTracking **{game_name}** will replace your current tracking.",
                color=discord.Color.orange()
            )
            embed.set_footer(text="Click 'Continue' to replace, 'Cancel' to keep current tracking, or 'Remove' to stop tracking.")
            
            view = discord.ui.View(timeout=60)
            
            # Continue button
            continue_btn = discord.ui.Button(label="✅ Continue & Replace", style=discord.ButtonStyle.success)
            async def continue_callback(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("❌ This is not your request.", ephemeral=True)
                    return
                await interaction.response.defer()
                # Proceed with normal tracking flow
                await self._do_track_search(ctx, game_name, track_type, interaction)
            continue_btn.callback = continue_callback
            view.add_item(continue_btn)
            
            # Cancel button
            cancel_btn = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
            async def cancel_callback(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("❌ This is not your request.", ephemeral=True)
                    return
                await interaction.response.defer()
                await interaction.edit_original_response(content="❌ Cancelled. Your current tracking remains unchanged.", embed=None, view=None)
            cancel_btn.callback = cancel_callback
            view.add_item(cancel_btn)
            
            # Remove button
            remove_btn = discord.ui.Button(label="🗑️ Remove Current Tracking", style=discord.ButtonStyle.danger)
            async def remove_callback_btn(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("❌ This is not your request.", ephemeral=True)
                    return
                await interaction.response.defer()
                from utils.database import remove_tracked_game_by_id
                await remove_tracked_game_by_id(existing['id'])
                embed = discord.Embed(
                    title="✅ Tracking Removed",
                    description=f"Stopped tracking **{existing['game_name']}**. You can now track a new game!",
                    color=discord.Color.green()
                )
                await interaction.edit_original_response(embed=embed, view=None)
            remove_btn.callback = remove_callback_btn
            view.add_item(remove_btn)
            
            await ctx.reply(embed=embed, view=view)
            return

        # No existing tracking or is owner - proceed normally
        async with ctx.typing():
            await self._do_track_search(ctx, game_name, track_type)
    
    async def _do_track_search(self, ctx, game_name, track_type="sale", interaction=None):
        """Helper method to handle the game search and confirmation."""
        # Get matches using existing logic
        matches, error = await self.fetch_game_data(game_name, return_matches=True)
        if error:
            if interaction:
                await interaction.edit_original_response(content=error, embed=None, view=None)
            else:
                await ctx.reply(error)
            return
        
        # Get the top match
        game_title, score, game_dict = matches[0]
        game_id = game_dict.get("gameID")
        
        # Create confirmation embed
        embed = discord.Embed(
            title=f"🔔 Confirm Tracking",
            description=f"Track **{game_title}** for price drops?",
            color=ctx.author.color
        )
        embed.set_footer(text=f"Preference: {'All-time low' if track_type == 'atl' else 'Any sale'} • You can only track one game at a time.")
        
        # Show confirmation view
        view = TrackConfirmView(self, game_id, game_title, ctx.author, ctx.channel.id, matches, game_name, track_type)
        
        if interaction:
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await ctx.reply(embed=embed, view=view)


    @tasks.loop(hours=6)
    async def check_tracked_games_task(self):
        """Background task to check tracked games and send notifications."""
        from utils.database import get_all_tracked_games, remove_tracked_game
        
        tracked_games = await get_all_tracked_games()
        if not tracked_games:
            return
        
        print(f"🔍 Checking {len(tracked_games)} tracked games...")
        
        for track in tracked_games:
            try:
                user_id = track.get("user_id")
                channel_id = track.get("channel_id")
                game_id = track.get("cheapshark_game_id")
                game_name = track.get("game_name")
                track_type = track.get("track_type", "sale")
                
                # Fetch current game data
                data, error = await self.fetch_game_data_by_id(game_id)
                if error or not data:
                    continue
                
                deals = data.get("deals", [])
                if not deals:
                    continue
                
                # Check if there's a deal that meets the user's criteria
                best_deal = None
                is_atl_hit = False
                
                # Get cheapest price ever for ATL check
                cheapest_ever = float(data.get("cheapestPriceEver", {}).get("price", 0))
                
                for deal in deals:
                    current_price = float(deal.get("price", 0))
                    savings = float(deal.get("savings", 0))
                    
                    if track_type == "atl":
                        if current_price <= cheapest_ever and savings > 0:
                            best_deal = deal
                            is_atl_hit = True
                            break
                    else: # type == "sale"
                        if savings > 0:
                            best_deal = deal
                            break
                
                if best_deal:
                    # Try to get channel from cache first
                    channel = self.bot.get_channel(int(channel_id))
                    
                    # If not in cache, try fetching it
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(int(channel_id))
                        except (discord.NotFound, discord.Forbidden):
                            print(f"⚠️ Channel {channel_id} no longer exists or is inaccessible. Removing tracking.")
                            from utils.database import remove_tracked_game_by_id
                            await remove_tracked_game_by_id(track['id'])
                            continue
                        except Exception as e:
                            print(f"❌ Error fetching channel {channel_id}: {e}")
                            continue

                    if channel:
                        try:
                            current_price = float(best_deal.get("price", 0))
                            retail_price = float(best_deal.get("retailPrice", 0))
                            savings = float(best_deal.get("savings", 0))
                            
                            # Get user for mention
                            user = await self.bot.fetch_user(int(user_id))
                            mention = user.mention if user else "User"
                            
                            title = f"🔔 All-Time Low Alert: {game_name}" if is_atl_hit else f"🔔 Price Alert: {game_name}"
                            desc = f"💰 **ALL-TIME LOW!**\nPrice dropped to **${current_price:.2f}** (Matches or beats ${cheapest_ever:.2f})!" if is_atl_hit else f"💰 **Sale Alert!**\nPrice dropped to **${current_price:.2f}** (was ${retail_price:.2f}) - **{savings:.0f}% off!**"
                            
                            embed = discord.Embed(
                                title=title,
                                description=f"{mention} {desc}",
                                color=discord.Color.gold() if is_atl_hit else discord.Color.green()
                            )
                            
                            # Add deal link
                            if best_deal.get("dealID"):
                                deal_link = f"https://www.cheapshark.com/redirect?dealID={best_deal['dealID']}"
                                embed.add_field(name="🛒 Get Deal", value=f"[Click here to claim]({deal_link})", inline=False)
                            
                            embed.set_footer(text=f"This was a one-time {track_type.upper()} notification.")
                            
                            await channel.send(content=mention, embed=embed)
                            print(f"✅ Sent {track_type} notification to user {user_id} for {game_name}")
                            
                            # Remove from tracking
                            from utils.database import remove_tracked_game_by_id
                            await remove_tracked_game_by_id(track['id'])
                        except discord.Forbidden:
                            print(f"❌ Cannot send to channel {channel_id} (Forbidden). Removing tracking.")
                            from utils.database import remove_tracked_game_by_id
                            await remove_tracked_game_by_id(track['id'])
                        except Exception as e:
                            print(f"❌ Error sending notification to channel {channel_id}: {e}")
            
            except Exception as e:
                print(f"❌ Error checking tracked game: {e}")
                continue
    
    @commands.command(name="isgood")
    async def isgood_command(self, ctx, *, game_name: str = None):
        """Check if a game is worth buying right now."""
        if not game_name:
            await ctx.reply("❌ Please provide a game name!")
            return

        async with ctx.typing():
            matches, error = await self.fetch_game_data(game_name, return_matches=True)
            if error:
                await ctx.reply(error)
                return
            
            view = GameSelectionView(self, matches, game_name, ctx.author.color, exact_match=True, action="isgood")
            await ctx.reply(embed=view.create_selection_embed(), view=view)

    @app_commands.command(name="isgood", description="Check if a game is worth buying right now")
    async def isgood_slash(self, interaction: discord.Interaction, game_name: str):
        await interaction.response.defer()
        matches, error = await self.fetch_game_data(game_name, return_matches=True)
        if error:
            await interaction.followup.send(error)
            return
        
        view = GameSelectionView(self, matches, game_name, interaction.user.color, exact_match=True, action="isgood")
        await interaction.followup.send(embed=view.create_selection_embed(), view=view)

    async def _isgood_logic(self, interaction, game_id, color):
        data, error = await self.fetch_game_data_by_id(game_id)
        if error:
            await interaction.edit_original_response(content=error, embed=None, view=None)
            return

        deals = data.get("deals", [])
        if not deals:
            await interaction.edit_original_response(content="❌ No deals found for this game.", embed=None, view=None)
            return

        # Cheapest deal across all stores
        best_deal = min(deals, key=lambda x: float(x.get("price", 99999)))
        curr = float(best_deal.get("price", 0))
        retail = float(best_deal.get("retailPrice", 0))
        atl = float(data.get("cheapestPriceEver", {}).get("price", 0))
        savings = float(best_deal.get("savings", 0))
        title = data.get("info", {}).get("title")
        store_name = self.stores.get(best_deal.get("storeID"), "Unknown Store")

        # Logic
        verdict_name = "WAIT FOR BETTER SALE"
        verdict_emoji = "🔴"
        explanation = "The current price is significantly higher than the all-time low. Only buy if you must play it right now."
        color_v = discord.Color.red()

        if curr <= atl:
            verdict_name = "BUY NOW (ATL)"
            verdict_emoji = "💎"
            explanation = "This price matches or beats the all-time low! It's the best time to buy."
            color_v = discord.Color.gold()
        elif curr <= atl * 1.1 or savings >= 75:
            verdict_name = "VERY GOOD DEAL"
            verdict_emoji = "🟢"
            explanation = "Extremely close to the all-time low or has a massive discount. Great value!"
            color_v = discord.Color.green()
        elif curr <= atl * 1.25 or savings >= 50:
            verdict_name = "GOOD DEAL"
            verdict_emoji = "🟡"
            explanation = "Worth buying, but it has dropped lower before."
            color_v = discord.Color.blue()

        # Calculation
        above_atl_text = "At its absolute lowest!"
        if curr > atl and atl > 0:
            diff_percent = ((curr - atl) / atl) * 100
            above_atl_text = f"{diff_percent:.0f}% above ATL"

        embed = discord.Embed(title=f"🎮 {title}", color=color_v)
        
        embed.add_field(name="💰 Current Price", value=f"${curr:.2f} on **{store_name}**", inline=True)
        embed.add_field(name="🏆 All-Time Low", value=f"${atl:.2f}", inline=True)
        embed.add_field(name="📉 Discount", value=f"{savings:.0f}% off", inline=True)
        
        embed.add_field(name="📊 Price Analysis", value=f"• {above_atl_text}", inline=False)
        embed.add_field(name="✅ Verdict", value=f"{verdict_emoji} **{verdict_name}**\n{explanation}", inline=False)
        
        if best_deal.get("dealID"):
            link = f"https://www.cheapshark.com/redirect?dealID={best_deal['dealID']}"
            embed.description = f"🔗 [Click to buy on {store_name}]({link})"

        embed.set_thumbnail(url=data.get("info", {}).get("thumb"))
        embed.set_footer(text="Powered by CheapShark • All stores compared")
        
        await interaction.edit_original_response(embed=embed, view=None)

    @commands.command(name="store", aliases=["stores"])
    async def store_command(self, ctx):
        """Show list of supported stores."""
        await self._stores_logic(ctx)

    @app_commands.command(name="stores", description="Show list of supported stores")
    async def stores_slash(self, interaction: discord.Interaction):
        await self._stores_logic(interaction)

    async def _stores_logic(self, target):
        """Logic for listing supported stores."""
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        
        # Sort stores by name
        sorted_stores = sorted(self.stores.values())
        store_list = "\n".join([f"• {store}" for store in sorted_stores])

        embed = discord.Embed(
            title="🛒 Supported Stores",
            description=f"We monitor and compare prices across **{len(sorted_stores)}** major stores:\n\n{store_list}",
            color=user.color
        )
        embed.set_footer(text="Powered by CheapShark API")

        if is_interaction:
            if not target.response.is_done():
                await target.response.send_message(embed=embed)
            else:
                await target.followup.send(embed=embed)
        else:
            await target.reply(embed=embed)

    @check_tracked_games_task.before_loop
    async def before_check_tracked_games(self):
        await self.bot.wait_until_ready()



async def setup(bot):
    await bot.add_cog(Deals(bot))
