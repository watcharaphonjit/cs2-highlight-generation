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
DATE_START  = None           # include files with ctime >= this date, e.g. "2024-07-20"
DATE_END    = None           # include files with ctime <= this date, e.g. "2024-07-26"
```

---

## How it works

1. **`scan()`** — finds every `.mp4` in `./source/` (recursive), filters by date if set, sorts oldest → newest
2. **`detect_kills()`** — OCR-reads the kill feed (top-right of screen) in each clip, records **every** kill timestamp
3. **`render()`** — creates one video segment per kill: `[kill_time − pre_sec → kill_time + post_sec]`, then concatenates all in order

A clip with 3 kills becomes **3 separate segments** in the output.

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

# Custom render settings
CS2Montage(player_name="YourName").run(
    pre_sec    = 2.0,   # seconds before each kill (default 2.0)
    post_sec   = 0.5,   # seconds after each kill (default 0.5)
    last_extra = 3.0,   # extra seconds at the end of the final segment (default 3.0)
    fps        = 60,    # output framerate (default 60)
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
2. List clip indices:
```bash
python -c "import json; [print(i, c['type'], c['score'], c['file'][:55]) for i,c in enumerate(json.load(open('output/clips.json')))]"
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
pip install moviepy easyocr opencv-python numpy
```

> **Note:** `detect_kills` uses EasyOCR to read the kill feed. The model loads once (~1–2 min on first run) then takes ~30–60 seconds per clip depending on kill count.
