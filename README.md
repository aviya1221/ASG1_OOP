# Ex1: Plane projection of a 3D volume

Introduction to Software Engineering (OOP, OOD), exercise 1.

Given a 3D volume and a plane, produce the 2D image the volume shows on that plane:
the "cut" that 3D Slicer shows in its axial, coronal and sagittal views, but along any plane, not only the three axes.

![How a cut is made: a sheet of grid squares placed at an angle inside a layered cake, then laid flat as an image](DATA/images/explain/how_a_cut_is_made.png)

*A 10 × 10 × 10 cake of three layers, a triangle placed at an angle inside it, and the image that comes out.
Each square of the output image takes the value of the voxel under its point in the volume.*

## The problem

**Input**

- A 3D matrix `M` of size `sx × sy × sz`, with `1 <= sx, sy, sz < 2^10` (at most 1023 on each axis).
  Each entry `M[x][y][z]` is an unsigned integer of 8, 16 or 32 bits.
  The volume is read from an [NRRD](https://teem.sourceforge.net/nrrd/format.html) file, the format of the 3D Slicer project.
- A plane `p`, given by 3 or 4 points in 3D:
  - **3 points** `a, b, c`: an isosceles triangle with apex `a`, so `dist(a,b) = dist(a,c)`.
  - **4 points**: an isosceles trapezoid, two sides of equal length on the same plane, `a' → b` and `a'' → c`.

**Output**

- A 2D matrix (image) `E` holding the values of `M` along the triangle (or trapezoid).
  Points of the plane that fall outside `M` get the value 0.

**The algorithm given in the assignment** (for the triangle; the trapezoid works the same way):

```
Dab = dist(a,b) = dist(a,c)
Dbc = dist(b,c)
v(a,b) = vector(a,b) / Dab          # unit step from a toward b
v(a,c) = vector(a,c) / Dab          # unit step from a toward c
E = new matrix of size Dab * Dbc

a1 = a, a2 = a
for y in 0 .. Dab-1:                # one output row per unit step down the sides
    a1 = a1 + v(a,b)
    a2 = a2 + v(a,c)
    d12 = dist(a1, a2)
    dp  = vector(a1, a2) / d12      # unit step along the row
    p   = a1
    for x1 in 0 .. d12:             # one output pixel per unit step along the row
        v = M[p]  (0 if p is outside M)
        x = Dbc/2 - d12/2 + x1      # center the row in E
        E[x][y] = v
        p = p + dp
return E
```

The assignment states that this problem is **not well defined for implementation**:
the pseudo-code leaves open questions that a detailed design has to answer (see [Open questions](#open-questions)).

## The program

The demo is run as:

```
python Ex0.py file.nrrd file.csv file.mp4
```

| Argument | Meaning |
|---|---|
| `file.nrrd` | the 3D volume |
| `file.csv` | a list of planes, each given by the coordinates of 3 or 4 points |
| `file.mp4` | the output video: one frame per plane, in the order of the CSV |

**Performance:** on a volume of 500³ bytes the projection must run at **30 frames per second at least**, and **100 is expected**.

## Scope

**In scope**

- Reading NRRD volumes of unsigned 8, 16 and 32-bit values, raw or gzip-compressed.
- Reading the planes from a CSV file, triangles (3 points) and trapezoids (4 points).
- Computing the projection image of each plane, correct and stable for any plane,
  including planes that lie partly or fully outside the volume.
- Writing the images as frames of an MP4 video.
- Meeting the speed target on a 500³ volume.
- Documents: this README, an SRS, a detailed description of the algorithm, the data set and a testing strategy.
- Tests, including tests of the demo, and an experiment with its results and output video.

**Out of scope**

- A graphical interface or an interactive viewer (3D Slicer is used to look at the data).
- Volume rendering: "projection" here means sampling the values on the plane, not summing or ray-casting through the volume.
- File formats other than NRRD for input and MP4 for output.
- Editing or segmenting the volume.

## Open questions

The design (SRS and algorithm document) has to settle these:

1. **Coordinate system.** Are the points in voxel indices, or in the physical space of the NRRD header
   (origin, spacing and direction, as 3D Slicer shows them)? The lecturer's `MRHead_1.nrrd` has voxels of 1 × 1 × 1.3 mm.
2. **Sampling between voxels.** `p` is almost never on a whole voxel: take the nearest voxel, or interpolate between neighbours?
3. **Rounding.** `Dab`, `Dbc`, `d12` and `x` are real numbers; how are they rounded to sizes and indices of `E`?
   The loop moves `a1` and `a2` before the first row, so the apex row is skipped; is that intended?
4. **Pixels outside the triangle.** `E` is a rectangle and the triangle covers about half of it; what value do the other pixels get?
5. **The trapezoid.** In which order are its 4 points written, and which of them are `a'`, `a''`, `b` and `c`?
6. **Invalid input.** What to do when the triangle is not isosceles (up to what tolerance), when the points are on one line,
   or when two points are the same?
7. **CSV format.** One plane per line? A header line? How are the 3 and 4 point planes told apart?
8. **Video frames.** Each plane gives an image of a different size, but an MP4 needs one frame size:
   pad, scale, or fix the size? How are 16 and 32-bit values mapped to the 8-bit gray levels of a video? At what frame rate?
9. **Axis order and signed data.** NRRD stores `x` fastest; how does that map to `M[x][y][z]`?
   `MRHead_1.nrrd` is signed 16-bit (all its values are positive) though the assignment speaks of unsigned values.
10. **What the speed target measures.** The projection alone, or also reading the file and writing the video?
    For which planes (the largest plane through a 500³ cube is about 866 voxels across)?

## Data

The data set is described in [DATA/README.md](DATA/README.md): the lecturer's MRI head scan,
simulated MRI scans of layered foods (including a 500³ file for the speed test), test volumes with known answers,
and a few real CT scans. Preview images are in [DATA/images/](DATA/images/).

The scripts that make the data are in [tools/](tools/). To set up:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Roadmap

- [x] Create a repository, define the problem and the scope (this README)
- [ ] Software Requirements Specification (SRS)
- [ ] Detailed description of the main algorithm
- [x] Data set of NRRD files (first version, see [DATA/README.md](DATA/README.md))
- [ ] Testing strategy, including the demo
- [ ] Implementation
- [ ] Demo: `python Ex0.py file.nrrd file.csv file.mp4`
- [ ] Experiment and a short description of its results, with the output video
