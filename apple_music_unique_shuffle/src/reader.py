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
    desktop = auto.GetRootControl()
    for window in desktop.GetChildren():
        if "music" in (window.Name or "").lower():
            return window
    return None


def _restore_window(window) -> bool:
    """Maximize window and bring to foreground. Returns True if it was minimized."""
    SW_MAXIMIZE = 3
    try:
        hwnd = window.NativeWindowHandle
        was_minimized = bool(ctypes.windll.user32.IsIconic(hwnd))
        ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(1.0)
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

    item = find_songs_item(window)
    if not item:
        raise RuntimeError("Could not find 'Songs' nav item — is the sidebar visible?")
    try:
        item.GetInvokePattern().Invoke()
    except Exception:
        item.Click()
    time.sleep(2.0)


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

    # Click twice: first click may set ascending, second sets descending
    for _ in range(2):
        try:
            header.GetInvokePattern().Invoke()
        except Exception:
            header.Click()
        time.sleep(0.5)


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


def refresh(restore_after: bool = True) -> dict[str, datetime | None]:
    """
    Open Apple Music, navigate to Songs, sort by Last Played (descending),
    and read every song row.

    Returns a dict mapping lowercase title → last_played datetime (or None if
    the date wasn't readable from the UI).

    If restore_after is True and the window was minimized before the refresh,
    it will be minimized again afterwards.
    """
    window = _find_window()
    if not window:
        raise RuntimeError("Apple Music window not found. Is the app running?")

    was_minimized = _restore_window(window)
    try:
        _navigate_to_songs(window)
        _sort_by_last_played(window)

        songs_list = _find_songs_list(window)
        if not songs_list:
            raise RuntimeError("Could not locate the Songs list control after navigation.")

        data: dict[str, datetime | None] = {}
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
            if last_played:
                dates_found += 1
            data[title.lower()] = last_played

        print(f"  [reader] Read {len(data)} songs, {dates_found} with Last Played dates.")
        return data

    finally:
        if restore_after and was_minimized:
            _minimize_window(window)
