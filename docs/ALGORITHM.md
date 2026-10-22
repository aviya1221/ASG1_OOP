# Algorithm

**Ex1: Plane projection of a 3D volume**
Version 1.0, 2026-10-22

This document describes, step by step, how the program meets the [Software Requirements Specification](SRS.md).
Requirements are cited by their IDs, such as FR-17 or NFR-1.

## Contents

1. [Overview](#1-overview)
2. [Data structures](#2-data-structures)
3. [Reading the inputs](#3-reading-the-inputs)
4. [Plane setup and checks](#4-plane-setup-and-checks)
5. [Projection](#5-projection)
6. [Speed](#6-speed)
7. [Frames and video](#7-frames-and-video)
8. [Errors and the run report](#8-errors-and-the-run-report)
9. [Program structure](#9-program-structure)
10. [Complexity](#10-complexity)

---

## 1. Overview

### 1.1 The main idea: start from the image

The program fills the output image pixel by pixel. For every pixel it computes the point of the volume under it, and reads the nearest voxel.
Think of a sheet of graph paper placed at an angle inside a cake: each square of the sheet asks one question, what lies at its center.

The opposite direction, going over every voxel and asking which pixel it falls on, was rejected:
some pixels would get no voxel and stay as holes, and every frame would touch the whole volume, 125 million voxels at 500³.
Starting from the image gives every pixel exactly one value, and the work grows with the size of the image, not the volume.

### 1.2 The main flow

```
volume = read_volume(nrrd_path)                          # once
planes = read_planes(csv_path)                           # once
setups = [plane_setup(plane, volume) for plane in planes]  # geometry and checks, per plane
W, H   = frame_size(setups)
gray   = GrayMap(volume.lo, volume.hi)

with VideoWriter(mp4_path, W, H, fps) as video:
    for setup in setups:
        E = project(volume, setup) if setup.valid else black image
        video.write(place(gray(E), W, H))

print_report()
```

All the planes are read and checked before the first one is projected, for two reasons:
the frame size depends on the largest valid plane (FR-30), and every fatal error must be found before the video is started (FR-4).

### 1.3 Steps and requirements

| Step | Section | Requirements |
|---|---|---|
| read the volume | [3.1](#31-volume) | FR-5 to FR-9 |
| read the planes | [3.2](#32-planes) | FR-10 to FR-14 |
| set up and check each plane | [4](#4-plane-setup-and-checks) | FR-15 to FR-18, FR-23 to FR-27 |
| project | [5](#5-projection) | FR-19 to FR-22, NFR-1 to NFR-3 |
| gray levels, placement, video | [7](#7-frames-and-video) | FR-28 to FR-34 |
| errors and report | [8](#8-errors-and-the-run-report) | FR-1 to FR-4, FR-35, FR-36 |

---

## 2. Data structures

| Name | Holds | Made by |
|---|---|---|
| `Volume` | `data`: the 3D array `M` in the type of the file; `flat`: a 1D view of the same memory; `shape`; `lo` and `hi`, the smallest and largest values | `read_volume` |
| `Plane` | the line number, the frame number, and either the 3 or 4 points or the reason the line could not be read | `read_planes` |
| `PlaneSetup` | `valid`, the reason when it is not, the warnings, and for a valid plane: `corner`, `right`, `down`, `rows`, `cols`, and the column span `c0[r]`, `c1[r]` of the shape on every row | `plane_setup` |
| `GrayMap` | `lo`, `hi`, and a lookup table for 8 and 16-bit volumes | `GrayMap(lo, hi)` |
| image `E` | `rows × cols` array of raw values, in the type of the volume | `project` |
| frame | `H × W` array of `uint8` gray levels | `place` |

All points and vectors are 3-element `float64` arrays. Every image and frame is indexed `[row, column]`.

---

## 3. Reading the inputs

### 3.1 Volume

1. Read the header and the data with `pynrrd` (`nrrd.read`).
2. Check the header, and stop with a fatal error (FR-4) on the first failure:
   3 dimensions and an attached data part (FR-5), `raw` or `gzip` encoding (FR-5), a value type from the table of FR-6, every size from 1 to 1023 (FR-7).
3. Keep the array as it comes. `pynrrd` returns it indexed `[x, y, z]` with `x` fastest in memory (Fortran order), which is exactly how NRRD stores it (FR-8).
   There is no copy and no transpose.
4. Make the flat view `flat = data.reshape(-1, order="F")`. It shares the memory of `data`, and voxel `(x, y, z)` is
   `flat[x + sx·(y + sy·z)]`. The sampling step reads voxels through this view.
5. For a signed type, set negative values to 0 in place, `np.maximum(data, 0, out=data)` (FR-6). This needs no second copy of the volume (NFR-6).
6. Find `lo = data.min()` and `hi = data.max()` for the gray levels (FR-32).

The `space origin` and `space directions` fields are not used (FR-9).

### 3.2 Planes

The file is read as text, one line at a time, so every plane keeps its line number for the warnings (FR-27).

```
frame = 0
for line_no, text in enumerate(file, start=1):
    if text is blank, or starts with "#":                      skip            # FR-11
    fields = [field.strip() for field in text.split(",")]
    if line_no == 1 and some field is not a number:              skip            # header, FR-11
    frame = frame + 1
    if some field is not a number, or is inf or nan:             bad plane       # FR-24
    elif the number of fields is not 9 or 12:                    bad plane       # FR-24
    else:                                                        points = the numbers in groups of 3
```

A field is a number if Python's `float()` accepts it, so `12`, `12.5` and `-3e2` are all numbers (FR-10).
A bad line is not an error of the whole file: it becomes a `Plane` that carries its reason, and later a black frame (FR-23).
If the file has no plane lines at all, the program stops with a fatal error (FR-14).
