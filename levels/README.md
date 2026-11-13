# Levels

One folder per level. Anyone on the team can make a level with an image editor.

```
levels/01-splinter/
  mask.png      1024 × 600 pixels
  level.json
```

## mask.png

| Colour | Meaning |
| --- | --- |
| Black | Wall: touching it counts as a contact |
| White | Corridor: the instrument can move here |

Colliding with a wall is a pixel lookup in this image. Targets are not drawn in the mask; they come from `level.json`.

## level.json

```json
{
  "name": "Splinter",
  "time_limit_s": 60,
  "start": [80, 300],
  "targets": [
    { "id": "bleeding", "position": [500, 300], "needs": "clamp", "timer_s": 15 },
    { "id": "splinter", "position": [900, 280], "needs": "forceps" }
  ]
}
```

- Coordinates are in pixels, measured from the top-left corner.
- `needs` names the instrument class that handles the target: `forceps`, `swab`, `clamp`, or `scalpel`.
- `timer_s` is optional; for bleeding, it is the time left before the patient's state gets worse.
