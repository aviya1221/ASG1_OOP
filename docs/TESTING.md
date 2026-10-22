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
