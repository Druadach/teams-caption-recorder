# Teams Caption Recorder

> 🌐 [中文说明](README.zh-CN.md)

Automatically records **Microsoft Teams meeting live captions** to timestamped
text transcripts — no recording permission or official transcription feature
required. Runs silently in the background and starts/stops by itself as
meetings come and go.

```
[17:00:54] --- Alice Chen ---
[17:00:54] But why?
[17:00:54] Do you know why I don't want to have a same situation, right?
[17:00:54] Because Azon have another type of palette for Yandex, we need individual palettes.
...
[17:01:10] --- Bob Wilson ---
[17:01:10] I don't understand what a problem really.
```

## How it works

Teams' new client renders captions with its native media engine, so caption
text never touches the DOM, disk, or IndexedDB. However, it **is** exposed
through the Windows UI Automation accessibility tree (the same interface
screen readers use). This tool simply polls that tree and journals every line
it sees.

A tiny watchdog process is registered to start at login:

```
logon ──> watchdog (idle, ~0 CPU)
             │  finds a window showing captions or hosting a call
             ├──> launches recorder -> Documents/TeamsCaptions/captions_<ts>.txt
             └──< window closes: recorder exits, watchdog returns to standby
```

Caption text is read from whichever Teams top-level window currently shows it:
the meeting window (captions docked at the bottom) or the separate **Open
captions in new window** pop-out. Both are tracked by window handle, so
switching between the two modes never interrupts the transcript.

Which window is which is decided by **content, not title**. Titles are
unreliable: the pop-out carries no caption keyword (its title is just
`… | Microsoft Teams | Pinned window`), and a running meeting's title is
usually only the meeting name. So a window is treated as a caption source
when it exposes live-caption controls, and as a live meeting when it exposes
call controls (hangup, roster, mic, …). A title keyword, when present, is
just a cheap fast path.

## Requirements

- Windows 10 / 11
- New Teams client (the WebView2-based one)
- Python 3.9+ on PATH (`python` / `pythonw`)
- Live captions must be turned on in the meeting (*More actions > Record and
  transcribe > Turn on live captions*)

## Install

```powershell
git clone https://github.com/Druadach/teams-caption-recorder.git
cd teams-caption-recorder
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer pip-installs `uiautomation`, registers the watchdog under the
`HKCU...\Run` registry key, and starts it immediately.

That's it — join your next meeting with captions on and transcripts will
appear in `Documents\TeamsCaptions\`.

### Manual run (no install)

```powershell
pip install uiautomation
python caption_recorder.py            # record right now, auto output path
python caption_watchdog.py            # or run the auto-start loop
```

### Tests

```powershell
python test_caption_tracking.py       # window/caption classification
python test_recorder_loop.py          # recorder loop across docked -> pop-out
```

Both are offline: they drive the real logic against fake window trees, so no
meeting (and no Teams) is needed.

## Output format

One file per meeting session at `%USERPROFILE%\Documents\TeamsCaptions`:

```
=== session 2026-08-25 17:00:54 ===

[17:00:54] --- Alice Chen ---
[17:00:54] But why?
...
[17:01:02] --- Bob Wilson ---
[17:01:02] I don't understand what a problem really.
```

Lines ending with `(digits)` are speaker separators; everything below a
separator belongs to that speaker until the next one. The last two caption
lines visible on screen are still being revised by live ASR, so they are only
written once finalized.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Removes the autostart entry and stops any running watchdog/recorder.
Transcripts are left untouched.

## Limitations

- Only captions **shown in the captions pane** are captured — if captions are
  off, or the Teams window is minimized to tray for a long stretch, that part
  of the conversation is lost.
- Recording starts when captions turn on; earlier speech is not retroactively
  available.
- Speaker names/timestamps reflect the captions pane, not an official
  transcript. For legally meaningful minutes, prefer the built-in
  *Transcribe* feature, which produces downloadable `.docx/.vtt` files.

## Privacy notice

This tool reads exactly the text you can already see on your own screen during
a meeting. You are responsible for complying with your organization's policies
and applicable law regarding meeting recording/notification.

## License

[MIT](LICENSE)
