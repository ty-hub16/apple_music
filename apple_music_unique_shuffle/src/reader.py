"""
reader.py - Apple Music UI reader
Navigates Apple Music to the Songs tab, sorts by Last Played,
and reads every song row to extract title + last played date.
"""

import ctypes
import re
import time
from datetime import datetime

import uiautomation as auto

# Apple Music displays dates in format "4/9/2026, 9:51 AM"
_DATE_FORMATS = [
    "%m/%d/%Y, %I:%M %p",
    "%m/%d/%Y, %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
]


def _try_parse_date(s: str) -> datetime | None:
    # Strip Unicode directional marks (\u200e etc.) that Apple Music embeds
    s = re.sub(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069]', '', (s or '')).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _child_count(ctrl) -> int:
    try:
        return len(ctrl.GetChildren())
    except Exception:
        return 0


def _find_window() -> auto.WindowControl | None:
    print("    [DEBUG] Getting root control...")
    desktop = auto.GetRootControl()
    print(f"    [DEBUG] Got root control, checking children...")
    children = desktop.GetChildren()
    print(f"    [DEBUG] Found {len(children)} top-level windows")
    for i, window in enumerate(children):
        window_name = window.Name or ""
        print(f"    [DEBUG]   Window {i}: {window_name}")
        if "music" in window_name.lower():
            print(f"    [DEBUG] Found Music window: {window_name}")
            return window
    print("    [DEBUG] No Music window found")
    return None


def _restore_window(window) -> bool:
    """Maximize window and bring to foreground. Returns True if it was minimized."""
    SW_MAXIMIZE = 3
    SW_SHOW = 5
    try:
        hwnd = window.NativeWindowHandle
        was_minimized = bool(ctypes.windll.user32.IsIconic(hwnd))
        
        # Multiple aggressive steps to bring window to foreground
        ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
        
        # Additional activation attempts
        try:
            ctypes.windll.user32.SetActiveWindow(hwnd)
        except Exception:
            pass
        
        time.sleep(2.0)  # Wait longer to ensure UI renders
        return was_minimized
    except Exception:
        return False


def _minimize_window(window) -> None:
    SW_MINIMIZE = 6
    try:
        hwnd = window.NativeWindowHandle
        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
    except Exception:
        pass


def _navigate_to_songs(window) -> None:
    def find_songs_item(element, depth=0):
        if depth > 12:
            return None
        try:
            for child in element.GetChildren():
                if child.ControlTypeName == "ListItemControl" and child.Name == "Songs":
                    return child
                result = find_songs_item(child, depth + 1)
                if result is not None:
                    return result
        except Exception:
            pass
        return None

    # Retry logic: Apple Music UI takes time to load after restore
    max_retries = 5
    for attempt in range(max_retries):
        print(f"    [DEBUG] Looking for Songs item (attempt {attempt+1}/{max_retries})...")
        item = find_songs_item(window)
        if item:
            try:
                item.GetInvokePattern().Invoke()
            except Exception:
                item.Click()
            time.sleep(2.0)
            return
        if attempt < max_retries - 1:
            time.sleep(1.5)  # Wait before retrying

    raise RuntimeError("Could not find 'Songs' nav item — is the sidebar visible? Tried 5 times.")


def _sample_top_dates(window, count: int = 5) -> list[datetime]:
    """Read the Last Played dates off the first few currently visible rows."""
    songs_list = _find_songs_list(window)
    if not songs_list:
        return []
    try:
        items = [c for c in songs_list.GetChildren() if c.ControlTypeName == "ListItemControl"]
    except Exception:
        return []
    dates = []
    for item in items[:count]:
        dt = _get_last_played_from_children(item)
        if dt:
            dates.append(dt)
    return dates


def _is_sorted_descending(dates: list[datetime]) -> bool:
    return len(dates) >= 2 and all(dates[i] >= dates[i + 1] for i in range(len(dates) - 1))


def _sort_by_last_played(window) -> None:
    def find_header(element, depth=0):
        if depth > 14:
            return None
        try:
            name = element.Name or ""
            if name == "Last Played" and element.ControlTypeName != "ListItemControl":
                return element
            for child in element.GetChildren():
                result = find_header(child, depth + 1)
                if result is not None:
                    return result
        except Exception:
            pass
        return None

    header = find_header(window)
    if not header:
        raise RuntimeError("Could not find 'Last Played' column header")

    # Rather than trying to read the sort-arrow icon (which Apple Music may
    # expose with no distinguishing accessible name/text — e.g. the same
    # glyph just rotated 180°), click and then check the *actual* row order:
    # read the Last Played dates of the first few visible rows and confirm
    # they're descending. This verifies the real thing we care about instead
    # of guessing at how the arrow is represented in the automation tree.
    max_clicks = 4
    for attempt in range(1, max_clicks + 1):
        try:
            header.GetInvokePattern().Invoke()
        except Exception:
            header.Click()
        time.sleep(0.6)

        dates = _sample_top_dates(window)
        descending = _is_sorted_descending(dates)
        print(
            f"    [DEBUG] Last Played sort after click {attempt}: "
            f"{'descending' if descending else 'not confirmed'} "
            f"(sampled {len(dates)} date(s): {[d.strftime('%m/%d %H:%M') for d in dates]})"
        )
        if descending:
            return

    print(
        f"    [DEBUG] Warning: could not confirm 'Last Played' is sorted descending "
        f"after {max_clicks} clicks; proceeding with current order."
    )


def _find_songs_list(window):
    """Return the ListControl that contains actual song rows."""
    results = []

    def search(element, depth=0):
        if depth > 14:
            return
        try:
            if element.ControlTypeName == "ListControl":
                results.append(element)
            for child in element.GetChildren():
                search(child, depth + 1)
        except Exception:
            pass

    search(window)

    # The songs list has items with duration patterns like "4:32"
    for ctrl in sorted(results, key=_child_count, reverse=True):
        try:
            children = ctrl.GetChildren()
            song_like = [
                c for c in children
                if c.ControlTypeName == "ListItemControl"
                and re.search(r'\b\d{1,2}:\d{2}\b', c.Name or "")
            ]
            if len(song_like) >= 5:
                return ctrl
        except Exception:
            continue
    return None


def _parse_title(name: str) -> str:
    """Extract just the song title from a ListItem Name string.

    ListItem Name format: "Title [Explicit] M:SS Artist Album Genre PlayCount"
    """
    m = re.search(r'\s+(?:Explicit\s+)?\d{1,2}:\d{2}\b', name)
    if m:
        raw = name[:m.start()].strip()
    else:
        raw = name.strip()
    return re.sub(r'\s*Explicit\s*$', '', raw).strip()


def _get_artist_from_children(item) -> str:
    """Read the artist name from a ListItem's child TextControls.

    Skips the title (index 0) and any node that looks like a duration (M:SS),
    then returns the first remaining non-empty text node which is the artist.
    """
    try:
        for group in item.GetChildren():
            text_nodes = []
            try:
                for child in group.GetChildren():
                    if child.ControlTypeName == "TextControl":
                        text_nodes.append(child.Name or "")
            except Exception:
                continue
            for node in text_nodes[1:]:
                node = node.strip()
                if node and not re.match(r'^\d{1,2}:\d{2}$', node):
                    return node
    except Exception:
        pass
    return ""


def _get_last_played_from_children(item) -> datetime | None:
    """Find the Last Played date from a ListItem's child TextControls.

    Structure: ListItem > GroupControl > [... TextControls ..., DateAdded, LastPlayed]
    The Last Played date is the last TextControl that parses as a date.
    """
    try:
        for group in item.GetChildren():
            # Collect all TextControl Names from the GroupControl's children
            text_nodes = []
            try:
                for child in group.GetChildren():
                    if child.ControlTypeName == "TextControl":
                        text_nodes.append(child.Name or "")
            except Exception:
                continue
            # Walk backwards — Last Played is the last date-parseable TextControl
            for text in reversed(text_nodes):
                dt = _try_parse_date(text)
                if dt:
                    return dt
    except Exception:
        pass
    return None


def refresh(restore_after: bool = True) -> dict[str, dict]:
    """
    Open Apple Music, navigate to Songs, sort by Last Played (descending),
    and read every song row.

    Returns a dict mapping lowercase title → {"last_played": datetime | None, "artist": str}.

    If restore_after is True and the window was minimized before the refresh,
    it will be minimized again afterwards.
    """
    print("  [DEBUG] Finding Apple Music window...")
    window = _find_window()
    if not window:
        raise RuntimeError("Apple Music window not found. Is the app running?")

    print("  [DEBUG] Window found. Restoring...")
    was_minimized = _restore_window(window)
    time.sleep(1.0)  # Give Apple Music UI time to fully load after restore
    try:
        print("  [DEBUG] Navigating to Songs tab...")
        _navigate_to_songs(window)
        print("  [DEBUG] Sorting by Last Played...")
        _sort_by_last_played(window)

        print("  [DEBUG] Finding songs list...")
        songs_list = _find_songs_list(window)
        if not songs_list:
            raise RuntimeError("Could not locate the Songs list control after navigation.")

        data: dict[str, dict] = {}
        items = [
            c for c in songs_list.GetChildren()
            if c.ControlTypeName == "ListItemControl"
        ]

        dates_found = 0
        for item in items:
            title = _parse_title(item.Name or "")
            if not title:
                continue
            last_played = _get_last_played_from_children(item)
            artist = _get_artist_from_children(item)
            if last_played:
                dates_found += 1
            data[title.lower()] = {"last_played": last_played, "artist": artist}

        print(f"  [reader] Read {len(data)} songs, {dates_found} with Last Played dates.")
        return data

    finally:
        if restore_after and was_minimized:
            _minimize_window(window)



