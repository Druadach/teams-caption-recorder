"""Teams caption recorder watchdog.

Starts with Windows (registered via HKCU Run). Every few seconds it
checks whether a Teams meeting/captions window exists; when one appears
it launches caption_recorder.py on a fresh timestamped transcript file.
When the meeting ends, the recorder exits on its own and the watchdog
goes back to standby, ready for the next meeting.

Detection is content-based (see teams_windows.py) because neither the
"Open captions in new window" pop-out nor a plain meeting window reliably
carries a caption/meeting keyword in its title.
"""
import os, sys, time, subprocess, datetime

if sys.stdout is None:                      # headless (pythonw) context
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOOLS  = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(os.path.expanduser('~'), 'Documents', 'TeamsCaptions')
RECORDER = os.path.join(TOOLS, 'caption_recorder.py')
LOG    = os.path.join(OUTDIR, 'watchdog_log.txt')

POLL_INTERVAL = 3
PROBE_INTERVAL = 12            # seconds between content probes of a window

sys.path.insert(0, TOOLS)

_last_probe = {}               # native handle -> last content probe time


def note(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        os.makedirs(OUTDIR, exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def _probe_due(handle):
    """Rate-limit content probes so the watchdog stays cheap.

    Windows handles are reused, so a stale entry could throttle a brand-new
    window; an unseen handle is therefore probed immediately rather than
    treated as recently checked.
    """
    now = time.monotonic()
    if now - _last_probe.get(handle, 0.0) < PROBE_INTERVAL:
        return False
    _last_probe[handle] = now
    return True


def _prune_probes(stale_handles):
    for h in stale_handles:
        _last_probe.pop(h, None)


def find_window():
    """Description of a window worth recording, or None.

    Captions and calls are detected by content (titles are only a hint), so
    the caption pop-out and meetings without a "meeting" keyword are found.
    """
    import teams_windows as tw
    try:
        children = tw.auto.GetRootControl().GetChildren()
        active = tw.find_active(children=children, probe=_probe_due)
    except Exception:
        return None
    if not active:
        # Forget closed windows so the probe cache cannot grow forever.
        live = {tw.handle(w) for w in children} if children else set()
        _prune_probes([h for h in _last_probe if h not in live])
        return None
    win, reason = active
    name = tw.safe_name(win) or 'Teams'
    return f'{name} [{reason}]'


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    note('watchdog started')
    proc = None
    while True:
        title = None
        try:
            title = find_window()
        except Exception as e:
            note(f'probe error: {e}')

        if proc is not None and proc.poll() is not None:
            note('recorder exited unexpectedly, restarting'
                 if title else 'meeting ended, recorder exited')
            proc = None

        if title and proc is None:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            outfile = os.path.join(OUTDIR, f'captions_{ts}.txt')
            kwargs = {}
            if getattr(sys, 'frozen', False) is False:
                kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            proc = subprocess.Popen(
                [sys.executable, RECORDER, outfile],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
            note(f'meeting detected ({title[:60]}) -> '
                 f'recording to {os.path.basename(outfile)} [pid {proc.pid}]')

        time.sleep(POLL_INTERVAL)


main()
