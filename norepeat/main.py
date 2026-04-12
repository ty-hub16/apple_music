"""
NoRepeat - Main entry point
Step 1: Test AppleScript integration with Apple Music.
Run this on your Mac to verify track reading and skipping work correctly.
"""

import sys
import logging
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from applescript import get_current_track, get_player_state, skip_track

load_dotenv()

# Load config
CONFIG_FILE = Path(__file__).parent / "config.json"
with open(CONFIG_FILE) as f:
    config = json.load(f)

CHECK_INTERVAL = config.get("check_interval_seconds", 30)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("norepeat")


def main():
    logger.info("=" * 60)
    logger.info("NoRepeat - Starting up")
    logger.info(f"Checking every {CHECK_INTERVAL} seconds")
    logger.info("=" * 60)

    while True:
        state = get_player_state()
        logger.info(f"Player state: {state}")

        if state == "playing":
            track = get_current_track()
            if track:
                logger.info(f"🎵 Now playing: {track}")
            else:
                logger.warning("Could not read current track")
        else:
            logger.info("Nothing playing, waiting...")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n✓ NoRepeat stopped")
