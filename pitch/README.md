# Pitch: Steady Hands (5 minutes)

Slides for the final pitch of team Steady Hands, in the app's own style: its colours (`app/trainer/ui/theme.py`), its fonts (Lilita One, Varela Round) and screenshots rendered from the real app.

Open `index.html` in Chrome, press `F` for full screen. Everything is local: no network needed.

## Keys

| Key | Does |
| --- | --- |
| → ↓ PageDown Enter, click | Next slide |
| ← ↑ PageUp Backspace | Previous slide |
| Space | Next slide; on the video slide: play / pause |
| `N` | Speaker notes with the planned time and a clock |
| `T` | Restart the clock at this slide's planned time |
| `F` | Full screen |
| Home / End | First / last slide |

A clicker (PageDown / PageUp) works. The clock starts when you leave the title slide. The video plays with sound as soon as slide 4 comes up: test the sound on the presentation laptop once.

## Timing (5:00)

| Slide | Time | Content |
| --- | --- | --- |
| 1 Steady Hands | 0:00–0:15 | Title, team |
| 2 In surgery, both hands are busy | 0:15–0:40 | Steady hand, clear calls, orders with a dose |
| 3 One round | 0:40–1:20 | The game: steer, call, order, score |
| 4 Demo video | 1:20–2:10 | One sentence, then the 45 s video |
| 5 The scalpel measures two distances | 2:10–2:45 | Two distance sensors instead of tilt, freeze key |
| 6 Two speech paths | 2:45–3:25 | The models on the board: Vosk, Whistle, Needle, Piper |
| 7 A keyword can't read a dose | 3:25–3:50 | Dose card: too little, right, too much, no number |
| 8 Light enough for the UNO Q | 3:50–4:25 | RAM, model size, latency, accuracy |
| 9 What's next | 4:25–4:40 | Next steps, thanks |

That leaves 20 s of buffer. The speaker notes (`N`) hold a script for each slide, at about 150 words a minute.

## Video

`media/demo.mp4` is the first 45 s of the phone recording `IMG_4590.mp4`, the full frame as filmed (16:9, no crop, no zoom), scaled to 1920×1080, H.264 with sound. `media/demo-poster.jpg` is its frame at 0:21; it stands in for the video in the PDF and before the video starts.

```sh
python make_video.py ~/Downloads/IMG_4590.mp4   # needs ffmpeg
```

## PowerPoint

`steady-hands-pitch.pptx` is the same deck for PowerPoint, with the video embedded and set to start by itself on slide 4. The speaker notes are in PowerPoint's notes. It is not in the repository (about 42 MB): download it from the Releases on GitHub, or build it:

```sh
pip install python-pptx lxml
python make_pptx.py
```

Each slide is a picture rendered from `index.html` by Chrome, so the text cannot be edited in PowerPoint: change `index.html` and build again. If the video does not start by itself, click it, or set Playback → Start: Automatically.

## PDF

A PDF backup (`steady-hands-pitch.pdf`, with the poster frame on the video slide) for uploads:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer \
  --print-to-pdf=steady-hands-pitch.pdf "file://$PWD/index.html"
```

## Pictures

The screenshots in `media/` come from `make_media.py`, which runs the real app with a dummy video driver. Run it again if the UI changes:

```sh
cd app && .venv/bin/python ../pitch/make_media.py
```

`menu.png` and `result.png` are spares, for example if the video fails. The drawing on slide 5 is inline SVG in `index.html`.

## Numbers

Every number on the slides is measured: [docs/measurements.md](../docs/measurements.md) and [docs/needle-integration.md](../docs/needle-integration.md). If a number changes there, change slides 6 and 8. The 127 MB are the three model files on disk (Vosk small 71 MB unpacked, Whistle 17 MB, Needle 12L 39 MB).

Fonts: SIL Open Font License 1.1, licences in `fonts/`.
