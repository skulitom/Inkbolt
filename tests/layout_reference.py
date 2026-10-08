"""Exhaustive original partition oracle; independent of the engine's optimizer."""
from fractions import Fraction as F


def optimum(sizes, width, gap=(0, 0)):
    sizes = [(F(w), F(h)) for w, h in sizes]
    width, gx, gy = F(width), F(gap[0]), F(gap[1])
    n = len(sizes)
    candidates = []
    for mask in range(1 << (n - 1)):
        ends = [i + 1 for i in range(n - 1) if mask & (1 << i)] + [n]
        start, height = 0, F(0)
        for end in ends:
            row = sizes[start:end]
            if sum(w for w, _ in row) + gx * (len(row) - 1) > width:
                break
            height += max(h for _, h in row) + (gy if start else 0)
            start = end
        else:
            candidates.append((height, len(ends), ends))
    return min(candidates) if candidates else None


def rectangle_bounds(geometry, matrix):
    x, y, w, h = [geometry[k] for k in ('x', 'y', 'width', 'height')]
    a, b, c, d, e, f = matrix
    points = [(a*u+c*v+e, b*u+d*v+f) for u, v in [(x,y), (x+w,y), (x+w,y+h), (x,y+h)]]
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]
