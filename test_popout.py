"""Regression test for the pop-out caption window fix.

Simulates a meeting where captions start docked in the meeting window and
then the user clicks "Open captions in new window": a second top-level
window (title with 字幕/Captions) appears while the meeting window stays
open but becomes caption-less. The recorder must follow the pop-out.

Run:  python test_popout.py
"""
import os
import sys
import tempfile

import caption_recorder as cr


class FakeWin:
    def __init__(self, name, handle, lines):
        self.Name = name
        self.NativeWindowHandle = handle
        self.ClassName = 'TeamsWebView'
        self._lines = lines


class FakeRoot:
    """Returns a different window set on each GetChildren() call.

    The recorder takes exactly one desktop snapshot per poll (shared by
    liveness + discovery), so one call == one phase.
    """

    def __init__(self, phases):
        self.phases = phases
        self.calls = 0

    def GetChildren(self):
        idx = min(self.calls, len(self.phases) - 1)
        self.calls += 1
        return list(self.phases[idx])


def main():
    meeting = FakeWin('会议紧凑视图 | Acme | Microsoft Teams', 1001,
                      ['Alice (101)', 'Docked caption one', 'docked two', 'docked three'])
    popout = FakeWin('辅助字幕 | Acme | Microsoft Teams', 2002,
                     ['Bob (202)', 'Pop-out caption one', 'pop-out two', 'pop-out three'])

    phases = [
        [meeting],            # consumed by the pre-loop seeding snapshot
        [meeting],            # captions docked in the meeting window
        [meeting, popout],    # user opened captions in a new window
        [],                   # windows closed -> recorder exits
    ]

    # --- patch the UIA boundary -----------------------------------------
    # NOTE: the same FakeRoot instance must be reused across GetRootControl()
    # calls, otherwise its poll counter resets every time and the phases
    # never advance (the recorder would loop forever on phase 0).
    root = FakeRoot(phases)
    cr.POLL_INTERVAL = 0.01
    cr.auto.GetRootControl = lambda: root
    cr.get_lines = lambda w: list(w._lines)

    out = os.path.join(tempfile.mkdtemp(prefix='caption_test_'), 'transcript.txt')
    sys.argv = ['caption_recorder.py', out]

    cr.main()

    with open(out, encoding='utf-8') as f:
        text = f.read()

    ok = True

    def check(cond, msg):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + msg)
        ok = ok and cond

    check('Docked caption one' in text, 'docked caption recorded')
    check('Pop-out caption one' in text, 'pop-out caption recorded after switching')
    check('--- Alice (101) ---' in text, 'speaker separator for docked speaker')
    check('--- Bob (202) ---' in text, 'speaker separator for pop-out speaker')
    # the last two lines of each window are still being revised -> not written
    check('docked three' not in text, 'unfinalized docked line skipped')
    check('pop-out three' not in text, 'unfinalized pop-out line skipped')
    # once the pop-out is open the caption-less meeting window must not be read
    check('docked two' not in text, 'meeting window no longer read after pop-out opens')

    print('\n--- transcript ---')
    print(text)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
