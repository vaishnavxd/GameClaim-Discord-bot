# 🎮 GameClaim — Free Game Alert Discord Bot

**Epic Games + Steam free games delivered directly to your Discord server.**  
Lightweight, async, and reliable — built with discord.py and Supabase.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/discord.py-2.4-blueviolet?logo=discord&logoColor=white" />
  <img src="https://img.shields.io/badge/Supabase-Database-green?logo=supabase&logoColor=white" />
  <img src="https://img.shields.io/github/license/vaishnavxd/GameClaim-Discord-bot?color=orange" />
  <img src="https://img.shields.io/github/stars/vaishnavxd/GameClaim-Discord-bot?style=social" />
</p>

---

## ✨ What’s new / Overview

This README was updated to reflect recent code changes:

- The bot uses background loops to monitor free game drops (Epic + Steam).
- Slash commands are synced on startup; prefix commands are still supported (prefix: `g!`).
- Supabase is used to store per-guild settings and to prevent duplicate announcements (with automatic cleanup).
- Owner broadcast modal lets the bot owner send announcements to all servers in parallel.
- Price / deal UI includes currency selection and a link to the best deal (CheapShark integration).
- Keep-alive helper included (small web server) for hosts that require it (Replit / UptimeRobot / similar).
- Improved error handling and logging on startup and command execution.

---

## ✨ Features

- 🔔 Instant notifications for free PC games (Epic & Steam)
- 📡 Per-server configurable alert channel
- 🎭 Optional ping roles to notify users for new games
- 🛡️ Duplicate prevention via Supabase (sent_games table)
- 🧹 Automatic cleanup of old sent entries (configured to remove old entries after a period)
- 🧰 Owner-only broadcast (modal + preview) to send announcements across guilds
- 💱 Currency selection for price/deal embeds
- ⚡ Slash command support (and prefix commands with `g!`)
- 🏷️ Minimal, asynchronous, and designed to be run on lightweight hosts

---

## Commands

Prefix: `g!` (examples)
- `g!ping` — Basic latency check.
- `g!setchannel <#channel>` — (Admin) Set the server alert channel.
- `g!updateping <@role>` — (Admin) Set or remove ping role.
- `g!credit` — Show credits and links.

Slash equivalents:
- `/ping`
- `/setchannel` (admin)
- `/updateping` (admin)
- Other slash commands are synced on startup (the bot logs how many were synced).

Owner utilities:
- Owner-only broadcast via modal (preview + confirm) to send announcement embeds to all guilds.

Note: behaviour and exact command names are defined in the cogs (see cogs/ directory).

---

## Installation

1. Clone the repository
```bash
git clone https://github.com/vaishnavxd/GameClaim-Discord-bot.git
cd GameClaim-Discord-bot
```

2. Create and activate a Python 3.12 virtual environment (recommended)
```bash
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
.venv\Scripts\activate      # Windows
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root with at least:
```
DISCORD_TOKEN=your_discord_bot_token
SUPABASE_URL=your_supabase_project_url    # optional but recommended
SUPABASE_KEY=your_supabase_service_role_key  # optional but recommended
```
- If `SUPABASE_*` variables are missing, Supabase features will be disabled and the bot will log a warning. The bot checks for the env values on startup.

5. Run the bot
```bash
python main.py
```

- `main.py` loads cogs automatically from the `cogs/` folder and attempts to sync slash commands on startup.
- A keep-alive small web server is started if `keepAlive` is present (useful for long-running hosts that require an HTTP endpoint).

---

## Configuration

- Set an alert channel:
  - Prefix: `g!setchannel #channel` (admin-only)
  - Slash: `/setchannel` (admin-only)
- Set a ping role:
  - Prefix: `g!updateping @role` (admin-only)
  - Slash: `/updateping` (admin-only)
- Guild settings are stored in Supabase `guild_settings` table (if configured).

---

## Tech stack

- Python 3.12
- discord.py (v2.x)
- aiohttp (HTTP requests)
- Supabase (PostgreSQL) — optional but used for persistence
- rapidfuzz (fuzzy matching in deal lookups)
- Flask (small keep-alive server helper)
- CheapShark / GamerPower / Epic APIs (for deals/free games)

Files of interest:
- `main.py` — entrypoint, loads cogs and syncs slash commands
- `cogs/` — contains `games.py`, `admin.py`, `general.py`, `deals.py`, `owner.py`, etc.
- `utils/database.py` — Supabase helpers and DB functions
- `requirements.txt` — dependency list

---

## Deployment tips

- Use a process manager (systemd, pm2, or a container) for production.
- If hosting on Replit / Glitch / similar, the included `keepAlive` helper opens a small HTTP endpoint so uptime monitors can prevent sleeping.
- Ensure the bot has the necessary Discord intents (message content intent is enabled in `main.py` and must be enabled in your bot settings if you rely on message content features).

---

## Troubleshooting

- Bot exits with "Missing DISCORD_TOKEN": ensure `.env` contains `DISCORD_TOKEN`.
- Supabase features not working: check `SUPABASE_URL` and `SUPABASE_KEY` and confirm network connectivity.
- Slash commands not appearing: allow a few minutes after the bot logs the number of synced commands; if sync fails, check logs printed at startup.
- Cog loading errors: `main.py` logs failed cog imports with full tracebacks.

---

## Contributing

Pull requests are welcome — open issues for bugs or feature requests. Follow the existing style (async, cog-based organization) when adding features.

---

## License

This project is licensed under the MIT License.

---

## Author / Links

- GitHub: https://github.com/vaishnavxd
- YouTube: https://youtube.com/@vaishnavtf
- Instagram: https://instagram.com/vaishnavxd

