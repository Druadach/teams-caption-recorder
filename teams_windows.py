"""Teams window/caption detection shared by the recorder and the watchdog.

Title matching alone is not reliable:

* the "Open captions in new window" pop-out carries no caption keyword (its
  title is e.g. "... | Microsoft Teams | Pinned window"), and
* a running meeting's window title is usually just the meeting name
  (e.g. "Project Falcon | Microsoft Teams"), with no "meeting" keyword
  either.

Windows are therefore classified by their *content*: a window showing
captions exposes live-caption controls, and a window hosting a call exposes
call controls (hangup, roster, mic, ...). Titles are only a cheap fast path.
"""
import time

import uiautomation as auto

WALK_TIME_BUDGET = 15.0        # max seconds spent walking one window tree

# --- title keywords (fast path only) ---------------------------------------
CAPTION_HINTS = ('caption', 'captions', 'subtitle', 'subtitles',
                 '字幕', '辅助字幕')
POPOUT_HINTS = ('pinned window', '固定窗口')

TEAMS_MARKER = 'microsoft teams'
TEAMS_CLASS = 'TeamsWebView'

# --- content markers --------------------------------------------------------
CAPTION_AID_PREFIXES = ('captions-', 'closed-captions')
CAPTION_NAME_HINTS = ('caption', 'subtitle', '字幕')
CALL_AID_HINTS = ('hangup-button', 'call-duration', 'raisehands-button',
                  'roster-button', 'share-button', 'microphone-button',
                  'video-button', 'screensharing-control-button',
                  'callingbuttons-showmorebtn')

# UI chrome that is never caption text.
NOISE_LINES = {
    'Untitled', 'Open in split screen',
    'Captions', 'Caption', 'Live captions', 'Live Captions', 'Meeting captions',
    '字幕', '辅助字幕',
}


def handle(win):
    """Native window handle, or None if the control is gone."""
    try:
        return win.NativeWindowHandle
    except Exception:
        return None


def safe_name(win):
    try:
        return win.Name or ''
    except Exception:
        return ''


def is_caption_title(name):
    """True if *name* carries an explicit caption/subtitle keyword."""
    low = (name or '').lower()
    return any(k in low for k in CAPTION_HINTS)


def is_popout_title(name):
    """True for a popped-out Teams window (title "... | Pinned window").

    A pop-out is not *necessarily* captions (chat can be popped out too), so
    it still has to be confirmed by content; this only helps prefer the
    dedicated caption window when several windows happen to show captions.
    """
    low = (name or '').lower()
    return any(k in low for k in POPOUT_HINTS)


def is_candidate_window(w):
    """Any Teams top-level window that might host captions (title-agnostic)."""
    try:
        low = (w.Name or '').lower()
        cls = w.ClassName or ''
    except Exception:
        return False
    return TEAMS_MARKER in low or cls == TEAMS_CLASS


def iter_candidate_windows(children=None):
    """Every Teams top-level window, regardless of title.

    Pass *children* (a single GetRootControl().GetChildren() snapshot) to
    avoid enumerating the desktop more than once per poll.
    """
    if children is None:
        try:
            children = auto.GetRootControl().GetChildren()
        except Exception:
            return []
    return [w for w in children if is_candidate_window(w)]


def collect(win):
    """One tree walk: caption text + caption/call markers.

    Returns (lines, has_captions, has_call). Recognising the caption pop-out
    and the meeting window costs nothing extra, because it reuses the walk
    that gathers the text anyway.
    """
    lines = []
    has_captions = False
    has_call = False
    deadline = time.monotonic() + WALK_TIME_BUDGET

    def walk(c, depth=0):
        nonlocal has_captions, has_call
        if depth > 30 or time.monotonic() > deadline:
            return
        try:
            kids = c.GetChildren()
        except Exception:
            return
        for k in kids:
            try:
                aid = (k.AutomationId or '').lower()
                if not has_captions:
                    if aid.startswith(CAPTION_AID_PREFIXES):
                        has_captions = True
                    else:
                        nm = (k.Name or '').strip().lower()
                        if any(h in nm for h in CAPTION_NAME_HINTS):
                            has_captions = True
                if not has_call and any(h in aid for h in CALL_AID_HINTS):
                    has_call = True
                if k.ControlTypeName == 'TextControl':
                    n = (k.Name or '').strip()
                    if len(n) >= 2:
                        lines.append(n)
                else:
                    walk(k, depth + 1)
            except Exception:
                continue

    walk(win)
    return [l for l in lines if l not in NOISE_LINES], has_captions, has_call


def find_active(children=None, probe=None):
    """Something worth recording, or None. Returns (window, reason).

    *reason* is one of:
      'captions' - a window is showing live captions, or is titled as a caption
                   window (such a pop-out only exists while captions are on),
      'meeting'  - a window hosts a call, even if captions are not on yet.

    A mere "meeting" *title* is deliberately not enough: before the call
    controls exist there is nothing to record, and returning it would make a
    watchdog launch a recorder that immediately finds nothing and exits, over
    and over. Requiring content confirmation keeps the two in agreement.

    Titles are checked first and cost nothing. Only if no title matches is the
    expensive content walk used, and then only for windows for which
    *probe(handle)* returns True - so a caller can throttle content probes.
    """
    caps_fallback = None
    for w in iter_candidate_windows(children):
        name = safe_name(w)
        if is_caption_title(name):
            return w, 'captions'
        if probe is not None and not probe(handle(w)):
            continue
        _, has_caps, has_call = collect(w)
        if has_caps:
            # A popped-out caption window is the dedicated source; a meeting
            # window that also exposes captions is only a fallback, so keep
            # looking for a better one.
            if is_popout_title(name):
                return w, 'captions'
            if caps_fallback is None:
                caps_fallback = (w, 'captions')
        elif has_call and caps_fallback is None:
            caps_fallback = (w, 'meeting')
    return caps_fallback
