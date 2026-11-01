"""Simulated T1-weighted MRI of an onion, made in the style of the head scan MRHead_1.nrrd.

An onion is a single object with many layers, nested like the layers of the head. The model follows
a real yellow onion:

    scales      eleven fleshy scales, 4 to 5 mm thick outside and 2 mm thick inside. Every scale runs
                from the base plate at the bottom up into the neck, so in a vertical cut the rings
                close at the top and at the bottom, and in a horizontal cut they are closed rings
    middle      two growing points side by side (a "double" onion), so the inner rings split in two
    between     a thin dark line between neighboring scales (their skins and a film of air), widening
                into small air gaps here and there, more of them toward the neck
    in a scale  a faint row of vascular bundles along its middle; a little darker near its surfaces
    base plate  the flat stem at the bottom, with a tuft of dry, trimmed roots under it
    neck        the dry neck on top, cut off at a slant
    outside     the outermost scale is drying out, so it is darker; the papery skin gives no MRI signal

Nothing is perfectly regular: the outline bulges a little, the scales thicken and thin, the inner
rings sit off-center, and the onion leans slightly, as it would lying in a scanner.

Lengths are in mm, in the onion's frame: z up along its axis, origin CENTER_Z above the middle of the
field of view.
"""

import math

import numpy as np

import head_style
from scan_simulation import (Scan, edge_coverage, ellipsoid_distance, gradient_norms, region_coverage,
                             sheet_coverage, smooth_noise, smoothstep, tilt_matrix)

VOXEL_MM = 0.55                    # 0.55 x 0.55 x 0.715 mm voxels: the onion fills the frame like the head
CENTER_Z = 6.0                     # the onion's origin sits this far above the middle of the field of view
DTYPE = np.uint8                   # 8 bits, one of the three sizes the assignment allows; ...
SCALE = 1.8                        # ... the head scan's values times 1.8 use its range, up to about 230
RNG_SEED = 2027
TILT_DEG, TILT_TOWARD_DEG = 7.0, 40.0

# --- Shape of the bulb ---------------------------------------------------------------------------
BASE_Z = -36.0                     # the scales start on the base plate here, ...
EQUATOR_Z = -4.0                   # ... are widest here ...
TOP_Z = 36.0                       # ... and close into the neck here
RADIUS_MM = 44.0                   # half-width at the widest point (before the pole radius is added)
TOP_SHAPE = 0.9                    # the shoulders: round, with a short pinch into the neck
BOTTOM_SHAPE = 0.4                 # the bottom: rounder still, flattening onto the base plate
PLATE_RADIUS_MM = 13.0             # the scales sit on the base plate across this radius
NECK_RADIUS_MM = 5.5
NECK_MM = 14.0                     # dry neck above the bulb ...
NECK_CUT_SLOPE = 0.2               # ... cut off at a slant
PLATE_CENTER_Z = BASE_Z - 1.0
PLATE_SEMI_AXES_MM = (14.0, 14.0, 3.6)
OUTLINE_BULGE = 0.03               # the outline deviates from the ideal by about 3% ...
OUTLINE_BULGE_MM = 30.0            # ... over this distance

# --- Layers --------------------------------------------------------------------------------------
SCALES_MM = (4.3, 5.0, 4.9, 4.6, 4.3, 4.0, 3.6, 3.2, 2.8, 2.4, 2.0)  # at the widest point, outside in
SCALE_WOBBLE = 0.02                # scales thicken and thin by about 0.9 mm ...
SCALE_WOBBLE_MM = 12.0             # ... over this distance
OFF_CENTER = (0.05, -0.03)         # the inner rings drift this far off the axis (fraction of the radius)
TWIN_SPLIT = 0.17                  # the two growing points sit this far from the axis (fraction of the radius) ...
TWIN_BALANCE = 0.56                # ... and one is a little larger than the other
TWIN_TOWARD_DEG = 65.0
SKIN_MM = 0.25                     # the dark line between neighboring scales
GAP_MM = 0.6                       # extra air between scales, in patches ...
GAP_PATCH_MM = 5.0                 # ... about this size
BUNDLE_SPACING_MM = 3.5            # vascular bundles along the middle of each scale
BUNDLE_SIGMA_MM = 0.4
ROOTS = 30

# --- MRI signal, on the head scan's scale (brain about 70, fat about 140) -----------------------
SCALE_SIGNAL = (62, 92, 95, 97, 99, 101, 102, 103, 104, 105, 106)   # outermost first: it is drying out
BUD_SIGNAL = 100                   # the growing points
SURFACE_DIP = 0.08                 # a scale is this much darker at its surfaces than in its middle
BUNDLE_SIGNAL = -16
PLATE_SIGNAL = 64
DRY_ROOT_SIGNAL, FRESH_ROOT_SIGNAL = 28, 55
NECK_DRYING = 0.8                  # the neck keeps only a fifth of the signal
GRAIN, PATCHY = 3.0, 3.0           # fine and coarse texture of the tissue


def profile(z):
    """Radius of the outermost scale at height z."""
    up = np.clip((z - EQUATOR_Z) / (TOP_Z - EQUATOR_Z), 0, 1)
    down = np.clip((EQUATOR_Z - z) / (EQUATOR_Z - BASE_Z), 0, 1)
    shoulder = np.maximum(np.cos(0.5 * np.pi * up), 0) ** TOP_SHAPE   # max: cos(pi/2) rounds below 0 in float32
    bottom = np.maximum(np.cos(0.5 * np.pi * down), 0) ** BOTTOM_SHAPE
    body = RADIUS_MM * np.where(z >= EQUATOR_Z, shoulder, bottom)
    pole = PLATE_RADIUS_MM + (NECK_RADIUS_MM - PLATE_RADIUS_MM) * smoothstep((z - BASE_Z) / (TOP_Z - BASE_Z))
    neck = NECK_RADIUS_MM * (1 - 0.3 * np.clip((z - TOP_Z) / NECK_MM, 0, 1))
    return np.where(z > TOP_Z, neck, np.sqrt(body ** 2 + pole ** 2))


def scale_boundaries() -> np.ndarray:
    """Normalized radius of the boundary inside each scale, outside in. The outermost scale's outer
    surface is at 1; the last boundary encloses the growing points."""
    widest = float(profile(np.float32(EQUATOR_Z)))
    return 1 - np.cumsum(SCALES_MM) / widest


def layer_field(x, y, z, rng):
    """Normalized radius: 1 on the outside of the outermost scale, smaller toward the middle.

    Every boundary between two scales is a surface where this field is constant. Near the axis the
    field is the product of the distances to the two growing points (Cassini ovals), so the outer
    rings are single loops and the inner ones split in two.
    """
    radius = profile(z) * (1 + OUTLINE_BULGE * head_style.noise(rng, OUTLINE_BULGE_MM, VOXEL_MM))
    u, v = x / radius, y / radius
    drift = np.clip(1 - np.sqrt(u * u + v * v), 0, 1) ** 2   # inner rings drift, the outside stays put
    u, v = u - OFF_CENTER[0] * drift, v - OFF_CENTER[1] * drift
    a = math.radians(TWIN_TOWARD_DEG)
    fu, fv = TWIN_SPLIT * math.cos(a), TWIN_SPLIT * math.sin(a)
    near = np.sqrt((u - fu) ** 2 + (v - fv) ** 2)
    far = np.sqrt((u + fu) ** 2 + (v + fv) ** 2)
    rho = near ** TWIN_BALANCE * far ** (1 - TWIN_BALANCE)
    rho += SCALE_WOBBLE * head_style.noise(rng, SCALE_WOBBLE_MM, VOXEL_MM)
    return rho.astype(np.float32), u, v


def scale_signal(rho, u, v, x, y, z, rng) -> np.ndarray:
    """MRI signal of the scales, as if they filled the whole field of view."""
    spacing = head_style.spacing(VOXEL_MM)
    per_voxel, per_mm = gradient_norms(rho, spacing)
    boundaries = scale_boundaries()
    outer = np.concatenate([[1.0], boundaries]).astype(np.float32)   # outer surface of scale m ...
    inner = np.concatenate([boundaries, [0.0]]).astype(np.float32)   # ... and its inner surface
    index = np.searchsorted(-boundaries, -rho)                       # scale of each voxel, 0 = outermost
    is_scale = index < len(boundaries)

    # Each scale's own signal, blended across the boundaries so that the steps do not alias.
    levels = np.array(SCALE_SIGNAL + (BUD_SIGNAL,), np.float32)
    signal = np.full(rho.shape, levels[0], np.float32)
    for m, b in enumerate(boundaries, start=1):
        signal += (levels[m] - levels[m - 1]) * edge_coverage((rho - b) / per_voxel)

    # A little darker near both surfaces of a scale.
    position = np.clip((outer[index] - rho) / (outer[index] - inner[index]), 0, 1)
    signal *= np.where(is_scale, 1 - SURFACE_DIP * (1 - np.sin(np.pi * position)), 1).astype(np.float32)

    # Vascular bundles: strands along the middle of each scale, from the base plate to the neck.
    widest = float(profile(np.float32(EQUATOR_Z)))
    middle = (outer + inner) / 2
    counts = np.maximum(np.rint(2 * np.pi * middle * widest / BUNDLE_SPACING_MM), 3)
    phases = rng.random(len(counts))
    turns = np.arctan2(v, u) / (2 * np.pi) * counts[index] + phases[index]
    along = (np.abs(turns - np.rint(turns)) * (2 * np.pi / counts[index]) * np.hypot(x, y)).astype(np.float32)
    across = (rho - middle[index]) / per_mm
    bundles = np.exp(-(along ** 2 + across ** 2) / (2 * BUNDLE_SIGMA_MM ** 2))
    crowded = smoothstep((profile(z) / widest - 0.3) / 0.4)   # near the poles they crowd together: fade them out
    signal += (BUNDLE_SIGNAL * bundles * crowded * is_scale).astype(np.float32)
    del turns, along, across, bundles

    # Dark lines between the scales, widening into air gaps in patches, more of them toward the neck.
    patches = np.clip(head_style.noise(rng, GAP_PATCH_MM, VOXEL_MM) - 1.4, 0, None)
    thickness = SKIN_MM + GAP_MM * patches * (1 + smoothstep((z - 10) / 25))
    covered = np.zeros_like(rho)
    for b in boundaries:
        covered += sheet_coverage((rho - b) / per_voxel, thickness * per_mm / per_voxel)
    signal *= 1 - np.minimum(covered, 1)

    # The neck and the shoulders below it are drying out, the outer scales most.
    drying = smoothstep((z - (TOP_Z - 8)) / 18) * (0.4 + 0.6 * np.clip(rho, 0, 1))
    return signal * (1 - NECK_DRYING * drying)


def root_paths(rng) -> list:
    """Center lines of the roots under the base plate: (points, radius, signal) for each root."""
    roots = []
    for _ in range(ROOTS):
        r0, a0 = 10.0 * math.sqrt(rng.random()), 2 * math.pi * rng.random()
        rim = PLATE_SEMI_AXES_MM[2] * math.sqrt(max(1 - (r0 / PLATE_SEMI_AXES_MM[0]) ** 2, 0))
        point = np.array([r0 * math.cos(a0), r0 * math.sin(a0), PLATE_CENTER_Z - rim + 0.5])
        fresh = rng.random() < 0.15
        length = rng.uniform(14, 22) if fresh else rng.uniform(4, 12)
        lean = math.radians(10 + 45 * r0 / 10 + rng.normal(0, 8))
        heading = a0 + rng.normal(0, 0.45)
        points = [point]
        for _ in range(4):
            step = np.array([math.sin(lean) * math.cos(heading), math.sin(lean) * math.sin(heading), -math.cos(lean)])
            point = point + step * length / 4
            points.append(point)
            lean = float(np.clip(lean + rng.normal(0, 0.25), 0.05, 1.45))
            heading += rng.normal(0, 0.3)
        radius = rng.uniform(0.55, 0.8) if fresh else rng.uniform(0.45, 0.65)
        roots.append((np.array(points), radius, FRESH_ROOT_SIGNAL if fresh else DRY_ROOT_SIGNAL))
    return roots


def draw_roots(signal, tissue, x, y, z, rotation, rng) -> None:
    """Paint the roots, each a thin tube along its path, into signal and tissue (in place)."""
    voxel = VOXEL_MM * head_style.SLICE_RATIO ** (1 / 3)   # mean voxel width
    for points, radius, value in root_paths(rng):
        # bounding box of the root in voxel indices
        patient = points @ rotation.T + np.array([0.0, 0.0, CENTER_Z])
        index = np.column_stack([patient[:, 1] / VOXEL_MM, -patient[:, 2] / VOXEL_MM,
                                 -patient[:, 0] / (head_style.SLICE_RATIO * VOXEL_MM)])
        index += (np.array(head_style.GRID) - 1) / 2
        low = np.maximum(np.floor(index.min(0)) - 3, 0).astype(int)
        high = np.minimum(np.ceil(index.max(0)) + 4, head_style.GRID).astype(int)
        box = tuple(slice(lo, hi) for lo, hi in zip(low, high))
        bx, by, bz = x[box], y[box], z[box]
        distance = np.full(bx.shape, np.inf, np.float32)
        for a, b in zip(points[:-1], points[1:]):
            d = b - a
            t = np.clip(((bx - a[0]) * d[0] + (by - a[1]) * d[1] + (bz - a[2]) * d[2]) / (d @ d), 0, 1)
            gap = np.sqrt((bx - a[0] - t * d[0]) ** 2 + (by - a[1] - t * d[1]) ** 2 + (bz - a[2] - t * d[2]) ** 2)
            np.minimum(distance, gap, out=distance)
        cover = edge_coverage((distance - radius) / voxel)
        signal[box] += (value - signal[box]) * cover
        np.maximum(tissue[box], cover, out=tissue[box])


def build() -> Scan:
    rng = np.random.default_rng(RNG_SEED)
    rotation = tilt_matrix(TILT_DEG, TILT_TOWARD_DEG)
    x, y, z = head_style.object_coordinates(VOXEL_MM, rotation, (0.0, 0.0, CENTER_Z))
    rho, u, v = layer_field(x, y, z, rng)
    signal = scale_signal(rho, u, v, x, y, z, rng)
    del u, v

    bulb = region_coverage(rho, 1.0)
    bulb *= region_coverage(BASE_Z - z)                                    # the scales start on the plate
    bulb *= region_coverage(z - (TOP_Z + NECK_MM + NECK_CUT_SLOPE * x))    # the neck is cut off
    plate = region_coverage(ellipsoid_distance(x, y, z - PLATE_CENTER_Z, PLATE_SEMI_AXES_MM))
    signal = signal * bulb * (1 - plate) + PLATE_SIGNAL * plate
    tissue = np.maximum(bulb, plate)
    del rho, bulb, plate
    draw_roots(signal, tissue, x, y, z, rotation, rng)

    signal += (GRAIN * smooth_noise(head_style.GRID, 0.8, rng)
               + PATCHY * head_style.noise(rng, 4.0, VOXEL_MM)) * tissue
    image = head_style.acquire(np.maximum(signal, 0), rng, DTYPE, SCALE)
    return Scan(image, head_style.spacing(VOXEL_MM))
