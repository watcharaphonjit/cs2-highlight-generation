"""
CS2 Highlight Montage — Entry Point

How to use:
1. Drop your .mp4 clip files into the ./source/ folder
2. Edit PLAYER_NAME below to match your in-game name
3. Run: python run.py

Output: ./output/final_highlight.mp4
"""

from cs2montage import CS2Montage

# ── Config ────────────────────────────────────────────────────────────────────

PLAYER_NAME = "ongaj"       # your name as it appears in the CS2 kill feed

DATE_START  = None          # only include files created on/after this date, e.g. "2024-07-20"
DATE_END    = None          # only include files created on/before this date, e.g. "2024-07-26"

MUSIC_FILE  = None          # path to mp3/wav, e.g. r".\music\song.mp3"  (None = no music)
MUSIC_VOL   = 0.5           # music loudness  0.0–1.0
GAME_VOL    = 0.8           # game audio loudness 0.0–1.0
BEAT_SYNC   = True         # snap every segment to a beat boundary (requires MUSIC_FILE)

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    CS2Montage(
        player_name = PLAYER_NAME,
        date_start  = DATE_START,
        date_end    = DATE_END,
    ).run(
        pre_sec      = 3.0,
        post_sec     = 3.0,
        music_path   = MUSIC_FILE,
        music_volume = MUSIC_VOL,
        game_volume  = GAME_VOL,
        beat_sync    = BEAT_SYNC,
    )
