"""What the food scans copy from the lecturer's example, MRHead_1.nrrd.

Measured on MRHead_1.nrrd:

    grid         256 x 256 x 130 voxels of int16 ("short"), gzip-compressed, little endian
    voxel        1 x 1 x 1.3 mm: the 130 slices are 1.3 times farther apart than the pixels of a slice
    orientation  sagittal slices: index i runs from the front to the back, j from the top down and
                 k from the left to the right (space directions (0,1,0) (0,0,-1) (-1.3,0,0))
    object       one head in the middle, filling about 90% of each axis, on a black background
    layers       a line through the middle crosses 23 clear steps or lines: skin, fat, skull, fluid,
                 gray and white matter, the ventricles
    values       0 to 279: background 0 to 7, brain about 70, fat about 140; noise sigma about 4.5
    look         a T1-weighted MRI: edges slightly soft with faint ringing, slow shading across the image

A food scan keeps the grid, the voxel shape, the orientation and the MRI look. Only the voxel size is
scaled, so that the food fills the field of view the way the head does. Each food is stored in another
of the three types the assignment allows, unsigned integers of 8, 16 or 32 bits, with the head scan's
values multiplied to suit that type. The large scan for the speed test has its own grid and cubic
voxels, passed as grid and slice_ratio to the functions below.
Each food is modeled in patient coordinates, millimeters from the middle of the field of view:
x toward the patient's left (L), y toward the back (P) and z up (S).
"""

import numpy as np

from scan_simulation import bias_field, kspace_window, kspace_window_in_place, quantize, rician_noise, smooth_noise

GRID = (256, 256, 130)            # voxels along i, j, k
SLICE_RATIO = 1.3                 # slice spacing (k) over pixel spacing (i, j)
AXES = np.array([[0.0, 1.0, 0.0],     # i: front to back
                 [0.0, 0.0, -1.0],    # j: top to bottom
                 [-1.0, 0.0, 0.0]])   # k: left to right
HEAD_DTYPE = np.int16             # the head scan's own type

# MRI acquisition, as measured in the head scan
KSPACE_KEEP = 0.85                # fraction of the spatial frequencies measured ...
KSPACE_TAPER = 0.3                # ... with a smooth roll-off over the outer part of them
BIAS_GRADIENT = (0.05, -0.04, 0.04)
BIAS_CURVATURE = 0.04
NOISE_SIGMA = 4.5
NOISE_FLOOR = 4.5                 # subtracted, then clipped at 0: as in the head scan's corners,
                                  # 40% of the background is 0 and its mean is about 1.8


def spacing(voxel_mm: float, slice_ratio: float = SLICE_RATIO) -> tuple:
    """Voxel size along i, j, k in mm."""
    return (voxel_mm, voxel_mm, slice_ratio * voxel_mm)


def header(voxel_mm: float, grid=GRID, slice_ratio: float = SLICE_RATIO) -> dict:
    """NRRD header fields laid out like MRHead's, with the middle of the field of view at (0, 0, 0)."""
    directions = AXES * np.array(spacing(voxel_mm, slice_ratio))[:, None]
    middle = (np.array(grid) - 1) / 2
    return {
        "space": "left-posterior-superior",
        "space directions": directions,
        "space origin": -(middle @ directions),
        "kinds": ["domain", "domain", "domain"],
        "endian": "little",
        "encoding": "gzip",
    }


def patient_axes(voxel_mm: float, grid=GRID, slice_ratio: float = SLICE_RATIO):
    """Patient coordinates (x, y, z) = (L, P, S) of the voxel centers, in mm from the middle of the
    field of view, as arrays that broadcast to the grid."""
    i, j, k = (np.arange(n, dtype=np.float32) - (n - 1) / 2 for n in grid)
    s = np.float32(voxel_mm)
    x = (-np.float32(slice_ratio) * s * k)[None, None, :]
    y = (s * i)[:, None, None]
    z = (-s * j)[None, :, None]
    return x, y, z


def object_coordinates(voxel_mm: float, rotation: np.ndarray, center_mm=(0.0, 0.0, 0.0)):
    """Coordinates of every voxel center in an object's own frame: the object's origin sits at
    center_mm and its axes are the columns of rotation, both in patient coordinates."""
    x, y, z = patient_axes(voxel_mm)
    dx, dy, dz = x - np.float32(center_mm[0]), y - np.float32(center_mm[1]), z - np.float32(center_mm[2])
    r = rotation.astype(np.float32)
    return tuple(r[0, a] * dx + r[1, a] * dy + r[2, a] * dz for a in range(3))


def noise(rng: np.random.Generator, correlation_mm: float, voxel_mm: float) -> np.ndarray:
    """Smooth random field (mean 0, std 1) whose features are about correlation_mm across."""
    return smooth_noise(GRID, [correlation_mm / s for s in spacing(voxel_mm)], rng)


def acquire(signal: np.ndarray, rng: np.random.Generator, dtype=HEAD_DTYPE, scale: float = 1.0) -> np.ndarray:
    """Image a map of MRI signal the way the head was scanned, then store it as dtype, with every value
    multiplied by scale."""
    image = kspace_window(signal.astype(np.float32), KSPACE_KEEP, KSPACE_TAPER)
    image *= bias_field(signal.shape, BIAS_GRADIENT, BIAS_CURVATURE)
    return quantize(scale * np.maximum(rician_noise(image, NOISE_SIGMA, rng) - NOISE_FLOOR, 0), dtype)


def acquire_large(signal: np.ndarray, rng: np.random.Generator, dtype, scale: float, chunk: int = 25) -> np.ndarray:
    """The same as acquire, for a volume too large to hold several copies of in memory: the
    resolution limit is applied one axis at a time in place (signal is overwritten), and the shading
    and the noise are added slab by slab along i."""
    kspace_window_in_place(signal, KSPACE_KEEP, KSPACE_TAPER, chunk)
    x, y, z = (np.linspace(-1, 1, n, dtype=np.float32) for n in signal.shape)
    gx, gy, gz = BIAS_GRADIENT
    image = np.empty(signal.shape, dtype)
    for start in range(0, signal.shape[0], chunk):
        rows = slice(start, min(start + chunk, signal.shape[0]))
        xs = x[rows][:, None, None]
        shading = 1 + gx * xs + gy * y[None, :, None] + gz * z[None, None, :] \
            - BIAS_CURVATURE * (xs ** 2 + y[None, :, None] ** 2 + z[None, None, :] ** 2) / 3
        noisy = rician_noise(signal[rows] * shading, NOISE_SIGMA, rng)
        image[rows] = quantize(scale * np.maximum(noisy - NOISE_FLOOR, 0), dtype)
    return image
