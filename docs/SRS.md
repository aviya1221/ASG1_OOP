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
