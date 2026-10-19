"""Synthetic T2-weighted MRI scan of a tomato, built from a tissue model of a real tomato.

The model follows the anatomy of a round tomato: a thin skin, a thick outer wall (pericarp) with a
ring of vascular bundles, five chambers (locules) separated by radial walls (septa), a central
column (columella) with placenta lobes, seeds in the gel around the placenta, and the stem with its
sepals on top. Nothing is perfectly regular: the outline has shallow grooves and random dents, the
septa bend, the chambers differ in size, one chamber holds a small air pocket, and the fruit lies
slightly tilted and off-center, as it would in a scanner.

The tissue map is then imaged as an MRI scan (see scan_simulation.py): the water-rich gel is bright,
the flesh is mid-gray, the seeds and stem are dark, and the image gets texture, blur, coil shading
and Rician noise. The tissue map itself is kept as exact ground truth.

All lengths are in millimeters. Fruit-frame coordinates (qx, qy, qz) have their origin at the fruit
center, with +qz pointing out through the stem.
"""

import math
from dataclasses import dataclass
from enum import IntEnum

import numpy as np
from scipy import ndimage

from scan_simulation import (Scan, bias_field, kspace_window, paint_ellipsoid, quantize, rician_noise,
                             smooth_noise, voxel_box)

# --- Scan geometry -----------------------------------------------------------------------------
VOXEL_MM = 0.4
SHAPE = (204, 196, 184)            # voxels: an 81.6 x 78.4 x 73.6 mm field of view
CENTER_MM = (40.0, 40.5, 32.0)     # fruit center, a little off the middle of the field of view
TILT_DEG = 8.0                     # the stem axis leans this far from +z ...
TILT_TOWARD_DEG = 35.0             # ... toward this azimuth (from +x toward +y)

# --- Fruit anatomy -----------------------------------------------------------------------------
RADIUS_MM = 32.0                   # equatorial radius
HALF_HEIGHT_MM = 26.0              # polar radius: the fruit is oblate
SKIN_MM = 0.45
WALL_MM = 6.2                      # pericarp thickness
BUNDLES = 18                       # main vascular bundles, about 4.6 mm under the skin ...
SMALL_BUNDLES = 14                 # ... and thinner ones closer to the skin
DIMPLE_DEPTH = 0.13                # the dimple around the stem, as a fraction of the radius ...
DIMPLE_WIDTH_RAD = 0.30            # ... and its angular width
GROOVE_DEPTH = 0.035               # shallow grooves where the septa meet the wall
LOCULES = 5
SEPTUM_HALF_MM = 0.9
COLUMELLA_MM = 5.5                 # columella radius at the equator
PLACENTA_MM = 4.0                  # how far the placenta lobes reach into each locule
FILLET_VOX = 2.5                   # rounds the corners of the locules
SEEDS_PER_LOCULE = 42
SEED_SEMI_AXES_MM = (1.6, 1.25, 0.45)  # length, width, thickness
STEM_LENGTH_MM = 13.0
STEM_RADIUS_MM = 2.1
SEPALS = 6
RNG_SEED = 2026

# --- MRI acquisition ---------------------------------------------------------------------------
KSPACE_KEEP = 0.8                  # fraction of the spatial frequencies the scan measures ...
KSPACE_TAPER = 0.25                # ... with a smooth roll-off over the outer quarter of them
BIAS_GRADIENT = (0.08, -0.06, 0.07)
BIAS_CURVATURE = 0.08
NOISE_SIGMA = 38.0


class Tissue(IntEnum):
    """Label values of tomato.seg.nrrd."""
    BACKGROUND = 0
    SKIN = 1
    PERICARP = 2
    SEPTUM = 3
    COLUMELLA = 4
    PLACENTA = 5
    GEL = 6
    SEED = 7
    VASCULAR_BUNDLE = 8
    STEM = 9
    SEPAL = 10
    AIR_POCKET = 11


@dataclass(frozen=True)
class Appearance:
    """How a tissue looks in a T2-weighted scan: mean signal and relative texture amplitudes."""
    signal: float
    fine: float = 0.0      # grain at the scale of a voxel
    patchy: float = 0.0    # variation over a few millimeters
    broad: float = 0.0     # slow variation across the fruit
    fibrous: float = 0.0   # streaks along the stem axis


APPEARANCE = {
    Tissue.BACKGROUND: Appearance(0),
    Tissue.SKIN: Appearance(600, fine=0.05),
    Tissue.PERICARP: Appearance(1250, fine=0.05, patchy=0.05),
    Tissue.SEPTUM: Appearance(1150, fine=0.05, patchy=0.04),
    Tissue.COLUMELLA: Appearance(1100, fine=0.04, fibrous=0.08),
    Tissue.PLACENTA: Appearance(1450, fine=0.06, patchy=0.05),
    Tissue.GEL: Appearance(1900, fine=0.03, patchy=0.06, broad=0.05),
    Tissue.SEED: Appearance(300, fine=0.08),
    Tissue.VASCULAR_BUNDLE: Appearance(750, fine=0.05),
    Tissue.STEM: Appearance(600, fine=0.06, fibrous=0.10),
    Tissue.SEPAL: Appearance(750, fine=0.05),
    Tissue.AIR_POCKET: Appearance(0),
}
GEL_DIMMING = 0.18        # the gel is this much darker right next to a wall ...
GEL_DIMMING_MM = 1.2      # ... fading out over this distance
PERICARP_GRADIENT = 0.15  # the inner pericarp is this much brighter than the outer

# Segment colors (RGB, 0..1) for the segmentation file.
COLORS = {
    Tissue.SKIN: (0.55, 0.05, 0.05),
    Tissue.PERICARP: (0.90, 0.20, 0.15),
    Tissue.SEPTUM: (0.95, 0.45, 0.35),
    Tissue.COLUMELLA: (0.98, 0.85, 0.75),
    Tissue.PLACENTA: (0.95, 0.70, 0.60),
    Tissue.GEL: (0.85, 0.90, 0.35),
    Tissue.SEED: (0.95, 0.90, 0.65),
    Tissue.VASCULAR_BUNDLE: (1.00, 1.00, 0.60),
    Tissue.STEM: (0.35, 0.50, 0.15),
    Tissue.SEPAL: (0.20, 0.60, 0.20),
    Tissue.AIR_POCKET: (0.55, 0.65, 0.80),
}

# Large tissues from brightest to darkest in the scan; the self-check asserts this order.
# (Small parts such as seeds are left out: blur mixes them with their surroundings.)
CONTRAST = (Tissue.GEL, Tissue.PERICARP, Tissue.COLUMELLA, Tissue.STEM)


def wrap(angle):
    """Wrap an angle (radians) into [-pi, pi)."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


def distance_to_half_planes(r_xy, theta, angles):
    """Distance from each point to the nearest vertical half-plane that starts on the fruit axis
    at one of the given azimuths. An azimuth may be an array that varies from point to point."""
    distance = np.full(np.shape(r_xy), np.inf, np.float32)
    for angle in angles:
        d = wrap(theta - angle)
        distance = np.minimum(distance, np.where(np.cos(d) > 0, r_xy * np.abs(np.sin(d)), np.inf))
    return distance


def tilt_rotation(tilt_deg: float, toward_deg: float) -> np.ndarray:
    """Rotation matrix that leans +z by tilt_deg toward the azimuth toward_deg (Rodrigues' formula)."""
    toward, angle = math.radians(toward_deg), math.radians(tilt_deg)
    ax, ay = -math.sin(toward), math.cos(toward)  # horizontal axis, perpendicular to the lean
    k = np.array([[0, 0, ay], [0, 0, -ax], [-ay, ax, 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k


class TomatoModel:
    """The fruit's geometry, with its random irregularities drawn once from the RNG."""

    def __init__(self, rng: np.random.Generator):
        self.center = np.array(CENTER_MM)
        self.rotation = tilt_rotation(TILT_DEG, TILT_TOWARD_DEG)  # fruit frame -> scanner frame
        step = 2 * math.pi / LOCULES
        self.septum_angles = (0.3 + step * np.arange(LOCULES) + rng.uniform(-0.15, 0.15, LOCULES)).tolist()
        self.septum_bends = rng.uniform(-0.12, 0.12, LOCULES).tolist()
        self.locule_middles = [a + wrap(b - a) / 2 for a, b in
                               zip(self.septum_angles, self.septum_angles[1:] + self.septum_angles[:1])]
        self.dents = []  # smooth random dents in the outline: (amplitude, wave vector, phase)
        for _ in range(4):
            wave = rng.normal(size=3)
            wave *= rng.uniform(2.0, 3.5) / np.linalg.norm(wave)
            self.dents.append((rng.uniform(0.008, 0.015), wave.tolist(), rng.uniform(0, 2 * math.pi)))
        self.bundles = []  # vascular bundles in the pericarp: (azimuth, depth under the skin, radius)
        for angle in np.linspace(0, 2 * math.pi, BUNDLES, endpoint=False).tolist():
            self.bundles.append((angle + rng.uniform(-0.1, 0.1), rng.uniform(4.0, 5.2), rng.uniform(0.42, 0.65)))
        for _ in range(SMALL_BUNDLES):
            self.bundles.append((rng.uniform(0, 2 * math.pi), rng.uniform(2.2, 3.2), rng.uniform(0.28, 0.4)))
        self.sepal_angles = (np.linspace(0, 2 * math.pi, SEPALS, endpoint=False) + 0.4
                             + rng.uniform(-0.15, 0.15, SEPALS)).tolist()
        self.sepal_lengths = rng.uniform(14.0, 18.0, SEPALS).tolist()

    # --- coordinates ---

    def to_fruit(self, x, y, z):
        """Voxel indices (broadcastable arrays) -> fruit-frame coordinates in mm (float32)."""
        d = [np.asarray(i, np.float32) * VOXEL_MM - float(c) for i, c in zip((x, y, z), self.center)]
        r = self.rotation
        return tuple(float(r[0, k]) * d[0] + float(r[1, k]) * d[1] + float(r[2, k]) * d[2] for k in range(3))

    def to_voxel(self, q) -> np.ndarray:
        """Fruit-frame point in mm -> continuous voxel index (x, y, z)."""
        return (self.center + self.rotation @ np.asarray(q, float)) / VOXEL_MM

    # --- anatomy ---

    def surface_radius(self, qx, qy, qz):
        """Distance from the fruit center to the skin, in the direction of each point."""
        r = np.maximum(np.sqrt(qx ** 2 + qy ** 2 + qz ** 2), 1e-3)
        r_xy = np.hypot(qx, qy)
        theta = np.arctan2(qy, qx)
        sin_phi, cos_phi = r_xy / r, qz / r
        phi = np.arctan2(r_xy, qz)  # 0 at the stem end
        shape = 1 - DIMPLE_DEPTH * np.exp(-(phi / DIMPLE_WIDTH_RAD) ** 2)
        grooves = sum(np.exp(-(wrap(theta - a) / 0.2) ** 2) for a in self.septum_angles_at(RADIUS_MM - WALL_MM))
        shape = shape * (1 - GROOVE_DEPTH * grooves * sin_phi ** 2)
        for amplitude, (wx, wy, wz), phase in self.dents:
            shape = shape * (1 + amplitude * np.cos((wx * qx + wy * qy + wz * qz) / r + phase))
        return shape / np.sqrt((sin_phi / RADIUS_MM) ** 2 + (cos_phi / HALF_HEIGHT_MM) ** 2)

    def septum_angles_at(self, r_xy):
        """Azimuth of each septum at distance r_xy from the axis; the septa bend slightly."""
        return [a + b * (r_xy - 14.0) / 18.0 for a, b in zip(self.septum_angles, self.septum_bends)]

    @staticmethod
    def columella_radius(qz):
        return COLUMELLA_MM * (1 - 0.45 * (qz / HALF_HEIGHT_MM) ** 2)

    def placenta_radius(self, theta, qz):
        """The columella plus a rounded placenta lobe that reaches into the middle of each locule."""
        lobes = sum(np.exp(-(wrap(theta - m) / 0.42) ** 2) for m in self.locule_middles)
        return self.columella_radius(qz) + PLACENTA_MM * lobes * np.exp(-(qz / 11.0) ** 2)

    def stem_top_mm(self) -> float:
        """Height (qz) of the skin at the bottom of the stem dimple."""
        return float(self.surface_radius(0.0, 0.0, 1.0))


def tissue_map(model: TomatoModel, rng: np.random.Generator):
    """Label every voxel with its tissue. Returns the labels, the seed centers and the air-pocket center."""
    x, y, z = np.ogrid[: SHAPE[0], : SHAPE[1], : SHAPE[2]]
    qx, qy, qz = model.to_fruit(x, y, z)
    r_xy = np.hypot(qx, qy)
    theta = np.arctan2(qy, qx)
    depth = model.surface_radius(qx, qy, qz) - np.sqrt(qx ** 2 + qy ** 2 + qz ** 2)  # mm below the skin

    labels = np.zeros(SHAPE, np.uint8)
    fruit = depth >= 0
    labels[fruit] = Tissue.PERICARP
    labels[fruit & (depth < SKIN_MM)] = Tissue.SKIN

    # Locules: the space inside the wall minus the septa and the columella, with rounded corners.
    inside_wall = depth >= WALL_MM
    septum_distance = distance_to_half_planes(r_xy, theta, model.septum_angles_at(r_xy))
    columella_r = model.columella_radius(qz)
    solid = ~inside_wall | (septum_distance <= SEPTUM_HALF_MM) | (r_xy <= columella_r)
    solid = ndimage.gaussian_filter(solid.astype(np.float32), FILLET_VOX) > 0.42
    cavity = inside_wall & ~solid
    labels[inside_wall & solid & (septum_distance <= SEPTUM_HALF_MM + 2.0)] = Tissue.SEPTUM
    labels[inside_wall & solid & (r_xy <= columella_r + 1.2)] = Tissue.COLUMELLA
    labels[fruit & (r_xy <= 2.8) & (qz > 0) & ~cavity] = Tissue.COLUMELLA  # the core runs up to the stem
    labels[cavity] = Tissue.GEL
    labels[cavity & (r_xy <= model.placenta_radius(theta, qz))] = Tissue.PLACENTA
    del solid, cavity, inside_wall, septum_distance, columella_r

    # Vascular bundles: strands that run pole to pole in the pericarp, and six in the core.
    pericarp = np.nonzero(labels == Tissue.PERICARP)
    d, rx, th = depth[pericarp], r_xy[pericarp], theta[pericarp]
    on_bundle = np.zeros(d.shape, bool)
    for angle, bundle_depth, radius in model.bundles:
        a = wrap(th - angle)
        on_bundle |= (np.abs(d - bundle_depth) <= radius) & (np.cos(a) > 0) & (rx * np.abs(np.sin(a)) <= radius)
    labels[tuple(i[on_bundle] for i in pericarp)] = Tissue.VASCULAR_BUNDLE
    for angle in np.linspace(0, 2 * math.pi, 6, endpoint=False).tolist():
        strand = (qx - 2.6 * math.cos(angle)) ** 2 + (qy - 2.6 * math.sin(angle)) ** 2 <= 0.4 ** 2
        labels[strand & (labels == Tissue.COLUMELLA)] = Tissue.VASCULAR_BUNDLE

    add_stem_and_sepals(labels, model, qx, qy, qz, r_xy, theta, depth)
    del qx, qy, qz, r_xy, theta, depth

    pocket_center = carve_air_pocket(labels, model, rng)
    seed_centers = place_seeds(labels, model, rng)
    return labels, seed_centers, pocket_center


def add_stem_and_sepals(labels, model, qx, qy, qz, r_xy, theta, depth) -> None:
    """The stem rises from the dimple with a slight bend; six tapered sepals lie over the shoulders."""
    top = model.stem_top_mm()

    # Sepals: thin tapered leaves that follow the skin and curl up toward their tips.
    near = np.nonzero((depth < 0) & (depth > -3.5) & (qz > 8.0))
    rx, th, height = r_xy[near], theta[near], -depth[near]
    leaf = (rx <= 3.2) & (height <= 0.9)  # the small calyx disk around the stem
    for k, (angle, length) in enumerate(zip(model.sepal_angles, model.sepal_lengths)):
        d = wrap(th - (angle + 0.1 * np.sin(rx / 4.0 + k)))
        frac = np.clip(rx / length, 0, 1)
        leaf |= ((rx >= 1.8) & (rx <= length) & (np.cos(d) > 0)
                 & (rx * np.abs(np.sin(d)) <= 1.6 * (1 - frac) ** 0.55)
                 & (np.abs(height - (0.35 + 2.6 * frac ** 2.2)) <= 0.35))
    labels[tuple(i[leaf] for i in near)] = Tissue.SEPAL

    # Stem: a cylinder with a slight bend and a swelling (the abscission knuckle), rooted 2 mm deep.
    near = np.nonzero(qz > top - 2.5)
    sx, sy, t = qx[near], qy[near], qz[near] - top
    rise = np.clip(t, 0, None) / STEM_LENGTH_MM
    radius = STEM_RADIUS_MM + 0.35 * np.exp(-((t - 4.5) / 1.3) ** 2)
    stem = (t >= -2.0) & (t <= STEM_LENGTH_MM) & ((sx - 2.2 * rise ** 2) ** 2 + (sy - 0.6 * rise) ** 2 <= radius ** 2)
    labels[tuple(i[stem] for i in near)] = Tissue.STEM


def carve_air_pocket(labels, model, rng) -> np.ndarray:
    """A small, irregular gas-filled gap in one locule, against its outer wall."""
    m = model.locule_middles[3]
    radial = np.array([math.cos(m), math.sin(m), 0.0])
    direction = radial + [0.0, 0.0, 0.25]
    direction /= np.linalg.norm(direction)
    center = direction * (float(model.surface_radius(*direction)) - WALL_MM - 2.6)

    region = voxel_box(model.to_voxel(center), 5.0 / VOXEL_MM, SHAPE)
    qx, qy, qz = model.to_fruit(*np.ogrid[region])
    dx, dy, dz = qx - float(center[0]), qy - float(center[1]), qz - float(center[2])
    along = dx * math.cos(m) + dy * math.sin(m)
    across = -dx * math.sin(m) + dy * math.cos(m)
    size = np.sqrt((along / 3.6) ** 2 + (across / 2.6) ** 2 + (dz / 2.2) ** 2)
    pocket = size <= 1 + 0.25 * np.tanh(smooth_noise(size.shape, 2.0, rng))
    block = labels[region]
    block[pocket & (block == Tissue.GEL)] = Tissue.AIR_POCKET
    return center


def place_seeds(labels, model, rng) -> list:
    """Cluster seeds in the gel along each placenta lobe, keeping them apart and off the walls."""
    cavity = (labels == Tissue.GEL) | (labels == Tissue.PLACENTA)
    clearance = ndimage.distance_transform_edt(cavity) * VOXEL_MM
    centers = []
    for middle in model.locule_middles:
        placed = tries = 0
        while placed < SEEDS_PER_LOCULE and tries < 5000:
            tries += 1
            angle = middle + rng.normal(0, 0.3)
            qz = rng.uniform(-16, 16)
            r = float(model.placenta_radius(angle, qz)) + rng.uniform(0.3, 3.5)
            q = np.array([r * math.cos(angle), r * math.sin(angle), qz])
            v = tuple(np.rint(model.to_voxel(q)).astype(int))
            if not all(0 <= i < n for i, n in zip(v, SHAPE)) or not cavity[v] or clearance[v] < 0.6:
                continue
            if any(np.linalg.norm(q - c) < 2.0 for c in centers):
                continue
            paint_seed(labels, model, q, angle, rng)
            centers.append(q)
            placed += 1
    return centers


def paint_seed(labels, model, q, angle, rng) -> None:
    """A flat, lens-shaped seed pointing roughly away from the placenta."""
    lean, turn = rng.normal(0, 0.35), rng.normal(0, 0.3)
    length_axis = np.array([math.cos(angle + turn) * math.cos(lean),
                            math.sin(angle + turn) * math.cos(lean), math.sin(lean)])
    other = rng.normal(size=3)
    thickness_axis = other - other.dot(length_axis) * length_axis
    thickness_axis /= np.linalg.norm(thickness_axis)
    width_axis = np.cross(length_axis, thickness_axis)
    axes = model.rotation @ np.column_stack([length_axis, width_axis, thickness_axis])  # scanner frame
    paint_ellipsoid(labels, model.to_voxel(q), axes, SEED_SEMI_AXES_MM, Tissue.SEED, VOXEL_MM,
                    onto=(Tissue.GEL, Tissue.PLACENTA))


def simulate_mri(labels: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Image the tissue map as a T2-weighted MRI scan, stored as uint16."""
    def table(attribute):
        return np.array([getattr(APPEARANCE[t], attribute) for t in Tissue], np.float32)[labels]

    signal = table("signal")
    # The gel is a little darker where it touches a wall (seeds do not count as walls).
    gel = labels == Tissue.GEL
    to_wall = ndimage.distance_transform_edt(gel | (labels == Tissue.SEED))[gel] * VOXEL_MM
    signal[gel] *= 1 - GEL_DIMMING * np.exp(-to_wall / GEL_DIMMING_MM)
    # The inner pericarp holds more free water than the outer pericarp, so it is brighter.
    pericarp = labels == Tissue.PERICARP
    depth = ndimage.distance_transform_edt(labels != Tissue.BACKGROUND)[pericarp] * VOXEL_MM
    signal[pericarp] *= 1 - PERICARP_GRADIENT / 2 + PERICARP_GRADIENT * np.clip(depth / WALL_MM, 0, 1)

    texture = table("fine") * smooth_noise(SHAPE, 1.0, rng)
    texture += table("patchy") * smooth_noise(SHAPE, 5.0, rng)
    texture += table("broad") * smooth_noise(SHAPE, 15.0, rng)
    texture += table("fibrous") * smooth_noise(SHAPE, (0.8, 0.8, 5.0), rng)
    image = kspace_window(signal * (1 + texture), KSPACE_KEEP, KSPACE_TAPER)
    image *= bias_field(SHAPE, BIAS_GRADIENT, BIAS_CURVATURE)
    return quantize(rician_noise(image, NOISE_SIGMA, rng), np.uint16)


def landmarks(model: TomatoModel, seed_centers, pocket_center) -> dict:
    """Voxels whose tissue is known from the model, for the self-check."""
    def voxel(q):
        return tuple(int(v) for v in np.rint(model.to_voxel(q)))

    m = model.locule_middles[0]
    equator = np.array([math.cos(m), math.sin(m), 0.0])
    skin_reach = float(model.surface_radius(*equator))
    rise = 6.0 / STEM_LENGTH_MM
    return {
        (0, 0, 0): Tissue.BACKGROUND,
        voxel([0, 0, 0]): Tissue.COLUMELLA,
        voxel(equator * (skin_reach - 1.2)): Tissue.PERICARP,  # under the skin, above the bundles
        voxel([20 * math.cos(m), 20 * math.sin(m), 0.0]): Tissue.GEL,  # beyond the seeds, inside the wall
        voxel(seed_centers[0]): Tissue.SEED,
        voxel(pocket_center): Tissue.AIR_POCKET,
        voxel([2.2 * rise ** 2, 0.6 * rise, model.stem_top_mm() + 6.0]): Tissue.STEM,
    }


def build() -> Scan:
    rng = np.random.default_rng(RNG_SEED)
    model = TomatoModel(rng)
    labels, seed_centers, pocket_center = tissue_map(model, rng)
    image = simulate_mri(labels, rng)
    return Scan(image, (VOXEL_MM,) * 3, labels, landmarks(model, seed_centers, pocket_center))
