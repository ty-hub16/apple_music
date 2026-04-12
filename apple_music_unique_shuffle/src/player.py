"""
player.py - Apple Music now-playing reader and skip command
Reads the currently playing track directly from the Apple Music UI transport bar,
and sends a skip via Win32 media key.
"""

import ctypes
import uiautomation as auto


def _find_window():
    for w in auto.GetRootControl().GetChildren():
        if "music" in (w.Name or "").lower():
            return w
    return None


def get_current_track() -> tuple[str, str] | None:
    """
    Read the currently playing title and artist from the Apple Music transport bar.
    Returns (title, artist) or None if nothing is playing / not found.
    """
    window = _find_window()
    if not window:
        return None

    def search(element, depth=0):
        if depth > 10:
            return None
        try:
            # The now-playing GroupControl contains two PaneControls: title and artist·album
            if element.ControlTypeName == "GroupControl":
                children = element.GetChildren()
                panes = [c for c in children if c.ControlTypeName == "PaneControl" and c.Name]
                if len(panes) >= 2:
                    title = panes[0].Name.strip()
                    # artist pane is "Artist · Album" — take just the artist part
                    artist_album = panes[1].Name.strip()
                    artist = artist_album.split("\u00b7")[0].strip()
                    if title:
                        return (title, artist)
            for child in element.GetChildren():
                result = search(child, depth + 1)
                if result is not None:
                    return result
        except Exception:
            pass
        return None

    return search(window)


def skip_track() -> None:
    """Send a Next Track media key press via Win32."""
    VK_MEDIA_NEXT_TRACK = 0xB0
    KEYEVENTF_KEYUP = 0x0002
    ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, KEYEVENTF_KEYUP, 0)
