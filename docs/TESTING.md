# Testing strategy

**Ex1: Plane projection of a 3D volume**
Version 1.0, 2026-10-22

This document describes how the program is tested: what each test checks, how the expected result is known, and when the tests run.
It builds on the [Software Requirements Specification](SRS.md), whose [section 7](SRS.md#7-verification) names the method for every requirement,
and on the [algorithm document](ALGORITHM.md), whose [section 9](ALGORITHM.md#9-program-structure) names the modules under test.

## Contents

1. [Goals and principles](#1-goals-and-principles)
2. [Test levels and tools](#2-test-levels-and-tools)
3. [Where the expected results come from](#3-where-the-expected-results-come-from)
4. [Unit tests](#4-unit-tests)
5. [Command-line tests](#5-command-line-tests)
6. [The demo](#6-the-demo)
7. [Speed, memory and robustness](#7-speed-memory-and-robustness)
8. [Portability and continuous integration](#8-portability-and-continuous-integration)
9. [Workflow and done criteria](#9-workflow-and-done-criteria)

---

## 1. Goals and principles

- **Every checkable requirement has a test.** Each test names the requirements it checks, so `grep FR-19 tests/` finds the tests of FR-19 (NFR-14).
- **The expected result never comes from the code under test.** It is computed by hand, by a separate slow reference, or from data whose answer is known by construction
  ([section 3](#3-where-the-expected-results-come-from)).
- **Small data first.** Most tests build a tiny volume in memory, a few voxels on a side, where every pixel can be checked.
  The files of the data set are used where real sizes, types and content matter.
- **Fixed seeds.** Every random input comes from a generator with a fixed seed, so a failure can be repeated.
- **Fast by default.** The everyday suite runs in under a minute. Slow tests are marked and run before every push.
- **Tests before code.** During the implementation, the tests of a module are written from this document before the module itself.

---

## 2. Test levels and tools

| Level | What it runs | Example | Requirements |
|---|---|---|---|
| unit | one module, in memory | `plane_setup` of the worked example gives 11 rows and 9 columns | FR-5 to FR-34 |
| command line | `Ex0.main()` in the same process, on files in a temporary folder | a missing volume file gives exit code 1 and one error line | FR-1 to FR-4, FR-23 to FR-36 |
| demo | `python Ex0.py` as a separate process, on the data set | the head demo writes a video with 280 frames | FR-1, FR-28 to FR-34 |
| speed and memory | the benchmark and memory measurements | 100 planes on the croissant at 30 fps or more | NFR-1 to NFR-7 |
| robustness | random and broken input | 1000 random lines give 1000 frames and no crash | NFR-8, NFR-9 |
| by eye | a person watches the videos and compares frames with 3D Slicer | the oblique head frames look like the Reformat view | FR-21, FR-28 |

**Tools.**

| Tool | Use |
|---|---|
| `pytest` | runs all the automated tests |
| `pytest-cov` | measures which lines of the package the tests reach |
| `tracemalloc` | measures the peak memory of NumPy arrays (from the Python standard library) |
| `imageio-ffmpeg` | reads the videos back, as well as writing them |
| 3D Slicer | shows the same plane with its Reformat module, for the checks by eye |

`pytest` and `pytest-cov` are only needed for development, so they go in `requirements-dev.txt`, not in `requirements.txt`.

**Layout.**

```
tests/
    conftest.py           shared fixtures: the cake volume, the index volume, writing small NRRD files
    reference.py          the slow reference projection (section 3.2)
    test_volume.py        one test file for each module of the package
    test_planes.py
    test_geometry.py
    test_projector.py
    test_frames.py
    test_video.py
    test_cli.py           Ex0.main() on temporary files
    test_demo.py          Ex0.py as a separate process on the data set
    test_robustness.py
```

**Markers** sort the tests by cost:

```
pytest                     # the everyday suite: unit and command-line tests, under a minute
pytest -m slow             # tests that read the data set files or write long videos
pytest -m "slow or not slow"   # everything
python tools/benchmark.py  # the speed benchmark, which depends on the machine and is not a pass-or-fail test of the suite
```

---

## 3. Where the expected results come from

A test is only as good as its expected result. These are the sources, from the simplest to the broadest.

### 3.1 Results worked out by hand

The worked example of [SRS 3.4](SRS.md#34-projection-geometry) is a 10 × 10 × 10 cake of three layers, with chocolate, cream and biscuit as the values 1, 2 and 3.
Its image for the triangle `a = (5, 0, 8)`, `b = (1, 6, 0)`, `c = (9, 6, 0)` is written out in the test as an 11 × 9 matrix,
copied from the [picture](../DATA/images/explain/how_a_cut_is_made.png) square by square.
The setup values, `right`, `down`, `corner` and the row spans, are written out too, from [ALGORITHM 5.3](ALGORITHM.md#53-worked-example).

### 3.2 A slow reference

`tests/reference.py` projects a plane the slowest and plainest way: one pixel at a time, in Python floats, following the text of SRS 3.4 line by line.
It shares no code with the package, and it decides "inside the shape" in a different way:

| | The package | The reference |
|---|---|---|
| speed | NumPy arrays, bands, threads | a Python loop over pixels |
| inside the shape | the row spans `c0[r]`, `c1[r]` ([ALGORITHM 4.3](ALGORITHM.md#43-row-spans)) | the point is on the inner side of every edge, by cross products |
| nearest voxel | `floor` on a whole array | `math.floor(p + 0.5)` for each axis |

The two must give the same image, pixel for pixel. Because they reach it in different ways, a mistake in one shows up as a difference.
The reference is slow, so it is used on images of up to about 60 × 60 pixels.

### 3.3 Volumes that show where each value came from

The **index volume** holds in each voxel its own position, `M[x][y][z] = x + 1000·y + 1000000·z`, in `uint32`.
Any pixel of any image can then be decoded back to the voxel it read, so a test sees not only that a pixel is wrong, but which voxel it took instead.
This is how the rounding of FR-19 and the edges of FR-20 are checked: the voxel is compared with `floor(p + 0.5)` computed separately.

### 3.4 Slices along the axes

For a plane perpendicular to an axis, with integer points, the image must equal a slice that NumPy cuts directly from the array (FR-22).
For example, the rectangle `(0, 0, z), (sx − 1, 0, z), (0, sy − 1, z), (sx − 1, sy − 1, z)`, written as a trapezoid, gives `M[:, :, z]` turned so that `x` runs along the columns.
This checks the axis order of FR-8 on the real files of the data set.

### 3.5 Shapes known in advance

`DATA/synthetic/dice.nrrd` holds exact values, 100000 for the body and 200000 for the pips, so some images are known before they are computed
([DATA/README.md](../DATA/README.md#syntheticdicenrrd)):

| Plane | Expected image |
|---|---|
| axial, `z = 139` | a 120 × 120 square of 100000, with one pip of 200000 in the middle |
| axial, `z = 20` | the same square with six pips |
| through the center, perpendicular to the main diagonal | a regular hexagon with a side of about 84.9, so an area of about 18,700 pixels |
| `x + y + z = 408.5` | an equilateral triangle with a side of about 56.6, cut off the corner `(159, 149, 139)` |

The number of body pixels, the number of pips and the area of each shape are checked, with a margin of one pixel along the edge.

### 3.6 Label volumes

The cake and the tomato of `DATA/synthetic/` come with a `.seg.nrrd` file that gives the material of every voxel.
Projecting the label file with a plane gives the material of every pixel. For example, a horizontal plane in the middle of the ganache layer of the cake
shows ganache everywhere inside the cake, and a plane through the tomato shows its gel brighter than its seeds in the scan.

### 3.7 3D Slicer

The Reformat module of 3D Slicer shows any plane of a volume. It smooths between voxels instead of taking the nearest one,
so its images are compared with ours by eye, not pixel for pixel.

---

## 4. Unit tests

Each table lists the cases of one module, with the requirements they check. Small NRRD and CSV files are written by the tests into a temporary folder.

### 4.1 `volume.py`: reading the volume

| Case | Expected | Requirements |
|---|---|---|
| a small volume of each type `uint8`, `uint16`, `uint32` | read with its type and values unchanged | FR-5, FR-6 |
| `int8`, `int16`, `int32` with some negative values | read, with the negative values set to 0 | FR-6 |
| `float32`, `float64`, `int64`, `uint64` | fatal error naming the type | FR-4, FR-6 |
| `raw` and `gzip` encodings | both read to the same array | FR-5 |
| `ascii` encoding, or a detached header (`.nhdr`) | fatal error | FR-4, FR-5 |
| 2 or 4 dimensions | fatal error | FR-4, FR-5 |
| a size of 1 on every axis, and 1023 on one axis | read | FR-7 |
| a size of 1024 on one axis | fatal error | FR-4, FR-7 |
| a volume whose values are `x + 10·y + 100·z` | `data[x, y, z]` holds that value: the first axis is `x` | FR-8 |
| the flat view | shares memory with the array, and `flat[x + sx·(y + sy·z)]` equals `data[x, y, z]` | FR-8, NFR-6 |
| a header with an unusual origin and spacing | the same array as without them | FR-9 |
| `lo` and `hi` | the smallest and largest values, after negatives were set to 0 | FR-32 |
| a missing file, a file that is not NRRD, a cut-off gzip file | fatal error naming the file | FR-4 |

### 4.2 `planes.py`: reading the planes

| Case | Expected | Requirements |
|---|---|---|
| a triangle line and a trapezoid line | 3 and 4 points, in the order of the line | FR-10, FR-12 |
| integers, decimals, `-3e2`, spaces around the fields | read as numbers | FR-10 |
| blank lines and `#` comments between planes | skipped; line numbers still count them | FR-11, FR-27 |
| a first line with a word in it | skipped as a header | FR-11 |
| the same line on line 2 | a bad plane, not a header | FR-11, FR-24 |
| 8, 10 or 13 numbers | a bad plane, with the count in its reason | FR-24 |
| a field `abc`, an empty field, `nan`, `inf` | a bad plane | FR-24 |
| a file with three planes and one bad line | four planes with frame numbers 1 to 4 and their line numbers | FR-23, FR-27 |
| an empty file, or one with only a header and comments | fatal error | FR-4, FR-14 |
| a missing file | fatal error naming the file | FR-4 |

### 4.3 `geometry.py`: plane setup and checks

| Case | Expected | Requirements |
|---|---|---|
| the worked example | `right = (1, 0, 0)`, `down = (0, 0.6, −0.8)`, `corner = (1, 0, 8)`, 9 columns, 11 rows, and the row spans of ALGORITHM 5.3 | FR-15 to FR-17 |
| the same triangle with `b` and `c` swapped | `right` reversed, so the image is mirrored | FR-21 |
| a rectangle written as a trapezoid | every row spans all the columns | FR-16, FR-18 |
| the apex | in row 0, at the column of its own `s` | FR-21 |
| a base of length `7.9999999` | counted as 8, so 9 columns | FR-16 |
| `b = c` | bad: base | FR-24 |
| three points on one line | bad: one line | FR-24 |
| `a''` 0.6 off the plane, and 0.4 off | bad, and valid | FR-24 |
| a trapezoid with `a'` and `a''` swapped, so its sides cross | bad: shape | FR-24 |
| a trapezoid with `a' = a''` | valid, with the same image as the triangle `a', b, c` | FR-24 |
| an image of 4097 columns, and of 4096 | bad: size, and valid | FR-24 |
| legs that differ by 0.6, and by 0.4 | a warning, and none | FR-25 |
| a trapezoid whose top side is tilted by 0.6 | valid, with a warning | FR-25 |
| 1000 random triangles and trapezoids | for every pixel, the row spans agree with the inside test of the reference | FR-18 |

### 4.4 `projector.py`: the projection

| Case | Expected | Requirements |
|---|---|---|
| the cake of the worked example | exactly the 11 × 9 matrix of [3.1](#31-results-worked-out-by-hand) | FR-17 to FR-21 |
| 1000 random planes on index volumes from 1 × 1 × 1 to 40 × 30 × 20, some partly or fully outside | the same image as the reference, pixel for pixel | FR-19, FR-20 |
| a point at exactly 2.5 on an axis | voxel 3: halves round up | FR-19 |
| a point at −0.5, and at `size − 0.5` | inside, and outside | FR-20 |
| a plane that misses the volume | all zeros, through the early exit | FR-26 |
| a plane with points near `10⁹` | all zeros, and no warning from NumPy about overflow | FR-20, NFR-8 |
| each value type | `E` has the type of the volume, and `uint32` values above 65535 are kept | FR-6, FR-20 |
| 1, 2, 4 and 8 threads | the same image every time | NFR-9 |
| slow: axis slices of `MRHead_1.nrrd`, the foods and the die | equal to NumPy slices ([3.4](#34-slices-along-the-axes)) | FR-8, FR-22 |
| slow: the planes of the die in [3.5](#35-shapes-known-in-advance) | the counts and areas listed there | FR-19, FR-20 |
| slow: the label volumes of [3.6](#36-label-volumes) | the expected materials | FR-19, FR-20 |

All the tests in this table, except the slow ones, build their volume in memory and open no file (NFR-12).

### 4.5 `frames.py`: frame size, gray levels, placement

| Case | Expected | Requirements |
|---|---|---|
| valid planes of 101 × 57 and 80 × 90 (columns × rows) | frames of 102 × 90 | FR-30 |
| no valid plane | frames of 64 × 64 | FR-30 |
| an image of 5 × 3 in a frame of 8 × 6 | placed at column 1, row 1, with black around it | FR-31 |
| a bad plane | an all-black frame | FR-24, FR-31 |
| `uint8`, `lo = 0`, `hi = 200`: the values 0, 100, 200 | 0, 128, 255 | FR-32 |
| every value from 0 to `hi` of a `uint16` volume | the table gives exactly the formula of FR-32 | FR-32 |
| `uint32` values up to `4·10⁹` | exactly the formula of FR-32 | FR-32 |
| `lo` above 0 | the value 0 is still black | FR-32 |
| all values equal | values above 0 are white, 0 is black | FR-32 |
| any input type | the frame is `uint8` | FR-32 |

### 4.6 `video.py`: writing the video

Each test writes a short video into a temporary folder and reads it back with `imageio-ffmpeg`.

| Case | Expected | Requirements |
|---|---|---|
| 10 frames of 64 × 48 at 30 fps | 10 frames of 64 × 48, codec `h264`, pixel format `yuv420p`, 30 fps | FR-28, FR-29, FR-33 |
| frames of different brightness | read back in the same order | FR-29 |
| a test pattern of stripes and steps | each frame within 2 gray levels of the original on average, since H.264 loses a little | FR-28 |
| `fps = 12.5` | a rate of 12.5 | FR-33 |
| an output file that already exists | replaced | FR-34 |
| an error raised while frames are being written | the unfinished file is deleted | FR-3 |
| an odd frame size | refused, since the frame size is always even by FR-30 | FR-30 |

---

## 5. Command-line tests

`tests/test_cli.py` calls `Ex0.main(argv)` in the same process, on small files in a temporary folder,
and captures the exit code, the standard output and the standard error.

| Case | Expected | Requirements |
|---|---|---|
| no arguments, two arguments, an unknown option, `--fps 0`, `--fps abc` | exit code 2 and the usage on the standard error | FR-1 to FR-3 |
| `--help` | exit code 0, and text that explains the three arguments and the planes file | FR-2, NFR-15 |
| a good run: a 20 × 20 × 20 volume and 5 planes | exit code 0, a video of 5 frames, the summary on the standard output, nothing on the standard error | FR-1, FR-29, FR-35, FR-36 |
| a missing volume, an invalid volume, a missing planes file, a planes file without planes, a missing output folder | exit code 1, one line `error: <file>: <cause>`, no traceback, and no video file | FR-3, FR-4 |
| one bad and one doubtful plane among good ones | exit code 0; two warnings in the format of FR-27, with the right line and frame numbers; one frame per plane line, the bad one black | FR-23 to FR-27 |
| planes of different sizes | the frame size is that of the largest valid plane, rounded up to even | FR-30 |
| the summary | counts the frames, the black frames and the warnings correctly | FR-35 |
| an error forced inside the projection of one plane | a black frame and a warning, exit code 0 | NFR-8 |
| an error forced inside the encoder | exit code 1, and no file left behind | FR-3 |
