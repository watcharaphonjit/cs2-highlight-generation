# CS2 Highlight Montage

Automatically generate a highlight reel from CS2 gameplay clips.

---

## Quick Start

### 1. Add your clips

Drop your `.mp4` files into **`./source/`**

### 2. Set your player name

Open `run.py` and change:

```python
PLAYER_NAME = "ongaj"   # ← your name as it appears in the CS2 kill feed
```

### 3. Run

```bash
python run.py
```

Output: **`./output/final_highlight.mp4`**

---

## Project Structure

```
cs2-highlight-generation/
├── source/              ← drop .mp4 clips here
├── music/               ← drop background music file here (mp3/wav)
├── output/              ← rendered video goes here
│   ├── final_highlight.mp4
│   └── clips.json       ← OCR data (auto-generated, skips OCR on next run)
├── run.py               ← entry point
├── cs2montage.py        ← core library
├── render.py            ← advanced: custom clip order
└── README.md
```

---

## Configuration (`run.py`)

```python
PLAYER_NAME = "ongaj"        # name in the kill feed (case-insensitive)
DATE_START  = None           # only include files with mtime >= this date, e.g. "2024-07-20"
DATE_END    = None           # only include files with mtime <= this date, e.g. "2024-07-26"

MUSIC_FILE  = None           # path to music file, e.g. r".\music\song.mp3"
MUSIC_VOL   = 0.5            # music loudness 0.0–1.0
GAME_VOL    = 0.8            # game audio loudness 0.0–1.0
BEAT_SYNC   = False          # snap every segment length to a beat boundary (requires MUSIC_FILE)
```

### Background music

1. Drop an `.mp3` or `.wav` into `./music/`
2. Set `MUSIC_FILE = r".\music\your_song.mp3"` in `run.py`
3. Music auto-loops if shorter than the video and fades out at the end
4. Game audio is kept and mixed with the music at the configured volumes

### Beat sync

Set `BEAT_SYNC = True` (requires `MUSIC_FILE`) to snap every segment to an exact beat boundary.

- BPM is auto-detected from the music file
- Each segment's length is rounded up to the nearest multiple of the beat interval
- Every cut between segments lands exactly on a beat
- Kill moment stays visible; any extra time is added as post-kill footage

> **Note:** This aligns *cut points* to beats. For perfect gunshot-on-drumkick sync, fine-tune in CapCut's Beat Sync feature afterwards.

---

## How it works

1. **`scan()`** — finds every `.mp4` in `./source/` (recursive), filters by modified date if set, sorts oldest → newest by modified date
2. **`detect_kills()`** — OCR-reads the kill feed (top-right of screen) in each clip, records every kill timestamp
3. **`render()`** — groups kills that are less than `pre_sec + post_sec` apart into one segment, then renders each group as `[first_kill − pre_sec → last_kill + post_sec]`

**Example** with pre/post = 3s (merge threshold = 6s):

| Kills in clip | Gap | Result |
|---------------|-----|--------|
| kill@3s, kill@5s | 2s < 6s | 1 segment: [0s → 8s] |
| kill@3s, kill@10s | 7s > 6s | 2 segments: [0s→6s] and [7s→13s] |

No overlap is possible — two separate segments always start at least `pre_sec + post_sec` apart.

---

## Library Usage (for developers)

```python
from cs2montage import CS2Montage

# One-liner: scan + OCR + render
CS2Montage(player_name="YourName").run()

# With date filter
CS2Montage(
    player_name = "YourName",
    date_start  = "2024-07-20",
    date_end    = "2024-07-26",
).run()

# All render options
CS2Montage(player_name="YourName").run(
    pre_sec      = 3.0,             # seconds before first kill in a group (default 3.0)
    post_sec     = 3.0,             # seconds after last kill in a group (default 3.0)
    last_extra   = 3.0,             # extra seconds added to the final segment (default 3.0)
    fps          = 60,              # output framerate (default 60)
    music_path   = r".\music\song.mp3",  # background music (default None)
    music_volume = 0.5,             # music loudness 0.0–1.0 (default 0.5)
    game_volume  = 0.8,             # game audio loudness 0.0–1.0 (default 0.8)
    music_fade   = 2.0,             # music fade-out duration in seconds (default 2.0)
    beat_sync    = False,           # snap segment lengths to beat grid (default False)
)
```

### Skip OCR on subsequent runs (saves ~10–15 min)

```python
m = CS2Montage(player_name="YourName")

# First run: scan + OCR + save
clips = m.scan()
clips = m.detect_kills(clips)
m.save(clips)           # saved to output/clips.json

# Next run: load and render directly
clips = m.load()
m.render(clips)
```

---

## Advanced: Custom Clip Order (`render.py`)

Use this when you want manual control over which clips appear and in what order.

**Steps:**

1. Run `run.py` first (or `m.save(clips)`) to generate `output/clips.json`
2. List clips with their indices:
```bash
python -c "import json; [print(i, c['duration_total'], c['file'][:60]) for i,c in enumerate(json.load(open('output/clips.json')))]"
```
3. Edit `TIMELINE` in `render.py`:
```python
TIMELINE = [
    # (index, label,    pre_override, post_override)
    (4,  "clip_01",  None, None),   # standard clip
    (0,  "finale",   5.0,  3.0),    # finale: 5s lead-in, 3s extra ending
]
```
4. Run:
```bash
python render.py
```

---

## Requirements

```bash
pip install moviepy easyocr opencv-python numpy librosa
```

| Package | Used for |
|---------|----------|
| `moviepy` | video trimming, concatenation, audio mixing |
| `easyocr` | reading the CS2 kill feed (OCR) |
| `opencv-python` | frame extraction for OCR |
| `numpy` | array operations |
| `librosa` | BPM detection for beat sync (only needed if `BEAT_SYNC = True`) |

> **Note:** `detect_kills` uses EasyOCR — model loads once (~1–2 min on first run) then takes ~30–60 seconds per clip.
