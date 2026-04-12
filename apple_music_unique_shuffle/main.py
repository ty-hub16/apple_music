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

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def was_played_recently(
    title: str,
    songs_data: dict,
    cooldown_days: int,
) -> bool:
    if cooldown_days <= 0:
        return False
    last_played = songs_data.get(title.strip().lower())
    if last_played is None:
        return False
    return datetime.now() - last_played < timedelta(days=cooldown_days)


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

    print("Reading Last Played data from Apple Music...")
    songs_data = refresh()
    last_refresh = time.monotonic()
    print("  Done. Monitoring started.\n")

    last_track: tuple | None = None
    skip_count = 0

    while True:
        try:
            # Periodic UI refresh
            if time.monotonic() - last_refresh >= refresh_interval:
                print(f"\n[{datetime.now().strftime('%H:%M')}] Refreshing Last Played data...")
                try:
                    songs_data = refresh()
                    last_refresh = time.monotonic()
                except Exception as e:
                    print(f"  Refresh failed: {e} — keeping previous data.")

            track = get_current_track()

            if track and track != last_track:
                title, artist = track
                if not title:
                    last_track = track
                    time.sleep(interval)
                    continue

                if was_played_recently(title, songs_data, cooldown_days):
                    print(f"  SKIP  {title}  (played within {cooldown_days}d)")
                    skip_track()
                    skip_count += 1
                    time.sleep(2)
                    continue

                print(f"  PLAY  {title}  — {artist}")
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

