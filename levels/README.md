# Levels

One folder per level. Anyone on the team can make a level with an image editor; `app/tools/make_levels.py` generates the three demo levels so that playable levels always exist (re-running it overwrites them).

```
levels/01-splinter/
  mask.png      1024 × 600 pixels
  level.json
```

## mask.png

| Colour | Meaning |
| --- | --- |
| Black (dark) | Wall: touching it counts as a contact |
| White (light) | Corridor: the instrument can move here |

Colliding with a wall is a pixel lookup in this image (`CollisionMap`). Keep the top 56 pixels black: the HUD covers them. Targets are not drawn in the mask; they come from `level.json`. The renderer recolours the mask (tissue and skin colours from `app/trainer/ui/theme.py`).

## level.json

```json
{
  "name": "Splinter",
  "time_limit_s": 60,
  "start": [80, 300],
  "targets": [
    { "id": "bleeding", "position": [500, 300], "needs": "clamp", "timer_s": 15 },
    { "id": "splinter", "position": [900, 280], "needs": "forceps" }
  ],
  "dark": [[560, 400, 300, 170]]
}
```

- Coordinates are in pixels, measured from the top-left corner.
- `needs` names the instrument that handles the target: `forceps`, `swab`, `clamp`, or `scalpel`. Hovering over a target with the right instrument for one second (or pressing A) applies it; the wrong instrument counts as a wrong call.
- `timer_s` is optional; for bleeding, it is the time until the patient's state gets worse (one contact), and it restarts until the target is clamped.
- `dark` is optional: rectangles `[x, y, w, h]` that are blacked out until someone calls `light`.
- Level order is alphabetical by folder name; make them harder step by step (narrower corridors, less time).
