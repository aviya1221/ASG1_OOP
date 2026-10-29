# Software Requirements Specification

**Ex1: Plane projection of a 3D volume**
Version 2.0, 2026-10-29

## Contents

1. [Introduction](#1-introduction)
2. [Overall description](#2-overall-description)
3. [Specific requirements](#3-specific-requirements)
4. [Appendices](#4-appendices): use cases, traceability matrix

---

## 1. Introduction

### 1.1 Purpose

The assignment says the problem is not well defined for implementation.
This document states, in testable requirements, what the program shall do.
The [algorithm document](ALGORITHM.md) and the [testing strategy](TESTING.md) are built on it.

### 1.2 Scope

The product is a command-line program, `Ex0.py`. It reads a 3D volume from an NRRD file and a list of planes from a CSV file,
and writes an MP4 video with one frame per plane: the volume sampled on that plane.
What is out of scope is listed in the [README](../README.md#scope).

### 1.3 Definitions and data dictionary

| Term | Meaning | Type and range |
|---|---|---|
| `M`, the volume | The 3D array of voxel values read from the NRRD file, `sx × sy × sz`. | each size 1 to 1023; `uint8`, `uint16`, `uint32`, `int8`, `int16` or `int32` (FR-6, FR-7) |
| Voxel unit | The distance between the centers of two neighboring voxels. All lengths in this document are in voxel units. | |
| Plane | One line of the planes file: a triangle of 3 points or a trapezoid of 4. It fixes the plane in space and the part of it that is drawn. | 3 numbers `x, y, z` per point, voxel indices that may have fractions and lie outside `M` (FR-12, FR-13) |
| Valid plane | A plane that passes the checks of [FR-24](#35-input-validation). | |
| Projection | Sampling the volume at the points of the shape. It is a slice, not a sum along rays. | |
| `E`, the image | The 2D array of `rows × cols` voxel values that the projection gives for one plane. | each size 1 to 4096 (FR-16, FR-24) |
| Frame | One picture of the video: the image in gray levels, in the middle of a `W × H` picture. | `W` and `H` even, 64 × 64 if no plane is valid; gray levels 0 to 255 (FR-30, FR-32) |

### 1.4 References

| Reference | Use |
|---|---|
| Ex1 assignment text, Introduction to Software Engineering | the problem and the speed target |
| [demo/lecturer_example.csv](../demo/lecturer_example.csv), a copy of the [example the lecturer shared](https://docs.google.com/spreadsheets/d/1Tfy1yMYhAJjRBA8ZpRp_07pZXqGtxWhWoP02yZW1FQE/edit) | the planes file format |
| [NRRD file format](https://teem.sourceforge.net/nrrd/format.html) | the volume file format |
| Software Engineering Documents, Intro2SE lecture 02a | the structure of this document |

---

## 2. Overall description

### 2.1 Product perspective

The program is a single pipeline: it reads both input files once, projects every plane, and writes the video.
Warnings and a summary are printed to the terminal.

### 2.2 User classes

| User | Needs |
|---|---|
| The lecturer and graders | run the demo on their own NRRD and CSV files, and get a video and clear messages |
| The developers | run the tests and the speed benchmark, and call the projection from code |

### 2.3 Operating environment

Python 3.12 or newer on Windows, macOS or Linux, with the packages of `requirements.txt` ([NFR-10, NFR-11](#38-non-functional-requirements)).

### 2.4 Constraints

- The program is written in Python, one of the languages the assignment allows.
- A volume can be 1023 × 1023 × 1023 voxels of 32 bits, about 4.3 GB.
- H.264 video needs a frame width and height that are even numbers.
- Plane points carry rounding errors, so every geometric check has a tolerance.

### 2.5 Assumptions

- Plane points are voxel indices of `M`, not positions in millimeters.
- The volume holds one value per voxel.
- The triangles and trapezoids of the planes file are isosceles, as the lecturer said.

---

## 3. Specific requirements

Every requirement is mandatory unless it is marked **(Should)**. Sections 3.1, 3.2, 3.3 and 3.6 are the external interfaces.
The IDs of removed requirements are not used again.

### 3.1 Command line

**FR-1.** The program shall run as `python Ex0.py file.nrrd file.csv file.mp4 [--fps N]`: the volume, the planes and the output video, in this order.

**FR-2.** The program shall accept these options:

| Option | Meaning | Default |
|---|---|---|
| `--fps N` | frame rate of the output video, a positive number | `30` |
| `--help` | print the usage and exit | |

**FR-3.** The program shall exit with code `0` when the video was written, even if some planes gave warnings,
`1` after a fatal error, and `2` for wrong command-line arguments.

**FR-4a.** On a fatal error, the program shall print one message to the standard error that names the file and the cause, without a Python traceback, and shall write no video.

**FR-4b.** The fatal errors shall be: a missing or unreadable input file, a volume that breaks [3.2](#32-volume-file), a planes file with no planes, and an output folder that does not exist.

**FR-4c.** The program shall find every fatal error before it projects the first plane.

### 3.2 Volume file

**FR-5.** The program shall read the volume from an NRRD file with 3 dimensions, a single file for header and data (`.nrrd`), and `raw` or `gzip` encoding.

**FR-6a.** The program shall accept the value types `uint8`, `uint16`, `uint32`, `int8`, `int16` and `int32`. Any other type shall be a fatal error.

**FR-6b.** The program shall read values below 0 as 0.

**FR-7.** Every axis size shall be between 1 and 1023. Any other size shall be a fatal error.

**FR-8.** `M[x][y][z]` shall be the value at index `(x, y, z)`, where `x` is the first axis of the NRRD `sizes` field, the one that is fastest on disk.

**FR-9.** The program shall not use the `space origin` and `space directions` fields of the header for sampling.

### 3.3 Planes file

The planes file has the format of the lecturer's example, [demo/lecturer_example.csv](../demo/lecturer_example.csv):

```
Number of Points (3 or 4),x1,y1,z1,x2,y2,z2,x3,y3,z3,x4,y4,z4
3,200,200,0,0,200,400,400,200,400,,,
4,200,0,0,200,0,500,200,400,0,200,400,500
```

**FR-10a.** Every line that is not blank and not a comment shall be one plane.

**FR-10b.** Fields shall be separated by commas, with spaces around a field ignored. Each field shall be an integer or a decimal number (`12`, `12.5`, `-3e2`), and empty fields at the end of a line shall be ignored.

**FR-11a.** Lines starting with `#` shall be comments.

**FR-11b.** The first line shall be skipped as a header if it has a field that is neither empty nor a number.

**FR-12.** The first field of a plane shall be the number of points, 3 or 4, followed by `x, y, z` of each point. A triangle leaves the fields of the fourth point empty, or leaves them out.

| Points | Shape | Point order in the file | Sides |
|---|---|---|---|
| 3 | triangle | `a, b, c` | apex `a`, legs `a → b` and `a → c`, base `b → c` |
| 4 | trapezoid | `a', b, a'', c` | legs `a' → b` and `a'' → c`, top side `a' → a''`, base `b → c` |

**FR-13.** Points shall be voxel indices of `M`. They may have fractions and may lie outside `M`.

**FR-14.** A planes file without any plane line shall be a fatal error.

### 3.4 Projection geometry

These requirements define the image of a valid plane, for the triangle and the trapezoid alike.
`P0` is the first point of the plane: `a` for a triangle, `a'` for a trapezoid.

**FR-15. Directions in the plane.** The directions of the image shall be

```
right = (c − b) / |c − b|
w     = (b − P0) − ((b − P0) · right) · right
down  = w / |w|
```

**FR-16. Image size.** With `s(v) = (v − P0) · right` and `t(v) = (v − P0) · down` for every input point `v`, the image shall have

```
cols = floor(s_max − s_min + 1e-6) + 1
rows = floor(t_max − t_min + 1e-6) + 1
```

**FR-17. Pixel position.** Pixel `(r, c)`, row `r` and column `c`, shall sit at the point

```
corner  = P0 + s_min · right + t_min · down
p(r, c) = corner + c · right + r · down
```

**FR-18. Inside the shape.** Pixel `(r, c)` shall belong to the shape if its plane point `(s_min + c, t_min + r)` lies inside the triangle `a, b, c`,
or inside the quadrilateral `a', a'', c, b`, or on its edge, with a tolerance of `1e-6`.

**FR-19. Sampling.** The value at a point `p` shall be that of the nearest voxel: `index = floor(p + 0.5)` on each axis.

**FR-20. Pixel value.** `E[r][c]` shall be `M[index]` if the pixel belongs to the shape and `0 <= index < size` on all three axes, and 0 otherwise.

**FR-21. Orientation.** Row 0 shall hold the apex, or the top side of a trapezoid, and the last row the base, with `b` on the left and `c` on the right.

### 3.5 Input validation

**FR-23.** Every plane line shall give exactly one frame, in the order of the file.

**FR-24. Bad planes.** A plane that fails one of these checks shall give a black frame and a warning:

| Check | The plane is bad when |
|---|---|
| count | its first field is not 3 or 4, or it does not have 3 numbers for each point |
| numbers | a field is not a number, or is infinite or not a number (`inf`, `nan`) |
| base | `\|c − b\| < 1e-6` |
| one line | `\|w\| < 1e-6`: `P0` lies on the line of the base |
| flat trapezoid | `a''` is more than 0.5 from the plane through `a'`, `b` and `c` |
| trapezoid shape | the quadrilateral `a', a'', c, b` is not convex, for example because its sides cross |
| size | the image would have more than 4096 rows or columns |

**FR-25. Doubtful planes (Should).** A plane that passes FR-24 but breaks a promise of the assignment shall be drawn as given, with a warning:

| Check | Warning when |
|---|---|
| equal legs | the two legs differ by more than 0.5: `\|ab\|` and `\|ac\|`, or `\|a'b\|` and `\|a''c\|` |
| parallel sides | in a trapezoid, `\|t(a'')\| > 0.5`: the top side is not parallel to the base |

**FR-26.** A valid plane that does not meet the volume shall give a black image, without a warning.

**FR-27.** A warning shall name the line of the file and the frame, both counted from 1, the cause and the result:

```
warning: line 7, frame 5: points a, b and c are on one line; the frame is black
```

### 3.6 Video output

**FR-28.** The output shall be an MP4 file with H.264 video in the `yuv420p` pixel format.

**FR-29.** The video shall have one frame per plane line, in the order of the file.

**FR-30a.** All frames shall have the same size `W × H`: the largest number of columns and the largest number of rows among the valid planes, each rounded up to an even number.

**FR-30b.** If no plane is valid, the frames shall be 64 × 64.

**FR-31.** Each image shall be placed in its frame at column `(W − cols) // 2` and row `(H − rows) // 2`, and the rest of the frame shall be black.

**FR-32a.** Values shall become gray levels by one map for the whole video, where `lo` and `hi` are the smallest and largest values of `M`:

```
gray(v) = round(255 · (v − lo) / (hi − lo)), clipped to 0 … 255
```

**FR-32b.** A value of 0 shall always be black. If `hi = lo`, every value above 0 shall be white.

**FR-33.** The video shall play at the rate set by `--fps`.

**FR-34.** The program shall overwrite an existing output file.

### 3.7 Run report

**FR-35. Summary (Should).** When the video is written, the program shall print a summary:

```
volume:      DATA/croissant.nrrd, 500 x 500 x 500, uint8
frames:      120 (2 black, 3 warnings)
load:        1.42 s
projection:  0.95 s total, 7.9 ms per frame, 126 fps
video:       3.10 s
```

`projection` is the time of NFR-3, `load` covers reading both input files, and `video` the gray levels, the placement and the encoding.

**FR-36.** The summary shall go to the standard output, and warnings and errors to the standard error, as they happen.

### 3.8 Non-functional requirements

**NFR-1. Speed.** On the benchmark of NFR-4, the projection shall run at 30 frames per second or more.

**NFR-2. Speed target (Should).** On the same benchmark, the projection shall run at 100 frames per second or more.

**NFR-3. What is measured.** The time of a plane shall run from its points to its image `E`, including FR-15 to FR-17, and shall not include reading the files,
the gray levels, the placement or the encoding. The rate is the number of planes divided by the total of these times.

**NFR-4. Benchmark.**

| Item | Value |
|---|---|
| volume | `DATA/croissant.nrrd`, 500 × 500 × 500 voxels of `uint8` |
| planes | 100 isosceles triangles with a base of 500 and a height of 500, so each image is 501 × 501 pixels |
| position | the point halfway between the apex and the middle of the base is at the center of the volume, `(249.5, 249.5, 249.5)` |
| directions | spread evenly over all directions, made with a fixed random seed, and kept in the repository as a CSV file |
| record | the result is written down with the processor, memory, operating system, and Python and NumPy versions |

**NFR-6. Memory.** The program shall hold the volume in memory once, in its own value type, and the rest of its memory shall grow with the size of an image, not with the size of the volume or the number of planes.

**NFR-8. Reliability.** No content of a plane line shall stop the program.

**NFR-9. Determinism.** The same inputs shall always give the same images `E` and the same frames before encoding.

**NFR-10. Portability.** The program shall run on Python 3.12 or newer, on Windows, macOS and Linux.

**NFR-11. Installation.** Every dependency, the video encoder included, shall install with `pip` from `requirements.txt`.

**NFR-12. Testability.** The projection shall be a function of a volume array and a plane, with no file access.

**NFR-14a. Code.** The code shall have type hints and docstrings.

**NFR-14b. Tests.** Every requirement that a program can check shall have an automated test that runs with `pytest`.

**NFR-15. Usability (Should).** `--help` shall describe the three arguments and the format of the planes file.

---

## 4. Appendices

### 4.1 Use cases

| Use case | Actor | Main flow and result | Alternative flows |
|---|---|---|---|
| UC-01 Make a video | the lecturer or a grader | runs `Ex0.py` with a volume and a planes file (FR-1); the program checks them, projects each plane, writes an MP4 file with one frame per plane line, prints the summary and exits with code 0 | wrong arguments: exit code 2 (FR-3); fatal error: no video, exit code 1 (FR-4); bad plane: a black frame and a warning (FR-24); doubtful plane: drawn, with a warning (FR-25) |
| UC-02 Measure the speed | a developer | runs `python tools/benchmark.py`, which projects the planes of NFR-4 and prints the median rate, recorded with the machine | under 30 frames per second: exit code 1 (NFR-1) |
| UC-03 Project a plane from code | a developer | calls `plane_setup` and then `Projector.project` with a volume array and a plane of 3 or 4 points, and gets the image of FR-15 to FR-21, with no file read or written (NFR-12) | bad plane: the setup gives the reason, and there is no image (FR-24) |

### 4.2 Traceability matrix

Design sections are in the [algorithm document](ALGORITHM.md), and test files in `tests/`.

| Requirements | Use case | Design | Tests | Status |
|---|---|---|---|---|
| FR-1 to FR-14, command line and input files | UC-01 | [3](ALGORITHM.md#3-reading-the-inputs), [8.1](ALGORITHM.md#81-errors) | `test_cli`, `test_volume`, `test_planes` | passed |
| FR-15 to FR-21, geometry | UC-01, UC-03 | [4](ALGORITHM.md#4-plane-setup-and-checks), [5](ALGORITHM.md#5-projection) | `test_geometry`, `test_projector`, `test_demo` | passed |
| FR-23 to FR-27, input validation | UC-01, UC-03 | [4](ALGORITHM.md#4-plane-setup-and-checks), [8.1](ALGORITHM.md#81-errors) | `test_planes`, `test_geometry`, `test_cli`, `test_demo` | passed |
| FR-28 to FR-36, video and run report | UC-01 | [7](ALGORITHM.md#7-frames-and-video), [8.2](ALGORITHM.md#82-run-report) | `test_frames`, `test_video`, `test_cli`, `test_demo` | passed |
| NFR-1 to NFR-4, speed | UC-02 | [6](ALGORITHM.md#6-speed) | `test_benchmark`, and the benchmark of the [experiment](../experiment/README.md#3-speed) | passed, 317 fps |
| NFR-6 to NFR-15, other qualities | UC-01, UC-03 | [5.2](ALGORITHM.md#52-sampling), [7.4](ALGORITHM.md#74-encoding), [9](ALGORITHM.md#9-program-structure), [10](ALGORITHM.md#10-complexity) | `test_volume`, `test_robustness`, `test_projector`, `test_cli`, and the continuous integration | passed on Windows, 98% of the lines covered |

Status of 2026-10-29: the 155 everyday tests and the 42 slow tests pass on Windows.
