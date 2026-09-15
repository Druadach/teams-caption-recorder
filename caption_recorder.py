"""Teams meeting live-caption recorder.

Reads the Microsoft Teams meeting window (and, when present, the separate
"Open captions in new window" pop-out) through the UI Automation
accessibility tree, and writes every caption line to a timestamped
transcript file, with speaker separators and wall-clock timestamps.

Usage:
    python caption_recorder.py [output_file]

If no output file is given, one is created under
    %USERPROFILE%\\Documents\\TeamsCaptions\\captions_<timestamp>.txt

The recorder exits automatically when every Teams meeting/captions window
has closed.
"""
import sys, os, re, time, datetime

if sys.stdout is None:                      # headless (pythonw) context
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import uiautomation as auto

POLL_INTERVAL = 0.8            # seconds between UI polls
NOISE_LINES = {
    'Untitled', 'Open in split screen',
    'Captions', 'Caption', 'Live captions', 'Meeting captions',
    '字幕', '辅助字幕',
}
SPEAKER_RE = re.compile(r'^.{0,45}\(\d{2,8}\)$')   # "Name (id)" lines


def default_output() -> str:
    outdir = os.path.join(os.path.expanduser('~'), 'Documents', 'TeamsCaptions')
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(outdir, f'captions_{ts}.txt')


def _handle(win):
    """Native window handle, or None if the control is gone."""
    try:
        return win.NativeWindowHandle
    except Exception:
        return None


def _safe_name(win):
    try:
        return win.Name or ''
    except Exception:
        return ''


# --- Teams window discovery -------------------------------------------------
# Captions are shown either inside the meeting window (docked at the bottom)
# or in a separate "Open captions in new window" pop-out (title e.g.
# "辅助字幕 | ... | Microsoft Teams"). Both are distinct top-level windows and
# GetChildren() lists the meeting window first, so enumerate *all* candidates
# and prefer dedicated caption pop-outs.
CAPTION_HINTS = ('caption', 'captions', 'subtitle', 'subtitles',
                 '字幕', '辅助字幕')
MEETING_HINTS = ('meeting', '会议')
TEAMS_MARKER = 'microsoft teams'
TEAMS_CLASS = 'TeamsWebView'


def is_caption_window(name):
    """True if *name* looks like a dedicated caption / pop-out window."""
    low = (name or '').lower()
    return any(k in low for k in CAPTION_HINTS)


def iter_teams_windows(children=None):
    """Every Teams top-level window that may host live captions, pop-outs first.

    Pass *children* (a single GetRootControl().GetChildren() snapshot) to
    avoid enumerating the desktop more than once per poll.
    """
    if children is None:
        try:
            children = auto.GetRootControl().GetChildren()
        except Exception:
            return []

    wins = []
    for w in children:
        try:
            name = w.Name or ''
            cls = w.ClassName or ''
        except Exception:
            continue
        low = name.lower()
        if not (TEAMS_MARKER in low or cls == TEAMS_CLASS):
            continue
        if is_caption_window(name) or any(k in low for k in MEETING_HINTS):
            wins.append(w)

    wins.sort(key=lambda w: 0 if is_caption_window(_safe_name(w)) else 1)
    return wins


def get_lines(win):
    """Collect all visible text lines from the captions area."""
    lines = []

    def walk(c, depth=0):
        if depth > 30:
            return
        try:
            kids = c.GetChildren()
        except Exception:
            return
        for k in kids:
            try:
                if k.ControlTypeName == 'TextControl':
                    n = (k.Name or '').strip()
                    if len(n) >= 2:
                        lines.append(n)
                else:
                    walk(k, depth + 1)
            except Exception:
                continue

    walk(win)
    return [l for l in lines if l not in NOISE_LINES]


def main():
    outfile = sys.argv[1] if len(sys.argv) > 1 else default_output()

    # Track every candidate window by native handle so title changes
    # (screen sharing, compact view, ...) do not drop a window, and so a
    # pop-out caption window appearing mid-meeting is picked up.
    tracked = {}                      # native handle -> window control
    for w in iter_teams_windows():
        h = _handle(w)
        if h is not None:
            tracked[h] = w

    if not tracked:
        print('No Teams meeting/captions window found - exiting.')
        sys.exit(1)

    f = open(outfile, 'a', encoding='utf-8')
    print(f'recording -> {outfile}', flush=True)
    for w in tracked.values():
        print(f'  window: {_safe_name(w)!r}', flush=True)
    f.write(f"\n=== session {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    f.flush()

    recorded = set()          # finalized lines already written to disk
    while True:
        try:
            # One desktop snapshot per poll, shared by liveness and discovery
            # so a window appearing mid-poll cannot be added and pruned at once.
            try:
                children = auto.GetRootControl().GetChildren()
                live = {_handle(c) for c in children}
            except Exception:
                children, live = None, None

            # Discover / refresh Teams windows (a pop-out may have appeared).
            for w in iter_teams_windows(children):
                h = _handle(w)
                if h is None:
                    continue
                if h not in tracked:
                    print(f'+ window: {_safe_name(w)!r}', flush=True)
                tracked[h] = w

            if live is not None:
                for h in list(tracked):
                    if h not in live:
                        print(f'- window: {_safe_name(tracked[h])!r}', flush=True)
                        del tracked[h]

            if not tracked:
                f.write(f"\n=== window closed {datetime.datetime.now():%H:%M:%S} ===\n")
                f.close()
                print('window closed, exiting', flush=True)
                break

            # A dedicated captions pop-out is authoritative; otherwise read
            # every tracked (meeting) window.
            cap = [w for w in tracked.values() if is_caption_window(_safe_name(w))]
            use = cap or list(tracked.values())

            # Per window, the last two lines are still being revised by live
            # ASR; everything before them is final.
            finalized = []
            for w in use:
                cur = get_lines(w)
                finalized.extend(cur[:-2] if len(cur) > 2 else [])

            for line in finalized:
                if line not in recorded:
                    recorded.add(line)
                    ts = datetime.datetime.now().strftime('%H:%M:%S')
                    if SPEAKER_RE.match(line):
                        f.write(f"\n[{ts}] --- {line} ---\n")
                    else:
                        f.write(f"[{ts}] {line}\n")
                    f.flush()
                    print(line, flush=True)
        except Exception as e:
            print('err', e, flush=True)
        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()