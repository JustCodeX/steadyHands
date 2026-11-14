"""The assistant's face on the 7-inch display.

The avatar is not decoration: it is how the player sees what the voice system
is doing. PLAN.md fixes four states and their colours, and the same states go
to the board's RGB LED 4, so screen and LED always agree.

| State      | Face                                   |
| ---------- | -------------------------------------- |
| off        | grey, eyes closed                      |
| listening  | green, breathing, eyes open            |
| processing | amber, eyes narrowed                   |
| speaking   | blue, mouth moving while a line plays  |

Drawn with Pillow into the framebuffer, so it needs no X server and no root.
The face is rendered on a band in the middle of the screen and only those
rows are written, which keeps a full-HD panel affordable to animate.
"""

import math

from PIL import Image, ImageDraw, ImageFont

from .framebuffer import Framebuffer

OFF, LISTENING, PROCESSING, SPEAKING = "off", "listening", "processing", "speaking"

# (background, face) per state.
PALETTE = {
    OFF:        ((18, 18, 20), (90, 92, 98)),
    LISTENING:  ((10, 26, 16), (64, 200, 110)),
    PROCESSING: ((30, 24, 8), (230, 180, 50)),
    SPEAKING:   ((10, 20, 34), (70, 150, 240)),
}

CAPTION = {OFF: "", LISTENING: "Listening", PROCESSING: "Thinking", SPEAKING: ""}

FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


class Avatar:
    """A face that shows what the voice system is doing."""

    def __init__(self, framebuffer=None, band_height=None):
        self.fb = framebuffer or Framebuffer()
        self.width = self.fb.width
        # Only a band in the middle is animated; the rest stays black.
        self.height = band_height or min(self.fb.height, int(self.fb.height * 0.8))
        self.top = (self.fb.height - self.height) // 2

        scale = min(self.width, self.height)
        self.radius = int(scale * 0.30)
        self.centre = (self.width // 2, int(self.height * 0.44))
        self.font = _font(max(20, int(scale * 0.075)))
        self.small = _font(max(16, int(scale * 0.05)))
        self.tiny = _font(max(14, int(scale * 0.038)))

        self.state = OFF
        self.subtitle = ""
        self.transcript = ""
        self._t = 0.0
        self.fb.clear()

    def set_state(self, state, subtitle="", transcript=None):
        """subtitle is the command we acted on, transcript is what was heard.

        Both are shown: the player has to be able to see *why* the trainer
        did what it did, which the command alone does not tell them.
        """
        self.state = state
        self.subtitle = subtitle
        if transcript is not None:
            self.transcript = transcript

    def draw(self, dt=1 / 15):
        self._t += dt
        background, face = PALETTE[self.state]
        image = Image.new("RGB", (self.width, self.height), background)
        draw = ImageDraw.Draw(image)

        # Listening breathes slowly; speaking bobs with the voice.
        if self.state == LISTENING:
            pulse = 1.0 + 0.05 * math.sin(self._t * 3.2)
        elif self.state == SPEAKING:
            pulse = 1.0 + 0.02 * math.sin(self._t * 11.0)
        else:
            pulse = 1.0
        radius = int(self.radius * pulse)
        cx, cy = self.centre

        draw.ellipse(self._box(cx, cy, radius + 10), outline=face, width=4)
        draw.ellipse(self._box(cx, cy, radius), fill=face)
        self._eyes(draw, cx, cy, radius, background)
        self._mouth(draw, cx, cy, radius, background)

        caption = CAPTION[self.state]
        if caption:
            self._centre_text(draw, self.font, caption, face,
                              int(self.height * 0.78))
        if self.subtitle:
            self._centre_text(draw, self.small, self.subtitle, (225, 225, 230),
                              int(self.height * 0.87))
        if self.transcript:
            self._centre_text(draw, self.tiny, f"\u201c{self.transcript}\u201d",
                              (130, 132, 140), int(self.height * 0.94))

        self.fb.flush(self.fb.blit(image, self.top))

    @staticmethod
    def _box(cx, cy, r):
        return (cx - r, cy - r, cx + r, cy + r)

    def _eyes(self, draw, cx, cy, radius, colour):
        dx, dy = int(radius * 0.38), int(radius * 0.22)
        size = max(3, int(radius * 0.13))
        for side in (-1, 1):
            x, y = cx + side * dx, cy - dy
            if self.state == OFF:                         # closed: a line
                draw.line((x - size, y, x + size, y), fill=colour,
                          width=max(3, size // 2))
            elif self.state == PROCESSING:                # narrowed
                draw.ellipse((x - size, y - size // 2, x + size, y + size // 2),
                             fill=colour)
            else:
                draw.ellipse(self._box(x, y, size), fill=colour)

    def _mouth(self, draw, cx, cy, radius, colour):
        width = int(radius * 0.52)
        y = cy + int(radius * 0.36)
        if self.state == SPEAKING:
            # Opens and closes while a line plays, so it reads as talking.
            opening = int(abs(math.sin(self._t * 9.0)) * radius * 0.30) + 6
            draw.ellipse((cx - width // 2, y - opening // 2,
                          cx + width // 2, y + opening // 2), fill=colour)
        elif self.state == OFF:
            draw.line((cx - width // 2, y, cx + width // 2, y), fill=colour, width=5)
        else:
            draw.arc((cx - width // 2, y - width // 4,
                      cx + width // 2, y + width // 4), 0, 180, fill=colour, width=5)

    def _centre_text(self, draw, font, text, colour, y):
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        draw.text(((self.width - (right - left)) // 2, y - (bottom - top) // 2),
                  text, font=font, fill=colour)

    def pump(self):
        """No window system, so there is nothing to poll. Ctrl+C quits."""
        return True

    def close(self):
        self.fb.close()
