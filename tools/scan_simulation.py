"""Building blocks for synthetic scans: the result container, shape painting, and acquisition effects.

A real scanner never sees sharp boundaries or perfectly uniform tissue. Each acquisition helper
below adds one effect and is controlled by one parameter:

    smooth_noise    texture: smooth random variation inside a tissue
    partial_volume  limited resolution (CT-like): boundaries blur over about one voxel
    kspace_window   limited resolution of MRI: the outer spatial frequencies are never measured,
                    which blurs edges slightly and leaves faint ringing (Gibbs) next to them
    bias_field      slow intensity drift across the field of view (receive-coil sensitivity)
    rician_noise    the noise of an MRI magnitude image (air becomes faint noise, not 0)
    quantize        rounding to the integer type the scanner stores
    window          mapping a range of values (such as CT densities) onto an integer type
"""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import fft, ndimage


@dataclass(frozen=True)
class Scan:
    """One generated volume. Arrays are indexed [x, y, z]."""
    image: np.ndarray                   # what the scanner stores
    spacing_mm: tuple = (1.0, 1.0, 1.0) # voxel size along x, y, z
    labels: np.ndarray | None = None    # ground-truth tissue label of every voxel (uint8), if any
    landmarks: dict = field(default_factory=dict)  # voxel (x, y, z) -> value it must hold (in labels, else image)


def voxel_box(center_vox, half_vox, shape) -> tuple:
    """Slices of the voxels within half_vox voxels of a point (one number, or one per axis), clipped to the volume."""
    halves = np.broadcast_to(np.asarray(half_vox, dtype=float), (len(shape),))
    return tuple(slice(max(int(math.floor(c - h)), 0), min(int(math.ceil(c + h)) + 1, n))
                 for c, h, n in zip(center_vox, halves, shape))


def paint_ellipsoid(labels, center_vox, axes, semi_axes_mm, value, spacing_mm, onto=None) -> None:
    """Paint an ellipsoid of any orientation into a label map.

    axes holds the ellipsoid's unit axes as columns, in scanner coordinates; spacing_mm is the voxel
    size (one number, or one per axis). Only voxels whose label is in `onto` are painted, or every
    voxel if onto is None.
    """
    spacing = np.broadcast_to(np.asarray(spacing_mm, dtype=float), (3,))
    region = voxel_box(center_vox, max(semi_axes_mm) / spacing + 1, labels.shape)
    offsets = [(i - c) * s for i, c, s in zip(np.ogrid[region], center_vox, spacing)]  # mm
    inside = sum(((offsets[0] * axes[0, k] + offsets[1] * axes[1, k] + offsets[2] * axes[2, k])
                  / semi_axes_mm[k]) ** 2 for k in range(3)) <= 1
    block = labels[region]
    if onto is not None:
        inside &= np.isin(block, onto)
    block[inside] = value


def smooth_noise(shape, sigma_vox, rng: np.random.Generator) -> np.ndarray:
    """Random field with zero mean, unit standard deviation and a correlation length of about sigma_vox."""
    sigma = np.broadcast_to(np.asarray(sigma_vox, dtype=float), (len(shape),))
    step = max(1, int(sigma.min() // 3))  # long correlation lengths are computed on a coarser grid
    coarse = [-(-n // step) for n in shape]
    noise = ndimage.gaussian_filter(rng.standard_normal(coarse, dtype=np.float32), sigma / step)
    if step > 1:
        noise = ndimage.zoom(noise, step, order=1)[tuple(slice(0, n) for n in shape)]
    return (noise - noise.mean()) / noise.std()


def partial_volume(image: np.ndarray, sigma_vox: float) -> np.ndarray:
    """Blur with the scanner's point-spread function, so each voxel averages its neighborhood."""
    return ndimage.gaussian_filter(image, sigma_vox)


def kspace_window(image: np.ndarray, keep: float, taper: float) -> np.ndarray:
    """Keep only the central `keep` fraction of spatial frequencies on every axis (1 = up to Nyquist),
    rolling off with a cosine over the outer `taper` part of that range, as MRI scanners do."""
    spectrum = fft.rfftn(image, workers=-1)
    for axis, n in enumerate(image.shape):
        is_last = axis == image.ndim - 1
        frequency = np.abs(fft.rfftfreq(n) if is_last else fft.fftfreq(n)) / 0.5
        ramp = np.clip((keep - frequency) / (keep * taper), 0, 1)
        window = (0.5 - 0.5 * np.cos(np.pi * ramp)).astype(np.float32)
        spectrum *= window.reshape([-1 if a == axis else 1 for a in range(image.ndim)])
    return fft.irfftn(spectrum, s=image.shape, workers=-1).astype(np.float32)


def bias_field(shape, gradient, curvature: float) -> np.ndarray:
    """Smooth multiplicative shading: a linear ramp plus a dome that is brightest in the middle.

    gradient is the relative change from the center to the edge of the field of view along x, y, z.
    """
    x, y, z = np.meshgrid(*(np.linspace(-1, 1, n, dtype=np.float32) for n in shape),
                          indexing="ij", sparse=True)
    gx, gy, gz = gradient
    return 1 + gx * x + gy * y + gz * z - curvature * (x ** 2 + y ** 2 + z ** 2) / 3


def rician_noise(image: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """Magnitude of a complex signal with Gaussian noise of std sigma in both channels."""
    real = image + sigma * rng.standard_normal(image.shape, dtype=np.float32)
    imaginary = sigma * rng.standard_normal(image.shape, dtype=np.float32)
    return np.hypot(real, imaginary)


def quantize(image: np.ndarray, dtype) -> np.ndarray:
    """Round to the nearest integer and clip to the range of dtype."""
    info = np.iinfo(dtype)
    return np.clip(np.rint(image), info.min, info.max).astype(dtype)


def window(image: np.ndarray, low: float, high: float, dtype) -> np.ndarray:
    """Map [low, high] linearly onto 0 .. the maximum of an unsigned integer type; values outside saturate."""
    return quantize((image - low) * (np.iinfo(dtype).max / (high - low)), dtype)
