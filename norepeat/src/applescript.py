"""
AppleScript integration for NoRepeat.
Handles all communication with Apple Music via osascript subprocess calls.
"""

import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Track:
    """Represents the currently playing track."""
    name: str
    artist: str
    album: str

    def __str__(self) -> str:
        return f"{self.artist} - {self.name}"


def _run_applescript(script: str) -> tuple[str, str]:
    """
    Run an AppleScript string via osascript.

    Returns:
        (stdout, stderr) both stripped strings.
    """
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.stderr.strip()


def get_player_state() -> str:
    """
    Returns the current Apple Music player state.
    Possible values: 'playing', 'paused', 'stopped'
    """
    script = 'tell application "Music" to get player state as string'
    stdout, stderr = _run_applescript(script)
    if stderr:
        logger.debug(f"Player state error: {stderr}")
    return stdout.lower()


def get_current_track() -> Optional[Track]:
    """
    Returns the currently playing Track, or None if nothing is playing.
    Uses a pipe delimiter internally to split the AppleScript response.
    """
    # Only attempt to read the track if Music is actually playing
    state = get_player_state()
    if state != "playing":
        logger.debug(f"Apple Music is not playing (state: {state})")
        return None

    script = """
    tell application "Music"
        set t to name of current track
        set a to artist of current track
        set b to album of current track
        return t & "|~|" & a & "|~|" & b
    end tell
    """
    stdout, stderr = _run_applescript(script)

    if stderr:
        logger.warning(f"AppleScript error reading track: {stderr}")
        return None

    if not stdout or "|~|" not in stdout:
        logger.warning(f"Unexpected AppleScript response: {stdout!r}")
        return None

    parts = stdout.split("|~|")
    if len(parts) != 3:
        logger.warning(f"Could not parse track parts: {parts}")
        return None

    name, artist, album = [p.strip() for p in parts]
    return Track(name=name, artist=artist, album=album)


def skip_track() -> bool:
    """
    Sends a skip (next track) command to Apple Music.
    Returns True if successful, False if an error occurred.
    """
    script = 'tell application "Music" to next track'
    stdout, stderr = _run_applescript(script)
    if stderr:
        logger.error(f"Failed to skip track: {stderr}")
        return False
    logger.info("⏭ Skipped track")
    return True
