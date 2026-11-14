"""Drawing straight into the Linux framebuffer.

No X server, no desktop and no SDL: the board shows the trainer, not a
desktop with the trainer on top of it. SDL's KMSDRM backend would have done
the same job, but the pygame wheel ships an SDL built without it, and
building one needs root. /dev/fb0 belongs to the `video` group, which the
`arduino` user is already in, so this needs no privileges at all.

A full 1920x1080 frame is 8.3 MB, which is too much to push 30 times a
second on this board, so only the rows that actually changed are written.
"""

import numpy as np

SYS = "/sys/class/graphics/fb0"


class Framebuffer:
    """The screen as a numpy array, flushed row-band by row-band."""

    def __init__(self, device="/dev/fb0", sysfs=SYS):
        with open(f"{sysfs}/virtual_size") as f:
            self.width, self.height = (int(n) for n in f.read().strip().split(","))
        with open(f"{sysfs}/bits_per_pixel") as f:
            bits = int(f.read())
        with open(f"{sysfs}/stride") as f:
            self.stride = int(f.read())
        if bits != 32:
            raise RuntimeError(f"expected a 32-bit framebuffer, found {bits}")

        self.device = device
        self._fb = open(device, "r+b", buffering=0)
        # The panel is BGRA, so the colour channels are written back to front.
        self.buffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        self.buffer[..., 3] = 255

    def blit(self, image, top=0):
        """Copy a PIL RGB image into the buffer at a row offset."""
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        rows = rgb.shape[0]
        self.buffer[top:top + rows, :, 2] = rgb[..., 0]
        self.buffer[top:top + rows, :, 1] = rgb[..., 1]
        self.buffer[top:top + rows, :, 0] = rgb[..., 2]
        return top, top + rows

    def flush(self, rows=None):
        """Write the buffer, or only the given (top, bottom) band of rows."""
        top, bottom = rows if rows else (0, self.height)
        top, bottom = max(0, top), min(self.height, bottom)
        if bottom <= top:
            return
        self._fb.seek(top * self.stride)
        self._fb.write(self.buffer[top:bottom].tobytes())

    def clear(self):
        self.buffer[..., :3] = 0
        self.flush()

    def close(self):
        try:
            self.clear()
        finally:
            self._fb.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
