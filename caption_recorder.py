"""Teams meeting live-caption recorder.

Reads the Microsoft Teams meeting window through the UI Automation
accessibility tree and writes every caption line to a timestamped
transcript file, with speaker separators and wall-clock timestamps.

Usage:
    python caption_recorder.py [output_file]

If no output file is given, one is created under
    %USERPROFILE%\\Documents\\TeamsCaptions\\captions_<timestamp>.txt

The recorder exits automatically when the meeting/captions window closes.
"""
import sys, os, re, time, datetime

if sys.stdout is None:                      # headless (pythonw) context
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import uiautomation as auto

POLL_INTERVAL = 0.8            # seconds between UI polls
NOISE_LINES = {'Untitled', 'Open in split screen'}
SPEAKER_RE = re.compile(r'^.{0,45}\(\d{2,8}\)$')   # "Name (id)" lines


def default_output() -> str:
    outdir = os.path.join(os.path.expanduser('~'), 'Documents', 'TeamsCaptions')
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(outdir, f'captions_{ts}.txt')


def find_window():
    """Return the Teams meeting/captions top-level window, or None."""
    for w in auto.GetRootControl().GetChildren():
        t = w.Name or ''
        if 'Microsoft Teams' in t and any(k in t for k in ('Captions', 'Meeting', '会议', '字幕')):
            return w
    return None


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
    f = open(outfile, 'a', encoding='utf-8')

    win = find_window()
    if not win:
        print('No Teams meeting/captions window found - exiting.')
        sys.exit(1)

    print(f'recording -> {outfile}', flush=True)
    f.write(f"\n=== session {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    f.flush()

    recorded = set()          # finalized lines already written to disk
    while True:
        try:
            try:
                win.Name                     # window still alive? (title may
            except Exception:                # change mid-meeting, so we keep
                win = find_window()          # following it instead of re-matching)
                if win is None:
                    f.write(f"\n=== window closed {datetime.datetime.now():%H:%M:%S} ===\n")
                    f.close()
                    print('window closed, exiting', flush=True)
                    break

            cur = get_lines(win)
            # The last two lines are still being revised by live ASR;
            # everything before them is final.
            finalized = cur[:-2] if len(cur) > 2 else []
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


main()
