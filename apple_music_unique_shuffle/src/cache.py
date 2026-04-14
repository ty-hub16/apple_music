"""
cache.py - CSV-based Last Played cache
Persists recently played songs to disk so history survives restarts.
"""

import csv
import os
from datetime import datetime, timedelta

_FIELDNAMES = ["title", "last_played"]
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def load(path: str) -> dict[str, datetime]:
    """Load cache from CSV. Returns dict of lowercase title → datetime."""
    data: dict[str, datetime] = {}
    if not os.path.exists(path):
        return data
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                data[row["title"]] = datetime.strptime(row["last_played"], _DATE_FMT)
            except (KeyError, ValueError):
                continue
    return data


def save(path: str, data: dict[str, datetime]) -> None:
    """Write cache to CSV, sorted most-recent first."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for title, dt in sorted(data.items(), key=lambda x: x[1], reverse=True):
            writer.writerow({"title": title, "last_played": dt.strftime(_DATE_FMT)})


def prune(data: dict[str, datetime], cooldown_days: int) -> dict[str, datetime]:
    """Return a new dict with entries older than cooldown_days removed."""
    cutoff = datetime.now() - timedelta(days=cooldown_days)
    return {t: dt for t, dt in data.items() if dt >= cutoff}


def update(data: dict[str, datetime], title: str) -> None:
    """Record a play for title with the current timestamp (in-place)."""
    data[title.strip().lower()] = datetime.now()
