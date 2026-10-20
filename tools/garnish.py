"""Strawberries, for the foods that carry them as landmarks: whole berries standing on top of a cake,
and slices lying in a layer of cream.

A strawberry is mostly water, so in a T1-weighted MRI it is darker than the cakes (about 55 on the head
scan's scale), with a paler core along its axis (about 75). Its outline, from the stem end (t = 0) to the tip (t = 1),
has the half-width 2.6 * sqrt(t) * (1 - t) times its radius: round at the stem end, widest a third
of the way along, and pointed at the tip.
"""

import numpy as np

from scan_simulation import edge_coverage, region_coverage

BERRY_SIGNAL = 55.0
CORE_SIGNAL = 75.0
CORE = 0.35                        # the core's width, as a fraction of the berry's


def half_width(t):
    """Half-width of a strawberry at the fraction t of its length from the stem end, per unit radius."""
    t = np.clip(t, 0, 1)
    return 2.6 * np.sqrt(t) * (1 - t)


def standing_berry(dx, dy, dz, length_mm: float, radius_mm: float, voxel_mm: float, cut: float = 0.12):
    """Coverage of a whole strawberry standing on its cut stem end, tip up, and of its core.

    dx, dy, dz are the voxel centers' offsets in mm from the middle of the berry's flat base. The stem end
    was cut off at the fraction `cut` of the berry's length, which leaves the flat base.
    """
    t = cut + dz / length_mm
    across = np.hypot(dx, dy)
    sides = edge_coverage((across - radius_mm * half_width(t)) / voxel_mm)
    ends = edge_coverage(-dz / voxel_mm) * edge_coverage((dz - (1 - cut) * length_mm) / voxel_mm)
    core = edge_coverage((across - CORE * radius_mm * half_width(t)) / voxel_mm)
    berry = sides * ends
    return berry, np.minimum(core, berry)


def berry_slice(u, w, center, angle_rad: float, length_mm: float, radius_mm: float):
    """Coverage of a lengthwise slice of a strawberry lying flat, and of its core, on a 2D grid
    of columns: u and w are the columns' coordinates in mm; the slice's axis points at angle_rad."""
    du, dw = u - center[0], w - center[1]
    along = (np.cos(angle_rad) * du + np.sin(angle_rad) * dw) / length_mm + 0.5   # 0 at the stem end
    across = np.abs(-np.sin(angle_rad) * du + np.cos(angle_rad) * dw)
    outside_ends = np.maximum(-along, along - 1) * length_mm
    slice_ = region_coverage(np.maximum(across - radius_mm * half_width(along), outside_ends))
    core = region_coverage(np.maximum(across - CORE * radius_mm * half_width(along), outside_ends))
    return slice_, np.minimum(core, slice_)
