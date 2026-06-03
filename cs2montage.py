"""
cs2montage — CS2 Highlight Montage Library

Default paths (relative to this file):
    ./source/   ← drop your .mp4 clips here
    ./output/   ← final_highlight.mp4 will appear here

Quick start:
    from cs2montage import CS2Montage

    CS2Montage(player_name="YourName").run()

With date filter:
    CS2Montage(
        player_name="YourName",
        date_start="2024-07-20",
        date_end="2024-07-26",
    ).run()

Step-by-step:
    m = CS2Montage(player_name="YourName")
    clips = m.scan()               # find + score clips
    clips = m.detect_kills(clips)  # OCR kill timestamps (~10-15 min)
    m.render(clips)                # export mp4
"""

import os, sys, re, json, glob
from datetime import datetime, timezone, date as _date
from typing import Optional, Union

import numpy as np
import cv2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Default paths relative to this library file
_HERE       = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_SOURCE = os.path.join(_HERE, "source")
_DEFAULT_OUTPUT = os.path.join(_HERE, "output")

# ── Scoring table ─────────────────────────────────────────────────────────────

_EVENT_SCORE = {
    "Ace": 10, "4K": 9, "3K": 8, "Multi kill": 8,
    "Double kill": 6, "AWP kill": 7, "Headshot": 5, "Kill": 4,
    "Death": 1, "Round": 2, "Unknown": 2,
}

_HEADSHOT_SCORE = {
    "desert eagle": 7, "r8 revolver": 7,
    "usp-s": 6, "usp": 6, "p2000": 6,
    "five-seven": 6, "tec-9": 6, "cz75": 6,
}

_TYPE_KILL_COUNT = {
    "Kill": 1, "Double kill": 2, "3K": 3, "4K": 4, "Ace": 5,
    "AWP kill": 1, "Headshot": 1,
}

# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_event(filename: str) -> tuple[str, int]:
    """Classify a CS2 clip by its filename. Returns (event_type, score)."""
    low = filename.lower()

    m = re.search(r"You killed (.+?) with the", filename, re.IGNORECASE)
    if m:
        victims = m.group(1)
        parts = re.split(r"\s+and\s+", victims)
        all_victims = []
        for p in parts:
            all_victims.extend(re.split(r"-\s+|,\s*", p))
        count = len([v.strip() for v in all_victims if v.strip()])
        if count >= 5: return "Ace", 10
        if count == 4: return "4K", 9
        if count == 3: return "3K", 8
        if count == 2: return "Double kill", 6

    if "ace" in low:                        return "Ace", 10
    if "4k" in low:                         return "4K", 9
    if "triple" in low or "3k" in low:      return "3K", 8
    if "multi kill" in low:                 return "Multi kill", 8
    if "double kill" in low:                return "Double kill", 6
    if "awp" in low:                        return "AWP kill", 7

    # "with the [weapon]" without "You killed" = headshot single kill
    if re.search(r"\bwith the \b", low) and "you killed" not in low:
        wm = re.search(r"with the (.+?)\.mp4", filename, re.IGNORECASE)
        weapon = wm.group(1).lower() if wm else ""
        for key, score in _HEADSHOT_SCORE.items():
            if key in weapon:
                return "Headshot", score
        return "Headshot", 5

    if "you killed" in low:      return "Kill", 4
    if "you were killed" in low: return "Death", 1
    if "round" in low:           return "Round", 2
    # Any remaining .mp4 that looks like a gameplay clip (has a timestamp)
    if re.search(r"\d{4}-\d{2}-\d{2}", filename):
        return "Kill", 4
    return "Unknown", 2


def _expected_kills(clip: dict) -> int:
    t = clip.get("type", "Kill")
    if t in _TYPE_KILL_COUNT:
        return _TYPE_KILL_COUNT[t]
    m = re.search(r"\bYou killed (.+?) with\b", clip.get("file", ""))
    if m:
        parts = re.split(r"\s+and\s+", m.group(1))
        count = sum(
            len([v for v in re.split(r"-\s+|,\s*", p) if v.strip()])
            for p in parts
        )
        return max(1, count)
    return 1


def _to_date(d: Union[str, _date, None]) -> Optional[_date]:
    if d is None:
        return None
    if isinstance(d, _date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


# ── OCR helpers ───────────────────────────────────────────────────────────────

_KF_X_START, _KF_X_END   = 0.58, 1.00
_KF_Y_START, _KF_Y_END   = 0.00, 0.18
_OCR_THRESHOLD            = 140
_SCAN_INTERVAL            = 0.15
_KILL_COOLDOWN            = 1.5


def _preprocess(crop_bgr: np.ndarray) -> np.ndarray:
    rgb  = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    big  = cv2.resize(rgb, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(big, cv2.COLOR_RGB2GRAY)
    _, th = cv2.threshold(gray, _OCR_THRESHOLD, 255, cv2.THRESH_BINARY)
    return cv2.cvtColor(th, cv2.COLOR_GRAY2RGB)


def _ocr_count(crop_bgr: np.ndarray, reader, player_names: list[str]) -> int:
    proc    = _preprocess(crop_bgr)
    results = reader.readtext(proc, detail=0, paragraph=False)
    text    = " ".join(results).lower()
    return sum(text.count(n) for n in player_names)


def _group_kills(kill_times: list[float], gap: float) -> list[tuple[float, float]]:
    """
    Group consecutive kills where the gap between them is <= gap seconds.
    Returns a list of (first_kill, last_kill) per group.

    Example with gap=3:
        kills=[3, 5, 10, 11, 13] → [(3,5), (10,13)]
    """
    if not kill_times:
        return []
    groups = []
    start = end = kill_times[0]
    for kt in kill_times[1:]:
        if kt - end <= gap:
            end = kt          # extend current group
        else:
            groups.append((start, end))
            start = end = kt  # new group
    groups.append((start, end))
    return groups


def _find_kills(src_path: str, duration: float,
                reader, player_names: list[str]) -> list[float]:
    """Scan the kill feed and return timestamps for every detected kill."""
    cap = cv2.VideoCapture(src_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    W   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    x1, y1 = int(W * _KF_X_START), int(H * _KF_Y_START)
    x2, y2 = int(W * _KF_X_END),   int(H * _KF_Y_END)

    kill_times, prev_count, skip_until = [], 0, -1.0
    t = duration * 0.05

    while t <= duration * 0.90:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ret, frame = cap.read()
        if not ret:
            break
        if t >= skip_until:
            crop  = frame[y1:y2, x1:x2]
            count = _ocr_count(crop, reader, player_names)
            if count > prev_count:
                for _ in range(count - prev_count):
                    kill_times.append(round(t, 3))
                prev_count = count
                skip_until = t + _KILL_COOLDOWN
            elif count < prev_count:
                prev_count = count
        t += _SCAN_INTERVAL

    cap.release()
    return kill_times


# ── Main class ────────────────────────────────────────────────────────────────

class CS2Montage:
    """
    CS2 highlight montage pipeline.

    Parameters
    ----------
    player_name : name shown in the kill feed (case-insensitive substring)
    clips_dir   : folder with .mp4 clips  (default: ./source/)
    output_dir  : where to write output   (default: ./output/)
    date_start  : only include files with ctime >= this date ("YYYY-MM-DD")
    date_end    : only include files with ctime <= this date ("YYYY-MM-DD")
    min_score   : minimum clip score to include (Kill=4, Double=6, 3K=8, Ace=10)
    """

    def __init__(
        self,
        player_name: str = "ongaj",
        clips_dir:  Optional[str] = None,
        output_dir: Optional[str] = None,
        date_start: Union[str, _date, None] = None,
        date_end:   Union[str, _date, None] = None,
    ):
        self.clips_dir   = clips_dir or _DEFAULT_SOURCE
        self.player_name = player_name.lower()
        self.date_start  = _to_date(date_start)
        self.date_end    = _to_date(date_end)
        self.output_dir  = output_dir or _DEFAULT_OUTPUT
        self._reader     = None   # lazy-loaded EasyOCR

        os.makedirs(self.output_dir, exist_ok=True)

    # ── Step 1: scan ──────────────────────────────────────────────────────────

    def scan(self) -> list[dict]:
        """
        Find every .mp4 in clips_dir (recursive), filter by created date if set,
        and return sorted by created date oldest → newest.

        Returns list of clip dicts with keys:
            file, path, ctime, ctime_date, duration_total, resolution
        """
        from moviepy import VideoFileClip

        all_mp4 = sorted(glob.glob(os.path.join(self.clips_dir, "**", "*.mp4"), recursive=True))
        print(f"Found {len(all_mp4)} mp4 files in {self.clips_dir}")

        clips = []
        for path in all_mp4:
            name       = os.path.basename(path)
            ctime      = os.stat(path).st_ctime
            ctime_date = datetime.fromtimestamp(ctime, tz=timezone.utc).date()

            if self.date_start and ctime_date < self.date_start:
                continue
            if self.date_end and ctime_date > self.date_end:
                continue

            try:
                with VideoFileClip(path) as vid:
                    duration = round(vid.duration, 2)
                    w, h = vid.size
            except Exception as e:
                print(f"  [skip] {name}: {e}")
                continue

            clips.append({
                "file":           name,
                "path":           path,
                "ctime":          ctime,
                "ctime_date":     str(ctime_date),
                "duration_total": duration,
                "resolution":     f"{w}x{h}",
            })

        clips.sort(key=lambda c: c["ctime"])

        date_info = f" [{self.date_start} → {self.date_end}]" if (self.date_start or self.date_end) else ""
        print(f"Loaded {len(clips)} clips{date_info}, sorted oldest→newest\n")
        for c in clips:
            print(f"  {c['duration_total']:>5.1f}s  {c['ctime_date']}  {c['file'][:60]}")
        return clips

    # ── Step 2: detect_kills ─────────────────────────────────────────────────

    def detect_kills(self, clips: list[dict]) -> list[dict]:
        """
        Scan every clip's kill feed with OCR and record ALL kill timestamps.

        Adds to each clip dict:
            kill_times  : list of timestamps (one per kill found)
            kill_count  : number of kills detected
            kill_method : "ocr_Nk" or "heuristic" if OCR found nothing
        """
        if self._reader is None:
            import easyocr
            print("Loading EasyOCR model (one-time, ~60s)...")
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            print("Ready.\n")

        player_names = [self.player_name]

        print(f"{'#':<3} {'kills':>5}  {'timestamps':<30}  file")
        print("-" * 85)

        for i, clip in enumerate(clips, 1):
            dur  = clip["duration_total"]
            path = clip["path"]

            kill_times = _find_kills(path, dur, self._reader, player_names)

            if kill_times:
                clip["kill_times"]  = kill_times
                clip["kill_count"]  = len(kill_times)
                clip["kill_method"] = f"ocr_{len(kill_times)}k"
            else:
                # Heuristic fallback: one kill ~3.5s before end
                fallback = round(max(1.0, dur - 3.5), 3)
                clip["kill_times"]  = [fallback]
                clip["kill_count"]  = 0
                clip["kill_method"] = "heuristic"

            times_str = str([f"{t:.2f}s" for t in clip["kill_times"]])
            print(f"{i:<3} {clip['kill_count']:>5}  {times_str:<30}  {clip['file'][:45]}")

        return clips

    # ── Step 3: render ────────────────────────────────────────────────────────

    def render(
        self,
        clips: list[dict],
        output: Optional[str] = None,
        pre_sec:    float = 3.0,
        post_sec:   float = 3.0,
        last_extra: float = 3.0,
        fps:        int   = 60,
    ) -> str:
        """
        Render kill segments across all clips (ctime-sorted).

        merge logic: kills are merged into one segment when the gap between them
        is less than pre_sec + post_sec — the exact threshold that would cause
        overlapping windows, so overlap is mathematically impossible.

            segment = [first_kill - pre_sec  →  last_kill + post_sec]

        The very last segment gets last_extra additional seconds at the end.

        Returns the output file path.
        """
        from moviepy import VideoFileClip, concatenate_videoclips

        if output is None:
            output = os.path.join(self.output_dir, "final_highlight.mp4")

        # merge_gap = pre_sec + post_sec guarantees no two segments ever overlap
        merge_gap = pre_sec + post_sec

        # Build flat list of segments: (clip, first_kill, last_kill)
        segments = []
        for clip in clips:
            kill_times = clip.get("kill_times", [max(1.0, clip["duration_total"] - 3.5)])
            for first_k, last_k in _group_kills(kill_times, merge_gap):
                segments.append((clip, first_k, last_k))

        print(f"\nRendering {len(segments)} segments from {len(clips)} clips → {output}\n")
        print(f"{'#':<4} {'kills':>18}  {'window':>15}  {'dur':>5}  file")
        print("-" * 80)

        rendered = []
        for i, (clip, first_k, last_k) in enumerate(segments, 1):
            is_last = (i == len(segments))
            dur     = clip["duration_total"]
            extra   = last_extra if is_last else 0.0

            ts = max(0.0, first_k - pre_sec)
            te = min(dur,  last_k  + post_sec + extra)
            kills_str = f"{first_k:.1f}s" if first_k == last_k else f"{first_k:.1f}s–{last_k:.1f}s"

            print(f"{i:<4} {kills_str:>18}  [{ts:.1f}s→{te:.1f}s] {te-ts:>5.1f}s  {clip['file'][:40]}")

            try:
                vid = VideoFileClip(clip["path"]).subclipped(ts, te).without_audio()
                rendered.append(vid)

            except Exception as e:
                print(f"  ERROR: {e}")

        if not rendered:
            raise RuntimeError("No clips rendered successfully.")

        print(f"\nConcatenating {len(rendered)} clips...")
        final     = concatenate_videoclips(rendered, method="compose")
        total_dur = final.duration
        print(f"Total duration: {total_dur:.1f}s ({total_dur/60:.1f} min)")

        print(f"Exporting → {output}")
        final.write_videofile(
            output, fps=fps,
            codec="libx264",
            ffmpeg_params=["-preset", "fast", "-crf", "18"],
            logger="bar",
        )

        for v in rendered:
            v.close()
        final.close()

        print(f"\nDone: {output}")
        return output

    # ── Full pipeline ─────────────────────────────────────────────────────────

    def run(self, output: Optional[str] = None, **render_kwargs) -> str:
        """
        Full pipeline: scan → detect_kills → render.
        Returns the output file path.
        """
        clips = self.scan()
        if not clips:
            raise RuntimeError("No clips found. Check clips_dir and date filters.")
        clips = self.detect_kills(clips)
        return self.render(clips, output=output, **render_kwargs)

    # ── Persistence helpers ───────────────────────────────────────────────────

    def save(self, clips: list[dict], path: Optional[str] = None) -> str:
        """Save clips list to JSON (so detect_kills doesn't re-run next time)."""
        if path is None:
            path = os.path.join(self.output_dir, "clips.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(clips, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(clips)} clips → {path}")
        return path

    def load(self, path: Optional[str] = None) -> list[dict]:
        """Load clips list from a previously saved JSON."""
        if path is None:
            path = os.path.join(self.output_dir, "clips.json")
        with open(path, encoding="utf-8") as f:
            clips = json.load(f)
        print(f"Loaded {len(clips)} clips from {path}")
        return clips
