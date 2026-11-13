#!/usr/bin/env python3
"""Generate the three demo levels (mask.png + level.json) under levels/.

Anyone can replace these with hand-drawn masks; this just guarantees that
playable levels exist. Corridors get narrower and time shorter per level.
Usage: python tools/make_levels.py [levels_dir]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

W, H = 1024, 600
HUD = 56  # the HUD covers the top; keep corridors below it

LEVELS = [
    {
        "dir": "01-splinter",
        "name": "Splinter",
        "time_limit_s": 60,
        "width": 96,
        "path": [(90, 330), (300, 330), (300, 160), (560, 160), (560, 420), (820, 420), (920, 300)],
        "targets": [
            {"id": "splinter", "position": [560, 160], "needs": "forceps"},
            {"id": "shard", "position": [920, 300], "needs": "forceps"},
        ],
    },
    {
        "dir": "02-bleeding",
        "name": "Bleeding",
        "time_limit_s": 55,
        "width": 76,
        "path": [(90, 480), (260, 480), (260, 200), (480, 200), (480, 470), (700, 470), (700, 180), (930, 180)],
        "targets": [
            {"id": "bleeding", "position": [480, 200], "needs": "clamp", "timer_s": 20},
            {"id": "blood", "position": [700, 470], "needs": "swab"},
            {"id": "button", "position": [930, 180], "needs": "forceps"},
        ],
    },
    {
        "dir": "03-deep-cut",
        "name": "Deep cut",
        "time_limit_s": 50,
        "width": 60,
        "path": [(80, 150), (220, 150), (220, 500), (400, 500), (400, 220), (600, 220), (600, 480), (780, 480), (780, 160), (940, 160), (940, 420)],
        "targets": [
            {"id": "bleeding_1", "position": [400, 220], "needs": "clamp", "timer_s": 18},
            {"id": "blood", "position": [600, 480], "needs": "swab"},
            {"id": "glass", "position": [940, 160], "needs": "forceps"},
            {"id": "needle", "position": [940, 420], "needs": "forceps"},
        ],
        "dark": [[560, 400, 300, 170]],
    },
]


def draw_mask(spec: dict) -> pygame.Surface:
    surf = pygame.Surface((W, H))
    surf.fill((0, 0, 0))
    w = spec["width"]
    pts = spec["path"]
    for a, b in zip(pts, pts[1:]):
        pygame.draw.line(surf, (255, 255, 255), a, b, w)
        pygame.draw.circle(surf, (255, 255, 255), a, w // 2)
    pygame.draw.circle(surf, (255, 255, 255), pts[-1], w // 2)
    # start pad and target pads: round chambers
    pygame.draw.circle(surf, (255, 255, 255), pts[0], w)
    for t in spec["targets"]:
        pygame.draw.circle(surf, (255, 255, 255), t["position"], int(w * 0.9))
    # keep the HUD strip solid wall
    pygame.draw.rect(surf, (0, 0, 0), (0, 0, W, HUD + 8))
    return surf


def main(levels_dir: Path) -> None:
    pygame.display.init()
    for spec in LEVELS:
        d = levels_dir / spec["dir"]
        d.mkdir(parents=True, exist_ok=True)
        pygame.image.save(draw_mask(spec), str(d / "mask.png"))
        data = {
            "name": spec["name"],
            "time_limit_s": spec["time_limit_s"],
            "start": list(spec["path"][0]),
            "targets": spec["targets"],
        }
        if spec.get("dark"):
            data["dark"] = spec["dark"]
        with open(d / "level.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"wrote {d}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "levels")
