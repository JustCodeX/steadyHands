from trainer.game.collision_map import CollisionMap


def make_map():
    # 10x10, wall everywhere except a 4-wide corridor in rows 3..6
    w = h = 10
    walls = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            walls[y * w + x] = 0 if 3 <= y <= 6 else 1
    return CollisionMap(w, h, walls)


def test_wall_and_corridor():
    m = make_map()
    assert m.is_wall(5, 0)
    assert not m.is_wall(5, 4)
    assert m.is_wall(-1, 4) and m.is_wall(5, 10)


def test_circle_hits_wall_near_edge():
    m = make_map()
    assert not m.circle_hits_wall(5, 4.5, 1.0)
    assert m.circle_hits_wall(5, 3.2, 1.0)


def test_from_png(tmp_path):
    import pygame

    surf = pygame.Surface((8, 4))
    surf.fill((0, 0, 0))
    surf.fill((255, 255, 255), (2, 0, 4, 4))
    p = tmp_path / "mask.png"
    pygame.image.save(surf, str(p))
    m = CollisionMap.from_png(p)
    assert m.is_wall(0, 1) and not m.is_wall(3, 1) and m.is_wall(7, 1)
