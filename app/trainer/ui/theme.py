"""Colours and sizes used by the renderer. Our own artwork, not Dr. Bibber's."""
from __future__ import annotations

from pathlib import Path

# --- operating room ----------------------------------------------------------
ROOM = (18, 54, 62)  # floor
ROOM_LINE = (24, 66, 74)
ROOM_LIGHT = (40, 104, 108)  # under the surgical lamp
DARK = (5, 6, 10)

# --- patient -----------------------------------------------------------------
SKIN = (245, 205, 178)
SKIN_LIGHT = (252, 224, 202)
SKIN_SHADE = (226, 174, 148)
SKIN_LINE = (150, 92, 78)
CHEEK = (244, 160, 150)
CAP = (64, 176, 166)
CAP_DARK = (40, 132, 128)

# --- the wound: the corridor the instrument moves in --------------------------
CAVITY = (150, 38, 56)
CAVITY_LIGHT = (206, 84, 92)
CAVITY_DARK = (70, 12, 28)
WOUND_EDGE = (112, 30, 44)
WOUND_HALO = (232, 120, 112)  # reddened skin around the wound

# --- panels and text ---------------------------------------------------------
PANEL = (22, 32, 46)
PANEL_LIGHT = (40, 54, 72)
PANEL_LINE = (62, 80, 102)
PAPER = (252, 246, 232)
PAPER_LINE = (222, 212, 190)
INK = (44, 52, 66)
TEXT = (240, 244, 248)
MUTED = (150, 164, 182)
ACCENT = (90, 200, 250)
GOOD = (84, 208, 128)
WARN = (255, 196, 66)
BAD = (240, 82, 82)

# --- instruments -------------------------------------------------------------
OUTLINE = (30, 38, 54)
STEEL = (208, 218, 230)
STEEL_LIGHT = (240, 245, 250)
STEEL_DARK = (132, 146, 166)
TOOL_STEADY = (120, 230, 255)

TARGET_COLOURS = {
    "forceps": (110, 170, 255),  # blue: foreign object
    "swab": (236, 96, 110),  # red: blood
    "clamp": (255, 150, 50),  # orange: bleeding
    "scalpel": (186, 132, 255),  # violet: sealed passage
}

TOOL_LETTERS = {"forceps": "F", "swab": "S", "clamp": "C", "scalpel": "K"}

MIC_COLOURS = {
    "OFF": (90, 90, 100),
    "LISTENING": GOOD,
    "PROCESSING": WARN,
    "SPEAKING": ACCENT,
}

HUD_HEIGHT = 56

# --- fonts (SIL Open Font License, see assets/fonts) --------------------------
FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
FONT_DISPLAY = FONT_DIR / "LilitaOne-Regular.ttf"
FONT_BODY = FONT_DIR / "VarelaRound-Regular.ttf"
