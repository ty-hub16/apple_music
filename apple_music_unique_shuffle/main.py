"""
main.py - Apple Music Unique Shuffle
Reads Last Played dates from Apple Music UI every refresh_interval_seconds,
then skips any currently playing song that was played within cooldown_days.

Usage:
    python main.py

Commands:
    p/pause        - Pause skip mode (songs won't be cached)
    resume/start   - Resume skip mode
    r/refresh      - Instantly re-seed the cache from Apple Music
    chat           - Enter interactive chat about your music
    q/quit         - Exit

Press Ctrl+C to stop.
"""

import json
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from queue import Queue, Empty

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


def _get_status_prefix(pause_mode: bool) -> str:
    """Return the status indicator for log lines."""
    return "[⏸ PAUSED] " if pause_mode else ""


def _try_claude_api(messages: list) -> str | None:
    """Try to call Claude API. Returns response or None if unavailable."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        turns = [m for m in messages if m["role"] != "system"]
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            system=system,
            messages=turns,
        )
        return response.content[0].text
    except Exception:
        return None


def _try_openai_api(messages: list) -> str | None:
    """Try to call OpenAI API (free tier). Returns response or None if unavailable."""
    try:
        import openai
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=1024,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception:
        return None


def _try_gemini_api(messages: list) -> str | None:
    """Try to call the Gemini API (free tier). Returns response or None if unavailable."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client()
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_content = next((m["content"] for m in messages if m["role"] == "user"), "")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_content,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return response.text
    except Exception:
        return None


def _try_ollama_api(messages: list) -> str | None:
    """Try to call a local Ollama server. Returns response or None if unavailable."""
    try:
        import urllib.request

        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_content = next((m["content"] for m in messages if m["role"] == "user"), "")
        prompt = f"{system}\n\n{user_content}" if system else user_content
        payload = json.dumps({
            "model": "llama3.2",
            "prompt": prompt,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("response")
    except Exception:
        return None


def _call_llm(messages: list) -> str | None:
    """Call Claude first, then OpenAI, then Gemini, then a local Ollama server."""
    response = _try_claude_api(messages)
    if response:
        return response
    response = _try_openai_api(messages)
    if response:
        return response
    response = _try_gemini_api(messages)
    if response:
        return response
    return _try_ollama_api(messages)


def _format_music_history(songs_data: dict, limit: int = 20) -> str:
    """Format recently played songs for LLM context."""
    sorted_songs = sorted(
        songs_data.items(),
        key=lambda x: x[1]["last_played"],
        reverse=True
    )[:limit]
    
    lines = ["Recently played songs:"]
    for key, info in sorted_songs:
        title = key.split("|")[0]
        artist = info.get("artist", "Unknown")
        played_date = info["last_played"].strftime("%m/%d/%Y")
        lines.append(f"  - {title} by {artist} (played {played_date})")
    
    return "\n".join(lines)


def _input_listener(command_queue: Queue, stop_event: threading.Event) -> None:
    """Listen for user input in a separate thread."""
    while not stop_event.is_set():
        try:
            user_input = input().strip()
            if user_input:
                command_queue.put(user_input)
        except EOFError:
            break
        except Exception:
            pass


def _chat_mode(songs_data: dict, pause_mode: bool, command_queue: Queue) -> bool:
    """Interactive chat mode. Returns True to resume monitoring, False to quit."""
    print("\n[CHAT MODE]")
    print("Ask questions about your music history (type 'exit' to return to monitoring):")
    print(f"  - 'songs from [artist]'")
    print(f"  - 'top artists this week'")
    print(f"  - 'songs played today'")
    print(f"  - 'listening patterns'")

    music_context = _format_music_history(songs_data)

    while True:
        try:
            print("You: ", end="", flush=True)
            # Read from the shared command_queue (filled by the background
            # _input_listener thread) instead of calling input() directly —
            # calling input() here too would race with that thread for stdin,
            # requiring the user to type each line twice.
            user_query = None
            while user_query is None:
                try:
                    user_query = command_queue.get(timeout=0.2).strip()
                except Empty:
                    continue
            if not user_query:
                continue
            print(user_query)
            if user_query.lower() in ["exit", "q", "quit"]:
                print("[Returning to monitoring...]\n")
                return True
            
            # Build message with music context
            messages = [
                {
                    "role": "system",
                    "content": f"You are a helpful assistant analyzing a user's music listening history. Here's their data:\n\n{music_context}\n\nAnswer questions about their listening patterns concisely.",
                },
                {"role": "user", "content": user_query},
            ]
            
            response = _call_llm(messages)
            if response:
                print(f"Assistant: {response}\n")
            else:
                print("Assistant: (Unable to connect to AI service. Install 'anthropic', 'openai', 'google-genai', or run Ollama locally.)\n")
        
        except KeyboardInterrupt:
            print("\n[Returning to monitoring...]\n")
            return True
        except Exception as e:
            print(f"Error: {e}\n")

def _refresh_and_merge(songs_data: dict, cooldown_days: int) -> tuple[dict, int]:
    """Pull Last Played data from the Apple Music UI and merge it into songs_data.

    Returns the (possibly pruned) songs_data dict and the number of new/updated entries.
    """
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
    return songs_data, merged


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
    print("  Commands: 'p'/'pause' to pause, 'resume'/'start' to resume, 'r'/'refresh' to re-seed now, 'chat' for AI chat")
    print("  Press Ctrl+C to stop.\n")

    # Setup input listener thread
    command_queue: Queue = Queue()
    stop_event = threading.Event()
    input_thread = threading.Thread(target=_input_listener, args=(command_queue, stop_event), daemon=True)
    input_thread.start()

    print("Seeding cache from Apple Music...")
    songs_data = cache.load(CACHE_PATH)
    songs_data, seeded = _refresh_and_merge(songs_data, cooldown_days)
    print(f"  {len(songs_data)} songs in cooldown window ({seeded} seeded from UI).")
    print("  Done. Monitoring started.\n")

    last_track: tuple | None = None
    skip_count = 0
    last_refresh = time.monotonic()
    pause_mode = False

    while True:
        try:
            # Check for user commands
            while not command_queue.empty():
                cmd = command_queue.get().lower()
                if cmd in ["p", "pause"]:
                    pause_mode = True
                    print(f"\n{_get_status_prefix(pause_mode)}⏸ PAUSE MODE ON — songs will not be cached")
                    print(f"{_get_status_prefix(pause_mode)}(type 'resume' or 'start' to resume)\n")
                elif cmd in ["resume", "start"]:
                    pause_mode = False
                    print(f"\n▶ PAUSE MODE OFF — resuming cache\n")
                elif cmd in ["r", "refresh"]:
                    print(f"\n{_get_status_prefix(pause_mode)}[{datetime.now().strftime('%H:%M')}] Refreshing Last Played from Apple Music...")
                    try:
                        songs_data, merged = _refresh_and_merge(songs_data, cooldown_days)
                        print(f"  {merged} new/updated entries merged. {len(songs_data)} songs in cooldown window.\n")
                        last_refresh = time.monotonic()
                    except Exception as e:
                        print(f"  Refresh failed: {e} — keeping existing cache.\n")
                elif cmd == "chat":
                    if _chat_mode(songs_data, pause_mode, command_queue):
                        continue
                    else:
                        stop_event.set()
                        break

            # Hourly UI refresh — picks up plays from other devices (skip if paused)
            if not pause_mode and time.monotonic() - last_refresh >= refresh_interval:
                print(f"\n{_get_status_prefix(pause_mode)}[{datetime.now().strftime('%H:%M')}] Refreshing Last Played from Apple Music...")
                try:
                    songs_data, merged = _refresh_and_merge(songs_data, cooldown_days)
                    print(f"  {merged} new/updated entries merged. {len(songs_data)} songs in cooldown window.")
                    last_refresh = time.monotonic()
                except Exception as e:
                    print(f"  Refresh failed: {e} — keeping existing cache.")
            elif pause_mode and time.monotonic() - last_refresh >= refresh_interval:
                # Reset refresh timer even when paused so it doesn't try to refresh again immediately when resumed
                last_refresh = time.monotonic()

            track = get_current_track()

            if track and track != last_track:
                title, artist = track
                if not title:
                    last_track = track
                    time.sleep(interval)
                    continue

                if was_played_recently(title, artist, songs_data, cooldown_days):
                    if not pause_mode:
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

                # Only cache if not in pause mode
                if not pause_mode:
                    print(f"  PLAY  {title}  — {artist}")
                    cache.update(songs_data, title, artist)
                    songs_data = cache.prune(songs_data, cooldown_days)
                    cache.save(CACHE_PATH, songs_data)
                last_track = track

            time.sleep(interval)

        except KeyboardInterrupt:
            stop_event.set()
            print(f"\nStopped. Skipped {skip_count} song(s) this session.")
            break
        except Exception as e:
            print(f"  ERROR: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    main()

