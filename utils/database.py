import os
import traceback
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client

# Load env but don't crash yet if missing (let main handle criticals, though here we need CLIENT)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize client lazily or immediately? 
# If we do it here, it might block import, but typically create_client is fast (just config).
# We will wrap the actual network calls.
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase client initialized.")
else:
    supabase = None
    print("⚠️ Supabase credentials missing. DB features will fail.")

# -----------------------
# Database helper funcs
# -----------------------

async def run_db(func, *args, **kwargs):
    """Run a blocking DB call in a separate thread with a timeout."""
    if supabase is None:
        return None
    try:
        # Wrap the thread execution in a timeout
        return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=20)
    except asyncio.TimeoutError:
        print("❌ DB call timed out.")
        return None
    except Exception as e:
        # Catch connection errors (e.g., bad URL, DNS failure)
        print(f"❌ DB connection error: {e}")
        return None

async def upsert_guild_setting(guild_id: str, channel_id: str, ping_roles):
    payload = {
        "guild_id": guild_id,
        "channel_id": str(channel_id) if channel_id is not None else "0",
        "ping_roles": ping_roles or []
    }
    def _op():
        return supabase.table("guild_settings").upsert(payload).execute()
        
    try:
        res = await run_db(_op)
        return res
    except Exception as e:
        print("❌ upsert_guild_setting error:", e)
        traceback.print_exc()
        return None

async def get_all_guild_settings():
    def _op():
        return supabase.table("guild_settings").select("*").execute()
    try:
        res = await run_db(_op)
        return res.data if getattr(res, "data", None) is not None else []
    except Exception as e:
        print("❌ get_all_guild_settings error:", e)
        traceback.print_exc()
        return []

async def get_guild_setting(guild_id: str):
    def _op():
        return supabase.table("guild_settings").select("*").eq("guild_id", str(guild_id)).limit(1).execute()
    try:
        res = await run_db(_op)
        rows = res.data if getattr(res, "data", None) is not None else []
        return rows[0] if rows else None
    except Exception as e:
        print("❌ get_guild_setting error:", e)
        traceback.print_exc()
        return None

async def delete_guild_setting(guild_id: str):
    def _op():
        return supabase.table("guild_settings").delete().eq("guild_id", str(guild_id)).execute()
    try:
        res = await run_db(_op)
        return res
    except Exception as e:
        print("❌ delete_guild_setting error:", e)
        traceback.print_exc()
        return None

async def is_game_sent(guild_id: str, game_identifier: str):
    def _op():
        return supabase.table("sent_games").select("id").eq("guild_id", str(guild_id)).eq("game_identifier", game_identifier).limit(1).execute()
    try:
        res = await run_db(_op)
        rows = res.data if getattr(res, "data", None) is not None else []
        return len(rows) > 0
    except Exception as e:
        print("❌ is_game_sent error:", e)
        traceback.print_exc()
        return False

async def mark_game_sent(guild_id: str, game_identifier: str, title: str = None, url: str = None, announced_at=None):
    # normalize announced_at to an ISO8601 string
    announced_at_iso = None
    try:
        if announced_at is None:
            announced_at_iso = datetime.now(timezone.utc).isoformat()
        elif isinstance(announced_at, str):
            try:
                _dt = datetime.fromisoformat(announced_at.replace("Z", "+00:00"))
                announced_at_iso = _dt.isoformat()
            except Exception:
                announced_at_iso = announced_at
        else:
            announced_at_iso = announced_at.isoformat()
    except Exception:
        announced_at_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "guild_id": str(guild_id),
        "game_identifier": game_identifier,
        "title": title,
        "url": url,
        "announced_at": announced_at_iso
    }
    
    def _op():
        return supabase.table("sent_games").insert(payload).execute()

    try:
        res = await run_db(_op)
        return res
    except Exception as e:
        print("❌ mark_game_sent error (insert):", e)
        return None

async def cleanup_sent_games_db(cutoff_days=15):
    # Default changed to 15 days to match README
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    def _op():
        return supabase.table("sent_games").delete().lt("announced_at", cutoff.isoformat()).execute()
    try:
        res = await run_db(_op)
        return res
    except Exception as e:
        print("❌ cleanup_sent_games_db error:", e)
        traceback.print_exc()
        return None
