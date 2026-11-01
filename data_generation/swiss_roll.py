"""Simulated T1-weighted MRI of a Swiss roll, made in the style of the head scan MRHead_1.nrrd.

A Swiss roll is a single object with many layers: a sheet of sponge cake spread with jam and whipped
cream and rolled up, so its cross-section is a spiral of four turns. It lies on its seam, with chocolate
and five rosettes of cream on top. Its three sides clearly differ, 26 cm long, 9 cm wide and 7.5 cm tall, so each view in 3D Slicer
shows something else:

    from the front (Coronal)  the spiral
    from the side (Sagittal)  the 26 cm long side: stripes of sponge and cream, chocolate on top and the
                              flattened seam at the bottom
    from above (Axial)        the 26 cm long side again, with chocolate along both edges

The model follows a real roll:

    sponge     5.5 mm thick, with gas bubbles and darker baked surfaces
    filling    a thin layer of jam (1.2 mm, dark) under 2.7 mm of whipped cream (rich in fat, so bright),
               so each turn shows a dark and a bright line, and the way the spiral turns can be seen
    fruit      a row of strawberry pieces in the middle of the spiral, in the back half of the roll only
    spiral     the roll has settled, so it is wider than tall; the end of the sheet thins out at the seam,
               where a little cream shows, and the spiral is not quite even along the roll
    chocolate  2.5 mm of ganache over the top and the sides; the cut ends show the bare spiral
    rosettes   five rosettes of whipped cream along the top, each with a strawberry on it
    plate      the roll lies on a plate, which gives no MRI signal

The roll lies along the front-to-back axis, turned a little. Lengths are in mm, in the roll's frame:
u across the roll (toward the patient's left), w along it (toward the back) and v up, with the
origin in the middle of the field of view.
"""

import math

import numpy as np

import garnish
import head_style
from scan_simulation import (Scan, edge_coverage, region_coverage, sheet_coverage, smooth_noise, smoothstep,
                             turn_matrix)

VOXEL_MM = 1.1                     # 1.1 x 1.1 x 1.43 mm voxels: the roll fills the frame from front to back
DTYPE = np.uint32                  # 32 bits, one of the three sizes the assignment allows; ...
SCALE = 1000.0                     # ... values up to about 200,000, more than 16 bits can hold
RNG_SEED = 2031
TURN_DEG = 2.5                     # the roll is not quite square to the scanner

# --- Shape ---------------------------------------------------------------------------------------
LENGTH_MM = 260.0
END_CUT_DEG = (3.0, -2.0)          # the front and back ends were cut a little off square
SPONGE_MM = 5.5
CREAM_MM = 2.7
JAM_MM = 1.2
TURNS = 4                          # layers of cream, from the middle outward
CURL_MM = 3.0                      # radius of the tight curl in the middle
SQUASH = 0.88                      # the roll has settled: its height over its width
FLAT_BOTTOM_MM = 3.0               # flattened by this much where it lies on the plate
SEAM_DEG = -90.0                   # the end of the sheet is at the bottom
SPIRAL_WOBBLE = 0.04               # the layers wander by about this fraction of a turn ...
SPIRAL_WOBBLE_MM = 10.0            # ... over this distance
PITCH_DRIFT = 0.03                 # along the roll, the spiral is a little tighter in places ...
CENTER_DRIFT_MM = 1.0              # ... and its middle wanders by about this much
OUTLINE_BUMPS_MM = (0.8, 15.0)     # (height, size) of the bumps of the outside
CHOCOLATE_MM = 2.5                 # ganache on top, ...
CHOCOLATE_STOP_DEG = 30.0          # ... running down the sides to this far below the widest point
BUBBLES = 0.6                      # gas bubbles: a voxel full of them keeps 40% of the sponge's signal
CRUST_MM = 0.8
FRUIT_ALONG_MM = (-10.0, 118.0)    # strawberry pieces in the middle of the spiral, from here to here along the roll, ...
FRUIT_RADIUS_MM = 6.0              # ... each this thick ...
FRUIT_PERIOD_MM = 15.0             # ... one every 15 mm
ROSETTES_ALONG_MM = (-104.0, -52.0, 0.0, 52.0, 104.0)
ROSETTE_MM = (12.0, 16.0)          # radius at the bottom and height of a rosette of cream
ROSETTE_RIDGES = 8                 # the star-shaped nozzle leaves this many ridges
ROSETTE_BERRY_MM = (22.0, 9.0)     # length and radius of the strawberry on each rosette

# --- MRI signal, on the head scan's scale (brain about 70, fat about 140) -----------------------
SPONGE_SIGNAL = 72.0
CRUST_SIGNAL = -14.0
CREAM_SIGNAL = 132.0
JAM_SIGNAL = 50.0
CHOCOLATE_SIGNAL = 150.0
GRAIN, PATCHY = 3.0, 3.0


def drift(w, rng, modes: int = 6):
    """A smooth random function of the position w along the roll, mean 0 and std 1."""
    wave = np.zeros_like(w)
    for m in range(1, modes + 1):
        wave += rng.normal() / m * np.cos(np.pi * m * w / LENGTH_MM + rng.uniform(0, 2 * np.pi))
    return wave / math.sqrt(sum(0.5 / m ** 2 for m in range(1, modes + 1)))


def voxel_gradient(du, dv):
    """Lengths, per voxel step and per mm, of a gradient given in the roll's cross-section (u, v):
    u turns with the roll in the horizontal plane, v is vertical."""
    s = head_style.spacing(VOXEL_MM)
    c, t = math.cos(math.radians(TURN_DEG)), math.sin(math.radians(TURN_DEG))
    per_voxel = np.sqrt((du * c * s[2]) ** 2 + (du * t * s[0]) ** 2 + (dv * s[1]) ** 2)  # x runs along k, y along i
    per_mm = np.sqrt(du * du + dv * dv)
    return np.maximum(per_voxel, 1e-6), np.maximum(per_mm, 1e-6)


def add_rosettes(signal, tissue, u, w, v, base_v: float) -> None:
    """Pipe the rosettes of cream along the top of the roll and put a strawberry on each (in place)."""
    voxel = float(np.prod(head_style.spacing(VOXEL_MM))) ** (1 / 3)
    radius_mm, height_mm = ROSETTE_MM
    for along in ROSETTES_ALONG_MM:
        dw, dv = w - along, v - base_v
        near = (np.abs(dw) < radius_mm + 3) & (np.abs(u) < radius_mm + 3) & (dv > -3) & (dv < height_mm + 30)
        if not near.any():
            continue
        du, dw, dv = u[near], dw[near], dv[near]
        across = np.hypot(du, dw)
        ridges = 1 + 0.15 * np.cos(ROSETTE_RIDGES * np.arctan2(dw, du) + 0.25 * dv)
        outline = radius_mm * np.clip(1 - dv / height_mm, 0, 1) ** 0.7 * ridges
        cream = (edge_coverage((across - outline) / voxel) * edge_coverage(-dv / voxel)
                 * edge_coverage((dv - height_mm) / voxel))
        berry, core = garnish.standing_berry(du, dw, dv - (height_mm - 5.0), *ROSETTE_BERRY_MM, voxel)
        cream = np.minimum(cream, 1 - berry)
        value = signal[near]
        value = value * (1 - cream - berry) + CREAM_SIGNAL * cream \
            + garnish.BERRY_SIGNAL * (berry - core) + garnish.CORE_SIGNAL * core
        signal[near] = value
        tissue[near] = np.maximum(tissue[near], cream + berry)


def build() -> Scan:
    rng = np.random.default_rng(RNG_SEED)
    u, w, v = head_style.object_coordinates(VOXEL_MM, turn_matrix(TURN_DEG))

    # The spiral. In the cross-section, stretched back to round, a point at radius r and at the fraction
    # `turn` of a full turn past the seam lies on spiral coordinate phi: whole numbers of phi are the
    # inner faces of the cream layers.
    pitch = (SPONGE_MM + CREAM_MM + JAM_MM) * (1 + PITCH_DRIFT * drift(w, rng))
    big_u = u - CENTER_DRIFT_MM * drift(w, rng)
    big_v = (v - CENTER_DRIFT_MM * drift(w, rng)) / SQUASH
    r = np.maximum(np.hypot(big_u, big_v), 1e-3)
    turn = np.remainder(np.arctan2(big_v, big_u) - math.radians(SEAM_DEG), 2 * np.pi) / (2 * np.pi)
    phi = (r - CURL_MM) / pitch - turn + SPIRAL_WOBBLE * head_style.noise(rng, SPIRAL_WOBBLE_MM, VOXEL_MM)
    dr_du, dr_dv = big_u / r, big_v / (r * SQUASH)
    dturn_du, dturn_dv = -big_v / (2 * np.pi * r * r), big_u / (2 * np.pi * r * r * SQUASH)
    phi_voxel, phi_mm = voxel_gradient(dr_du / pitch - dturn_du, dr_dv / pitch - dturn_dv)
    r_voxel, r_mm = voxel_gradient(dr_du, dr_dv)
    del dturn_du, dturn_dv, turn

    # The filling: in each turn, cream and then jam, nearest the middle first.
    turn_mm = SPONGE_MM + CREAM_MM + JAM_MM
    cream_share, jam_share = CREAM_MM / turn_mm, JAM_MM / turn_mm   # their parts of one turn
    filling_share = cream_share + jam_share

    def layer(start, share):
        """Coverage of the nearest layer that starts at `start` of each turn and fills `share` of it."""
        middle = np.clip(np.rint(phi - start - share / 2), 0, TURNS - 1) + start + share / 2
        return sheet_coverage((phi - middle) / phi_voxel, share / phi_voxel), np.abs(phi - middle) - share / 2

    cream, _ = layer(0.0, cream_share)
    jam, _ = layer(cream_share, jam_share)
    _, past_filling = layer(0.0, filling_share)
    face_mm = np.maximum(past_filling, 0) / phi_mm             # from the sponge to the nearest filling
    del past_filling, phi, phi_voxel

    # The outside: the outermost sponge ends at the seam, so the roll stays round.
    radius = CURL_MM + turn_mm * (TURNS + filling_share) - 1.0
    radius += OUTLINE_BUMPS_MM[0] * head_style.noise(rng, OUTLINE_BUMPS_MM[1], VOXEL_MM) * r_mm
    outside = r - radius                                       # > 0 outside the roll
    depth_mm = np.maximum(-outside, 0) / r_mm
    roll = edge_coverage(outside / r_voxel)
    bottom = -radius.mean() * SQUASH + FLAT_BOTTOM_MM
    on_plate = edge_coverage((bottom - v) / head_style.spacing(VOXEL_MM)[1])
    front, back = (math.tan(math.radians(a)) for a in END_CUT_DEG)
    ends = region_coverage(-LENGTH_MM / 2 + front * u - w) * region_coverage(w - LENGTH_MM / 2 - back * u)

    # Strawberry pieces in the middle of the spiral, in the back half only.
    first = FRUIT_ALONG_MM[0] + FRUIT_PERIOD_MM / 2
    piece = np.clip(np.rint((w - first) / FRUIT_PERIOD_MM), 0,
                    (FRUIT_ALONG_MM[1] - FRUIT_ALONG_MM[0]) // FRUIT_PERIOD_MM - 1)
    along_piece = w - (first + piece * FRUIT_PERIOD_MM)
    voxel = float(np.prod(head_style.spacing(VOXEL_MM))) ** (1 / 3)
    fruit = edge_coverage((np.hypot(r, along_piece) - FRUIT_RADIUS_MM) / voxel)
    del r, piece, along_piece

    # Chocolate over the top and the sides, down to CHOCOLATE_STOP_DEG below the widest point.
    upward = dr_dv / r_mm                                     # vertical part of the outward direction
    thickness = CHOCOLATE_MM * smoothstep((upward + math.sin(math.radians(CHOCOLATE_STOP_DEG))) / 0.3)
    chocolate = sheet_coverage(outside / r_voxel - 0.5 * thickness * r_mm / r_voxel, thickness * r_mm / r_voxel)
    del upward, thickness, outside, dr_du, dr_dv, r_voxel, r_mm

    # Sponge: darker near its baked surfaces, with gas bubbles.
    crust = np.maximum(np.exp(-(face_mm / CRUST_MM) ** 2), np.exp(-(depth_mm / CRUST_MM) ** 2))
    sponge = SPONGE_SIGNAL + CRUST_SIGNAL * crust
    bubbles = smoothstep((smooth_noise(head_style.GRID, 0.7, rng) - 1.4) / 0.8)   # in about 8% of the sponge
    sponge *= 1 - BUBBLES * bubbles
    del crust, face_mm, depth_mm, bubbles

    keep = on_plate * ends
    filled = sponge * (1 - cream - jam) + CREAM_SIGNAL * cream + JAM_SIGNAL * jam
    filled = filled * (1 - fruit) + garnish.BERRY_SIGNAL * fruit
    signal = (roll * filled + CHOCOLATE_SIGNAL * chocolate) * keep
    tissue = np.minimum(roll + chocolate, 1) * keep
    del filled, sponge, cream, jam, fruit
    add_rosettes(signal, tissue, u, w, v, radius.mean() * SQUASH + CHOCOLATE_MM - 1.0)
    signal += (GRAIN * smooth_noise(head_style.GRID, 0.8, rng)
               + PATCHY * head_style.noise(rng, 5.0, VOXEL_MM)) * tissue
    image = head_style.acquire(np.maximum(signal, 0), rng, DTYPE, SCALE)
    return Scan(image, head_style.spacing(VOXEL_MM))
