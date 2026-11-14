"""Cut the demo video for slide 4 from the phone recording.

    python make_video.py ~/Downloads/IMG_4590.mp4      # from pitch/, needs ffmpeg and numpy

The phone filmed the screen sideways and in 4K. This takes the first 45 s,
turns the picture upright and cuts a 16:9 strip out of it that follows the
game screen up and down (found by the pink corridors of the wound), then
writes media/demo.mp4 (H.264, 1920 x 1080, with sound) and the poster frame
media/demo-poster.jpg.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SECONDS = 45
UP_W, UP_H = 2160, 3840   # the 4K frame turned upright
CROP_H = UP_W * 9 // 16   # 16:9 at full width
SMALL_W, SMALL_H, FPS = 108, 192, 10


def screen_centre(src: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Time, weight and vertical centre (0..1) of the pink corridors, 10 times a second."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", src, "-t", str(SECONDS),
         "-vf", f"transpose=2,scale={SMALL_W}:{SMALL_H},fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, SMALL_H, SMALL_W, 3).astype(int)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    pink = (r > 150) & (r - g > 60) & (b - g > 15) & (r - b > 30)
    n = pink.sum(axis=(1, 2))
    cy = (pink * np.arange(SMALL_H)[None, :, None]).sum(axis=(1, 2)) / np.maximum(n, 1) / SMALL_H
    t = np.arange(len(f)) / FPS
    return t, np.clip(n, 0, 100) * (n >= 10), cy


def crop_filter(t: np.ndarray, w: np.ndarray, cy: np.ndarray) -> str:
    """A crop whose top follows the smoothed screen centre, keyed every 0.5 s."""
    keys = np.arange(0, SECONDS + 0.01, 0.5)
    ys = []
    for k in keys:
        g = np.exp(-0.5 * ((t - k) / 0.7) ** 2) * w
        centre = (g * cy).sum() / g.sum()
        ys.append(min(max(centre * UP_H - 0.45 * CROP_H, 0), UP_H - CROP_H))
    terms = [f"gte(t\\,{a:.1f})*lt(t\\,{b:.1f})*({ya:.1f}+({(yb - ya) / (b - a):.2f})*(t-{a:.1f}))"
             for a, b, ya, yb in zip(keys, keys[1:], ys, ys[1:])]
    terms.append(f"gte(t\\,{keys[-1]:.1f})*{ys[-1]:.1f}")
    fade = SECONDS - 0.7
    return (f"[0:v:0]transpose=2,crop={UP_W}:{CROP_H}:0:'{'+'.join(terms)}',"
            f"scale=1920:1080,fps=30,fade=t=out:st={fade}:d=0.7[v]")


def main(src: str) -> None:
    out, poster = HERE / "media" / "demo.mp4", HERE / "media" / "demo-poster.jpg"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(crop_filter(*screen_centre(src)))
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", src, "-/filter_complex", fh.name, "-map", "[v]", "-map", "0:a:0",
         "-t", str(SECONDS), "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-af", f"afade=t=out:st={SECONDS - 1}:d=1", "-movflags", "+faststart", str(out)],
        check=True)
    Path(fh.name).unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "21", "-i", str(out), "-frames:v", "1", "-q:v", "3", str(poster)],
                   check=True)
    print(f"saved {out.name} ({out.stat().st_size / 1e6:.0f} MB) and {poster.name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
