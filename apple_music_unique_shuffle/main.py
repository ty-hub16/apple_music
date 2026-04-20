"""
main.py - Apple Music Unique Shuffle
Reads Last Played dates from Apple Music UI every refresh_interval_seconds,
then skips any currently playing song that was played within cooldown_days.

Usage:
    python main.py

Press Ctrl+C to stop.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from src.reader import refresh
from src.player import get_current_track, skip_track
from src import cache
from src.cache import _make_key

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
CACHE_PATH = os.path.join(os.path.dirname(__file__), "last_played_cache.csv")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _find_key_by_title(songs_data: dict, title: str) -> str | None:
    """Return the first cache key matching this title, regardless of artist."""
    prefix = title.strip().lower() + "|"
    for key in songs_data:
        if key.startswith(prefix):
            return key
    return None


def was_played_recently(
    title: str,
    artist: str,
    songs_data: dict,
    cooldown_days: int,
) -> bool:
    if cooldown_days <= 0:
        return False
    entry = songs_data.get(_make_key(title, artist))
    if entry is None:
        # Fall back to any entry for this title (e.g. seeded from UI without artist)
        key = _find_key_by_title(songs_data, title)
        entry = songs_data.get(key) if key else None
    if entry is None:
        return False
    return datetime.now() - entry["last_played"] < timedelta(days=cooldown_days)


def main():
    config = load_config()
    cooldown_days: int = config.get("cooldown_days", 21)
    interval: float = config.get("check_interval_seconds", 10)
    refresh_interval: float = config.get("refresh_interval_seconds", 3600)

    print("Apple Music Unique Shuffle")
    print(f"  Cooldown : {cooldown_days} day(s)")
    print(f"  Poll     : every {interval}s")
    print(f"  Refresh  : every {refresh_interval / 60:.0f} min")
    print("  Press Ctrl+C to stop.\n")

    print("Seeding cache from Apple Music...")
    ui_data = refresh()
    songs_data = cache.load(CACHE_PATH)
    seeded = 0
    for title, entry in ui_data.items():
        dt = entry["last_played"]
        ui_artist = entry["artist"]
        if dt is None:
            continue
        existing_key = _find_key_by_title(songs_data, title)
        if existing_key:
            cached = songs_data[existing_key]
            best_artist = cached["artist"] or ui_artist
            if dt > cached["last_played"]:
                songs_data[existing_key] = {"last_played": dt, "artist": best_artist}
                seeded += 1
            elif best_artist != cached["artist"]:
                songs_data[existing_key]["artist"] = best_artist
        else:
            key = _make_key(title, ui_artist)
            songs_data[key] = {"last_played": dt, "artist": ui_artist}
            seeded += 1
    songs_data = cache.prune(songs_data, cooldown_days)
    cache.save(CACHE_PATH, songs_data)
    print(f"  {len(songs_data)} songs in cooldown window ({seeded} seeded from UI).")
    print("  Done. Monitoring started.\n")

    last_track: tuple | None = None
    skip_count = 0
    last_refresh = time.monotonic()

    while True:
        try:
            # Hourly UI refresh — picks up plays from other devices
            if time.monotonic() - last_refresh >= refresh_interval:
                print(f"\n[{datetime.now().strftime('%H:%M')}] Refreshing Last Played from Apple Music...")
                try:
                    ui_data = refresh()
                    merged = 0
                    for title, entry in ui_data.items():
                        dt = entry["last_played"]
                        ui_artist = entry["artist"]
                        if dt is None:
                            continue
                        existing_key = _find_key_by_title(songs_data, title)
                        if existing_key:
                            cached = songs_data[existing_key]
                            best_artist = cached["artist"] or ui_artist
                            if dt > cached["last_played"]:
                                songs_data[existing_key] = {"last_played": dt, "artist": best_artist}
                                merged += 1
                            elif best_artist != cached["artist"]:
                                songs_data[existing_key]["artist"] = best_artist
                        else:
                            key = _make_key(title, ui_artist)
                            songs_data[key] = {"last_played": dt, "artist": ui_artist}
                            merged += 1
                    songs_data = cache.prune(songs_data, cooldown_days)
                    cache.save(CACHE_PATH, songs_data)
                    print(f"  {merged} new/updated entries merged. {len(songs_data)} songs in cooldown window.")
                    last_refresh = time.monotonic()
                except Exception as e:
                    print(f"  Refresh failed: {e} — keeping existing cache.")

            track = get_current_track()

            if track and track != last_track:
                title, artist = track
                if not title:
                    last_track = track
                    time.sleep(interval)
                    continue

                if was_played_recently(title, artist, songs_data, cooldown_days):
                    key = _make_key(title, artist)
                    if key not in songs_data:
                        key = _find_key_by_title(songs_data, title) or key
                    entry = songs_data.get(key)
                    last_played = entry["last_played"] if entry else None
                    played_str = f"{last_played.month}/{last_played.day}/{last_played.year}" if last_played else "unknown"
                    print(f"  SKIP  {title}  (played within {cooldown_days}d — last played {played_str})")
                    skip_track()
                    skip_count += 1
                    time.sleep(2)
                    continue

                print(f"  PLAY  {title}  — {artist}")
                cache.update(songs_data, title, artist)
                songs_data = cache.prune(songs_data, cooldown_days)
                cache.save(CACHE_PATH, songs_data)
                last_track = track

            time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\nStopped. Skipped {skip_count} song(s) this session.")
            break
        except Exception as e:
            print(f"  ERROR: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    main()

