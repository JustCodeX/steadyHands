"""Our patient: the face (it shows how close the patient is to waking up) and
the whole body on the operating table for the menu."""
from __future__ import annotations

import math

import pygame

from .. import theme
from .canvas import Pen, curve, render

FACE_BOX = 100.0
BODY_BOX = (800.0, 250.0)

EYE_INK = (52, 40, 48)
MOUTH = (126, 34, 48)

# Where a level's marker sits on the body (design units of the body picture).
BODY_SPOTS = ((438, 60), (404, 126), (300, 118), (352, 192), (262, 150), (480, 106))


class PatientArt:
    """Draws the patient. Moods: asleep, happy, stirring, alarmed, awake."""

    MOODS = ("asleep", "stirring", "alarmed", "awake")

    def __init__(self) -> None:
        self._cache: dict[tuple, pygame.Surface] = {}

    @classmethod
    def mood_for(cls, contacts: int, max_contacts: int) -> str:
        """Each wall contact wakes the patient a little more."""
        if contacts <= 0:
            return "asleep"
        if contacts >= max_contacts:
            return "awake"
        return "alarmed" if contacts >= max_contacts - 1 else "stirring"

    def face(self, mood: str, size: int) -> pygame.Surface:
        key = ("face", mood, size)
        if key not in self._cache:
            self._cache[key] = render((size, size), FACE_BOX, lambda pen: self._face(pen, mood))
        return self._cache[key]

    def body(self, width: int) -> pygame.Surface:
        """The patient lying on the table, head to the left."""
        key = ("body", width)
        if key not in self._cache:
            height = round(width * BODY_BOX[1] / BODY_BOX[0])
            surface = render((width, height), BODY_BOX[0], self._body, oversample=2)
            k = width / BODY_BOX[0]
            face = pygame.transform.rotate(self.face("asleep", round(136 * k)), 90)
            surface.blit(face, face.get_rect(center=(round(132 * k), round(125 * k))))
            self._cache[key] = surface
        return self._cache[key]

    @staticmethod
    def body_spot(index: int, width: int) -> tuple[int, int]:
        """Pixel position of the marker for level `index` inside `body(width)`."""
        k = width / BODY_BOX[0]
        x, y = BODY_SPOTS[index % len(BODY_SPOTS)]
        return (round(x * k), round(y * k))

    # --- face ------------------------------------------------------------------

    def _face(self, pen: Pen, mood: str) -> None:
        cx, cy, r = 50.0, 55.0, 37.0
        # ears, head
        for ex in (cx - r, cx + r):
            pen.circle(theme.SKIN_LINE, (ex, cy + 3), 8.5)
            pen.circle(theme.SKIN_SHADE, (ex, cy + 3), 6)
        pen.circle(theme.SKIN_LINE, (cx, cy), r + 2.5)
        pen.circle(theme.SKIN, (cx, cy), r)
        pen.circle(theme.CHEEK, (cx - 21, cy + 13), 6.5)
        pen.circle(theme.CHEEK, (cx + 21, cy + 13), 6.5)
        # surgical cap
        cap = [
            (cx + (r + 4) * math.cos(math.radians(a)), cy - (r + 4) * math.sin(math.radians(a)) * 1.12)
            for a in range(20, 161, 5)
        ]
        pen.path(theme.SKIN_LINE, cap, 5, closed=True)
        pen.poly(theme.CAP, cap)
        band = curve(cap[-1], (cx, cap[0][1] + 5), cap[0])
        pen.path(theme.SKIN_LINE, band, 9)
        pen.path(theme.CAP_DARK, band, 5)
        pen.circle((150, 222, 214), (cx - 12, cy - r - 2), 4)
        # nose
        pen.path(theme.SKIN_LINE, curve((cx - 2, cy + 7), (cx - 1, cy + 15), (cx + 5, cy + 12), 8), 2.6)

        left, right = (cx - 15, cy + 3), (cx + 15, cy + 3)
        if mood in ("asleep", "happy"):
            dip = 5 if mood == "asleep" else -5
            for ex, ey in (left, right):
                pen.path(EYE_INK, curve((ex - 7, ey), (ex, ey + dip), (ex + 7, ey), 10), 3)
            smile = 7 if mood == "happy" else 4
            pen.path(EYE_INK, curve((cx - 8, cy + 21), (cx, cy + 21 + smile), (cx + 8, cy + 21), 10), 3)
        elif mood == "stirring":
            ex, ey = left
            pen.path(EYE_INK, curve((ex - 7, ey), (ex, ey + 5), (ex + 7, ey), 10), 3)
            self._open_eye(pen, right, 7.5, 3.2)
            pen.line(EYE_INK, (right[0] - 8, right[1] - 12), (right[0] + 7, right[1] - 14), 2.6)
            wave = [(cx - 9, cy + 23), (cx - 4.5, cy + 21), (cx, cy + 23), (cx + 4.5, cy + 21), (cx + 9, cy + 23)]
            pen.path(EYE_INK, wave, 3)
            self._sweat(pen, (cx + 30, cy - 12))
        else:  # alarmed, awake
            wide = mood == "awake"
            for (ex, ey), tilt in ((left, -1), (right, 1)):
                self._open_eye(pen, (ex, ey), 9.5 if wide else 8.5, 2.6 if wide else 3.2)
                pen.line(EYE_INK, (ex - 7, ey - 14 - 2 * tilt), (ex + 7, ey - 14 + 2 * tilt), 2.8)
            if wide:
                pen.ellipse(EYE_INK, (cx - 11, cy + 15, 22, 19))
                pen.ellipse(MOUTH, (cx - 8.5, cy + 17.5, 17, 14))
                pen.ellipse((232, 110, 120), (cx - 6, cy + 25, 12, 6))
            else:
                pen.circle(EYE_INK, (cx, cy + 23), 6)
                pen.circle(MOUTH, (cx, cy + 23), 3.6)
            self._sweat(pen, (cx + 30, cy - 12))

    @staticmethod
    def _open_eye(pen: Pen, centre, radius: float, pupil: float) -> None:
        pen.circle(EYE_INK, centre, radius + 1.8)
        pen.circle((255, 255, 255), centre, radius)
        pen.circle(EYE_INK, centre, pupil)

    @staticmethod
    def _sweat(pen: Pen, at) -> None:
        x, y = at
        drop = [(x, y - 8), (x + 4.5, y), (x, y + 4.5), (x - 4.5, y)]
        pen.path((60, 130, 180), drop, 2.4, closed=True)
        pen.poly((150, 214, 250), drop)
        pen.circle((150, 214, 250), (x, y + 0.5), 4)

    # --- body ------------------------------------------------------------------

    @staticmethod
    def _body(pen: Pen) -> None:
        line = theme.SKIN_LINE
        # table and mattress
        pen.rect((14, 40, 46), (34, 56, 746, 176), radius=34)  # shadow on the floor
        pen.rect(theme.OUTLINE, (22, 34, 756, 182), radius=36)
        pen.rect((150, 172, 186), (26, 38, 748, 174), radius=32)
        pen.rect((232, 240, 244), (36, 46, 728, 152), radius=28)
        pen.rect((206, 218, 226), (36, 176, 728, 22), radius=11)
        # pillow
        pen.rect((176, 190, 204), (48, 62, 150, 126), radius=34)
        pen.rect((255, 255, 255), (52, 66, 142, 118), radius=30)
        # arms
        upper = curve((250, 92), (330, 46), (438, 60))
        lower = curve((250, 158), (330, 204), (438, 190))
        for arm in (upper, lower):
            pen.path(line, arm, 31)
            pen.circle(line, arm[-1], 18.5)
        for arm in (upper, lower):
            pen.path(theme.SKIN, arm, 26)
            pen.circle(theme.SKIN, arm[-1], 16)
        # neck, torso
        pen.rect(line, (182, 104, 52, 42), radius=8)
        pen.rect(theme.SKIN_SHADE, (184, 106.5, 50, 37), radius=6)
        pen.rect(line, (212, 76, 300, 98), radius=40)
        pen.rect(theme.SKIN, (214.5, 78.5, 295, 93), radius=38)
        pen.path(theme.SKIN_SHADE, curve((262, 100), (300, 110), (262, 150)), 3)  # collar bone
        pen.path(line, curve((452, 119), (460, 125), (452, 131), 6), 2.6)  # belly button
        # blanket over the legs, with the feet under it
        pen.rect(theme.OUTLINE, (468, 56, 286, 138), radius=32)
        pen.rect((112, 182, 214), (471, 59, 280, 132), radius=30)
        pen.rect((172, 220, 238), (471, 59, 34, 132), radius=14)
        for y in (72, 130):
            pen.ellipse((146, 204, 228), (696, y, 44, 48))
        for x in (560, 630):
            pen.line((90, 160, 196), (x, 74), (x + 14, 176), 2.5)
