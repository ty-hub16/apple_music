# apple_music

**Skills Used:**
Python, JSON parsing, CSV read/write, Windows UI Automation, Date/time parsing, Deduplication, Polling loop, LLM integration

A collection of Apple Music automation tools.

---

## [apple_music_unique_shuffle](apple_music_unique_shuffle/)

Skips songs you've already played recently while shuffling, so you actually hear new stuff.

**Features:**
- ⏭️ On startup, seeds play history from the Apple Music UI into a local CSV cache
- 📝 Every play is logged to the CSV so history persists across restarts
- ⏸️ **Pause mode**: Temporarily stop skipping to replay recently heard songs without caching
- 🤖 **AI chat**: Ask questions about your music listening history (powered by Claude or OpenAI)
- 🔄 Automatically skips any song played within the last X days
- 📱 Refreshes every hour from the Apple Music UI to pick up plays from other devices
- **Windows only** (requires the Apple Music Microsoft Store app + Python 3.10+)

> **On an Apple device?** Use this Shortcut instead: [Apple Music Unique Shuffle](https://www.icloud.com/shortcuts/009acbd61de5401b8eb364f1a67e7308)
> Filters out recently played songs and shuffles the rest. Asks for the cooldown period on first run.
