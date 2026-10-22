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
the video format and the speed target. The design, the [algorithm document](ALGORITHM.md) and the tests are built on it.

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
127.5,0,65, 0,255,65, 255,255,65
60,40,20, 190,40,20, 20,200,110, 230,200,110
```

### 3.4 Projection geometry

These requirements define the image of a valid plane exactly. They hold for the triangle and the trapezoid alike.
`P0` is the first point of the plane: `a` for a triangle, `a'` for a trapezoid.

**FR-15. Directions in the plane.**

```
right = (c − b) / |c − b|
w     = (b − P0) − ((b − P0) · right) · right
down  = w / |w|
```

`right` runs along the base from `b` to `c`. `down` lies in the plane, perpendicular to the base, and points from `P0` toward the base.
Both have length 1 and are perpendicular to each other.

**FR-16. Image size.** For every input point `v`, its position in the plane is `s(v) = (v − P0) · right` and `t(v) = (v − P0) · down`.
With the smallest and largest of these over the input points:

```
cols = floor(s_max − s_min) + 1
rows = floor(t_max − t_min) + 1
```

The floor is taken after adding `1e-6`, so that a length of `7.9999999` caused by rounding counts as 8.

**FR-17. Pixel position.** Pixel `(r, c)`, row `r` and column `c`, sits at the point

```
corner = P0 + s_min · right + t_min · down
p(r, c) = corner + c · right + r · down
```

Neighboring pixels are one voxel unit apart in both directions, so the image keeps the true proportions of the shape.

**FR-18. Inside the shape.** In plane coordinates, pixel `(r, c)` is at `(s_min + c, t_min + r)`.
It belongs to the shape if that point lies inside the triangle `a, b, c`, or inside the quadrilateral `a', a'', c, b`, or on its edge, with a tolerance of `1e-6`.

**FR-19. Sampling.** The value at a point is the value of the nearest voxel: on each axis, `index = floor(p + 0.5)`, so halves round up.

**FR-20. Pixel value.** `E[r][c] = M[index]` if the pixel belongs to the shape and `0 <= index < size` on all three axes. Otherwise `E[r][c] = 0`.

**FR-21. Orientation.** Row 0 is at the top and holds the apex, or the top side of a trapezoid. The base is in the last row, with `b` on the left and `c` on the right.

**FR-22. Slices along the axes.** For a plane perpendicular to an axis, with integer points, every pixel inside the shape equals the matching voxel exactly.
For example, the triangle `a = (5, 0, z0)`, `b = (0, 10, z0)`, `c = (10, 10, z0)` gives `E[r][c] = M[c][r][z0]`.

**Worked example.** The cake in the picture below is 10 × 10 × 10 voxels. The plane is the triangle `a = (5, 0, 8)`, `b = (1, 6, 0)`, `c = (9, 6, 0)`.

| Step | Result |
|---|---|
| `right` | `(8, 0, 0) / 8 = (1, 0, 0)` |
| `w` | `(−4, 6, −8) − (−4) · (1, 0, 0) = (0, 6, −8)` |
| `down` | `(0, 6, −8) / 10 = (0, 0.6, −0.8)` |
| `s` of `a, b, c` | `0, −4, 4` |
| `t` of `a, b, c` | `0, 10, 10` |
| image size | 9 columns, 11 rows |
| `corner` | `(5, 0, 8) − 4 · (1, 0, 0) = (1, 0, 8)` |
| pixel `(5, 2)` | `(1, 0, 8) + 2 · (1, 0, 0) + 5 · (0, 0.6, −0.8) = (3, 3, 4)`, in the cream layer |

![The worked example: the triangle inside the cake, and the image it gives](../DATA/images/explain/how_a_cut_is_made.png)

### 3.5 Input validation

**FR-23.** Every plane line gives exactly one frame, in the order of the file, whatever it contains.

**FR-24. Bad planes.** A plane that fails one of these checks gives a black frame and a warning:

| Check | The plane is bad when |
|---|---|
| count | it does not have 9 or 12 numbers |
| numbers | a field is not a number, or is infinite or not a number (`inf`, `nan`) |
| base | `\|c − b\| < 1e-6` |
| one line | `\|w\| < 1e-6`: `P0` lies on the line of the base |
| flat trapezoid | `a''` is more than 0.5 from the plane through `a'`, `b` and `c` |
| trapezoid shape | the quadrilateral `a', a'', c, b` is not convex, for example because its sides cross |
| size | the image would have more than 4096 rows or columns |

The size limit keeps a point that is very far away from producing a huge video.

**FR-25. Doubtful planes.** A plane that passes the checks above but breaks a promise of the assignment is drawn as given, with a warning:

| Check | Warning when |
|---|---|
| equal legs | the two legs differ by more than 0.5: `\|ab\|` and `\|ac\|`, or `\|a'b\|` and `\|a''c\|` |
| parallel sides | in a trapezoid, `\|t(a'')\| > 0.5`, so the top side is not parallel to the base (`t(a')` is always 0) |

**FR-26.** A valid plane that does not meet the volume at all gives a black image without a warning. It is valid input.

**FR-27.** A warning names the line of the file and the frame, both counted from 1, the cause and the result:

```
warning: line 7, frame 5: points a, b and c are on one line; the frame is black
warning: line 9, frame 7: the legs differ by 3.2 voxels; drawn as given
```

### 3.6 Video output

**FR-28. Format.** The output is an MP4 file with H.264 video in the `yuv420p` pixel format, which plays in common players and web browsers.

**FR-29. Frames.** The video has one frame per plane line, in the order of the file (FR-23).

**FR-30. Frame size.** All frames have the same size: the largest number of columns and the largest number of rows among the valid planes,
each rounded up to an even number. If no plane is valid, the frames are 64 × 64.
The size is known from the checks of [3.5](#35-input-validation), before any plane is projected.

**FR-31. Placement.** Each image is placed in the middle of its frame, at column `(W − cols) // 2` and row `(H − rows) // 2`,
where `W × H` is the frame size. The rest of the frame is black.

**FR-32. Gray levels.** Values become gray levels by one linear map for the whole video, so the brightness does not jump between frames.
`lo` and `hi` are the smallest and largest values of `M`, found once when the volume is read.

```
gray(v) = round(255 · (v − lo) / (hi − lo)), clipped to 0 … 255
```

A value of 0, such as a pixel outside the shape or outside the volume, is always black.
If all values of `M` are equal (`hi = lo`), every value above 0 is white.

**FR-33. Frame rate.** The video plays at the rate set by `--fps` (FR-2), so it lasts `frames / fps` seconds.

**FR-34. Output file.** An existing output file is overwritten. An output folder that does not exist is a fatal error (FR-4).

H.264 compresses with some loss, so the gray levels in the video are close to those of FR-32 but not always equal.
Exact values are checked on the images `E` and on the frames before encoding.

### 3.7 Run report

**FR-35. Summary.** When the video is written, the program prints a summary:

```
volume:      DATA/croissant.nrrd, 500 x 500 x 500, uint8
frames:      120 (2 black, 3 warnings)
load:        1.42 s
projection:  0.95 s total, 7.9 ms per frame, 126 fps
video:       3.10 s
```

`projection` is the time defined in NFR-3. `load` covers reading both input files, and `video` covers the gray levels, the placement and the encoding.

**FR-36. Output streams.** The summary goes to the standard output. Warnings and errors go to the standard error, as they happen.

---

## 4. Non-functional requirements

### 4.1 Speed

**NFR-1.** On the benchmark of NFR-4, the projection runs at **30 frames per second at least**.

**NFR-2.** The target is **100 frames per second**.

**NFR-3. What is measured.** The time from the points of a plane to its image `E`, including the setup of FR-15 to FR-17 for that plane.
Reading the files, the gray levels, the placement in the frame and the video encoding are not included.
The rate is the number of planes divided by the total of these times.

**NFR-4. Benchmark.**

| Item | Value |
|---|---|
| volume | `DATA/croissant.nrrd`, 500 × 500 × 500 voxels of `uint8` |
| planes | 100 isosceles triangles with a base of 500 and a height of 500, so each image is 501 × 501 pixels |
| position | the point halfway between the apex and the middle of the base is at the center of the volume, `(249.5, 249.5, 249.5)` |
| directions | spread evenly over all directions, made with a fixed random seed, and kept in the repository as a CSV file |
| record | the result is written down with the processor, memory, operating system, and Python and NumPy versions |

**NFR-5.** The time to read the files and to write the video is measured and reported (FR-35), without a target,
because the assignment sets its target on the projection.

### 4.2 Memory

**NFR-6.** The volume is held in memory once, in its own value type: 125 MB for the benchmark volume, and 4.3 GB for the largest volume allowed,
1023 × 1023 × 1023 voxels of 32 bits. The extra memory for a plane grows with the size of its image, not with the size of the volume.

**NFR-7.** Frames are written to the video as they are made. Memory use does not grow with the number of planes.

### 4.3 Reliability

**NFR-8.** No content of a plane line can stop the program (FR-23).

**NFR-9.** The same inputs always give the same images `E` and the same frames before encoding.

### 4.4 Portability

**NFR-10.** The program runs on Python 3.12 or newer, on Windows, macOS and Linux.

**NFR-11.** Every dependency is listed in `requirements.txt` and installs with `pip`, the video encoder included. No other program has to be installed.

### 4.5 Design and code quality

The assignment puts the design and the quality of the code before the implementation.

**NFR-12.** The projection is a function of a volume array and a plane, with no file access, so tests can run it on small arrays they build themselves.

**NFR-13.** Reading the volume, reading and checking the planes, the plane geometry, the sampling, the frame placement, the video writing and the command line are separate units.
Each one can be tested on its own.

**NFR-14.** The code has type hints and docstrings. The tests are automated and run with `pytest`.
Every requirement that a program can check has at least one test ([section 7](#7-verification)).

### 4.6 Usability

**NFR-15.** `--help` explains the three arguments and the format of the planes file.
Every warning and error says which file and line it is about, and what happened (FR-4, FR-27).

---

## 5. Data

The data set is described in full in [DATA/README.md](../DATA/README.md). This table shows what each part is used to check.

| Data | Value type | Size | Used for |
|---|---|---|---|
| small arrays built inside the tests, such as the cake of the worked example | any | a few voxels | exact checks of the geometry, FR-15 to FR-22 |
| `DATA/synthetic/dice.nrrd` | `uint32` | 200 × 180 × 160 | values above 65535, and images known in advance: a square face with its pips, a hexagon through the center, a triangle cut off a corner |
| `DATA/synthetic/cake_3layers.nrrd` and `.seg.nrrd` | `uint8` | 256 × 180 × 96 | the label file gives the exact material of every pixel |
| `DATA/synthetic/tomato.nrrd` and `.seg.nrrd` | `uint16` | 204 × 196 × 184 | a tilted object that no axis lines up with |
| `DATA/MRHead_1.nrrd` | `int16` | 256 × 256 × 130 | the lecturer's file: a signed type (FR-6), and the main demo |
| `DATA/onion.nrrd`, `biscuit_cake.nrrd`, `swiss_roll.nrrd` | `uint8`, `uint16`, `uint32` | 256 × 256 × 130 | demo videos in all three value types of the assignment |
| `DATA/croissant.nrrd` | `uint8` | 500 × 500 × 500 | the speed benchmark, NFR-1 to NFR-4 |
| `DATA/real_scans/` | `uint8`, `uint16` | various | extra runs on real CT scans |

The planes files for the tests and the demo are part of the testing strategy.

---

## 6. Deviations from the assignment text

The algorithm in the assignment is a description, and it leaves points open. Where this document differs from it, this is why.

| Topic | Assignment | This project | Reason |
|---|---|---|---|
| computation | two points walk down the legs, and a third walks along each row between them | a direct formula for every pixel (FR-17) | all the pixels of an image can be computed at once, which is what makes the speed target reachable in Python; for an isosceles triangle it covers the same shape |
| row spacing | each row moves one unit along the legs | each row moves one unit along the height (FR-17) | in the assignment, rows are only `height / Dab` apart while pixels in a row are 1 apart, so the image is squeezed vertically; here both are 1 apart and the proportions are true. In the worked example `Dab = √116 ≈ 10.77` and the height is 10 |
| apex row | skipped, because `a1` and `a2` move before the first row is read | row 0 (FR-21) | the apex is part of the triangle |
| image size | `Dab × Dbc` | `floor(height) + 1` rows and `floor(Dbc) + 1` columns for a triangle (FR-16) | follows from the row spacing, and from counting both ends of each side |
| indexing | `E[x][y]` | `E[r][c]` | the same picture, written in the row-first order of NumPy |
| triangle shape | isosceles | any triangle, with a warning (FR-25) | the description of the CSV file in the assignment does not promise isosceles triangles, and rounding makes the legs slightly unequal anyway |
| sampling | `M[p]` for a point `p` with fractions, not specified further | the nearest voxel (FR-19) | the fastest choice; interpolation between voxels can be added later as an option |
| value types | unsigned 8, 16 and 32 bits | signed types too (FR-6) | the lecturer's `MRHead_1.nrrd` is `int16` |

---

## 7. Verification

How each requirement is checked. The [testing strategy](TESTING.md) describes the tests in detail.

| Method | Meaning |
|---|---|
| T | automated test |
| D | demo run, looked at by a person |
| B | benchmark run |
| I | inspection of the code or the documents |

| Requirements | Method | How |
|---|---|---|
| FR-1 to FR-4 | T, D | run the program with good and broken arguments and files; check the exit code, the message, and that no video is written after a fatal error |
| FR-5 to FR-9 | T | read every file of the data set, and small NRRD files written by the tests for each value type, encoding and size limit |
| FR-10 to FR-14 | T | planes files with a header, comments, blank lines, spaces, decimals and wrong counts |
| FR-15 to FR-21 | T | results computed by hand: the worked example, and a small volume whose every voxel holds its own index, `x + 1000·y + 1000000·z`, so each pixel shows which voxel it read |
| FR-22 | T | planes along the axes compared with NumPy slices of the data set volumes |
| FR-23 to FR-27 | T | one planes file for each bad and doubtful case; check the frame count, the black frames and the warning text |
| FR-28 to FR-34 | T, D | read the video back and check the codec, frame count, frame size and rate; compare the frames before encoding exactly |
| FR-35, FR-36 | T | capture the standard output and the standard error |
| NFR-1 to NFR-5 | B | run the benchmark on the croissant and record the result in the experiment report |
| NFR-6, NFR-7 | B | measure the peak memory during the benchmark and during a demo with many planes |
| NFR-8 | T | random and malformed plane lines; the program must finish and write one frame per line |
| NFR-9 | T | run twice and compare the images and frames |
| NFR-10, NFR-11 | D | install into a new virtual environment from `requirements.txt` and run the demo, on Windows and on macOS or Linux when available |
| NFR-12 to NFR-14 | I, T | review the code; the projection tests use arrays only, with no files |
| NFR-15 | I | read `--help` and the messages |
