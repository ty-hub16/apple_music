"""
cache.py - Postgres-backed Last Played cache
Keeps recently played songs in the apple_music database so history survives restarts.
Connection settings (PGHOST, PGUSER, PGPASSWORD, ...) come from the .env next to main.py.
"""

import os
from datetime import datetime, time, timedelta

import psycopg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_SEP = " — "  # Apple Music shows "Artist — Album"; the DB stores them in separate columns

_UPSERT_SQL = """
    INSERT INTO last_played (title, artist, album, last_played)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (title, artist) DO UPDATE
    SET last_played = GREATEST(last_played.last_played, EXCLUDED.last_played),
        album       = COALESCE(EXCLUDED.album, last_played.album)
"""


def _make_key(title: str, artist: str = "") -> str:
    """Composite cache key: 'title|artist' lowercased."""
    return f"{title.strip().lower()}|{artist.strip().lower()}"


def load() -> dict[str, dict]:
    """Load every row from Postgres. Returns dict of 'title|artist' → {last_played, artist}."""
    with psycopg.connect() as conn:
        rows = conn.execute(
            "SELECT title, artist, album, last_played FROM last_played"
        ).fetchall()

    data: dict[str, dict] = {}
    for title, artist, album, played in rows:
        # Rebuild "Artist — Album" so it matches what the rest of the script expects
        full_artist = f"{artist}{_SEP}{album}" if album else artist
        data[_make_key(title, full_artist)] = {
            "last_played": datetime.combine(played, time()),
            "artist": full_artist,
        }
    return data


def save(data: dict[str, dict]) -> None:
    """Upsert every in-memory entry into Postgres. Never moves a date backwards."""
    rows = []
    for key, info in data.items():
        title = key.split("|", 1)[0]
        artist, _, album = (info.get("artist") or "").partition(_SEP)
        rows.append((title, artist, album or None, info["last_played"].date()))

    with psycopg.connect() as conn:  # commits on success, rolls back on error
        with conn.cursor() as cur:
            cur.executemany(_UPSERT_SQL, rows)


def prune(data: dict[str, dict], cooldown_days: int) -> dict[str, dict]:
    """Return a new dict with entries older than cooldown_days removed.
    Only trims memory; old plays stay in the database as history."""
    cutoff = datetime.now() - timedelta(days=cooldown_days)
    return {t: info for t, info in data.items() if info["last_played"] >= cutoff}


def update(data: dict[str, dict], title: str, artist: str = "") -> None:
    """Record a play for title+artist with the current timestamp (in-place)."""
    data[_make_key(title, artist)] = {"last_played": datetime.now(), "artist": artist}
