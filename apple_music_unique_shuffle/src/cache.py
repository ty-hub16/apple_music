"""
cache.py - CSV-based Last Played cache
Persists recently played songs to disk so history survives restarts.
"""

import csv
import os
from datetime import datetime, timedelta

_FIELDNAMES = ["title", "artist", "last_played"]
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _make_key(title: str, artist: str = "") -> str:
    """Composite cache key: 'title|artist' lowercased."""
    return f"{title.strip().lower()}|{artist.strip().lower()}"


def load(path: str) -> dict[str, dict]:
    """Load cache from CSV. Returns dict of 'title|artist' → {last_played, artist}."""
    data: dict[str, dict] = {}
    if not os.path.exists(path):
        return data
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                artist = row.get("artist", "")
                key = _make_key(row["title"], artist)
                data[key] = {
                    "last_played": datetime.strptime(row["last_played"], _DATE_FMT),
                    "artist": artist,
                }
            except (KeyError, ValueError):
                continue
    return data


def save(path: str, data: dict[str, dict]) -> None:
    """Write cache to CSV, sorted most-recent first."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for key, info in sorted(data.items(), key=lambda x: x[1]["last_played"], reverse=True):
            # key is 'title|artist' — split back out for CSV columns
            parts = key.split("|", 1)
            writer.writerow({
                "title": parts[0],
                "artist": info.get("artist", ""),
                "last_played": info["last_played"].strftime(_DATE_FMT),
            })


def prune(data: dict[str, dict], cooldown_days: int) -> dict[str, dict]:
    """Return a new dict with entries older than cooldown_days removed."""
    cutoff = datetime.now() - timedelta(days=cooldown_days)
    return {t: info for t, info in data.items() if info["last_played"] >= cutoff}


def update(data: dict[str, dict], title: str, artist: str = "") -> None:
    """Record a play for title+artist with the current timestamp (in-place)."""
    data[_make_key(title, artist)] = {"last_played": datetime.now(), "artist": artist}
