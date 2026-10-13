"""Integration test: the recorder must keep capturing across the transition
that broke live capture - captions moving from the docked meeting window into
the "Open captions in new window" pop-out.

The window tree is faked and time is compressed, so the recorder's own loop
(windowing, handoff between windows, de-duplication, exit) runs for real.
"""
import importlib.util
import io
import os
import sys
import tempfile
import threading
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)

import teams_windows as tw


def load_recorder():
    spec = importlib.util.spec_from_file_location(
        'caption_recorder', os.path.join(TOOLS, 'caption_recorder.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeControl:
    def __init__(self, name='', ctrl_type='PaneControl', aid='', children=()):
        self.Name = name
        self.ControlTypeName = ctrl_type
        self.AutomationId = aid
        self._children = list(children)

    def GetChildren(self):
        return self._children


class FakeWindow(FakeControl):
    def __init__(self, title, children=(), handle=1):
        super().__init__(name=title, ctrl_type='WindowControl', children=children)
        self.ClassName = 'TeamsWebView'
        self.NativeWindowHandle = handle


def caption_group(lines):
    kids = [FakeControl('Live Captions', 'TextControl')]
    kids.append(FakeControl('', aid='captions-settings-menu-trigger-button-non-overflow'))
    for ln in lines:
        kids.append(FakeControl(ln, 'TextControl'))
    return FakeControl('Live Captions', 'GroupControl', children=kids)


def call_bar():
    return [FakeControl(aid='hangup-button'), FakeControl(aid='roster-button')]


MEETING_TITLE = 'Project Falcon | Microsoft Teams'
POPOUT_TITLE = MEETING_TITLE + ' | Pinned window'


def run_recorder(script, outfile, poll=0.01, reprobe=0.05, max_seconds=6.0):
    """Run caption_recorder.main() against a scripted window tree.

    *script* is a list of (duration_seconds, [FakeWindow, ...]). Each state is
    served until its duration elapses. Returns the recorder's stdout.
    """
    rec = load_recorder()
    rec.POLL_INTERVAL = poll
    rec.REPROBE_INTERVAL = reprobe
    rec.EMPTY_POLLS_BEFORE_EXIT = 2

    state = {'windows': []}
    timeline = []
    t = 0.0
    for duration, wins in script:
        timeline.append((t, wins))
        t += duration

    started = time.monotonic()

    def current_windows():
        elapsed = time.monotonic() - started
        wins = timeline[0][1]
        for at, ws in timeline:
            if elapsed >= at:
                wins = ws
        return wins

    class FakeRoot:
        def GetChildren(self):
            return current_windows()

    # Patch only the UIA entry point. The real teams_windows.iter_candidate_windows
    # and collect() then run against the fake controls, so the test exercises
    # the actual detection logic (that is where the bug lived).
    rec.auto.GetRootControl = lambda: FakeRoot()

    # Also make the initial enumeration see the first state.
    buf = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, buf
    try:
        rec.sys.argv = ['caption_recorder.py', outfile]
        th = threading.Thread(target=rec.main, daemon=True)
        th.start()
        th.join(max_seconds)
    finally:
        sys.stdout = real_stdout
    return buf.getvalue()


def test_capture_survives_popout_transition():
    """The bug: transcript stopped when captions were popped out."""
    meeting_then = FakeWindow(
        MEETING_TITLE, children=call_bar() + [caption_group(
            ['speaker one', 'alpha line', 'beta line', 'gamma line'])], handle=1)
    # After the pop-out, the meeting window keeps only its call controls.
    meeting_after = FakeWindow(
        MEETING_TITLE, children=call_bar() + [FakeControl('Untitled', 'TextControl')],
        handle=1)
    popout = FakeWindow(
        POPOUT_TITLE, children=[caption_group(
            ['speaker one', 'alpha line', 'beta line', 'gamma line',
             'delta line', 'epsilon line', 'zeta line',
             'tail one', 'tail two'])], handle=2)

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'captions.txt')
        run_recorder([(0.8, [meeting_then]),
                      (2.5, [meeting_after, popout]),
                      (1.5, [])], out)
        text = open(out, encoding='utf-8').read()

    # Captions captured while docked...
    assert 'alpha line' in text, text
    # ...and still captured after they moved to the pop-out. This is what
    # regressed: the pop-out's title has no caption keyword, so it used to be
    # ignored and the transcript silently stopped.
    assert 'delta line' in text, text
    assert 'zeta line' in text, text    # No duplicates from reading both windows at once.
    assert text.count('alpha line') == 1, text


def test_stops_when_windows_gone():
    meeting = FakeWindow(
        MEETING_TITLE, children=call_bar() + [caption_group(
            ['one line', 'two line', 'three line'])], handle=1)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'captions.txt')
        stdout = run_recorder([(1.0, [meeting]), (1.5, [])], out)
        text = open(out, encoding='utf-8').read()
    assert 'window closed' in text, text
    assert 'window closed' in stdout, stdout


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print(f'ok   {name}')
            except AssertionError as e:
                failed += 1
                print(f'FAIL {name}: {e}')
            except Exception as e:
                failed += 1
                print(f'ERR  {name}: {type(e).__name__}: {e}')
    print('\n' + ('all tests passed' if not failed else f'{failed} test(s) failed'))
    sys.exit(1 if failed else 0)
