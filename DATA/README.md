# Data set

The main data set is the lecturer's example, `MRHead_1.nrrd`, and three food scans made in its style.
Each food is a single object with many layers, so a plane through it at any angle shows a cut object with its layers:
the kind of image the projection algorithm has to produce.

| File | Object | Layers | Size (cm) | Voxel size (mm) |
|---|---|---|---|---|
| `MRHead_1.nrrd` | human head, T1-weighted MRI | skin, fat, skull, fluid, gray and white matter, ventricles | | 1 × 1 × 1.3 |
| `onion.nrrd` | onion | 11 scales around two growing points | 9 wide, 10 tall with its neck and roots | 0.55 × 0.55 × 0.715 |
| `biscuit_cake.nrrd` | biscuit cake | 7 layers of biscuits, 6 of cream, chocolate on top | 24 long, 11 wide, 8 tall | 1 × 1 × 1.3 |
| `swiss_roll.nrrd` | Swiss roll | a spiral of sponge and cream, 4 turns | 26 long, 9 wide, 7.5 tall | 1.1 × 1.1 × 1.43 |

All four files hold 256 × 256 × 130 voxels of `int16`, as gzip-compressed NRRD.
The food scans are simulated MRI scans, made by `tools/generate_foods.py`.

Two more folders:
- `synthetic/` holds test volumes with an exact answer for every voxel: a cake, a tomato and a die.
- `real_scans/` holds four real CT scans from an earlier step: a teapot, a tooth, an engine and a carp.
  They are not single objects with many layers, so they are not part of the main set.

## What each view shows

The cake and the roll have clearly different lengths, widths and heights, and the onion has a clear top and bottom,
so each of the three views of 3D Slicer shows something else:

| File | Axial: from above | Coronal: from the front | Sagittal: from the side |
|---|---|---|---|
| `onion.nrrd` | rings around the two growing points | rings closing at the neck and at the base | the same, with the two growing points side by side |
| `biscuit_cake.nrrd` | one layer of biscuits: a grid with cream in the joints | the 11 cm short side: stripes of biscuit and cream | the 24 cm long side: the same stripes, with the joints between biscuits |
| `swiss_roll.nrrd` | the long side, with chocolate along both edges | the spiral | the long side, with chocolate on top and the seam at the bottom |

## What the food scans copy from the head scan

| Property | `MRHead_1.nrrd` | Food scans |
|---|---|---|
| Content | one head in the middle, on a black background | one food in the middle, on a black background |
| Layers | a line through the middle crosses 23 clear steps or lines | 13 (cake), 19 (roll), 35 (onion) |
| Grid | 256 × 256 × 130 voxels | the same |
| Voxel type | `int16`, values 0 to 279 | `int16`, values 0 to 200 |
| Voxel shape | 1 × 1 × 1.3 mm: slices 1.3 times farther apart than pixels | s × s × 1.3s, with s = 0.55, 1 or 1.1 mm |
| Orientation | sagittal slices: i runs front to back, j top to bottom, k left to right | the same |
| Space directions | (0,1,0) (0,0,−1) (−1.3,0,0) | the same, times s |
| Fill | about 90% of each axis | 93 to 97% of the longest side; the shorter sides fill less |
| Intensity | brain about 70, fat about 140 | the same scale: biscuits, sponge and onion about 60 to 100; cream 122 to 132; chocolate 150 |
| Background | 0 to about 8; 40% of it is 0, mean about 1.8 | the same |
| MRI look | soft edges with faint ringing, slow shading, noise σ ≈ 4.5 | the same, simulated |

Only the voxel size changes from food to food, so that each food fills the field of view the way the head does.
A real scanner does the same: a smaller object is scanned with smaller voxels.

Because all four files share the grid, a plane given in voxel indices fits every one of them,
so one CSV of planes can be run on the head and on each food.

## `onion.nrrd`

A yellow onion, about 90 mm wide; with its neck and roots it is about 103 mm tall. It leans 7° and its outline bulges a little.

- **Scales:** 11 fleshy scales, from 4.3 to 5 mm thick near the outside down to 2 mm in the middle.
  Every scale runs from the base plate at the bottom up into the neck, so a vertical cut shows rings that close at the top and at the bottom,
  and a horizontal cut shows closed rings.
- **Middle:** two growing points side by side, so the innermost rings split in two. The inner rings also sit a little off-center.
- **Between scales:** a thin dark line, with small air gaps here and there, more of them toward the neck.
- **Inside a scale:** a faint row of vascular bundles along its middle.
- **Bottom and top:** the base plate with a tuft of dry, trimmed roots under it, and the dry neck, cut off at a slant.
- **Outside:** the outermost scale is drying out, so it is darker. The papery skin gives no MRI signal.

## `biscuit_cake.nrrd`

A biscuit cake built in a loaf pan: 24 cm long (front to back), 11 cm wide and 8 cm tall, with the same voxels as the head scan.
It stands level on a tray, which gives no MRI signal, so its layers lie along the voxel rows. It is turned 1.5° and sits 10 mm left of the middle,
so the middle slices do not fall into a joint between biscuits.

- **Biscuits:** 7 layers of petit-beurre biscuits, 54 × 58 mm with a scalloped edge and a grid of pricked holes, 5.5 mm thick after soaking in milk.
  They are wet near their surfaces and drier, so darker, in their middle. Each layer has two biscuits across and five pieces along;
  the layers alternate between two patterns, with broken pieces at the ends, so the joints do not line up.
- **Cream:** 5.9 mm of vanilla cream between the layers and in the 2 mm joints between biscuits. It bulges out a little at the sides.
- **Chocolate:** 5 mm of ganache on top, the brightest part, as it is rich in fat.

The layers repeat every 11.4 mm, which gives a check of the geometry: a plane tilted by an angle α from the horizontal
shows the stripes 11.4 / sin α mm apart, for example 11.4 mm in a vertical plane and 22.8 mm at α = 30°.
The middle of the field of view falls in the middle of the fourth biscuit layer, so the Axial view opens on a layer of biscuits.

## `swiss_roll.nrrd`

A Swiss roll lying along the front-to-back axis: 26 cm long, 9 cm wide and 7.5 cm tall. It is turned 2.5°.

- **Spiral:** a sheet of sponge spread with whipped cream and rolled up: 4 layers of cream in a spiral of 6.1 mm sponge and 3.3 mm cream.
  The roll has settled, so it is wider than tall, and the spiral is not quite even along the roll.
- **Sponge:** with gas bubbles and darker baked surfaces.
- **Seam:** the roll lies on the end of the sheet, which thins out there, so a little cream shows at the bottom.
- **Chocolate:** 2.5 mm of ganache over the top and the sides. The two ends were cut off after it was poured, so they show the bare spiral.

## Making the food scans again

```
python tools/generate_foods.py                    # all three foods into DATA/
python tools/generate_foods.py --only onion       # just one: onion, biscuit_cake or swiss_roll
```

Each food is built from a model of the real object, then imaged the way the head was scanned (`tools/head_style.py`):
blurred by the limited resolution of MRI, shaded, given noise, and stored as `int16`.
Surfaces are drawn as the fraction of each voxel that they cover, so slanted surfaces come out smooth, not as staircases.
The script reads each file back and checks the data, the header, the value range, the dark background,
that the food does not touch the edge of the field of view, and that a line through its middle crosses at least 10 layer boundaries.
Random choices use fixed seeds, so the data is identical on every run.

## Conventions of the main set

- The volumes are indexed `vol[i, j, k]`, which is `M[x][y][z]` in the assignment. On disk i is the fastest axis, as the NRRD standard requires.
- As in the head scan, i runs from the front to the back, j from the top to the bottom and k from the left to the right of the object.
- In 3D Slicer the foods stand upright, like the head: the Axial view cuts horizontally, the Coronal view shows the object from the front,
  and the Sagittal view from the side.
- In the food scans, the middle of the field of view is at (0, 0, 0) mm. The head scan's origin is elsewhere: (86.6, −133.9, 116.8) mm.

---

# Test volumes: `DATA/synthetic/`

Generated volumes with known geometry. Each scan comes with an exact answer:
a `.seg.nrrd` segmentation for the simulated scans, and exact values for the die.
They are meant for automated tests of the algorithm, where the expected image must be known.

| File | Source | Voxel type | Size (x × y × z) | Spacing (mm) | Content |
|---|---|---|---|---|---|
| `synthetic/cake_3layers.nrrd` | simulated MRI | `uint8` | 256 × 180 × 96 | 1 × 1 × 1.3 | rectangular three-layer cake, scanned in the style of MRHead |
| `synthetic/cake_3layers.seg.nrrd` | ground truth | `uint8` | 256 × 180 × 96 | 1 × 1 × 1.3 | material of every voxel of the cake (14 segments) |
| `synthetic/tomato.nrrd` | simulated MRI | `uint16` | 204 × 196 × 184 | 0.4 × 0.4 × 0.4 | T2-weighted scan of a tomato |
| `synthetic/tomato.seg.nrrd` | ground truth | `uint8` | 204 × 196 × 184 | 0.4 × 0.4 × 0.4 | tissue of every voxel of the tomato (11 segments) |
| `synthetic/dice.nrrd` | synthetic geometry | `uint32` | 200 × 180 × 160 | 1 × 1 × 1 | game die with pips; values above 65535 |

```
python tools/generate_datasets.py                  # all test volumes into DATA/synthetic/
python tools/generate_datasets.py --only cake      # just one: cake, tomato or dice
```

The script reads each file back after writing it and checks the data, the header, the set of label values and a list of known voxels.
For the simulated scans it also checks that the main materials have the expected brightness order.
Random choices use fixed seeds, so the voxel data is identical on every run; only the creation-time comment that pynrrd puts in the header changes.
The label values are defined as `IntEnum`s: `Material` in `tools/cake.py`, `Tissue` in `tools/tomato.py`, `Dice` in `tools/generate_datasets.py`.
For a test, project the `.seg.nrrd` file with the same plane as the scan: every pixel of that image has an exact material label.

These files use simpler conventions than the main set:
- Volumes are indexed `vol[x, y, z]`, the same as `M[x][y][z]` in the assignment. On disk x is the fastest axis.
- Header: `space: left-posterior-superior`, `space origin: (0,0,0)`, `encoding: gzip`, and diagonal `space directions` holding the voxel size.
- Voxel `(x, y, z)` is sampled at its center. Ranges written `[a, b)` include a and exclude b.
- In 3D Slicer the IJK index equals `(x, y, z)`. With voxel size (sx, sy, sz), RAS = `(-sx·x, -sy·y, sz·z)`, so the IJK-to-RAS matrix is `diag(-sx, -sy, sz)`.
- Slicer's Axial view shows x to the right and y downward. The Coronal view shows x to the right and z upward.

## `synthetic/cake_3layers.nrrd`

A simulated T1-weighted MRI of a rectangular three-layer cake, made to look like `MRHead_1.nrrd`:
the same voxel size (1 × 1 × 1.3 mm), intensity scale, noise level (σ = 4.5) and black background. Built by `tools/cake.py`.
The cake (170 × 110 mm, about 87 mm tall) sits square to the axes, so the axial view shows the top, the coronal view the long side and the sagittal view the short side.

- From the bottom, on a platter and a cake board: chocolate sponge (z 16 to 38 mm), ganache (38 to 44), vanilla sponge (44 to 66),
  whipped cream with lengthwise strawberry slices (66 to 74), and vanilla sponge with chocolate chips (74 to 96). The layers are trimmed flat.
- Buttercream frosting, 4 mm on the sides and flat on top at z = 100.5, under a 2 mm ganache glaze; five halved strawberries along the back.
- A chocolate truffle with a hazelnut, 32 mm across, centered at (128, 90, 55) mm.
- The corner piece x ≥ 168, y ≤ 80 mm has been cut out.

| Material | Label | Signal | Notes |
|---|---|---|---|
| Background, platter | 0, 1 | 0 | porcelain gives no MRI signal |
| Cake board | 2 | 3 | |
| Chocolate, vanilla, chip sponge | 3, 5, 7 | 66, 74, 72 | porous, with gas holes; darker baked surfaces |
| Ganache, glaze | 4, 11 | 122 | |
| Whipped cream | 6 | 105 | |
| Chocolate chip, truffle shell | 8, 12 | 16, 18 | solid chocolate: almost no signal |
| Strawberry | 9 | 44 | mostly water |
| Buttercream | 10 | 150 | mostly fat, like MRHead's scalp fat |
| Truffle filling, hazelnut | 13, 14 | 118, 155 | |

## `synthetic/tomato.nrrd`

A simulated T2-weighted MRI of a tomato, 64 mm wide and 52 mm tall, with 0.4 mm voxels. Built by `tools/tomato.py`.
It has a skin, a 6.2 mm pericarp with vascular bundles, five gel-filled locules separated by septa, a columella with placenta lobes,
210 seeds, a stem with six sepals and a small air pocket. The fruit is tilted 8° and off-center, so no axis is aligned with it.
The gel is the brightest tissue and the seeds are dark; the background is Rician noise (mean ≈ 48).

| Tissue | Label | Signal | Tissue | Label | Signal |
|---|---|---|---|---|---|
| Background | 0 | 0 | Gel | 6 | 1900 |
| Skin | 1 | 600 | Seed | 7 | 300 |
| Pericarp | 2 | 1250 | Vascular bundle | 8 | 750 |
| Septum | 3 | 1150 | Stem | 9 | 600 |
| Columella | 4 | 1100 | Sepal | 10 | 750 |
| Placenta | 5 | 1450 | Air pocket | 11 | 0 |

## `synthetic/dice.nrrd`

`uint32`, 200 × 180 × 160, two exact values: the body (100000), the cube x in [40, 160), y in [30, 150), z in [20, 140),
and the pips (200000), spheres of radius 9 centered on the face planes. Opposite faces add up to 7:
+z has 1 pip, −z 6, +x 2, −x 5, +y 3 and −y 4.

Expected images:
- **Axial z = 139:** a 120 × 120 square with one pip in the middle; **axial z = 20:** six pips; **coronal y = 30:** four pips.
- **Plane through the center, perpendicular to the main diagonal (x + y + z = 268.5):** a regular hexagon with side 60√2 ≈ 84.9.
- **Plane x + y + z = 408.5:** cuts off the corner (159, 149, 139) as an equilateral triangle with side 40√2 ≈ 56.6.

---

# Other real scans: `DATA/real_scans/`

Four real CT scans from the Open Scientific Visualization Datasets collection, https://klacansky.com/open-scivis-datasets/,
converted to NRRD with the conventions of `synthetic/` above. They are not single objects with many layers, so they are not part of the main set.

| File | Object | Voxel type | Size (x × y × z) | Spacing (mm) | Credit |
|---|---|---|---|---|---|
| `boston_teapot.nrrd` | ceramic teapot with a small lobster inside | `uint8` | 256 × 178 × 256 | 1 × 1 × 1 | volvis.org and Terarecon Inc, MERL, Brigham and Women's Hospital |
| `tooth.nrrd` | tooth (micro-CT) | `uint8` | 103 × 94 × 161 | 1 × 1 × 1 | GE Aircraft Engines, Evendale, Ohio, USA |
| `engine.nrrd` | two cylinders of an engine block | `uint8` | 256 × 256 × 128 | 1 × 1 × 1 | volvis.org and General Electric |
| `carp.nrrd` | carp fish | `uint16` | 256 × 256 × 512 | 0.78125 × 0.390625 × 1 | Michael Scheuring, Computer Graphics Group, University of Erlangen, Germany |

Keep the credits with the data. To download them again:

```
python tools/fetch_real_scans.py
```

The script downloads each raw file over plain HTTP (the collection's HTTPS port does not answer), checks it against the collection's SHA-512 checksum,
and converts it. The teapot and the carp are turned so that they stand upright; both turns are rotations, so nothing is mirrored.

---

## Viewing in 3D Slicer

Drag a `.nrrd` file into the Slicer window, or use File → Add Data.
For the test volumes, drag a scan together with its `.seg.nrrd` file to see each material as a colored, named overlay.

| Tool | Use |
|---|---|
| Data Probe (bottom left) | shows the IJK index, the value and the segment under the mouse |
| Reformat module | slices the volume along any oblique plane, which is what our algorithm will do |
| Volume Rendering module | 3D view of the volume |
| Volumes module → Window/Level | brightness and contrast |
