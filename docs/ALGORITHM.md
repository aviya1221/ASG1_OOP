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
setups = [plane_setup(plane) for plane in planes]        # geometry and checks, per plane
W, H   = frame_size(setups)
gray   = GrayMap(volume.lo, volume.hi)
projector = Projector(volume, threads=4)

with VideoWriter(mp4_path, W, H, fps) as video:
    for setup in setups:
        E = projector.project(setup) if setup.valid else black image
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
| project | [5](#5-projection) | FR-19 to FR-21, NFR-1 to NFR-3 |
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
| `Projector` | the volume and a pool of threads, kept for the whole run | `Projector(volume, threads)` |
| image `E` | `rows × cols` array of raw values, in the type of the volume | `Projector.project` |
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
    drop the empty fields at the end of fields                                   # FR-10
    if line_no == 1 and some field is neither empty nor a number: skip           # header, FR-11
    frame = frame + 1
    if some field is empty, not a number, or inf or nan:         bad plane       # FR-24
    elif the first field n is not 3 or 4:                        bad plane       # FR-24
    elif the other fields are not 3·n numbers:                   bad plane       # FR-24
    else:                                                        points = the other fields in groups of 3
                                                                 a trapezoid: a', b, a'', c becomes a', a'', b, c
```

A field is a number if Python's `float()` accepts it, so `12`, `12.5` and `-3e2` are all numbers (FR-10).
The empty fields at the end are the fourth point of a triangle, which the lecturer's example leaves empty (FR-12).
A trapezoid line lists its legs one after the other, `a', b, a'', c`; the reading swaps the middle two points,
so the rest of the program always sees `a', a'', b, c`, the order of the names in [4.1](#41-names).
A bad line is not an error of the whole file: it becomes a `Plane` that carries its reason, and later a black frame (FR-23).
If the file has no plane lines at all, the program stops with a fatal error (FR-14).

---

## 4. Plane setup and checks

`plane_setup` runs once per plane, before any projection. It does a fixed amount of work, plus one short pass over the rows of the image.
The steps run in this order, and the first check that fails makes the plane bad, with that reason (FR-24).

### 4.1 Names

| Shape | `P0` | `Q`, the start of the second leg | Corners in order around the shape |
|---|---|---|---|
| triangle `a, b, c` | `a` | `a` | `a, c, b` |
| trapezoid `a', a'', b, c` | `a'` | `a''` | `a', a'', c, b` |

### 4.2 Steps

These are the formulas of the geometry that [SRS 3.4](SRS.md#34-projection-geometry) states in words.

1. **Base.** `base = c − b`. If its length is below `1e-6`, the plane is bad. Otherwise `right = base / |base|` (FR-15).
2. **Down.** `w = (b − P0) − ((b − P0) · right) · right`, the part of `b − P0` that is perpendicular to the base.
   If its length is below `1e-6`, `P0` is on the line of the base and the plane is bad. Otherwise `down = w / |w|` (FR-15).
3. **Flat trapezoid.** `n = right × down` is the unit normal of the plane. If `|(a'' − a') · n| > 0.5`, the plane is bad (FR-24).
4. **Plane coordinates.** For each corner `v`: `s = (v − P0) · right` and `t = (v − P0) · down` (FR-16).
   This drops the small part of `a''` that is off the plane.
5. **Convex trapezoid.** Going around the corners `a', a'', c, b` in plane coordinates, the cross product of each edge with the next one
   must keep one sign: all `≥ −1e-6`, or all `≤ 1e-6`. Otherwise the sides cross or the shape is dented, and the plane is bad (FR-24).
   A cross product near 0 is allowed, so a trapezoid with `a' = a''`, which is really a triangle, passes.
6. **Size.** `cols = floor(s_max − s_min + 1e-6) + 1` and `rows = floor(t_max − t_min + 1e-6) + 1` (FR-16).
   If either is above 4096, the plane is bad (FR-24).
7. **Corner.** `corner = P0 + s_min · right + t_min · down`. Pixel `(r, c)` lies at `p(r, c) = corner + c · right + r · down` (FR-17).
8. **Warnings** (FR-25). The plane stays valid.
   - Equal legs: `abs(|b − P0| − |c − Q|) > 0.5`.
   - Parallel sides, trapezoid only: `abs(t(a'')) > 0.5`. `t(a')` is always 0, because `a'` is `P0`.
9. **Row spans** ([4.3](#43-row-spans)).

For a triangle, `t(a) = 0` and `t(b) = t(c) = |w|`, so the apex is in row 0 and the base in the last row (FR-21).

### 4.3 Row spans

Row `r` of the image lies on the line `t = t_min + r` of the plane. The shape is convex, so it meets that line in one interval, `[s_lo(r), s_hi(r)]`.
The interval comes from intersecting the line with each edge of the shape, at most 4 edges, for all the rows at once:

```
for each edge from p to q (in plane coordinates):
    if t_p != t_q:  where t lies between t_p and t_q (within 1e-6):  s = s_p + (t − t_p) · (s_q − s_p) / (t_q − t_p)
    else:           where t is within 1e-6 of t_p:                   both s_p and s_q
s_lo(r) = smallest s found on row r,  s_hi(r) = largest
```

The span is then turned into columns, with the tolerance of FR-18:

```
c0[r] = ceil(s_lo(r) − s_min − 1e-6)
c1[r] = floor(s_hi(r) − s_min + 1e-6)
```

A pixel `(r, c)` belongs to the shape exactly when `c0[r] <= c <= c1[r]`, which is the test of FR-18.
A row that misses the shape gets `c0[r] > c1[r]`.

---

## 5. Projection

`Projector.project(setup)` turns a valid plane into its image `E`. The projector holds the volume and a pool of threads,
made once for the whole run. It reads no files (NFR-12).

### 5.1 Early exit

The four corners of the image rectangle are `corner`, `corner + (cols − 1)·right`, `corner + (rows − 1)·down` and the sum of both steps.
If on some axis all four lie below `−0.5`, or all lie at `size − 0.5` or above, the plane misses the volume:
`E` is all zeros and nothing is sampled (FR-26).

### 5.2 Sampling

`E` starts as an array of zeros. Its rows are split into bands, and the pixels of each band are computed at once with NumPy arrays.
A band computes only the columns that the shape reaches in its rows: it is trimmed.
The voxel of a point `p` is `floor(p + 0.5)` on each axis, the nearest one with halves rounded up (FR-19).

```
R  = rows of the band, as a column                             (shape: band × 1)
C  = min c0[R] … max c1[R], as a row                           (shape: 1 × width)
ok = (C >= c0[R]) & (C <= c1[R])                              # inside the shape, FR-18
flat_index = 0
for axis k in x, y, z, with stride 1, sx, sx·sy:
    i_k = floor((corner_k + 0.5) + R · down_k + C · right_k)  # nearest voxel, FR-19
    ok &= (0 <= i_k) & (i_k < size_k)                          # inside M, FR-20
    clamp i_k to 0 … size_k − 1
    flat_index += i_k · stride_k
values = flat[flat_index]
values[~ok] = 0                                                # FR-20
E[R, C] = values
```

- **Direct, not stepped.** Each pixel's point is computed from `corner` in one formula, not by adding a step again and again as in the assignment's
  `p = p + dp`. Rounding errors do not pile up along a row; in `float64` they stay far below `1e-9` of a voxel for any image of up to 4096 pixels.
  This keeps the rounding of FR-19 exact, and the result identical on every run (NFR-9).
- **`+ 0.5` once.** `corner_k + 0.5` is computed once per plane, so rounding to the nearest voxel costs a single `floor`.
- **Clamping.** After `ok` is known, each index is clamped into the volume. The read is then always a real voxel, even for pixels that are masked out,
  and the flat index always fits in `int32`: the largest is `1023³ − 1`, about `1.07 · 10⁹`, below `2³¹`.
- **`int32` indices** take half the memory traffic of `int64`.
- **Trimmed bands.** Near the apex of a triangle, the shape covers only a few columns. Trimming each band to the columns of its rows
  skips most of the empty corners of the rectangle: with 4 bands, about a third of the pixels of a triangle's rectangle.
- **Bands in threads.** NumPy releases Python's global lock inside its array operations, so bands of rows run at the same time on different cores.
  Each band writes its own rows of `E`, so no locking is needed, and the result does not depend on the number of bands.
  The default is 4 threads with one band each ([6](#6-speed)).

The memory used grows with `rows × cols`, never with the volume (NFR-6).

### 5.3 Worked example

The cake in the picture below is 10 × 10 × 10 voxels of three layers. The plane is the triangle `a = (5, 0, 8)`, `b = (1, 6, 0)`, `c = (9, 6, 0)`.

**Setup**, by the formulas of [4.2](#42-steps):

| Step | Result |
|---|---|
| `right` | `(8, 0, 0) / 8 = (1, 0, 0)` |
| `w` | `(−4, 6, −8) − (−4) · (1, 0, 0) = (0, 6, −8)` |
| `down` | `(0, 6, −8) / 10 = (0, 0.6, −0.8)` |
| `s` of `a, b, c` | `0, −4, 4`, so `s_min = −4` |
| `t` of `a, b, c` | `0, 10, 10`, so `t_min = 0` |
| image size | 9 columns, 11 rows |
| `corner` | `(5, 0, 8) − 4 · (1, 0, 0) = (1, 0, 8)` |

![The worked example: the triangle inside the cake, and the image it gives](../DATA/images/explain/how_a_cut_is_made.png)

**Row spans.** The edges `a → b` and `a → c` give `s_lo(r) = −0.4·r` and `s_hi(r) = 0.4·r`, so `c0[r] = ceil(4 − 0.4·r − 1e-6)` and `c1[r] = floor(4 + 0.4·r + 1e-6)`:

| Row | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| columns | 4 | 4 | 4 | 3 to 5 | 3 to 5 | 2 to 6 | 2 to 6 | 2 to 6 | 1 to 7 | 1 to 7 | 0 to 8 |

These are exactly the colored squares of the image in the picture above.
In row 5, `4 − 0.4·5 = 2` exactly, and the tolerance keeps column 2 inside the triangle.

**Two pixels.**

| Pixel | `corner + 0.5 + c·right + r·down` | Voxel | Layer |
|---|---|---|---|
| row 5, column 2 | `(1.5, 0.5, 8.5) + (2, 0, 0) + (0, 3, −4) = (3.5, 3.5, 4.5)` | `(3, 3, 4)` | cream |
| row 3, column 4 | `(1.5, 0.5, 8.5) + (4, 0, 0) + (0, 1.8, −2.4) = (5.5, 2.3, 6.1)` | `(5, 2, 6)` | cream |

Every point of this triangle is inside the volume, so `ok` depends on the row spans alone.

---

## 6. Speed

### 6.1 Measurements

The design of [section 5](#5-projection) was chosen by measuring a prototype, [tools/prototype_speed.py](../tools/prototype_speed.py),
on the benchmark of NFR-4: `DATA/croissant.nrrd` and 100 triangles of 501 × 501 pixels in random directions.
It times the sampling only, as NFR-3 defines, and counts the pixels that differ from the exact rounding of FR-19.

| Machine | |
|---|---|
| processor | Intel Core i7-10610U, 1.8 GHz, 4 cores, 8 threads |
| memory | 16 GB |
| system | Windows 11, Python 3.13.15, NumPy 2.5.4 |

This is a laptop, and the times change from run to run. The table shows the range of two runs of the final script.
"Threads / bands" is the number of threads working at the same time, and the number of bands the image is split into.

| Variant | Threads / bands | ms per frame | Frames per second | Pixels that differ |
|---|---|---|---|---|
| pixel list: only the pixels inside the triangle, gathered into one list and scattered back | 1 / 1 | 10.4 to 10.8 | 92 to 97 | 0 |
| pixel list | 4 / 4 | 8.4 to 8.7 | 115 to 118 | 0 |
| rectangle: every pixel of the image, with masks | 1 / 1 | 14.0 to 15.6 | 64 to 72 | 0 |
| rectangle | 4 / 4 | 6.9 to 8.1 | 124 to 144 | 0 |
| rectangle | 8 / 8 | 9.4 to 9.7 | 103 to 106 | 0 |
| **trimmed rectangle** | **4 / 4** | **5.2 to 5.4** | **184 to 194** | **0** |
| trimmed rectangle | 8 / 8 | 7.8 to 8.0 | 124 to 129 | 0 |
| trimmed rectangle | 4 / 16 | 12.9 to 13.1 | 76 to 78 | 0 |
| trimmed rectangle in `float32` | 4 / 4 | 5.2 to 5.6 | 180 to 194 | 620 |
| trimmed rectangle in fixed point, integers with 16 bits of fraction | 4 / 4 | 5.1 to 5.4 | 187 to 195 | 46,393 |

The 100 images hold about 25 million pixels in all.

### 6.2 The choice

**The trimmed rectangle in `float64`, with `int32` indices, 4 threads and 4 bands.**
It ran at 184 to 194 frames per second, about 6 times the minimum of NFR-1 and almost twice the target of NFR-2, with exact rounding.

- **Rectangle or pixel list.** On one thread the list is faster, because it skips the pixels outside the triangle.
  But it gains little from threads, probably because building the list and scattering the values back into the image keep Python's lock, so the threads wait for each other.
  Trimming gives the rectangle most of the saving of the list, and the rectangle splits well over threads.
- **4 threads.** The processor has 4 cores. With 8 threads, two threads share each core and compete for memory, and every run was slower.
  Splitting the image into more bands than threads was slower too. The number of threads is a parameter of the projection, with a default of 4.
- **`float64`.** In this measurement, 32-bit floats and fixed point are no faster, and they round some points to a different voxel than FR-19 requires:
  620 and 46,393 pixels. So the exact `float64` stays.

The real program is measured on the same benchmark by `tools/benchmark.py`. Its first run on the same laptop, as the median of 3 rounds,
gave 304 fps on the `uint8` croissant, and 297 and 253 fps on copies in `uint16` and `uint32`.
The full result goes into the experiment report.

### 6.3 Kept in reserve

If the program falls short of the target on another machine:

- Compile the inner loop with Numba, at the price of one more dependency.
- Project several frames at the same time in separate processes, which share the volume in memory.

---

## 7. Frames and video

### 7.1 Frame size

`W` is the largest `cols` and `H` the largest `rows` among the valid planes, each rounded up to an even number.
With no valid plane, the frames are 64 × 64 (FR-30). The sizes come from the setups, so no plane has to be projected first.

### 7.2 Gray levels

`GrayMap` turns an image of raw values into gray levels (FR-32) by this formula:

```
gray(v) = floor(255 · (v − lo) / (hi − lo) + 0.5), clipped to 0 … 255
```

- **8 and 16-bit volumes.** The map is a lookup table with one entry for each value from 0 to `hi`, at most 65,536 entries, built once.
  Converting an image is then a single read per pixel: `table[E]`.
- **32-bit volumes.** A table would be too large, so the formula is computed per pixel, in `float64`, which keeps it exact.
- **Black stays black.** A value of 0 gives 0: if `lo` is 0 by the formula, and if `lo` is above 0 by the clipping.
- **All values equal** (`hi = lo`): every value above 0 maps to 255.

Negative values were already set to 0 when the volume was read ([3.1](#31-volume)), so every value in `E` is 0 or more.

### 7.3 Placement

One frame buffer of `H × W` gray levels is kept for the whole run. For each plane it is set to 0, and the image is copied in at
column `(W − cols) // 2` and row `(H − rows) // 2` (FR-31). A bad plane leaves the buffer all black.

### 7.4 Encoding

The video is written with [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg), whose `pip` package carries its own copy of the FFmpeg encoder (NFR-11).

| Setting | Value | Why |
|---|---|---|
| codec | `libx264` (H.264) | FR-28 |
| input pixels | `gray`, one byte per pixel | the frames are gray levels |
| output pixels | `yuv420p` | plays in common players and browsers (FR-28) |
| frame rate | `--fps` | FR-33 |
| `macro_block_size` | 1 | by default the library resizes frames to a multiple of 16; even sizes are enough for `yuv420p` |

Frames go to the encoder one at a time, as they are made, so the video is never held in memory (NFR-6).
The encoder starts only after all the checks have passed, so a fatal error never leaves a video behind (FR-3).
OpenCV was considered and rejected: its `pip` package does not write H.264 without extra files.

---

## 8. Errors and the run report

### 8.1 Errors

| Problem | Where it is found | What happens |
|---|---|---|
| wrong arguments | `argparse`, at the start | usage message, exit code 2 (FR-3) |
| missing output folder | at the start | fatal error |
| unreadable or invalid volume | `read_volume` | fatal error |
| missing planes file, or no plane lines | `read_planes` | fatal error |
| bad plane | `read_planes` or `plane_setup` | a black frame and a warning (FR-24) |
| doubtful plane | `plane_setup` | drawn, with a warning (FR-25) |
| unexpected error while projecting one plane | around `Projector.project` | a black frame and a warning naming the plane (NFR-8) |
| unexpected error while writing the video | around the encoder | fatal error, and the unfinished file is deleted |

A fatal error is an `InputError` that carries the file and the cause. The main function catches it,
prints `error: <file>: <cause>` to the standard error without a traceback, and exits with code 1 (FR-4).
A warning is printed to the standard error as soon as it is found, in the format of FR-27.

### 8.2 Run report

Three timers use `time.perf_counter`:

| Timer | Covers |
|---|---|
| load | reading the volume and the planes file |
| projection | `plane_setup` and `Projector.project` for every plane: the time of NFR-3 |
| video | gray levels, placement, encoding and closing the file |

At the end the program prints the summary of FR-35 to the standard output, with the projection rate as the number of planes divided by the projection time.

---

## 9. Program structure

Each step of the pipeline is its own module, in a package named `plane_projection`.
Only `Ex0.py` talks to the user; the modules return results or raise `InputError`, and never print.

| Module | Contents | Uses | Requirements |
|---|---|---|---|
| `Ex0.py` | command line, main flow, warnings, report, exit codes | all the modules below | FR-1 to FR-4, FR-35, FR-36 |
| `plane_projection/errors.py` | `InputError` | | FR-4 |
| `plane_projection/volume.py` | `Volume`, `read_volume` | `errors`, `pynrrd` | FR-5 to FR-9 |
| `plane_projection/planes.py` | `Plane`, `read_planes` | `errors` | FR-10 to FR-14 |
| `plane_projection/geometry.py` | `PlaneSetup`, `plane_setup` | `planes` | FR-15 to FR-18, FR-21, FR-23 to FR-27 |
| `plane_projection/projector.py` | `Projector` | `volume`, `geometry` | FR-19, FR-20, NFR-1 to NFR-3, NFR-12 |
| `plane_projection/frames.py` | `frame_size`, `GrayMap`, `place` | `geometry` | FR-29 to FR-32 |
| `plane_projection/video.py` | `VideoWriter` | `errors`, `imageio-ffmpeg` | FR-28, FR-33, FR-34, NFR-6 |
| `tests/` | one test file for each module | | NFR-14 |
| `tools/benchmark.py` | the benchmark of NFR-4 | `geometry`, `projector` | NFR-1 to NFR-4 |

`Volume`, `Plane` and `PlaneSetup` are frozen data classes: once made, they do not change.
`Projector` and `VideoWriter` are classes because they hold something for the whole run, a pool of threads and an open encoder.
`VideoWriter` is a context manager, so the file is closed, or deleted after a fatal error, whatever happens.

The projection depends only on `Volume` and `PlaneSetup`, never on files, so the tests can build a small volume in memory,
such as the cake of the worked example, and check every pixel (NFR-12).

---

## 10. Complexity

`V` is the number of voxels, `P` the number of planes, `n` the number of pixels in one image, and `W × H` the frame size.

| Step | Time | Extra memory |
|---|---|---|
| read the volume | `O(V)`, once | `V` values, the only copy of the volume |
| read the planes | `O(P)` | `O(P)` |
| set up one plane | `O(rows)` | `O(rows)` |
| project one plane | `O(n)` | `O(n)` |
| gray levels, placement, encoding of one frame | `O(W × H)` | `O(W × H)` |

The work for one frame does not depend on the size of the volume. Only reading the file does.
