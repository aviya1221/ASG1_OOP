"""The slow reference projection (docs/TESTING.md, section 3.2).

It follows docs/SRS.md, section 3.4, one pixel at a time in Python floats, and shares no code with the package.
It decides "inside the shape" by the side of every edge, not by row spans as the package does,
so a mistake in either one shows up as a difference.
"""

import math

import numpy as np

EPS = 1e-6


def dot(u, v):
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


def sub(u, v):
    return (u[0] - v[0], u[1] - v[1], u[2] - v[2])


def scale(u, k):
    return (u[0] * k, u[1] * k, u[2] * k)


def length(u):
    return math.sqrt(dot(u, u))


class Reference:
    """The geometry of one plane, computed from the text of FR-15 to FR-17."""

    def __init__(self, points):
        points = [tuple(float(x) for x in p) for p in points]
        if len(points) == 3:
            p0, b, c = points
            self.corners = [p0, c, b]
        else:
            p0, q, b, c = points
            self.corners = [p0, q, c, b]
        base = sub(c, b)
        self.right = scale(base, 1 / length(base))
        w = sub(sub(b, p0), scale(self.right, dot(sub(b, p0), self.right)))
        self.down = scale(w, 1 / length(w))
        self.st = [(dot(sub(v, p0), self.right), dot(sub(v, p0), self.down)) for v in self.corners]
        s = [p[0] for p in self.st]
        t = [p[1] for p in self.st]
        self.s_min, self.t_min = min(s), min(t)
        self.cols = math.floor(max(s) - self.s_min + EPS) + 1
        self.rows = math.floor(max(t) - self.t_min + EPS) + 1
        self.corner = tuple(p0[k] + self.s_min * self.right[k] + self.t_min * self.down[k] for k in range(3))
        area = sum(self.st[i][0] * self.st[i - 1][1] - self.st[i - 1][0] * self.st[i][1] for i in range(len(self.st)))
        self.turn = 1.0 if area <= 0 else -1.0

    def edge_distances(self, s, t):
        """Signed distance of (s, t) from every edge, positive on the inner side."""
        distances = []
        n = len(self.st)
        for i in range(n):
            (sp, tp), (sq, tq) = self.st[i], self.st[(i + 1) % n]
            edge = math.hypot(sq - sp, tq - tp)
            if edge < 1e-12:
                continue
            distances.append(self.turn * ((sq - sp) * (t - tp) - (tq - tp) * (s - sp)) / edge)
        return distances

    def inside(self, row, col):
        """FR-18: the pixel's point is inside the shape, or on its edge within EPS."""
        return all(d >= -EPS for d in self.edge_distances(self.s_min + col, self.t_min + row))

    def near_edge(self, row, col, margin=1e-4):
        """The point is so close to an edge that the two tolerances of FR-18 may disagree."""
        return any(abs(d) < margin for d in self.edge_distances(self.s_min + col, self.t_min + row))

    def point(self, row, col):
        return tuple(self.corner[k] + col * self.right[k] + row * self.down[k] for k in range(3))

    def project(self, data):
        """The image of the plane in the volume data (FR-19, FR-20)."""
        image = np.zeros((self.rows, self.cols), dtype=data.dtype)
        for row in range(self.rows):
            for col in range(self.cols):
                if not self.inside(row, col):
                    continue
                index = [math.floor(x + 0.5) for x in self.point(row, col)]
                if all(0 <= index[k] < data.shape[k] for k in range(3)):
                    image[row, col] = data[index[0], index[1], index[2]]
        return image


def random_plane(rng, shape, max_side=40):
    """A random triangle or isosceles trapezoid near a volume of this shape, with an image of at most max_side pixels."""
    center = np.array([rng.uniform(-0.3 * n, 1.3 * n) for n in shape])
    right = rng.normal(size=3)
    right /= np.linalg.norm(right)
    down = rng.normal(size=3)
    down -= (down @ right) * right
    down /= np.linalg.norm(down)
    height = rng.uniform(1, max_side - 1)
    base = rng.uniform(1, max_side - 1)
    if rng.random() < 0.5:
        apex = center - height / 2 * down + rng.uniform(-base / 2, base / 2) * right
        b = center + height / 2 * down - base / 2 * right
        return [apex, b, b + base * right]
    top = rng.uniform(0.5, base)
    a1 = center - height / 2 * down - top / 2 * right
    b = center + height / 2 * down - base / 2 * right
    return [a1, a1 + top * right, b, b + base * right]
