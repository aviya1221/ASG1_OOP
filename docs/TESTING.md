# Testing strategy

**Ex1: Plane projection of a 3D volume**
Version 1.0, 2026-10-22

This document describes how the program is tested: what each test checks, how the expected result is known, and when the tests run.
It builds on the [Software Requirements Specification](SRS.md), whose [traceability matrix](SRS.md#43-traceability-matrix) names the tests of every requirement,
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
| speed and memory | the benchmark and memory measurements | 100 planes on the croissant at 30 fps or more | NFR-1 to NFR-6 |
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

The worked example of [ALGORITHM 5.3](ALGORITHM.md#53-worked-example) is a 10 × 10 × 10 cake of three layers, with chocolate, cream and biscuit as the values 1, 2 and 3.
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

For a plane perpendicular to an axis, with integer points, the image must equal a slice that NumPy cuts directly from the array (FR-17, FR-19).
For example, the rectangle `(0, 0, z), (sx − 1, 0, z), (0, sy − 1, z), (sx − 1, sy − 1, z)`, written as a trapezoid, gives `M[:, :, z]` turned so that `x` runs along the columns.
This checks the axis order of FR-8 on the real files of the data set.

### 3.5 Shapes known in advance

`DATA/synthetic/dice.nrrd` holds exact values, 100000 for the body and 200000 for the pips, so some images are known before they are computed
([DATA.md](DATA.md#syntheticdicenrrd)):

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
so its view is compared with ours by eye. The filter behind it, `vtkImageReslice`, can also take the nearest voxel:
`tools/slicer_reslice.py` runs it inside 3D Slicer on our pixel grid, and the experiment compares the two images pixel for pixel
([experiment, section 2](../experiment/README.md#2-comparison-with-3d-slicer)).

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
| a triangle line `a, b, c` and a trapezoid line `a', b, a'', c` | 3 points, and 4 points kept as `a', a'', b, c` | FR-10, FR-12 |
| a triangle with and without the empty fields of the fourth point | the same points | FR-10, FR-12 |
| the lecturer's example file, as it is | 4 planes; the second trapezoid has legs of the same length | FR-10 to FR-12 |
| integers, decimals, `-3e2`, spaces around the fields | read as numbers | FR-10 |
| blank lines and `#` comments between planes | skipped; line numbers still count them | FR-11, FR-27 |
| the header of the lecturer's format on the first line | skipped as a header | FR-11 |
| a triangle with its empty fields on the first line | a plane, not a header | FR-11 |
| the header on line 2 | a bad plane, not a header | FR-11, FR-24 |
| 0, 2, 5, `3.5`, `-3` or `1e300` points | a bad plane, with the number of points in its reason | FR-12, FR-24 |
| 8 or 12 numbers for 3 points, 9, 11 or 13 for 4 | a bad plane, with the counts in its reason | FR-12, FR-24 |
| a field `abc`, an empty field, `nan`, `inf`, a line of commas | a bad plane | FR-24 |
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
| slow: axis slices of `MRHead_1.nrrd`, the foods and the die | equal to NumPy slices ([3.4](#34-slices-along-the-axes)) | FR-8, FR-19 |
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

---

## 6. The demo

The assignment asks for a demo run as `python Ex0.py file.nrrd file.csv file.mp4`. The demo is tested twice:
automatically, to check that every run produces the right video, and by eye, to check that the videos show what they should.

### 6.1 Demo planes files

The planes files of the demo are made by `tools/make_demo_planes.py`, with fixed numbers and seeds, and kept in `demo/`.
After writing a file, the script reads it back and checks every plane by the rules of [SRS 3.4 and 3.5](SRS.md#34-projection-geometry):
the five clean files must give no warning and no black frame, and each line of `edge_cases.csv` must give the result listed below.

```
python tools/make_demo_planes.py
```

| Planes file | Volume | Frames | Frame size | What the video shows |
|---|---|---|---|---|
| `demo/head.csv` | `DATA/MRHead_1.nrrd` | 280 | 256 × 256 | 130 slices `z = 0 … 129`, from one side of the head to the other; then 90 frames of a 256 × 256 square through the center, turning 2° per frame around the `y` axis, so the cut sweeps through oblique angles; then 60 frames of an equilateral triangle with sides of 180, turning 6° per frame around its middle within a plane tilted 40° from the axial plane |
| `demo/onion.csv` | `DATA/onion.nrrd` (`uint8`) | 120 | 256 × 256 | a square through the center, turning 3° per frame around an axis tilted 30° from upright |
| `demo/biscuit_cake.csv` | `DATA/biscuit_cake.nrrd` (`uint16`) | 120 | 256 × 256 | the same planes |
| `demo/swiss_roll.csv` | `DATA/swiss_roll.nrrd` (`uint32`) | 120 | 256 × 256 | the same planes |
| `demo/croissant.csv` | `DATA/croissant.nrrd` | 100 | 502 × 502 | the 100 planes of the speed benchmark (NFR-4), the same that `tools/prototype_speed.py` measured |
| `demo/edge_cases.csv` | `DATA/synthetic/dice.nrrd` | 16 | 282 × 244 | a header, comments, good triangles and trapezoids, a plane outside the volume, and one line for each bad and doubtful case of FR-24 and FR-25 |
| `demo/lecturer_example.csv` | `DATA/croissant.nrrd` | 4 | 454 × 502 | the example file the lecturer shared, unchanged: a triangle and a rectangle, then a triangle that is not isosceles and reaches out of the volume, and an isosceles trapezoid; the third line gives a warning for its legs (FR-25) |

The three foods use the three value types of the assignment, so together they show that the demo handles all of them.
All the files are in the format of the lecturer's example ([SRS 3.3](SRS.md#33-planes-file)), and start with its header line.
The five clean files hold nothing but the header and the planes, like the lecturer's example; `edge_cases.csv` adds comments
and blank lines (FR-11). `lecturer_example.csv` is not made by the script: it is the lecturer's file, kept as it is.

The lines of `edge_cases.csv`, with the frame and line numbers that the warnings must name (FR-27):

| Frame | Line | Plane | Expected |
|---|---|---|---|
| 1 | 11 | the top face, `z = 139`, as a rectangle | a 120 × 120 square with one pip |
| 2 | 13 | the bottom face, `z = 20`, in an isosceles trapezoid | the square with six pips |
| 3 | 16 | the front face, `y = 30`, as a rectangle, written with spaces around the numbers and `1.59e2` | the square with four pips |
| 4 | 18 | a triangle in the plane `x + y + z = 268.5` | a regular hexagon with sides of 84.9 |
| 5 | 21 | a triangle in the plane `x + y + z = 408.5` | an equilateral triangle with sides of 56.6, upside down |
| 6 | 25 | a triangle at `z = 300`, above the volume | black, without a warning (FR-26) |
| 7 | 29 | a triangle with legs of 188.8 and 226.6 | drawn, with a warning: equal legs (FR-25) |
| 8 | 31 | a trapezoid whose top side is not parallel to its base | drawn, with a warning: parallel sides (FR-25) |
| 9 | 35 | 4 points, but only the 9 numbers of a triangle | black, with a warning: count (FR-24) |
| 10 | 37 | a word | black, with a warning: numbers |
| 11 | 39 | `inf` | black, with a warning: numbers |
| 12 | 41 | `b = c` | black, with a warning: base |
| 13 | 43 | `a`, `b` and `c` on one line | black, with a warning: one line |
| 14 | 45 | `a''` 10 voxels off the plane of `a'`, `b` and `c` | black, with a warning: flat trapezoid |
| 15 | 47 | `a'` and `a''`, points 1 and 3, swapped, so the sides cross | black, with a warning: trapezoid shape |
| 16 | 49 | a base of 10199, so 10200 columns | black, with a warning: size |

The commands, from the project folder:

```
python Ex0.py DATA/MRHead_1.nrrd demo/head.csv demo/output/head.mp4
python Ex0.py DATA/onion.nrrd demo/onion.csv demo/output/onion.mp4
python Ex0.py DATA/biscuit_cake.nrrd demo/biscuit_cake.csv demo/output/biscuit_cake.mp4
python Ex0.py DATA/swiss_roll.nrrd demo/swiss_roll.csv demo/output/swiss_roll.mp4
python Ex0.py DATA/croissant.nrrd demo/croissant.csv demo/output/croissant.mp4
python Ex0.py DATA/synthetic/dice.nrrd demo/edge_cases.csv demo/output/edge_cases.mp4
python Ex0.py DATA/croissant.nrrd demo/lecturer_example.csv demo/output/lecturer_example.mp4
```

The videos go to `demo/output/`, which git ignores. The ones chosen for the experiment report are copied next to it.

### 6.2 Automatic checks

`tests/test_demo.py` (marked slow) runs each command above as a separate process, as a user would, and then reads the video back.

| Check | Expected | Requirements |
|---|---|---|
| exit code | 0 | FR-3 |
| the video | exists, is H.264 in `yuv420p`, and plays at 30 fps | FR-28, FR-33 |
| frames | one per plane line: 280, 120, 120, 120, 100 and 16 | FR-23, FR-29 |
| frame size | the largest valid plane of the file, rounded up to even | FR-30 |
| standard error | empty for the five clean files; for `edge_cases.csv` and `lecturer_example.csv`, exactly the expected list of warnings, with their line and frame numbers | FR-24 to FR-27, FR-36 |
| summary | printed, with the number of frames and the projection rate | FR-35 |
| black frames | in `edge_cases.mp4`, the frames of the bad lines and of the plane outside the volume are black | FR-24, FR-26 |
| known frames | frame 66 of `head.mp4` is within 3 gray levels on average of the slice `z = 65` after the gray map, and closer to it than to the slices around it; on the noise of the MRI, H.264 loses about 2.5 gray levels, and the next slices are 6 or more away | FR-19, FR-32 |

### 6.3 Checks by eye

A person watches every video and checks that:

- the motion is smooth, with no frame that jumps out of place;
- the brightness does not flicker between frames, since one gray map is used for the whole video (FR-32);
- the apex or top side of every shape is at the top of the frame, with `b` on the left (FR-21);
- the parts of a plane outside the volume are black (FR-20).

A few frames of each video are then compared with the same plane in the Reformat module of 3D Slicer ([3.7](#37-3d-slicer)). Two differences are expected:

- 3D Slicer smooths between voxels, while the program takes the nearest one (FR-19), so its images look softer.
- The program's pixels are voxel units (FR-13, FR-17), while 3D Slicer draws millimeters. The voxels of `MRHead_1.nrrd` are 1.3 times longer along `z`,
  so a cut that contains the `z` axis looks 1.3 times shorter along it than in 3D Slicer. The foods have the same voxel shape as the head; the croissant and the die have cubic voxels.

The experiment report shows frames of the program next to `vtkImageReslice` with the nearest voxel and with linear interpolation, as 3D Slicer shows them.

---

## 7. Speed, memory and robustness

### 7.1 Speed

`tools/benchmark.py` measures what NFR-3 defines, on the benchmark of NFR-4:

1. Read `DATA/croissant.nrrd`, and the 100 planes of `demo/croissant.csv`.
2. For every plane, time `plane_setup` and `Projector.project` together.
3. Repeat the 100 planes 3 times, and report the median rate, with the processor, memory, system and versions.

| Result | Meaning |
|---|---|
| 30 fps or more | NFR-1 is met |
| 100 fps or more | the target of NFR-2 is met |

The benchmark also runs on copies of the croissant in `uint16` and `uint32`, made in memory, to show how the value type changes the speed.
These rows are for information only; NFR-4 sets the target on `uint8`.

Speed depends on the machine, so the benchmark is not part of `pytest`. It runs whenever the projection changes, and on the final code before submission,
and its result goes into the experiment report. A quick test in the suite runs it on a small volume, so the script itself keeps working.

### 7.2 Memory

`tracemalloc` follows the arrays that NumPy allocates.

| Case | Expected | Requirements |
|---|---|---|
| the memory after reading a volume | at most 10% above the size of its data: one copy only | NFR-6 |
| the same 200 × 200 plane projected from volumes of 100³ and 400³, on one thread | the same peak memory for both, within 10%: it grows with the image, not the volume. With several threads the peak depends on how the bands overlap in time, so one thread gives a stable measure | NFR-6 |
| a full run with 10 planes and with 200 planes of 256 × 256 | each extra plane adds less than a quarter of a frame to the peak memory, so frames are not kept. The setup of each plane is kept, a few kB, as the complexity table of the algorithm document allows | NFR-6 |
| slow: a full run on the croissant | peak memory recorded in the experiment report | NFR-6 |

### 7.3 Robustness

| Case | Expected | Requirements |
|---|---|---|
| 1000 random lines from a fixed seed, the first of them a good plane so that it is not taken for a header: good planes, wrong numbers of points, wrong counts, words, empty fields, `±1e300`, `nan`, `inf`, repeated points, points on one line, lines of commas only, very long lines | exit code 0, 1000 frames, no traceback | NFR-8, FR-23 |
| the same file with no good plane at all | exit code 0 and 64 × 64 black frames | FR-30, NFR-8 |
| the demo planes projected twice | the images `E`, and the frames before encoding, identical byte for byte | NFR-9 |

---

## 8. Portability and continuous integration

A GitHub Actions workflow, `.github/workflows/tests.yml`, runs the tests on every push to the repository:

| Item | Value |
|---|---|
| systems | Windows, Ubuntu and macOS |
| Python | 3.12 and 3.13 |
| install | a new environment each time, from `requirements.txt` and `requirements-dev.txt` only |
| tests | the everyday suite on every system; the slow tests and the demo on Ubuntu with Python 3.13 |
| coverage | `pytest-cov` reports the lines of the package and of `Ex0.py` that the tests reach; the goal is 90% or more |

A fresh install on three systems shows that the program runs on all of them (NFR-10),
and that every dependency, the video encoder included, comes from `pip` (NFR-11).
The data set is part of the repository, so the slow tests have their files. A badge in the README shows the result of the last run.

---

## 9. Workflow and done criteria

### 9.1 Workflow

1. The package is built module by module, in the order of the pipeline. For each module, the tests of its table are written first and seen to fail,
   then the module is written until they pass. Tests and code are committed in small steps.
2. Before every commit, `pytest` runs. Before every push, all the tests run, the slow ones included.
3. A bug found later first gets a test that shows it, and only then the fix.
4. An item of the roadmap in the README is marked done only when the tests pass on the continuous integration.

### 9.2 Requirements and their tests

| Requirements | Sections of this document |
|---|---|
| FR-1 to FR-4 | [5](#5-command-line-tests), [6.2](#62-automatic-checks) |
| FR-5 to FR-9 | [4.1](#41-volumepy-reading-the-volume), [3.4](#34-slices-along-the-axes) |
| FR-10 to FR-14 | [4.2](#42-planespy-reading-the-planes) |
| FR-15 to FR-18 | [4.3](#43-geometrypy-plane-setup-and-checks), [3.1](#31-results-worked-out-by-hand), [3.2](#32-a-slow-reference) |
| FR-19 to FR-21 | [4.4](#44-projectorpy-the-projection), [3.2](#32-a-slow-reference) to [3.6](#36-label-volumes) |
| FR-23 to FR-27 | [4.2](#42-planespy-reading-the-planes), [4.3](#43-geometrypy-plane-setup-and-checks), [5](#5-command-line-tests), [6.2](#62-automatic-checks) |
| FR-28 to FR-34 | [4.5](#45-framespy-frame-size-gray-levels-placement), [4.6](#46-videopy-writing-the-video), [5](#5-command-line-tests), [6](#6-the-demo) |
| FR-35, FR-36 | [5](#5-command-line-tests), [6.2](#62-automatic-checks) |
| NFR-1 to NFR-4 | [7.1](#71-speed) |
| NFR-6 | [7.2](#72-memory) |
| NFR-8, NFR-9 | [7.3](#73-robustness), [4.4](#44-projectorpy-the-projection), [5](#5-command-line-tests) |
| NFR-10, NFR-11 | [8](#8-portability-and-continuous-integration) |
| NFR-12 | [4.4](#44-projectorpy-the-projection) |
| NFR-14 | [2](#2-test-levels-and-tools), [8](#8-portability-and-continuous-integration): one test file per module, and the coverage report |
| NFR-15 | [5](#5-command-line-tests) |

### 9.3 Done criteria

The testing is complete when:

- all the tests pass on the continuous integration, on all three systems;
- the tests reach 90% or more of the lines of the package and of `Ex0.py`;
- the benchmark reaches 30 fps or more, and its result, against the target of 100, is written in the experiment report;
- all six demo videos are made, checked by eye, and compared with the reslicing filter of 3D Slicer;
- every requirement in the table above has its tests.
