"""Synthetic T1-weighted MRI scan of a rectangular three-layer cake, made to look like DATA/MRHead_1.nrrd.

The cake is rectangular and sits square to the scanner axes, so every view is easy to recognize:
an axial slice shows the 17 x 11 cm top view, a coronal slice the long side with all the layers,
and a sagittal slice the short side. Inside are three sponge layers (chocolate, vanilla, and vanilla
with chocolate chips) separated by a ganache filling and a whipped-cream filling with strawberry
slices, and a chocolate truffle with a hazelnut hidden in the middle. Outside are buttercream
frosting smoothed flat on top, a thin ganache glaze, and halved strawberries along the back.
A corner piece has already been cut out. The cake stands on a cardboard cake board on a platter.

The material map is imaged the way the head scan was: T1-weighted MRI with 1 x 1 x 1.3 mm voxels,
the same intensity scale, the same noise level and the same black background. Fat-rich materials
(buttercream, hazelnut, ganache, cream) are bright like the scalp fat, the moist sponge is gray like
brain tissue, water-rich strawberries are darker, and solid chocolate, cardboard, porcelain and air
give almost no signal, as bone and air are dark in the head scan. The material map itself is kept
as exact ground truth.

All lengths are in millimeters, in scanner coordinates with the origin at voxel (0, 0, 0).
"""

import math
from dataclasses import dataclass
from enum import IntEnum
from statistics import NormalDist

import numpy as np

from scan_simulation import (Scan, bias_field, kspace_window, paint_ellipsoid, quantize, rician_noise,
                             smooth_noise, voxel_box)

# --- Scan geometry, as in the head scan: 1 mm pixels and 1.3 mm between slices ----------------
SPACING_MM = (1.0, 1.0, 1.3)
SHAPE = (256, 180, 96)             # voxels: a 256 x 180 x 124.8 mm field of view
RNG_SEED = 7

# --- Cake layout (mm); the cake is centered on the vertical line x = CX, y = CY ---------------
CX, CY = 128.0, 90.0
PLATTER_HALF = (98.0, 68.0)        # porcelain platter, 196 x 136 mm ...
PLATTER_Z = (8.0, 14.0)            # ... 6 mm thick ...
PLATTER_CORNER_MM = 12.0
RIM_MM = (2.0, 8.0)                # ... with an edge that rises 2 mm over its outer 8 mm
BOARD_HALF = (88.0, 58.0)          # cardboard cake board, 176 x 116 mm ...
BOARD_Z = (14.0, 16.0)             # ... 2 mm thick
CAKE_HALF = (81.0, 51.0)           # the layered cake inside the frosting, 162 x 102 mm
LAYER_Z = (16.0, 38.0, 44.0, 66.0, 74.0, 96.0)  # heights of the layer boundaries, bottom to top;
                                                 # the baker trimmed the layers flat
FROSTING_MM = 4.0                  # on the sides; the top is smoothed flat ...
FROSTING_TOP_MM = 100.5            # ... at this height
GLAZE_MM = 2.0
TRUFFLE_CENTER = (CX, CY, 55.0)
TRUFFLE_RADIUS_MM = 16.0
TRUFFLE_SHELL_MM = 2.5
CHIPS = 70
BERRIES = 5
CUT_CORNER = (CX + 40.0, CY - 10.0)  # the piece already eaten: x >= 168 and y <= 80

# --- MRI acquisition, matched to the head scan -------------------------------------------------
KSPACE_KEEP = 0.85                 # fraction of the spatial frequencies the scan measures ...
KSPACE_TAPER = 0.3                 # ... with a smooth roll-off over the outer part of them
BIAS_GRADIENT = (0.05, -0.04, 0.04)
BIAS_CURVATURE = 0.04
NOISE_SIGMA = 4.5                  # as measured in the head scan's white matter
NOISE_FLOOR = 6.0                  # subtracted, then clipped at 0: the head scan's black background


class Material(IntEnum):
    """Label values of cake_3layers.seg.nrrd."""
    BACKGROUND = 0
    PLATTER = 1
    CAKE_BOARD = 2
    CHOCOLATE_SPONGE = 3
    GANACHE = 4
    VANILLA_SPONGE = 5
    WHIPPED_CREAM = 6
    CHIP_SPONGE = 7
    CHOCOLATE_CHIP = 8
    STRAWBERRY = 9
    BUTTERCREAM = 10
    GLAZE = 11
    TRUFFLE_SHELL = 12
    TRUFFLE_FILLING = 13
    HAZELNUT = 14


# The layered part of the cake from bottom to top, and the layers that are baked sponge.
STACK = (Material.CHOCOLATE_SPONGE, Material.GANACHE, Material.VANILLA_SPONGE,
         Material.WHIPPED_CREAM, Material.CHIP_SPONGE)
SPONGES = (Material.CHOCOLATE_SPONGE, Material.VANILLA_SPONGE, Material.CHIP_SPONGE)


@dataclass(frozen=True)
class Signal:
    """How a material looks in the T1-weighted scan, on the head scan's scale
    (gray matter about 70, white matter about 90, scalp fat about 140)."""
    mean: float
    grain: float = 0.0     # std of the fine texture (pores, crumbs)
    patchy: float = 0.0    # std of the slow variation
    holes: float = 0.0     # share of the material taken by larger gas holes


SIGNAL = {
    Material.BACKGROUND: Signal(0),
    Material.PLATTER: Signal(0),                   # porcelain gives no MRI signal
    Material.CAKE_BOARD: Signal(3),                # dry cardboard, almost none
    Material.CHOCOLATE_SPONGE: Signal(66, grain=8, patchy=4, holes=0.025),
    Material.GANACHE: Signal(122, grain=4, patchy=3),
    Material.VANILLA_SPONGE: Signal(74, grain=9, patchy=5, holes=0.06),
    Material.WHIPPED_CREAM: Signal(105, grain=6, patchy=4),
    Material.CHIP_SPONGE: Signal(72, grain=9, patchy=5, holes=0.04),
    Material.CHOCOLATE_CHIP: Signal(16, grain=3),  # solid cocoa butter: almost no signal
    Material.STRAWBERRY: Signal(44, grain=4, patchy=3),  # mostly water: long T1, so darker
    Material.BUTTERCREAM: Signal(150, grain=5, patchy=4),  # mostly fat: short T1, bright like scalp fat
    Material.GLAZE: Signal(122, grain=4),
    Material.TRUFFLE_SHELL: Signal(18, grain=3),
    Material.TRUFFLE_FILLING: Signal(118, grain=4),
    Material.HAZELNUT: Signal(155, grain=6),       # nut oil
}
CRUST_SIGNAL = -12   # the baked surfaces of the sponges are drier, so darker ...
CRUST_MM = 1.5       # ... down to this depth

# Segment colors (RGB, 0..1) for the segmentation file.
COLORS = {
    Material.PLATTER: (0.92, 0.92, 0.95),
    Material.CAKE_BOARD: (0.75, 0.60, 0.40),
    Material.CHOCOLATE_SPONGE: (0.40, 0.22, 0.12),
    Material.GANACHE: (0.25, 0.12, 0.06),
    Material.VANILLA_SPONGE: (0.96, 0.87, 0.60),
    Material.WHIPPED_CREAM: (1.00, 0.98, 0.92),
    Material.CHIP_SPONGE: (0.93, 0.80, 0.55),
    Material.CHOCOLATE_CHIP: (0.30, 0.15, 0.08),
    Material.STRAWBERRY: (0.85, 0.10, 0.15),
    Material.BUTTERCREAM: (1.00, 0.85, 0.88),
    Material.GLAZE: (0.35, 0.18, 0.10),
    Material.TRUFFLE_SHELL: (0.45, 0.25, 0.12),
    Material.TRUFFLE_FILLING: (0.55, 0.32, 0.18),
    Material.HAZELNUT: (0.70, 0.50, 0.30),
}

# Large materials from brightest to darkest in the scan; the self-check asserts this order.
CONTRAST = (Material.BUTTERCREAM, Material.WHIPPED_CREAM, Material.VANILLA_SPONGE, Material.CHOCOLATE_SPONGE)


# --- Geometry helpers --------------------------------------------------------------------------

def grid_mm():
    """Voxel-center coordinates in mm, as broadcastable float32 arrays x (nx,1,1), y (1,ny,1), z (1,1,nz)."""
    return tuple((np.arange(n, dtype=np.float32) * s).reshape([-1 if a == axis else 1 for a in range(3)])
                 for axis, (n, s) in enumerate(zip(SHAPE, SPACING_MM)))


def ogrid_mm(region):
    """Coordinates in mm of the voxels in a region (a tuple of slices), as broadcastable arrays."""
    return tuple(i * s for i, s in zip(np.ogrid[region], SPACING_MM))


def to_voxel(point_mm) -> np.ndarray:
    return np.asarray(point_mm, float) / SPACING_MM


def box_around(center_mm, half_mm: float) -> tuple:
    """Slices of the voxels within half_mm of a point, clipped to the volume."""
    return voxel_box(to_voxel(center_mm), half_mm / np.array(SPACING_MM), SHAPE)


def rounded_rectangle(x, y, half, corner):
    """Signed distance (mm) to a rounded rectangle centered on the cake axis; negative inside."""
    qx = np.abs(x - CX) - (half[0] - corner)
    qy = np.abs(y - CY) - (half[1] - corner)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - corner


def smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    """A uniformly random 3D rotation matrix, from a random unit quaternion."""
    q = rng.normal(size=4)
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def strawberry_outline(x, y, center, heading: float, length: float, radius: float):
    """For points around a strawberry lying along `heading`, return the signed distance across its
    axis and the berry's half-width there (-1 beyond the stem end or the tip). The outline is a
    teardrop: round at the stem end, widest a third of the way along, pointed at the tip."""
    dx, dy = x - center[0], y - center[1]
    t = (dx * math.cos(heading) + dy * math.sin(heading)) / length + 0.5  # 0 at the stem end, 1 at the tip
    side = -dx * math.sin(heading) + dy * math.cos(heading)
    inside = (t >= 0) & (t <= 1)
    half_width = radius * 2.6 * np.sqrt(np.clip(t, 0, 1)) * (1 - np.clip(t, 0, 1))  # peaks at radius
    return side, np.where(inside, half_width, -1.0)


# --- The cake ----------------------------------------------------------------------------------

def material_map(rng: np.random.Generator):
    """Label every voxel with its material. Returns the labels, the sponges' baked crust and landmarks."""
    x, y, z = grid_mm()
    x2, y2 = x[:, :, 0], y[:, :, 0]
    labels = np.zeros(SHAPE, np.uint8)

    add_platter_and_board(labels, x2, y2, z)
    crust = add_layers(labels, rounded_rectangle(x2, y2, CAKE_HALF, 3.0)[..., None], z)
    add_frosting_and_glaze(labels, x2, y2, z)
    add_strawberry_slices(labels, rng)
    chips = add_chips(labels, rng)
    nut = add_truffle(labels, rng)
    berries = add_berries(labels, rng)
    cut_corner(labels, x, y, z)
    return labels, crust, landmarks(chips, nut, berries)


def add_platter_and_board(labels, x2, y2, z) -> None:
    """A porcelain platter with a raised edge, and a cardboard cake board on it."""
    footprint = rounded_rectangle(x2, y2, PLATTER_HALF, PLATTER_CORNER_MM)
    rim = RIM_MM[0] * smoothstep((footprint + RIM_MM[1]) / RIM_MM[1])
    platter = (footprint <= 0)[..., None] & (z >= PLATTER_Z[0]) & (z < (PLATTER_Z[1] + rim)[..., None])
    labels[platter] = Material.PLATTER
    board = (rounded_rectangle(x2, y2, BOARD_HALF, 2.0) <= 0)[..., None] & (z >= BOARD_Z[0]) & (z < BOARD_Z[1])
    labels[board] = Material.CAKE_BOARD


def add_layers(labels, inner, z) -> np.ndarray:
    """Stack the sponges and fillings inside the frosting. Returns the sponges' baked crust:
    the voxels near their top, bottom and sides."""
    crust = np.zeros(SHAPE, bool)
    inside = inner <= 0
    for material, low, high in zip(STACK, LAYER_Z[:-1], LAYER_Z[1:]):
        layer = inside & (z >= low) & (z < high)
        labels[layer] = material
        if material in SPONGES:
            crust |= layer & ((z - low < CRUST_MM) | (high - z < CRUST_MM) | (inner > -CRUST_MM))
    return crust


def add_frosting_and_glaze(labels, x2, y2, z) -> None:
    """Buttercream on the sides and over the top, smoothed flat, under a thin ganache glaze."""
    half = (CAKE_HALF[0] + FROSTING_MM, CAKE_HALF[1] + FROSTING_MM)
    covered = (rounded_rectangle(x2, y2, half, 7.0) <= 0)[..., None]
    frosting = covered & (z >= LAYER_Z[0]) & (z < FROSTING_TOP_MM) & (labels == Material.BACKGROUND)
    labels[frosting] = Material.BUTTERCREAM
    labels[covered & (z >= FROSTING_TOP_MM) & (z < FROSTING_TOP_MM + GLAZE_MM)] = Material.GLAZE


def add_strawberry_slices(labels, rng) -> None:
    """Lengthwise strawberry slices, 5 mm thick, laid flat in the whipped cream around the truffle."""
    z = (LAYER_Z[3] + LAYER_Z[4]) / 2  # the middle of the cream layer
    for gx in np.linspace(CX - 62, CX + 62, 5).tolist():
        for gy in (CY - 33, CY, CY + 33):
            x, y = gx + rng.uniform(-4, 4), gy + rng.uniform(-4, 4)
            heading, length, radius = rng.uniform(0, 2 * math.pi), rng.uniform(24, 30), rng.uniform(9.5, 12)
            if math.hypot(x - TRUFFLE_CENTER[0], y - TRUFFLE_CENTER[1]) < 22:
                continue
            region = box_around((x, y, z), length / 2 + 1)
            px, py, pz = ogrid_mm(region)
            side, half_width = strawberry_outline(px, py, (x, y), heading, length, radius)
            piece = (np.abs(side) <= half_width) & (np.abs(pz - z) <= 2.5)
            block = labels[region]
            block[piece & (block == Material.WHIPPED_CREAM)] = Material.STRAWBERRY


def add_chips(labels, rng) -> list:
    """Chocolate chips scattered through the top sponge, at least 7 mm apart. Returns their centers."""
    centers = []
    for _ in range(5000):
        if len(centers) == CHIPS:
            break
        x = rng.uniform(CX - CAKE_HALF[0] + 4, CX + CAKE_HALF[0] - 4)
        y = rng.uniform(CY - CAKE_HALF[1] + 4, CY + CAKE_HALF[1] - 4)
        z = rng.uniform(LAYER_Z[4] + 3, LAYER_Z[5] - 3)
        p = np.array([x, y, z])
        if any(np.linalg.norm(p - c) < 7 for c in centers):
            continue
        paint_ellipsoid(labels, to_voxel(p), random_rotation(rng), (3.6, 3.6, 2.6),
                        Material.CHOCOLATE_CHIP, SPACING_MM, onto=(Material.CHIP_SPONGE,))
        centers.append(p)
    return centers


def add_truffle(labels, rng) -> np.ndarray:
    """A chocolate truffle with a hazelnut inside, set into the middle of the cake.
    Returns the center of the hazelnut."""
    center = np.array(TRUFFLE_CENTER)
    region = box_around(center, TRUFFLE_RADIUS_MM + 1)
    x, y, z = ogrid_mm(region)
    r = np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2 + (z - center[2]) ** 2)
    block = labels[region]
    block[r <= TRUFFLE_RADIUS_MM] = Material.TRUFFLE_SHELL
    block[r <= TRUFFLE_RADIUS_MM - TRUFFLE_SHELL_MM] = Material.TRUFFLE_FILLING
    nut = center + (1.0, -0.8, 0.5)
    paint_ellipsoid(labels, to_voxel(nut), random_rotation(rng), (7.0, 6.0, 5.5), Material.HAZELNUT, SPACING_MM)
    return nut


def add_berries(labels, rng) -> list:
    """Halved strawberries lying cut side down in a row along the back of the top, tips toward the back.
    Returns a point inside each."""
    base = FROSTING_TOP_MM + GLAZE_MM
    points = []
    for k in range(BERRIES):
        bx = CX - 64 + 32 * k + rng.uniform(-2, 2)
        by = CY + 31 + rng.uniform(-2, 2)
        heading = math.pi / 2 + rng.normal(0, 0.2)
        length, radius = rng.uniform(26, 30), rng.uniform(10, 12)
        region = box_around((bx, by, base + radius / 2), length / 2 + 1)
        x, y, z = ogrid_mm(region)
        side, half_width = strawberry_outline(x, y, (bx, by), heading, length, radius)
        berry = (half_width >= 0) & (z >= base) & (side ** 2 + (z - base) ** 2 <= half_width ** 2)
        block = labels[region]
        block[berry & (block == Material.BACKGROUND)] = Material.STRAWBERRY
        points.append((bx, by, base + 3.0))
    return points


def cut_corner(labels, x, y, z) -> None:
    """Remove the piece already eaten: the corner x >= 168 mm, y <= 80 mm, down to the board."""
    piece = (x >= CUT_CORNER[0]) & (y <= CUT_CORNER[1]) & (z >= BOARD_Z[1])
    keep = np.isin(labels, (Material.BACKGROUND, Material.PLATTER, Material.CAKE_BOARD))
    labels[piece & ~keep] = Material.BACKGROUND


def landmarks(chips, nut, berries) -> dict:
    """Voxels whose material is known from the model, for the self-check."""
    def voxel(p):
        return tuple(int(v) for v in np.rint(to_voxel(p)))

    intact_chip = next(c for c in chips if c[0] < CUT_CORNER[0] - 4 or c[1] > CUT_CORNER[1] + 4)
    return {
        (0, 0, 0): Material.BACKGROUND,
        voxel((CX, CY, 11.0)): Material.PLATTER,
        voxel((CX, CY, 15.0)): Material.CAKE_BOARD,
        voxel((90.0, 55.0, 27.0)): Material.CHOCOLATE_SPONGE,
        voxel((90.0, 55.0, 41.0)): Material.GANACHE,
        voxel((90.0, 55.0, 55.0)): Material.VANILLA_SPONGE,
        voxel((CX - 46.5, CY - 16.5, 70.0)): Material.WHIPPED_CREAM,  # between the strawberry slices
        voxel(intact_chip): Material.CHOCOLATE_CHIP,
        voxel((CX, CY + CAKE_HALF[1] + 2.0, 60.0)): Material.BUTTERCREAM,  # the frosting on the back side
        voxel((90.0, 70.0, FROSTING_TOP_MM + 1.0)): Material.GLAZE,
        voxel((CX, CY, TRUFFLE_CENTER[2] + 14.8)): Material.TRUFFLE_SHELL,
        voxel((CX, CY, TRUFFLE_CENTER[2] - 10.0)): Material.TRUFFLE_FILLING,
        voxel(nut): Material.HAZELNUT,
        voxel((CUT_CORNER[0] + 25.0, CUT_CORNER[1] - 25.0, 60.0)): Material.BACKGROUND,  # in the cut-out corner
        voxel(berries[0]): Material.STRAWBERRY,
    }


# --- The MRI scan ------------------------------------------------------------------------------

def simulate_mri(labels: np.ndarray, crust: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Image the material map as a T1-weighted MRI scan, acquired and stored like the head scan."""
    def table(attribute):
        return np.array([getattr(SIGNAL[m], attribute) for m in Material], np.float32)[labels]

    signal = table("mean")
    signal[crust & np.isin(labels, SPONGES)] += CRUST_SIGNAL
    signal += table("grain") * smooth_noise(SHAPE, 0.8, rng)
    signal += table("patchy") * smooth_noise(SHAPE, 5.0, rng)
    tunnels = smooth_noise(SHAPE, (2.0, 2.0, 3.0), rng)  # gas holes, stretched upward as the batter rose
    for material, look in SIGNAL.items():
        if look.holes:
            signal[(labels == material) & (tunnels > NormalDist().inv_cdf(1 - look.holes))] = 0
    del tunnels
    np.maximum(signal, 0, out=signal)
    image = kspace_window(signal, KSPACE_KEEP, KSPACE_TAPER)
    image *= bias_field(SHAPE, BIAS_GRADIENT, BIAS_CURVATURE)
    return quantize(rician_noise(image, NOISE_SIGMA, rng) - NOISE_FLOOR, np.uint8)


def build() -> Scan:
    rng = np.random.default_rng(RNG_SEED)
    labels, crust, marks = material_map(rng)
    return Scan(simulate_mri(labels, crust, rng), SPACING_MM, labels, marks)
