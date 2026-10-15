"""Connection to Supabase (our database and login system).

Other files use it like this:
    from db import get_db
    rows = get_db().table("events").select("*").execute().data
"""
import threading

from httpx import Client as HttpxClient
from supabase import ClientOptions, create_client

import config

_client = None
_lock = threading.Lock()


def _create_client():
    """Build a new Supabase client from the values in backend/.env."""
    missing = config.missing_settings()
    if missing:
        # app.py turns this into a clear JSON error instead of a crash.
        raise RuntimeError("Missing in backend/.env.local: " + ", ".join(missing))
    try:
        options = ClientOptions()
        options.httpx_client = HttpxClient(timeout=options.postgrest_client_timeout)
        return create_client(config.SUPABASE_URL, config.SUPABASE_KEY, options=options)
    except Exception as err:  # e.g. the URL is not a valid address
        raise RuntimeError(f"Could not connect to Supabase. Check SUPABASE_URL and SUPABASE_KEY. ({err})") from err


def get_db():
    """The shared client used for all table queries.

    Created the first time it is needed (not when the file is imported),
    so the app and the tests can start even before .env is filled in.
    """
    global _client
    if _client is None:
        with _lock:                  # if two requests arrive together, only one builds it
            if _client is None:
                _client = _create_client()
    return _client


def get_auth_client():
    """A fresh client just for login, signup and checking tokens.

    Never use the shared client for these. Logging in on it would switch it
    to that one student's permissions, and every later query would run as them.
    """
    return _create_client()