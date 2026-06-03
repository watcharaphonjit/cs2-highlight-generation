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

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    CS2Montage(
        player_name = PLAYER_NAME,
        date_start  = DATE_START,
        date_end    = DATE_END,
    ).run(
        pre_sec  = 3.0,   # seconds before first kill in a group
        post_sec = 3.0,   # seconds after last kill in a group
        # kills within pre_sec + post_sec = 6s are auto-merged (no overlap guaranteed)
    )
