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

Window detection (see teams_windows.py): the caption pop-out and the plain
meeting window both lack reliable title keywords, so windows are classified
by content - live-caption controls vs. call controls. Caption text is read
from whichever window currently shows captions, so docking / popping out
mid-meeting is followed seamlessly.
"""
import sys, os, re, time, datetime

if sys.stdout is None:                      # headless (pythonw) context
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uiautomation as auto
import teams_windows as tw

POLL_INTERVAL = 0.8            # seconds between UI polls
REPROBE_INTERVAL = 15.0        # seconds between probes of caption-less windows
EMPTY_POLLS_BEFORE_EXIT = 3    # tolerate a transient empty window list

SPEAKER_RE = re.compile(r'^.{0,45}\(\d{2,8}\)$')   # "Name (id)" lines


def default_output() -> str:
    outdir = os.path.join(os.path.expanduser('~'), 'Documents', 'TeamsCaptions')
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(outdir, f'captions_{ts}.txt')


def main():
    outfile = sys.argv[1] if len(sys.argv) > 1 else default_output()

    # Windows worth following, keyed by native handle so title changes
    # (screen sharing, compact view, ...) never drop one. A window stays
    # relevant while it hosts a call or shows captions; idle Teams windows
    # are re-probed now and then in case a meeting starts in them.
    #
    # Per-window state: 'caps' is the last observed caption state (None until
    # the window has been read once), and 'checked' is when it was last walked
    # in full. Windows that show captions are read every poll; the others are
    # only walked periodically, because their jobs are to prove the meeting is
    # still alive and to notice captions appearing in them.
    tracked = {}                  # native handle -> dict(win, caps, checked)
    idle = {}                     # native handle -> last probe time

    candidates = {}
    for w in tw.iter_candidate_windows():
        h = tw.handle(w)
        if h is not None:
            candidates[h] = w

    if not candidates:
        print('No Teams meeting/captions window found - exiting.')
        sys.exit(1)

    f = open(outfile, 'a', encoding='utf-8')
    print(f'recording -> {outfile}', flush=True)
    f.write(f"\n=== session {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    f.flush()

    recorded = set()          # finalized lines already written to disk
    empty_polls = 0
    had_captions = False      # whether any window showed captions last poll
    while True:
        try:
            # One desktop snapshot per poll for discovery and liveness.
            try:
                children = auto.GetRootControl().GetChildren()
                candidates = {}
                for w in tw.iter_candidate_windows(children):
                    h = tw.handle(w)
                    if h is not None:
                        candidates[h] = w
            except Exception:
                children = None

            now = time.monotonic()

            # Discover / classify Teams windows. A caption keyword in a title
            # is proof; otherwise the window's content decides - which is how
            # the caption pop-out is caught despite bearing no such keyword,
            # and how a meeting window survives a title with no "meeting"
            # keyword either. Windows already known to be inert are re-probed
            # only every REPROBE_INTERVAL seconds.
            if children is not None:
                for h, w in candidates.items():
                    if h in tracked:
                        continue
                    name = tw.safe_name(w)
                    if tw.is_caption_title(name):
                        print(f'+ window (captions): {name!r}', flush=True)
                        tracked[h] = {'win': w, 'caps': True, 'checked': now}
                        idle.pop(h, None)
                        continue
                    if h in idle and now - idle[h] < REPROBE_INTERVAL:
                        continue
                    _, has_caps, has_call = tw.collect(w)
                    if has_caps or has_call:
                        print(f'+ window ({name!r}): captions={has_caps} call={has_call}',
                              flush=True)
                        tracked[h] = {'win': w, 'caps': has_caps, 'checked': now}
                        idle.pop(h, None)
                    else:
                        idle[h] = now

                # Prune windows that closed.
                for h in list(tracked):
                    if h not in candidates:
                        print(f'- window: {tw.safe_name(tracked[h]["win"])!r}', flush=True)
                        del tracked[h]
                for h in list(idle):
                    if h not in candidates:
                        del idle[h]

            if not tracked:
                empty_polls += 1
                if empty_polls >= EMPTY_POLLS_BEFORE_EXIT:
                    f.write(f"\n=== window closed {datetime.datetime.now():%H:%M:%S} ===\n")
                    f.close()
                    print('window closed, exiting', flush=True)
                    break
                time.sleep(POLL_INTERVAL)
                continue
            empty_polls = 0

            # Read caption windows. Live ASR still revises a window's last two
            # lines, so everything before them is final. A window known not to
            # show captions is only re-walked periodically - its jobs are to
            # prove the meeting is still alive and to notice captions appearing
            # in it. A window that shows neither captions nor a call is dropped,
            # which lets the recorder exit when the meeting ends.
            #
            # When captions were flowing and suddenly stop, every window is
            # re-probed at once: that gap means captions moved (e.g. the
            # pop-out was closed and they re-docked), and waiting out
            # REPROBE_INTERVAL would lose that speech.
            finalized = []
            reads = []

            def read_win(h, st):
                cur, has_caps, has_call = tw.collect(st['win'])
                st['caps'] = has_caps
                st['checked'] = time.monotonic()
                if has_caps:
                    reads.append((tw.is_caption_title(tw.safe_name(st['win']))
                                  or tw.is_popout_title(tw.safe_name(st['win'])), cur))
                elif not has_call:
                    del tracked[h]
                    idle[h] = time.monotonic()

            # Phase 1: the windows that were showing captions.
            for h, st in list(tracked.items()):
                if st['caps'] is not False:
                    read_win(h, st)

            # Captions were flowing but nothing reports them any more: they
            # just moved, so every remaining window is re-probed at once rather
            # than waiting out REPROBE_INTERVAL (which would lose that speech).
            lost = had_captions and not reads

            # Phase 2: windows last seen without captions.
            for h, st in list(tracked.items()):
                if st['caps'] is not False:
                    continue
                if not lost and now - st['checked'] < REPROBE_INTERVAL:
                    continue
                read_win(h, st)

            had_captions = bool(reads)

            # A dedicated caption pop-out is authoritative; if one is showing
            # captions, ignore any other window that happens to expose some,
            # so parallel ASR cannot write the same speech twice.
            if any(is_popout for is_popout, _ in reads):
                reads = [r for r in reads if r[0]]
            for _, cur in reads:
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
