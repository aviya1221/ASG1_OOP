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
