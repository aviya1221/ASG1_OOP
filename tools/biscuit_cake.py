"""Simulated T1-weighted MRI of a biscuit cake, made in the style of the head scan MRHead_1.nrrd.

A biscuit cake is a single object with many layers: seven layers of tea biscuits soaked in milk, a layer
of vanilla cream between each two, and chocolate ganache on top, built in a loaf pan. It is a box
with three clearly different sides, 24 cm long, 11 cm wide and 8 cm tall, so each view in 3D Slicer
shows something else:

    from above (Axial)        one layer of biscuits: two across and five along, with cream in the joints
    from the front (Coronal)  the 11 cm short side: stripes of biscuit and cream
    from the side (Sagittal)  the 24 cm long side: the same stripes, with the joints between biscuits

The model follows a real cake:

    biscuits  petit-beurre biscuits, 54 x 58 mm with a scalloped edge, soaked in milk: wet near their
              surfaces and drier, so darker, in their middle. Along the cake the layers alternate
              between two patterns, with broken pieces at the ends, so the joints do not line up
    cream     vanilla cream between the layers and in the joints between biscuits; it bulges out a
              little at the sides
    ganache   chocolate on top, rich in fat, so it is the brightest part
    tray      the cake stands on a tray, which gives no MRI signal

The layers are level, so they lie along the voxel rows. Lengths are in mm, in the cake's frame:
u across the cake (toward the patient's left), w along it (toward the back) and z up; the cake's
middle is at CENTER_MM in the field of view.
"""

import math

import numpy as np
from scipy import ndimage

import head_style
from scan_simulation import Scan, region_coverage, smooth_noise

VOXEL_MM = 1.0                     # the head scan's own voxel: 1 x 1 x 1.3 mm
RNG_SEED = 2030
TURN_DEG = 1.5                     # the cake is not quite square to the scanner
CENTER_MM = (10.0, 0.0)            # its middle sits this far to the left (x) and back (y) of the middle of
                                   # the field of view, so the middle slices do not fall into a joint

# --- Shape ---------------------------------------------------------------------------------------
LENGTH_MM, WIDTH_MM = 240.0, 110.0
CORNER_MM = 3.0
BISCUIT_MM = (54.0, 58.0)          # a whole biscuit, across and along the cake
BISCUIT_CORNER_MM = 4.0
SCALLOP_MM = 4.6                   # the edge of a biscuit has a bump every 4.6 mm ...
SCALLOP_DEPTH_MM = 0.8             # ... this high
BROKEN_ROUGHNESS_MM = 0.9          # the broken edge of a piece is this rough
HOLE_SPACING_MM = (10.0, 8.5)      # the pricked holes of a biscuit: a 4 x 6 grid, across x along ...
HOLE_RADIUS_MM = 0.7               # ... of holes this wide, which soak up milk
JOINT_MM = 2.0
ACROSS = (54.0, 54.0)              # the pieces across the cake, mm
ALONG = ((15.0, 58.0, 58.0, 58.0, 43.0),   # the pieces along the cake, from the front; the two
         (44.0, 58.0, 58.0, 58.0, 14.0))   # patterns alternate from the bottom layer up
PLACEMENT_MM = 0.6                 # each biscuit is placed by hand: off by about this much ...
PLACEMENT_DEG = 1.2                # ... and turned by about this much
BISCUIT_LAYERS = 7
BISCUIT_THICKNESS_MM = 5.5         # soaked
CREAM_MM = 5.9
BULGE_MM = 1.8                     # the cream bulges out of the sides by up to this much
BULGE_PATCH_MM = 15.0
GANACHE_MM = 5.0
BOTTOM_Z = -36.95                  # puts the middle of the fourth biscuit layer at the middle of the field of view

# --- MRI signal, on the head scan's scale (brain about 70, fat about 140) -----------------------
SOAK_PROFILE = ((0.22, 80.0), (0.38, 70.0), (0.62, 60.0), (0.78, 70.0), (1.0, 80.0))  # (up to fraction of
                                   # the biscuit's thickness, signal): wet surfaces, a drier middle
HOLE_SIGNAL = 84.0                 # milk in the holes
CREAM_SIGNAL = 122.0
GANACHE_SIGNAL = 150.0
GRAIN, PATCHY = 3.0, 3.0


def column_coordinates():
    """Cake-frame coordinates (u across, w along) of every column (i, k) of the scan."""
    x3, y3, _ = head_style.patient_axes(VOXEL_MM)
    dx, dy = x3[:, 0, :] - CENTER_MM[0], y3[:, 0, :] - CENTER_MM[1]   # (1, 130) and (256, 1)
    c, s = math.cos(math.radians(TURN_DEG)), math.sin(math.radians(TURN_DEG))
    return c * dx + s * dy, -s * dx + c * dy


def rounded_box(u, w, half_u, half_w, corner):
    """Signed distance (mm, negative inside) to a rectangle with rounded corners, centered at the origin;
    also the distances past each pair of sides (positive outside), to tell which side is nearest."""
    qu, qw = np.abs(u) - (half_u - corner), np.abs(w) - (half_w - corner)
    distance = np.hypot(np.maximum(qu, 0), np.maximum(qw, 0)) + np.minimum(np.maximum(qu, qw), 0) - corner
    return distance, qu, qw


def rough_edge(t, rng, modes: int = 10, period_mm: float = 60.0):
    """A smooth random function of a position t (mm) along an edge, mean 0 and std 1."""
    edge = np.zeros_like(t)
    for m in range(1, modes + 1):
        edge += rng.normal() / m * np.cos(2 * np.pi * m * t / period_mm + rng.uniform(0, 2 * np.pi))
    return edge / math.sqrt(sum(0.5 / m ** 2 for m in range(1, modes + 1)))


def biscuit(u, w, center, size, broken_end: int, rng):
    """Fractions of every column covered by one biscuit, or by a piece broken off one, and by its holes.
    broken_end is +1 or -1 if the piece's back or front edge (along the cake) is a broken edge, else 0."""
    angle = math.radians(rng.normal(0, PLACEMENT_DEG))
    du = u - center[0] - rng.normal(0, PLACEMENT_MM)
    dw = w - center[1] - rng.normal(0, PLACEMENT_MM)
    c, s = math.cos(angle), math.sin(angle)
    pu, pw = c * du + s * dw, -s * du + c * dw
    distance, qu, qw = rounded_box(pu, pw, size[0] / 2, size[1] / 2, BISCUIT_CORNER_MM)
    along_edge = np.where(qu > qw, pw, pu)                     # position along the nearest edge
    scallops = SCALLOP_DEPTH_MM * 0.5 * (1 + np.cos(2 * np.pi * along_edge / SCALLOP_MM))
    if broken_end:
        broken = (qw > qu) & (np.sign(pw) == broken_end)
        roughness = BROKEN_ROUGHNESS_MM * rough_edge(pu, rng)
        distance = distance - np.where(broken, roughness, scallops)
    else:
        distance = distance - scallops
    covered = region_coverage(distance)
    # the holes sit on a grid centered on the whole biscuit, so a broken piece keeps only some of them
    whole_w = pw - broken_end * (BISCUIT_MM[1] - size[1]) / 2
    nearest_u = np.clip(np.rint(pu / HOLE_SPACING_MM[0] - 0.5) + 0.5, -1.5, 1.5) * HOLE_SPACING_MM[0]
    nearest_w = np.clip(np.rint(whole_w / HOLE_SPACING_MM[1] - 0.5) + 0.5, -2.5, 2.5) * HOLE_SPACING_MM[1]
    holes = region_coverage(np.hypot(pu - nearest_u, whole_w - nearest_w) - HOLE_RADIUS_MM)
    return covered, np.minimum(holes, covered) * region_coverage(distance + 3.0)


def biscuit_layer(u, w, pattern, rng):
    """Fractions of every column covered by biscuits and by their holes, in one layer."""
    covered = np.zeros(np.broadcast_shapes(u.shape, w.shape), np.float32)
    holes = np.zeros_like(covered)
    pieces = ALONG[pattern]
    starts = -LENGTH_MM / 2 + np.concatenate([[0.0], np.cumsum(np.array(pieces[:-1]) + JOINT_MM)])
    for n, (start, length) in enumerate(zip(starts, pieces)):
        broken_end = -1 if n == 0 else (1 if n == len(pieces) - 1 else 0)
        if length == BISCUIT_MM[1]:
            broken_end = 0
        center_w = start + length / 2
        for m, width in enumerate(ACROSS):
            center_u = -WIDTH_MM / 2 + width / 2 + m * (width + JOINT_MM)
            piece, piece_holes = biscuit(u, w, (center_u, center_w), (width, length), broken_end, rng)
            np.maximum(covered, piece, out=covered)
            np.maximum(holes, piece_holes, out=holes)
    return covered, holes


def bulging_outline(u, w, bulge, rng) -> np.ndarray:
    """Fraction of every column inside the cake's outline, pushed out by up to `bulge` mm in patches."""
    shape = np.broadcast_shapes(u.shape, w.shape)
    spacing = head_style.spacing(VOXEL_MM)
    patches = ndimage.gaussian_filter(rng.standard_normal(shape), (BULGE_PATCH_MM / spacing[0],
                                                                  BULGE_PATCH_MM / spacing[2]))
    patches = np.clip(0.5 + 0.5 * patches / patches.std(), 0, 1)
    distance, _, _ = rounded_box(u, w, WIDTH_MM / 2, LENGTH_MM / 2, CORNER_MM)
    return region_coverage(distance - bulge * patches)


def stack(rng):
    """The cake from the bottom up, as (bottom, top, signal, cover) slabs. For every column (i, k),
    cover is the part of the column that the slab fills and signal is its MRI signal times that part."""
    u, w = column_coordinates()
    outline, _, _ = rounded_box(u, w, WIDTH_MM / 2, LENGTH_MM / 2, CORNER_MM)
    filled = region_coverage(outline + 0.5)                # the biscuit layers, up to the sides of the pan
    slabs = []
    z = BOTTOM_Z
    for layer in range(BISCUIT_LAYERS):
        biscuits, holes = biscuit_layer(u, w, layer % 2, rng)
        joints = np.maximum(filled - biscuits, 0)
        start = 0.0
        for end, signal in SOAK_PROFILE:
            bottom, top = z + start * BISCUIT_THICKNESS_MM, z + end * BISCUIT_THICKNESS_MM
            slabs.append((bottom, top, signal * (biscuits - holes) + HOLE_SIGNAL * holes + CREAM_SIGNAL * joints,
                          biscuits + joints))
            start = end
        z += BISCUIT_THICKNESS_MM
        if layer == BISCUIT_LAYERS - 1:
            break
        for part, bulge in ((0.25, 0.4), (0.75, 1.0), (1.0, 0.4)):   # the cream bulges most at mid-height
            cream = bulging_outline(u, w, bulge * BULGE_MM, rng)
            slabs.append((slabs[-1][1], z + part * CREAM_MM, CREAM_SIGNAL * cream, cream))
        z += CREAM_MM
    ganache = bulging_outline(u, w, 0.5, rng)
    slabs.append((z, z + 0.6 * GANACHE_MM, GANACHE_SIGNAL * ganache, ganache))
    rounded_top = region_coverage(outline + 1.2)                  # the top edge of the ganache is rounded
    slabs.append((z + 0.6 * GANACHE_MM, z + GANACHE_MM, GANACHE_SIGNAL * rounded_top, rounded_top))
    return slabs


def build() -> Scan:
    rng = np.random.default_rng(RNG_SEED)
    _, _, z3 = head_style.patient_axes(VOXEL_MM)
    height = head_style.spacing(VOXEL_MM)[1]
    low, high = z3[0, :, 0] - height / 2, z3[0, :, 0] + height / 2
    signal = np.zeros(head_style.GRID, np.float32)
    tissue = np.zeros(head_style.GRID, np.float32)
    for bottom, top, column_signal, cover in stack(rng):
        part = np.clip(np.minimum(top, high) - np.maximum(bottom, low), 0, None) / height   # of each voxel's height
        rows = np.nonzero(part)[0]
        signal[:, rows, :] += part[rows][None, :, None] * column_signal[:, None, :]
        tissue[:, rows, :] += part[rows][None, :, None] * cover[:, None, :]
    signal += (GRAIN * smooth_noise(head_style.GRID, 0.8, rng)
               + PATCHY * head_style.noise(rng, 5.0, VOXEL_MM)) * np.minimum(tissue, 1)
    image = head_style.acquire(np.maximum(signal, 0), rng)
    return Scan(image, head_style.spacing(VOXEL_MM))
