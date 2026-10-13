"""Tests for teams_windows detection and the recorder's window-tracking logic.

Uses fake window controls so the transition that broke live capture -
captions moving from the docked meeting window into the "Open captions in
new window" pop-out - can be replayed without a real meeting.

Run: python test_caption_tracking.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import teams_windows as tw


class FakeControl:
    """Minimal stand-in for a UIA control."""

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


def caption_group(n=5):
    """A subtree resembling the live-caption pane with *n* lines."""
    kids = [FakeControl('Live Captions', 'TextControl')]
    kids.append(FakeControl('', aid='captions-settings-menu-trigger-button-non-overflow'))
    for i in range(n):
        kids.append(FakeControl(f'line {i}', 'TextControl'))
    return FakeControl('Live Captions', 'GroupControl', children=kids)


def call_bar():
    return [
        FakeControl(aid='hangup-button'),
        FakeControl(aid='roster-button'),
        FakeControl(aid='microphone-button'),
    ]


# --- title helpers ----------------------------------------------------------

def test_caption_title():
    assert tw.is_caption_title('辅助字幕 | Foo | Microsoft Teams')
    assert tw.is_caption_title('Captions | Bar | Microsoft Teams')
    assert not tw.is_caption_title(
        'Project Falcon | Microsoft Teams')
    # The pop-out that broke capture carries no caption keyword.
    assert not tw.is_caption_title(
        'Project Falcon '
        '| Microsoft Teams | Pinned window')


def test_popout_title():
    assert tw.is_popout_title('Foo | Microsoft Teams | Pinned window')
    assert not tw.is_popout_title('Foo | Microsoft Teams')


# --- content classification -------------------------------------------------

def test_docked_captions_detected_by_content():
    """Meeting window with captions docked and no caption keyword in title."""
    win = FakeWindow('Project Falcon '
                     '| Microsoft Teams',
                     children=call_bar() + [caption_group(5)])
    _, has_caps, has_call = tw.collect(win)
    assert has_caps and has_call, (has_caps, has_call)


def test_popout_detected_by_content():
    """The pop-out: no caption keyword in title, captures only."""
    win = FakeWindow('Project Falcon '
                     '| Microsoft Teams | Pinned window',
                     children=[caption_group(5)])
    _, has_caps, has_call = tw.collect(win)
    assert has_caps and not has_call, (has_caps, has_call)


def test_popout_without_captions_is_not_a_source():
    win = FakeWindow('Foo | Microsoft Teams | Pinned window',
                     children=[FakeControl('Untitled', 'TextControl')])
    _, has_caps, has_call = tw.collect(win)
    assert not has_caps and not has_call


def test_plain_teams_window_ignored():
    win = FakeWindow('Microsoft Teams', children=[FakeControl('Chat', 'TextControl')])
    _, has_caps, has_call = tw.collect(win)
    assert not has_caps and not has_call


# --- the transition that broke capture --------------------------------------

def test_caption_source_follows_popout():
    """Captions move from the meeting window into the pop-out.

    Before the pop-out exists the meeting window is the caption source; after
    it exists, the pop-out is - and it is found by content, not title.
    """
    meeting_with_caps = FakeWindow(
        'Project Falcon | Microsoft Teams',
        children=call_bar() + [caption_group(5)], handle=1)
    popout = FakeWindow(
        'Project Falcon | Microsoft Teams | Pinned window',
        children=[caption_group(5)], handle=2)
    # Once captions are popped out, the meeting window keeps only its call bar.
    meeting_without_caps = FakeWindow(
        'Project Falcon | Microsoft Teams',
        children=call_bar() + [FakeControl('Untitled', 'TextControl')], handle=1)

    during = [meeting_with_caps]
    after = [meeting_without_caps, popout]

    win, reason = tw.find_active(children=during)
    assert win is meeting_with_caps and reason == 'captions', (reason,)

    win, reason = tw.find_active(children=after)
    assert win is popout and reason == 'captions', \
        f'should follow captions into pop-out, got {reason}'


def test_popout_preferred_over_meeting_captions():
    """If both windows expose captions, the pop-out is the chosen source."""
    meeting = FakeWindow('Project Falcon | Microsoft Teams',
                         children=call_bar() + [caption_group(5)], handle=1)
    popout = FakeWindow('Project Falcon | Microsoft Teams | Pinned window',
                        children=[caption_group(5)], handle=2)
    win, reason = tw.find_active(children=[meeting, popout])
    assert win is popout and reason == 'captions', (reason,)


def test_no_source_when_meeting_gone():
    assert tw.find_active(children=[]) is None


def test_meeting_without_captions_yet_still_detected():
    win = FakeWindow('Join | Microsoft Teams', children=call_bar(), handle=1)
    result = tw.find_active(children=[win])
    assert result is not None and result[0] is win and result[1] == 'meeting'


def test_join_screen_title_alone_is_not_enough():
    """A "Meeting join" title before any call controls must yield nothing.

    Returning it would make the watchdog launch a recorder that immediately
    finds nothing and exits, repeatedly.
    """
    win = FakeWindow('Meeting join | Project Falcon | Microsoft Teams',
                     children=[FakeControl('Join now', 'ButtonControl')], handle=1)
    assert tw.find_active(children=[win]) is None


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
