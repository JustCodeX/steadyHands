"""Cut the demo video for slide 4 from the phone recording.

    python make_video.py ~/Downloads/IMG_4590.mp4      # from pitch/, needs ffmpeg

Takes the first 45 s of the recording, the full frame as filmed (no crop, no
zoom), scales it from 4K to 1920 x 1080 and writes media/demo.mp4 (H.264, with
sound, a short fade at the end) and the poster frame media/demo-poster.jpg.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECONDS = 45


def main(src: str) -> None:
    out, poster = HERE / "media" / "demo.mp4", HERE / "media" / "demo-poster.jpg"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", src, "-t", str(SECONDS), "-map", "0:v:0", "-map", "0:a:0",
         "-vf", f"scale=1920:1080,fps=30,fade=t=out:st={SECONDS - 0.7}:d=0.7",
         "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-af", f"afade=t=out:st={SECONDS - 1}:d=1", "-movflags", "+faststart", str(out)],
        check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "21", "-i", str(out), "-frames:v", "1", "-q:v", "3", str(poster)],
                   check=True)
    print(f"saved {out.name} ({out.stat().st_size / 1e6:.0f} MB) and {poster.name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
