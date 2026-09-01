"""Teams caption recorder watchdog.

Starts with Windows (registered via HKCU Run). Every few seconds it
checks whether a Teams meeting/captions window exists; when one appears
it launches caption_recorder.py on a fresh timestamped transcript file.
When the meeting ends, the recorder exits on its own and the watchdog
goes back to standby, ready for the next meeting.
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


def note(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        os.makedirs(OUTDIR, exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def find_window():
    import uiautomation as auto
    try:
        for w in auto.GetRootControl().GetChildren():
            t = w.Name or ''
            if 'Microsoft Teams' in t and any(k in t for k in ('Captions', 'Meeting', '会议', '字幕')):
                return t
    except Exception:
        pass
    return None


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
            note(f'meeting detected ({title[:60]}...) -> '
                 f'recording to {os.path.basename(outfile)} [pid {proc.pid}]')


        time.sleep(POLL_INTERVAL)


main()
