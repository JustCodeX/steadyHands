"""Drawing helpers shared by the artwork classes.

All artwork is drawn with code: a `Pen` draws in design units on an oversized
surface, which `render()` scales down smoothly. Each picture is drawn once and
cached by its owner, so nothing here runs per frame.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

import pygame

Point = tuple[float, float]


class Pen:
    """Draws on `surface` in design units; `k` converts units to pixels."""

    def __init__(self, surface: pygame.Surface, k: float) -> None:
        self.surface = surface
        self.k = k

    def _p(self, pt: Point) -> tuple[int, int]:
        return (round(pt[0] * self.k), round(pt[1] * self.k))

    def _w(self, width: float) -> int:
        return max(1, round(width * self.k)) if width else 0

    def circle(self, colour, centre: Point, radius: float, width: float = 0) -> None:
        pygame.draw.circle(self.surface, colour, self._p(centre), max(1, round(radius * self.k)), self._w(width))

    def ellipse(self, colour, rect: Sequence[float], width: float = 0) -> None:
        x, y, w, h = rect
        r = pygame.Rect(round(x * self.k), round(y * self.k), max(1, round(w * self.k)), max(1, round(h * self.k)))
        pygame.draw.ellipse(self.surface, colour, r, self._w(width))

    def rect(self, colour, rect: Sequence[float], radius: float = 0, width: float = 0) -> None:
        x, y, w, h = rect
        r = pygame.Rect(round(x * self.k), round(y * self.k), max(1, round(w * self.k)), max(1, round(h * self.k)))
        pygame.draw.rect(self.surface, colour, r, self._w(width), border_radius=round(radius * self.k))

    def poly(self, colour, points: Sequence[Point]) -> None:
        pygame.draw.polygon(self.surface, colour, [self._p(p) for p in points])

    def line(self, colour, a: Point, b: Point, width: float) -> None:
        """A thick line with round ends."""
        ax, ay = a[0] * self.k, a[1] * self.k
        bx, by = b[0] * self.k, b[1] * self.k
        half = max(0.5, width * self.k / 2)
        length = math.hypot(bx - ax, by - ay)
        if length > 1e-6:
            nx, ny = -(by - ay) / length * half, (bx - ax) / length * half
            pygame.draw.polygon(
                self.surface, colour, [(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)]
            )
        for cx, cy in ((ax, ay), (bx, by)):
            pygame.draw.circle(self.surface, colour, (round(cx), round(cy)), max(1, round(half)))

    def path(self, colour, points: Sequence[Point], width: float, closed: bool = False) -> None:
        """A thick line through all points, with round joints."""
        pts = list(points) + ([points[0]] if closed else [])
        for a, b in zip(pts, pts[1:]):
            self.line(colour, a, b, width)

    def outlined_path(self, colour, outline, points: Sequence[Point], width: float, border: float = 2.0) -> None:
        self.path(outline, points, width + 2 * border)
        self.path(colour, points, width)


def curve(a: Point, control: Point, b: Point, steps: int = 14) -> list[Point]:
    """Points on a quadratic Bezier curve from a to b."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((u * u * a[0] + 2 * u * t * control[0] + t * t * b[0], u * u * a[1] + 2 * u * t * control[1] + t * t * b[1]))
    return out


def render(size: tuple[int, int], design_width: float, draw: Callable[[Pen], None], oversample: int = 3) -> pygame.Surface:
    """Draw with `draw(pen)` in a design space `design_width` wide; return it at `size` pixels, smoothed."""
    w, h = size
    big = pygame.Surface((w * oversample, h * oversample), pygame.SRCALPHA)
    draw(Pen(big, w * oversample / design_width))
    small = pygame.transform.smoothscale(big, (w, h))
    return small.convert_alpha() if pygame.display.get_surface() else small


def blur(surface: pygame.Surface, factor: int) -> pygame.Surface:
    """A cheap blur: scale down by `factor`, then back up."""
    w, h = surface.get_size()
    small = pygame.transform.smoothscale(surface, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


def radial(size: tuple[int, int], centre, edge, inner: float = 0.0, outer: float = 1.42, steps: int = 28) -> pygame.Surface:
    """An elliptical gradient from `centre` to `edge` (RGBA colours).

    `inner` and `outer` are where the gradient starts and ends, as a fraction
    of the ellipse that touches the four sides (the corners are at 1.41).
    Drawn small and scaled up in stages, which makes it smooth and cheap.
    """
    w = 128
    h = max(2, round(w * size[1] / size[0]))
    tiny = pygame.Surface((w, h), pygame.SRCALPHA)
    tiny.fill(edge)
    for i in range(steps + 1):
        f = i / steps
        scale = outer + (inner - outer) * f
        colour = tuple(round(e + (c - e) * f) for c, e in zip(centre, edge))
        rect = pygame.Rect(0, 0, max(1, round(w * scale)), max(1, round(h * scale)))
        rect.center = (w // 2, h // 2)
        pygame.draw.ellipse(tiny, colour, rect)
    soft = pygame.transform.smoothscale(pygame.transform.smoothscale(tiny, (w // 4, max(1, h // 4))), (w, h))
    return pygame.transform.smoothscale(soft, size)


def soft_glow(size: tuple[int, int], colour, alpha: int) -> pygame.Surface:
    """An elliptical glow that fades to nothing at the edge."""
    return radial(size, (*colour[:3], alpha), (*colour[:3], 0), inner=0.0, outer=1.0)


def ring(surface: pygame.Surface, colour, centre: Point, radius: float, width: float, fraction: float = 1.0) -> None:
    """Part of a ring, clockwise from 12 o'clock. Drawn as one polygon, so it has no gaps."""
    fraction = max(0.0, min(1.0, fraction))
    if fraction <= 0.0:
        return
    steps = max(2, int(48 * fraction))
    outer, inner = [], []
    for i in range(steps + 1):
        a = -math.pi / 2 + 2 * math.pi * fraction * i / steps
        c, s = math.cos(a), math.sin(a)
        outer.append((centre[0] + c * radius, centre[1] + s * radius))
        inner.append((centre[0] + c * (radius - width), centre[1] + s * (radius - width)))
    pygame.draw.polygon(surface, colour, outer + inner[::-1])
