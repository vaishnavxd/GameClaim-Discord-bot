import os
import traceback
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not (SUPABASE_URL and SUPABASE_KEY):
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Supabase client initialized.")

# -----------------------
# Database helper funcs
# -----------------------
def upsert_guild_setting(guild_id: str, channel_id: str, ping_roles):
    payload = {
        "guild_id": guild_id,
        "channel_id": str(channel_id) if channel_id is not None else "0",
        "ping_roles": ping_roles or []
    }
    try:
        res = supabase.table("guild_settings").upsert(payload).execute()
        return res
    except Exception as e:
        print("❌ upsert_guild_setting error:", e)
        traceback.print_exc()
        return None

def get_all_guild_settings():
    try:
        res = supabase.table("guild_settings").select("*").execute()
        return res.data if getattr(res, "data", None) is not None else []
    except Exception as e:
        print("❌ get_all_guild_settings error:", e)
        traceback.print_exc()
        return []

def get_guild_setting(guild_id: str):
    try:
        res = supabase.table("guild_settings").select("*").eq("guild_id", str(guild_id)).limit(1).execute()
        rows = res.data if getattr(res, "data", None) is not None else []
        return rows[0] if rows else None
    except Exception as e:
        print("❌ get_guild_setting error:", e)
        traceback.print_exc()
        return None

def delete_guild_setting(guild_id: str):
    try:
        res = supabase.table("guild_settings").delete().eq("guild_id", str(guild_id)).execute()
        return res
    except Exception as e:
        print("❌ delete_guild_setting error:", e)
        traceback.print_exc()
        return None

def is_game_sent(guild_id: str, game_identifier: str):
    try:
        res = supabase.table("sent_games").select("id").eq("guild_id", str(guild_id)).eq("game_identifier", game_identifier).limit(1).execute()
        rows = res.data if getattr(res, "data", None) is not None else []
        return len(rows) > 0
    except Exception as e:
        print("❌ is_game_sent error:", e)
        traceback.print_exc()
        return False

def mark_game_sent(guild_id: str, game_identifier: str, title: str = None, url: str = None, announced_at=None):
    """
    Insert a sent_games row. `announced_at` may be:
      - None (use now())
      - a datetime.datetime (will be isoformatted)
      - an ISO string (used as-is if parseable)
    """
    # normalize announced_at to an ISO8601 string
    announced_at_iso = None
    try:
        if announced_at is None:
            announced_at_iso = datetime.now(timezone.utc).isoformat()
        elif isinstance(announced_at, str):
            # if it's already an ISO string, try to validate/normalize it
            try:
                # this will raise if not parseable
                _dt = datetime.fromisoformat(announced_at.replace("Z", "+00:00"))
                announced_at_iso = _dt.isoformat()
            except Exception:
                # fallback: use the string as-provided
                announced_at_iso = announced_at
        else:
            # assume it's a datetime-like object
            announced_at_iso = announced_at.isoformat()
    except Exception:
        # last-resort fallback
        announced_at_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "guild_id": str(guild_id),
        "game_identifier": game_identifier,
        "title": title,
        "url": url,
        "announced_at": announced_at_iso
    }
    try:
        res = supabase.table("sent_games").insert(payload).execute()
        return res
    except Exception as e:
        # unique-constraint duplicates or other DB errors are non-fatal for sending flow
        print("❌ mark_game_sent error (insert):", e)
        return None


def cleanup_sent_games_db(cutoff_days=14):
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    try:
        res = supabase.table("sent_games").delete().lt("announced_at", cutoff.isoformat()).execute()
        return res
    except Exception as e:
        print("❌ cleanup_sent_games_db error:", e)
        traceback.print_exc()
        return None
