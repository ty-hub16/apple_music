# Apple Music Unique Shuffle

A Windows script that skips songs you've already played recently while shuffling Apple Music, so you actually hear new stuff.

> **Windows only** — this script requires the [Apple Music app for Windows](https://apps.microsoft.com/detail/9PFHDD62MXS1) (Microsoft Store). It will not work on Mac, iPhone, or iPad.
>
> **On an Apple device?** Use this Apple Shortcut instead: [Apple Music Unique Shuffle](https://www.icloud.com/shortcuts/009acbd61de5401b8eb364f1a67e7308)
> Filters out songs played within the last X days, then shuffles the remaining songs. It will ask you for the number of days when you first run it.

## How it works

1. On startup, opens Apple Music, navigates to the **Songs** tab, and sorts by **Last Played** — reading the date from each song row via Windows UI Automation.
2. Every 10 seconds, reads the currently playing song from the Apple Music transport bar.
3. If that song was played within the last `cooldown_days` days, it sends a **Next Track** media key to skip it automatically.
4. Every hour it re-reads Last Played dates from the Apple Music UI to stay in sync across devices.

## Requirements

- Windows 10/11
- Apple Music (Microsoft Store app)
- Python 3.10+

## Setup

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Edit `config.json`:

```json
{
  "cooldown_days": 21,
  "check_interval_seconds": 10,
  "refresh_interval_seconds": 3600
}
```

| Setting | Description |
|---|---|
| `cooldown_days` | Songs played within this many days are skipped |
| `check_interval_seconds` | How often to check what's currently playing |
| `refresh_interval_seconds` | How often to re-read Last Played from Apple Music UI (default: 1 hour) |

## Usage

Open Apple Music and start shuffling, then run:

```cmd
venv\Scripts\python.exe main.py
```

Output example:
```
Apple Music Unique Shuffle
  Cooldown : 21 day(s)
  Poll     : every 10s
  Refresh  : every 60 min
  Press Ctrl+C to stop.

Reading Last Played data from Apple Music...
  [reader] Read 124 songs, 124 with Last Played dates.
  Done. Monitoring started.

  SKIP  Savior  (played within 21d)
  PLAY  On & On  — Joey Bada$$
  SKIP  MÍA (feat. Drake)  (played within 21d)
  PLAY  Like That  — Future, Metro Boomin & Kendrick Lamar
```

Press `Ctrl+C` to stop.

## Notes

- Apple Music must be running (it will be un-minimized briefly on startup and each hourly refresh, then minimized again)
- Last Played dates sync across Apple devices, but the sync can take up to an hour — hence the hourly refresh
- The Songs tab must be visible in the sidebar; if it isn't, expand **Library** in the sidebar
