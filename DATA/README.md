# Data set

Test volumes for the plane-projection algorithm. `MRHead_1.nrrd` is real MRI data supplied with the assignment.
`cake_3layers.nrrd` and `tomato.nrrd` are simulated MRI scans built from models of real objects; the cake is made to look like `MRHead_1.nrrd`.
Each comes with a `.seg.nrrd` file that holds the exact material of every voxel, as ground truth.
`dice.nrrd` is a simple geometric volume with one exact value per part.

| File | Source | Voxel type | Size (x × y × z) | Spacing (mm) | Content |
|---|---|---|---|---|---|
| `MRHead_1.nrrd` | 3D Slicer sample data | `int16` (signed) | 256 × 256 × 130 | 1 × 1 × 1.3 | T1-weighted MRI of a head |
| `cake_3layers.nrrd` | simulated MRI | `uint8` | 256 × 180 × 96 | 1 × 1 × 1.3 | T1-weighted scan of a rectangular three-layer cake, in the style of MRHead |
| `cake_3layers.seg.nrrd` | ground truth | `uint8` | 256 × 180 × 96 | 1 × 1 × 1.3 | material of every voxel of `cake_3layers.nrrd` (14 segments) |
| `tomato.nrrd` | simulated MRI | `uint16` | 204 × 196 × 184 | 0.4 × 0.4 × 0.4 | T2-weighted scan of a tomato |
| `tomato.seg.nrrd` | ground truth | `uint8` | 204 × 196 × 184 | 0.4 × 0.4 × 0.4 | tissue of every voxel of `tomato.nrrd` (11 segments) |
| `dice.nrrd` | synthetic geometry | `uint32` | 200 × 180 × 160 | 1 × 1 × 1 | game die with pips |

## Why these volumes

- **Every voxel type the assignment names.** The generated volumes cover unsigned 8 bits (cake), 16 bits (tomato) and 32 bits (die),
  and MRHead adds signed 16-bit. The die's values are above 65535, so an implementation that truncates to 16 bits fails on it.
- **A different size on every axis.** sx ≠ sy ≠ sz in each generated file, so swapping two axes gives a wrong-sized or wrong-looking image.
- **Anisotropic voxels.** Like MRHead, the cake has 1.3 mm between slices and 1 mm pixels, so the same plane looks different in voxel space
  and in millimeters.
- **Clear orientation.** The cake is rectangular (170 × 110 mm, about 87 mm tall) and square to the scanner axes, so axial, coronal and sagittal
  slices look clearly different. The tomato is tilted and off-center, like a real object in a scanner.
- **Asymmetric features.** The cake's missing corner and its strawberries along one side, the tomato's unequal chambers,
  and the die's pips all change if the output is flipped or transposed.
- **Realistic and exact data.** The cake and the tomato have the texture, blur and noise of real scans, while their segmentations give
  the exact material of every voxel. The die has one constant value per part and no noise, so tests can compare its pixels exactly.
- **Background margin.** No object touches the volume border, so planes that run past the border show the "outside = 0" rule cleanly.

MRHead differs from the generated volumes in two ways. It is signed, and its index axes are not aligned with the patient axes
(it was scanned in sagittal slices): its space directions are `(0,1,0) (0,0,-1) (-1.3,0,0)`, so i points posterior, j points inferior and k points right.
The generated volumes keep their index axes along x, y and z, so it is always clear which dimension a slice cuts.

## Conventions (generated volumes)

- Volumes are indexed `vol[x, y, z]`, the same as `M[x][y][z]` in the assignment. On disk x is the fastest axis, as the NRRD standard requires.
- Header: `space: left-posterior-superior`, `space origin: (0,0,0)`, `encoding: gzip`, and diagonal `space directions` holding the voxel size
  (1 × 1 × 1.3 mm for the cake, 0.4 mm for the tomato, 1 mm for the die).
- Voxel `(x, y, z)` is sampled at its center. Ranges written `[a, b)` include a and exclude b.
- In 3D Slicer the IJK index equals `(x, y, z)`. With voxel size (sx, sy, sz), RAS = `(-sx·x, -sy·y, sz·z)`, so the IJK-to-RAS matrix is `diag(-sx, -sy, sz)`.
- Slicer's Axial view shows x to the right and y downward. The Coronal view shows x to the right and z upward.

## Regenerating

```
python tools/generate_datasets.py                  # all volumes into DATA/
python tools/generate_datasets.py --only cake      # just one: cake, tomato or dice
```

The script reads each file back after writing it and checks the data, the header, the set of label values and a list of known voxels.
For the simulated scans it also checks that the main materials have the expected brightness order.
Random choices use fixed seeds, so the voxel data is identical on every run; only the creation-time comment that pynrrd puts in the header changes.
The label values are defined as `IntEnum`s: `Material` in `tools/cake.py`, `Tissue` in `tools/tomato.py`, `Dice` in `tools/generate_datasets.py`.

---

## `cake_3layers.nrrd` and `cake_3layers.seg.nrrd`

A simulated T1-weighted MRI scan of a rectangular three-layer cake, made to look like `MRHead_1.nrrd`:
the same voxel size (1 × 1 × 1.3 mm), the same intensity scale, the same noise level and the same black background.
256 × 180 × 96 voxels (a 256 × 180 × 124.8 mm field of view), stored as `uint8`; like MRHead's, the values stay below 255.
It is built in two steps (`tools/cake.py`, with the acquisition effects in `tools/scan_simulation.py`).

The cake sits square to the scanner axes, so each view is easy to recognize:

| View | What it shows |
|---|---|
| Axial (constant z) | the top view, 170 × 110 mm, shaped like an L because one corner piece is missing |
| Coronal (constant y) | the long side, 170 mm wide, with all the layers stacked |
| Sagittal (constant x) | the short side, 110 mm wide, with all the layers stacked |

In Slicer's Axial view the missing corner is at the top right, and the strawberries on top run along the lower edge.

**1. Material model.** All lengths in mm; the cake is centered on x = 128, y = 90.
- A porcelain platter (196 × 136 × 6 mm, z 8 to 14, with a raised edge) and a 2 mm cardboard cake board on it (z 14 to 16).
- The layered cake, 162 × 102 mm inside the frosting. The layers are trimmed flat. From the bottom:
  chocolate sponge (z 16 to 38), ganache (38 to 44), vanilla sponge (44 to 66),
  whipped cream with lengthwise strawberry slices (66 to 74), and vanilla sponge with 70 chocolate chips (74 to 96).
- Buttercream frosting, 4 mm thick on the sides and smoothed flat on top at z = 100.5, under a 2 mm ganache glaze.
- A chocolate truffle 32 mm across with a hazelnut inside, centered at (128, 90, 55).
- Five halved strawberries lying cut side down in a row along the back of the top (y ≈ 121), tips pointing back.
- The corner piece x ≥ 168, y ≤ 80 has been cut out, down to the board.

The random parts (strawberry slices, chips, textures and noise) come from a fixed seed (7).

**2. MRI simulation, matched to MRHead.** The contrast is T1-weighted, as in MRHead.
Fat-rich materials are bright like the scalp fat, the moist sponge is gray like brain tissue, and water-rich strawberries are darker.
Solid chocolate, cardboard and porcelain give almost no signal, as bone does in MRHead, so the platter and the board are in the
segmentation but do not show in the scan. The sponges are porous (fine grain, and gas holes stretched upward as the batter rose),
and their baked surfaces are drier, so a little darker. Then come the effects of the acquisition:
85% of the spatial frequencies are kept (slight blur and faint ringing at edges), a mild coil shading,
Rician noise with σ = 4.5 (as measured in MRHead's white matter), and the noise floor of 6 subtracted and clipped at 0.
That leaves MRHead's black background: a mean of 1.4 here, 1.5 in MRHead.

| Material | Label | Signal before blur and noise | Notes |
|---|---|---|---|
| Background (air) | 0 | 0 | faint noise, mostly exactly 0 |
| Platter | 1 | 0 | porcelain gives no MRI signal |
| Cake board | 2 | 3 | dry cardboard |
| Chocolate sponge | 3 | 66 | denser crumb, fewer holes |
| Ganache | 4 | 122 | |
| Vanilla sponge | 5 | 74 | airiest crumb, most holes |
| Whipped cream | 6 | 105 | |
| Chip sponge | 7 | 72 | vanilla sponge of the top layer |
| Chocolate chip | 8 | 16 | solid cocoa butter, about 7 × 7 × 5 mm |
| Strawberry | 9 | 44 | mostly water |
| Buttercream | 10 | 150 | mostly fat, like the scalp fat in MRHead |
| Glaze | 11 | 122 | |
| Truffle shell | 12 | 18 | solid chocolate, 2.5 mm |
| Truffle filling | 13 | 118 | |
| Hazelnut | 14 | 155 | nut oil |

For comparison, MRHead's gray matter is about 70, its white matter about 90 and its scalp fat about 140.
After the noise floor is subtracted, the measured means are a little lower than the table: buttercream ≈ 140, the sponges ≈ 55 to 63.

What the scan looks like:
- **Axial z = 42 (55 mm):** the L-shaped vanilla sponge, gray with dark holes, inside the bright frosting rim, with the truffle as a bright disk in a dark ring.
- **Axial z = 54 (70 mm):** the bright cream layer with dark teardrop-shaped strawberry slices.
- **Coronal y = 90:** the long side: three gray sponges, the bright ganache and cream bands, the truffle in the middle,
  dark chips in the top sponge, and the bright frosting around. The platter does not show, so the cake seems to float.
- **Coronal y = 60:** the same, but the right end is missing (the cut-out corner).
- **Sagittal x = 128:** the short side, with the truffle and a halved strawberry on top.

For tests, project `cake_3layers.seg.nrrd` with the same plane: every pixel of that image has an exact material label.

---

## `tomato.nrrd` and `tomato.seg.nrrd`

A simulated T2-weighted MRI scan of a tomato: 0.4 mm voxels, an 81.6 × 78.4 × 73.6 mm field of view, stored as `uint16`.
It is built in two steps (`tools/tomato.py`, with the acquisition effects in `tools/scan_simulation.py`).

**1. Tissue model.** A round tomato about 64 mm wide and 52 mm tall, with the anatomy of a real one:
a thin skin; a 6.2 mm outer wall (pericarp) with two rings of vascular bundles; five chambers (locules) filled with gel and separated by radial walls (septa);
a central column (columella) with a placenta lobe reaching into each chamber; 210 flat seeds clustered in the gel along the placenta;
and a slightly bent stem with six tapered sepals lying over the shoulders.
Nothing is perfectly regular. The outline has shallow grooves where the septa meet the wall and random dents; the septa bend; the chambers differ in size;
one chamber holds a small air pocket; and the fruit is tilted 8° and sits off-center, so no scan axis is aligned with the fruit.
The random parts come from a fixed seed (2026). The fruit center is at voxel (100, 101.2, 80).

**2. MRI simulation.** Each tissue gets a mean T2-weighted signal and its own texture (grain, patches, and streaks along the core and the stem).
The gel is slightly darker next to the walls, and the inner pericarp is brighter than the outer.
Then come the main effects of a real acquisition:
only the central 80% of the spatial frequencies are kept, which blurs edges slightly and leaves faint ringing next to them;
a smooth coil-sensitivity shading of about ±10%; and Rician noise with σ = 38, so air shows as faint noise (mean ≈ 48) instead of 0.

| Tissue | Label | Signal before blur and noise | Geometry |
|---|---|---|---|
| Background | 0 | 0 (noise, mean ≈ 48) | air around the fruit |
| Skin | 1 | 600 | outer 0.45 mm of the fruit |
| Pericarp | 2 | 1250, inner side brighter | 6.2 mm outer wall |
| Septum | 3 | 1150 | 5 radial walls, 1.8 mm thick, with rounded joints |
| Columella | 4 | 1100, fibrous | central column, radius 5.5 mm at the equator, running up to the stem |
| Placenta | 5 | 1450 | lobes reaching 4 mm from the columella into each chamber |
| Gel | 6 | 1900, darker next to walls | fills the chambers |
| Seed | 7 | 300 | 210 flat seeds, about 3.2 × 2.5 × 0.9 mm |
| Vascular bundle | 8 | 750 | 32 strands running pole to pole in the pericarp, 6 in the core |
| Stem | 9 | 600, fibrous | 4.2 mm wide, 13 mm long, slightly bent, with a swelling |
| Sepal | 10 | 750 | 6 thin leaves around the stem, curling up at the tips |
| Air pocket | 11 | 0 | a small gas gap against the wall of one chamber |

What the scan looks like:
- **Axial slice through the middle (z = 80):** a round outline with a slightly lobed edge, a gray wall with dark dots (vascular bundles),
  five bright chambers separated by gray spokes, and a darker core surrounded by dark seed flecks.
- **Coronal (y = 101) or sagittal (x = 100) slice through the middle:** an oval with the core as a vertical streaked band, seeds along both sides,
  and the sepals on top. The stem leans with the fruit, so it shows fully only in slices that follow the tilt. The air pocket is a black spot in one chamber.

For tests, project `tomato.seg.nrrd` with the same plane: every pixel of that image has an exact tissue label.

---

## `dice.nrrd`

`uint32`, 200 × 180 × 160. Both values are above 65535. The body is painted first and the pips over it.

| Part | Geometry | Value |
|---|---|---|
| Body | cube x in [40, 160), y in [30, 150), z in [20, 140); side 120, center (99.5, 89.5, 79.5) | 100000 |
| Pips | spheres of radius 9 centered on the face planes, keeping only the part inside the cube | 200000 |

The pips sit on a 3 × 3 grid on each face, 30 voxels apart, centered on the face. As on a real die, opposite faces add up to 7.

| Face | Pips | Pip positions on the face |
|---|---|---|
| +z (top, z = 139) | 1 | center |
| −z (bottom, z = 20) | 6 | x = 69.5 and 129.5, each at y = 59.5, 89.5 and 119.5 |
| +x (x = 159) | 2 | (y, z) = (59.5, 49.5) and (119.5, 109.5) |
| −x (x = 40) | 5 | four corners and the center |
| +y (y = 149) | 3 | (x, z) = (69.5, 49.5), (99.5, 79.5) and (129.5, 109.5) |
| −y (y = 30) | 4 | four corners |

Expected images:
- **Axial z = 139:** a 120 × 120 square with one pip in the middle.
- **Axial z = 20:** the same square with six pips.
- **Axial z = 80:** a 120 × 120 square with half a pip on the x = 40 edge and on the y = 149 edge (the center pips of the 5 and 3 faces).
- **Coronal y = 30:** a square with four pips.
- **Plane through the center, perpendicular to the main diagonal (x + y + z = 268.5):** a regular hexagon with side 60√2 ≈ 84.9. Pips show on five of its six edges.
- **Plane x + y + z = 408.5:** cuts off the corner (159, 149, 139) as an equilateral triangle with side 40√2 ≈ 56.6.

---

## Viewing in 3D Slicer

Drag a `.nrrd` file into the Slicer window, or use File → Add Data.
Drag a scan together with its `.seg.nrrd` file to see each material as a colored, named overlay.

| Tool | Use |
|---|---|
| Data Probe (bottom left) | shows the IJK index, the value and the segment under the mouse |
| Reformat module | slices the volume along any oblique plane, which is what our algorithm will do |
| Volume Rendering module | 3D view of the volume |
| Segmentations module → Show 3D | 3D model of each material |
| Volumes module → Window/Level, Lookup Table | brightness, contrast and colors |
