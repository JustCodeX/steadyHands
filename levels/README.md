# Levels

One folder per level. Anyone on the team can make a level with an image editor; `app/tools/make_levels.py` generates the six demo levels so that playable levels always exist (re-running it overwrites them).

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

Colliding with a wall is a pixel lookup in this image (`CollisionMap`). Keep the top 56 pixels black: the HUD covers them. Targets are not drawn in the mask; they come from `level.json`. The game paints the mask as a picture (`MapPainter`): the corridor becomes an open wound, the wall the skin around it (colours in `app/trainer/ui/theme.py`). Small decorations (a plaster, moles) are placed on free skin automatically.

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
  "dark": [[560, 400, 300, 170]],
  "quiz": { "count": 2, "topics": ["instruments", "safety"] }
}
```

- Coordinates are in pixels, measured from the top-left corner.
- `needs` names the instrument that handles the target: `forceps`, `swab`, `clamp`, or `scalpel`. For `forceps` targets the `id` picks the picture: an id containing `splinter`, `shard`, `glass`, `needle` or `button` is drawn as that object. Hovering over a target with the right instrument for one second (or pressing A) applies it; the wrong instrument counts as a wrong call.
- `timer_s` is optional; for bleeding, it is the time until the patient's state gets worse (one contact), and it restarts until the target is clamped.
- `dark` is optional: rectangles `[x, y, w, h]` that are blacked out until the player presses the knob (or calls `light`); the light stays on for a few seconds.
- `quiz` is optional: `count` is how many questions the patient asks during the round (0 switches the quiz off for this level; without it the default from the config applies), and `topics` limits them to those topics of `app/assets/questions.json` (empty or missing: any topic).
- Level order is alphabetical by folder name; make them harder step by step (narrower corridors, less time).
