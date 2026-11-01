"""Simulated T1-weighted MRI of a croissant at high resolution: the large file for the speed test.

The assignment asks for 100 frames per second on a volume of 500 x 500 x 500 one-byte values, so this
scan holds 500 x 500 x 500 voxels of uint8, with cubic voxels of 0.37 mm. A croissant is worth that
resolution: inside, it is a honeycomb of thin sheets of dough with air between them.

A croissant is a single object with many layers, and each view in 3D Slicer shows something else:

    from above (Axial)        the crescent, with the turns of the rolled dough as bands along it
    from the front (Coronal)  a long, low arch through the body, in layers
    from the side (Sagittal)  the cross-section of the body: a spiral of rolled dough

It is about 16 cm from tip to tip, 9 cm from front to back and 6 cm tall. The model follows a real
croissant:

    shape    a triangle of laminated dough rolled up from its base and curved into a crescent, with the
             tips toward the front. The middle holds the most turns; toward the tips the outer turns
             end one after the other, which leaves shallow grooves across the top
    inside   each turn of dough is a stack of thin sheets with air between them, joined here and
             there, so the air forms long cells; a thin dense line marks where two turns touch
    crust    thin, dry and darker; the end of the dough lies on top of the middle
    filling  two sticks of chocolate rolled into the middle third, as in a chocolate croissant. Solid
             chocolate gives almost no MRI signal, so they are two dark bars inside the bright dough
    almonds  flaked almonds on top, rich in oil, so bright
    tray     the croissant sits on a tray, which gives no MRI signal, so its bottom is flat

The volume is built a slab at a time, so it needs only about 1.5 GB of memory.
Lengths are in mm, with the origin in the middle of the field of view and z up.
"""

import math

import numpy as np
from scipy import ndimage

import head_style
from scan_simulation import Scan, edge_coverage, sheet_coverage, value_noise

GRID = (500, 500, 500)
VOXEL_MM = 0.37                    # cubic voxels: a field of view of 185 x 185 x 185 mm
SLICE_RATIO = 1.0
DTYPE = np.uint8                   # one byte a voxel, as in the speed test of the assignment ...
SCALE = 1.8                        # ... with the head scan's values times 1.8, up to about 230
RNG_SEED = 2032
SLAB = 10                          # slices along i built at a time

# --- Shape ---------------------------------------------------------------------------------------
ARC_RADIUS_MM = 80.0               # the crescent bends around a circle of this radius ...
ARC_DEG = 70.0                     # ... out to this angle on each side of the middle
ARC_CENTER_Y = -70.0               # the circle's center, in front of the croissant
HALF_WIDTH_MM = 33.0               # the body at the middle: half its width across the crescent ...
HALF_HEIGHT_MM = 32.0              # ... and half its height, before the bottom is flattened
BOTTOM_Z = -30.0                   # the tray
SINK = 0.85                        # the body's middle sits this many half-heights above the tray
TAPER = (2.0, 0.75)                # the body thins toward the tips as (1 - |u|^2)^0.75 ...
TIP = 0.10                         # ... down to tips this thick (fraction of the middle)
TURNS = 3.6                        # turns of dough in the middle
GROOVE = 0.09                      # the outline dips by this fraction where an outer turn ends ...
GROOVE_WIDTH = 0.12                # ... over this fraction of a turn
TONGUE_DEG = 90.0                  # the end of the dough lies on top
BULGE = 0.04                       # the body bulges in and out by about this fraction ...
BULGE_MM = 25.0                    # ... over this distance along it

# --- Inside --------------------------------------------------------------------------------------
SHEETS = 4                         # sheets of dough in each turn ...
SHEET_MM = 0.55                    # ... this thick, ...
SHEET_WAVE = 0.25                  # ... wavy by this fraction of their spacing, so they touch here and there
WALL = 0.045                       # thin walls of dough between the sheets close off the air cells ...
CELL_MM = (7.0, 6.0)               # ... which are about this long along the croissant and along the dough
SEAM_MM = 0.8                      # where two turns of dough touch, the dough is dense
CRUST_MM = 1.0
CHOCOLATE_STICKS_MM = ((-4.0, -5.0), (6.0, 7.0))   # where the two sticks sit in the cross-section: mm out from
                                   # the middle of the crescent's curve and mm up from the middle of the body
STICK_MM = (10.0, 4.0)             # each stick's width and height ...
STICK_LENGTH_MM = 80.0             # ... and length along the croissant
ALMONDS = 26
ALMOND_MM = (9.0, 5.5, 0.6)        # half-length, half-width and half-thickness of a flake

# --- MRI signal, on the head scan's scale (brain about 70, fat about 140) -----------------------
DOUGH_SIGNAL = 105.0               # baked dough, rich in butter
SEAM_SIGNAL = 95.0
CRUST_SIGNAL = 45.0                # dry
CHOCOLATE_SIGNAL = 18.0            # solid chocolate
ALMOND_SIGNAL = 140.0
GRAIN, PATCHY = 3.0, 3.0


def body(u):
    """Size of the cross-section at position u along the croissant (0 in the middle, +-1 at the tips),
    as a fraction of the middle, and the number of turns of dough in it."""
    reach = np.clip(1 - np.abs(u) ** TAPER[0], 0, None) ** TAPER[1]
    tip = np.sqrt(np.clip(1 - (np.maximum(np.abs(u) - 0.97, 0) / 0.06) ** 2, 0, 1))   # rounded tips
    turns = TURNS * reach
    groove = 1 - GROOVE * np.exp(-((turns - np.rint(turns)) / GROOVE_WIDTH) ** 2) * (turns > 0.5)
    return np.hypot(reach, TIP * tip) * groove, turns + TURNS * TIP * tip


def slab_signal(rows, table, rng) -> tuple:
    """MRI signal and tissue fraction of the slices `rows` along i."""
    x3, y3, z3 = head_style.patient_axes(VOXEL_MM, GRID, SLICE_RATIO)
    x, y, z = x3, y3[rows], z3                                 # (1, 1, n), (slab, 1, 1), (1, n, 1)
    dy = y - ARC_CENTER_Y
    radius = np.hypot(x, dy)                                   # (slab, 1, n): from the crescent's center
    angle = np.arctan2(x, dy)
    u = angle / math.radians(ARC_DEG)
    along_mm = ARC_RADIUS_MM * angle
    size, turns = body(u)
    size = size * (1 + BULGE * value_noise([along_mm / BULGE_MM, 0 * u, 0 * u + 7.5], table))
    half_w, half_h = HALF_WIDTH_MM * size, HALF_HEIGHT_MM * size
    a = (radius - ARC_RADIUS_MM) / np.maximum(half_w, 1e-3)
    b = (z - (BOTTOM_Z + SINK * half_h)) / np.maximum(half_h, 1e-3)   # (slab, n, n)
    r = np.hypot(a, b)
    direction_mm = np.hypot(half_w * a, half_h * b) / np.maximum(r, 1e-6)   # radius of the outline this way
    phi = np.arctan2(b, a)

    # The croissant: inside its outline and above the tray.
    to_surface = (1 - r) * direction_mm
    inside = edge_coverage(-to_surface / VOXEL_MM) * edge_coverage((BOTTOM_Z - z) / VOXEL_MM)
    inside *= np.abs(u) < 1.03

    # The rolled dough: spiral coordinate psi grows by 1 per turn; the dough ends on top.
    behind = np.remainder(phi - math.radians(TONGUE_DEG), 2 * np.pi) / (2 * np.pi)
    psi = r * np.maximum(turns, 1e-3) - behind
    pitch = direction_mm / np.maximum(turns, 1e-3)             # thickness of one turn, mm
    seam = sheet_coverage((psi - np.rint(psi)) * pitch / VOXEL_MM, SEAM_MM / VOXEL_MM)
    # Position in the dough itself, as if unrolled: turns from its start (continuous along the
    # spiral, also where phi wraps around) and depth through it.
    strip_mm = (np.floor(psi) + behind) * 2 * np.pi * 20.0 * size
    depth = psi - np.floor(psi)
    wave = value_noise([along_mm / 10.0, strip_mm / 4.0, 0 * depth + 3.3], table)
    t = depth * SHEETS + SHEET_WAVE * wave / 0.37
    sheets = sheet_coverage((t - np.rint(t)) * pitch / SHEETS / VOXEL_MM, SHEET_MM / VOXEL_MM)
    cells = value_noise([along_mm / CELL_MM[0], strip_mm / CELL_MM[1], np.floor(t) + 50.0], table)
    walls = np.exp(-(cells / WALL) ** 2)
    dough = 1 - (1 - sheets) * (1 - walls)
    del wave, t, cells, walls, sheets

    # The crust, on the outline and on the bottom.
    crust = np.exp(-(np.minimum(to_surface, z - BOTTOM_Z) / CRUST_MM) ** 2)
    signal = (1 - crust) * (DOUGH_SIGNAL * dough * (1 - seam) + SEAM_SIGNAL * seam) + CRUST_SIGNAL * crust

    # The chocolate sticks, straight bars in the cross-section that follow the curve of the croissant.
    out_mm = radius - ARC_RADIUS_MM
    up_mm = z - (BOTTOM_Z + SINK * half_h)
    chocolate = np.zeros_like(signal)
    for out0, up0 in CHOCOLATE_STICKS_MM:
        bar = np.maximum(np.abs(out_mm - out0) - STICK_MM[0] / 2, np.abs(up_mm - up0) - STICK_MM[1] / 2)
        bar = np.maximum(bar, np.abs(along_mm) - STICK_LENGTH_MM / 2)
        np.maximum(chocolate, edge_coverage(bar / VOXEL_MM), out=chocolate)
    signal = (signal * (1 - chocolate) + CHOCOLATE_SIGNAL * chocolate) * inside

    texture = ndimage.gaussian_filter(rng.standard_normal(signal.shape, dtype=np.float32), 0.8, mode="reflect")
    texture /= texture.std()
    patchy = value_noise([along_mm / 8.0 + 0 * z, strip_mm / 8.0, depth * 2.0], table)
    signal += (GRAIN * texture + PATCHY * patchy / 0.37) * inside
    return np.maximum(signal, 0).astype(np.float32), inside


def add_almonds(signal, rng) -> None:
    """Scatter flaked almonds over the top of the croissant (in place)."""
    x3, y3, z3 = head_style.patient_axes(VOXEL_MM, GRID, SLICE_RATIO)
    reach = max(ALMOND_MM) + 2.0
    for _ in range(ALMONDS):
        u, a = rng.uniform(-0.6, 0.6), rng.uniform(-0.55, 0.55)   # along the croissant and across its top
        size, _ = body(np.array(u))
        half_w, half_h = HALF_WIDTH_MM * float(size), HALF_HEIGHT_MM * float(size)
        angle = u * math.radians(ARC_DEG)
        out = np.array([math.sin(angle), math.cos(angle), 0.0])      # away from the crescent's center
        across = math.sqrt(1 - a * a)
        surface = np.array([0.0, ARC_CENTER_Y, BOTTOM_Z + SINK * half_h + half_h * across]) \
            + (ARC_RADIUS_MM + a * half_w) * out
        normal = np.array([0.0, 0.0, 1.0]) + half_h * a / (half_w * across) * out
        normal /= np.linalg.norm(normal)
        first = np.cross(normal, rng.normal(size=3))
        first /= np.linalg.norm(first)
        second = np.cross(normal, first)
        center = surface + normal * (ALMOND_MM[2] + 0.3)
        # voxels near the flake: i follows y, j follows -z, k follows -x
        index = np.array([center[1], -center[2], -center[0]]) / VOXEL_MM + (np.array(GRID) - 1) / 2
        low = np.maximum(np.floor(index - reach / VOXEL_MM), 0).astype(int)
        high = np.minimum(np.ceil(index + reach / VOXEL_MM) + 1, GRID).astype(int)
        box = tuple(slice(lo, hi) for lo, hi in zip(low, high))
        dx = x3[:, :, box[2]] - center[0]
        dy = y3[box[0]] - center[1]
        dz = z3[:, box[1]] - center[2]
        size_ratio = sum(((dx * e[0] + dy * e[1] + dz * e[2]) / r) ** 2
                         for e, r in zip((first, second, normal), ALMOND_MM)) ** 0.5
        flake = edge_coverage((size_ratio - 1) * ALMOND_MM[2] / VOXEL_MM)
        signal[box] = signal[box] * (1 - flake) + ALMOND_SIGNAL * flake


def build() -> Scan:
    rng = np.random.default_rng(RNG_SEED)
    table = rng.uniform(-1, 1, 1 << 16).astype(np.float32)
    signal = np.zeros(GRID, np.float32)
    for start in range(0, GRID[0], SLAB):
        rows = slice(start, min(start + SLAB, GRID[0]))
        signal[rows], _ = slab_signal(rows, table, rng)
    add_almonds(signal, rng)
    image = head_style.acquire_large(signal, rng, DTYPE, SCALE, SLAB)
    return Scan(image, head_style.spacing(VOXEL_MM, SLICE_RATIO))
