"""Colours and sizes used by the renderer. Our own artwork, not Dr. Bibber's."""
from __future__ import annotations

BG = (18, 22, 30)
WALL = (46, 36, 52)  # tissue
WALL_EDGE = (120, 70, 90)
CORRIDOR = (236, 204, 196)  # skin
HUD_BG = (10, 12, 18)
TEXT = (235, 238, 245)
MUTED = (140, 148, 165)
ACCENT = (90, 200, 250)
GOOD = (80, 210, 120)
WARN = (250, 200, 70)
BAD = (240, 80, 80)
TOOL = (250, 250, 250)
TOOL_STEADY = (120, 230, 255)
DARK = (5, 6, 10)

TARGET_COLOURS = {
    "forceps": (120, 170, 255),  # blue: foreign object
    "swab": (200, 60, 60),  # red: blood
    "clamp": (255, 120, 40),  # orange: bleeding
    "scalpel": (180, 120, 255),  # violet: sealed passage
}

TOOL_LETTERS = {"forceps": "F", "swab": "S", "clamp": "C", "scalpel": "K"}

MIC_COLOURS = {
    "OFF": (90, 90, 100),
    "LISTENING": GOOD,
    "PROCESSING": WARN,
    "SPEAKING": ACCENT,
}

HUD_HEIGHT = 56
FONT = None  # default pygame font; swap for a TTF path if wanted
