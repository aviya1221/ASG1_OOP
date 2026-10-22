# Software Requirements Specification

**Ex1: Plane projection of a 3D volume**
Version 1.0, 2026-10-22

This document states what the program must do and how well it must do it.
Every requirement has an ID, `FR-n` for functional requirements and `NFR-n` for the others, so that tests and later documents can point to it.
The problem itself and the scope of the project are described in the [README](../README.md).

## Contents

1. [Introduction](#1-introduction)
2. [Overall description](#2-overall-description)
3. [Functional requirements](#3-functional-requirements)
4. [Non-functional requirements](#4-non-functional-requirements)
5. [Data](#5-data)
6. [Deviations from the assignment text](#6-deviations-from-the-assignment-text)
7. [Verification](#7-verification)

---

## 1. Introduction

### 1.1 Purpose

The assignment says the problem is not well defined for implementation.
This document closes the gaps: it fixes the input formats, the exact geometry of the output image, the behavior on bad input,
the video format and the speed target. The design, the algorithm document and the tests are built on it.

### 1.2 Scope

The product is a command-line program, `Ex0.py`. It reads a 3D volume from an NRRD file and a list of planes from a CSV file,
and writes an MP4 video with one frame per plane. Each frame is the image of the volume sampled on that plane.
What is in and out of scope is listed in the [README](../README.md#scope).

### 1.3 Definitions

| Term | Meaning |
|---|---|
| Volume, `M` | The 3D matrix read from the NRRD file, of size `sx × sy × sz`. |
| Voxel | One entry `M[x][y][z]`. Voxel `(x, y, z)` is centered on the point with those integer coordinates. |
| Voxel unit | The distance between the centers of two neighboring voxels. All lengths in this document are in voxel units. |
| Plane | One line of the CSV file: a triangle of 3 points or a trapezoid of 4 points. It fixes both the plane in space and the part of it that is drawn. |
| Shape | The triangle or trapezoid given by a plane. |
| Apex, base, legs | In a triangle `a, b, c`: `a` is the apex, `b → c` is the base, `a → b` and `a → c` are the legs. |
| Image, `E` | The 2D matrix of raw volume values that the projection produces for one plane. |
| Projection | Sampling the volume at the points of the shape. It is a slice, not a sum along rays. |
| Frame | One picture of the video: an image converted to gray levels and centered in a fixed-size picture. |
| Valid plane | A plane that passes the checks of [3.5](#35-input-validation). A bad plane gives a black frame. |
| fps | Frames per second. |

### 1.4 References

| Reference | Use |
|---|---|
| Ex1 assignment text, Introduction to Software Engineering | the problem, the algorithm and the speed target |
| [NRRD file format](https://teem.sourceforge.net/nrrd/format.html) | the input volume format |
| [3D Slicer](https://www.slicer.org) | viewing the volumes and checking results |
| [README](../README.md) | problem statement and scope |
| [DATA/README.md](../DATA/README.md) | the data set |

---

## 2. Overall description

### 2.1 Product perspective

The program is a single pipeline. It reads both input files once, projects every plane, and writes the video.

```
file.nrrd ──► read volume ──► M ──────┐
                                       ├──► project each plane ──► E ──► gray levels, center in frame ──► file.mp4
file.csv  ──► read and check planes ──┘                  (raw values)
```

Warnings about bad planes, and a short summary with timings, are printed to the terminal.

### 2.2 Users

| User | Needs |
|---|---|
| The lecturer and graders | run the demo on their own NRRD and CSV files, and get a video and clear messages |
| The developers | run the tests and the speed benchmark, and use the projection as a library function |

Users are expected to know the index ranges of their volume, for example from the Data Probe of 3D Slicer, which shows the voxel index (IJK) under the mouse.

### 2.3 Operating environment

- Python 3.12 or newer, on Windows, macOS or Linux.
- Python packages installed with `pip` from `requirements.txt`. No separate install of a video tool is needed.

### 2.4 Constraints

- The assignment allows Java, Python, C or C++. The project is written in Python.
- A volume can be as large as 1023 × 1023 × 1023 voxels of 32 bits, about 4.3 GB. It must fit in memory once.
- The H.264 video format needs frames whose width and height are even numbers.
- Plane points are written by hand or by scripts, so they carry rounding errors. Every geometric check has a tolerance.

### 2.5 Assumptions

- Plane points are voxel indices of `M`, not physical positions in millimeters.
- The volume holds one value per voxel (a scalar volume).
- The CSV file follows the format of [3.3](#33-planes-file).

---

## 3. Functional requirements

### 3.1 Command line

**FR-1.** The program runs as

```
python Ex0.py file.nrrd file.csv file.mp4 [--fps N]
```

with the volume, the planes and the output video, in this order.

**FR-2.** Options:

| Option | Meaning | Default |
|---|---|---|
| `--fps N` | frame rate of the output video, a positive number | `30` |
| `--help` | print the usage and exit | |

**FR-3.** Exit codes:

| Code | Meaning |
|---|---|
| `0` | the video was written, even if some planes gave warnings |
| `1` | fatal error: no video was written |
| `2` | wrong command-line arguments |

**FR-4.** A fatal error prints one message to the standard error that names the file and the cause, without a Python traceback.
Fatal errors are: a missing or unreadable input file, a volume that breaks [3.2](#32-volume-file), a planes file with no planes,
and an output folder that does not exist. All of them are found before the first plane is projected.

### 3.2 Volume file

**FR-5.** The volume is read from an NRRD file with 3 dimensions and a single header and data file (`.nrrd`), with `raw` or `gzip` encoding.

**FR-6.** Value types:

| Type | Accepted | Notes |
|---|---|---|
| `uint8`, `uint16`, `uint32` | yes | the types of the assignment |
| `int8`, `int16`, `int32` | yes | values below 0 are read as 0; the lecturer's `MRHead_1.nrrd` is `int16` |
| floating point, 64-bit, anything else | no | fatal error |

**FR-7.** Every axis size is between 1 and 1023, as in the assignment. Any other size is a fatal error.

**FR-8.** `M[x][y][z]` is the value at index `(x, y, z)`, where `x` is the first axis of the NRRD `sizes` field, the one that is fastest on disk.
This is the same index that 3D Slicer calls IJK.

**FR-9.** The `space origin` and `space directions` fields of the header are not used for sampling, because plane points are voxel indices.

### 3.3 Planes file

**FR-10.** Every line that is not blank and not a comment is one plane. Its fields are separated by commas,
spaces around a field are ignored, and each field is a number written as an integer or a decimal (`12`, `12.5`, `-3e2`).

**FR-11.** Lines starting with `#` are comments. The first line is a header, and is skipped, if one of its fields is not a number.

**FR-12.** A plane has 9 or 12 numbers, three per point, in the order `x, y, z`:

| Numbers | Shape | Point order |
|---|---|---|
| 9 | triangle | `a, b, c`: apex `a`, base `b → c` |
| 12 | trapezoid | `a', a'', b, c`: top side `a' → a''`, base `b → c`, legs `a' → b` and `a'' → c` |

**FR-13.** Points are in voxel indices of `M` and may have fractions. They may lie outside `M`.

**FR-14.** A planes file without any plane line is a fatal error.

Example with a header, a comment, a triangle and a trapezoid:

```
ax,ay,az,bx,by,bz,cx,cy,cz
# axial cut through the middle of a 256 x 256 x 130 volume
128,0,65, 0,255,65, 255,255,65
60,40,20, 190,40,20, 20,200,110, 230,200,110
