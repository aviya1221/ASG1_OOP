# Deviations from the assignment text

The algorithm in the assignment is a description, and it leaves points open.
Where the [Software Requirements Specification](SRS.md) differs from it, this is why.

| Topic | Assignment | This project | Reason |
|---|---|---|---|
| computation | two points walk down the legs, and a third walks along each row between them | a direct formula for every pixel ([FR-17](SRS.md#34-projection-geometry)) | all the pixels of an image can be computed at once, which is what makes the speed target reachable in Python; for an isosceles triangle it covers the same shape |
| row spacing | each row moves one unit along the legs | each row moves one unit along the height ([FR-17](SRS.md#34-projection-geometry)) | in the assignment, rows are only `height / Dab` apart while pixels in a row are 1 apart, so the image is squeezed vertically; here both are 1 apart and the proportions are true. In the worked example of the [algorithm document](ALGORITHM.md#53-worked-example) `Dab = √116 ≈ 10.77` and the height is 10 |
| apex row | skipped, because `a1` and `a2` move before the first row is read | row 0 ([FR-21](SRS.md#34-projection-geometry)) | the apex is part of the triangle |
| image size | `Dab × Dbc` | `floor(height) + 1` rows and `floor(Dbc) + 1` columns for a triangle ([FR-16](SRS.md#34-projection-geometry)) | follows from the row spacing, and from counting both ends of each side |
| indexing | `E[x][y]` | `E[r][c]` | the same picture, written in the row-first order of NumPy |
| triangle shape | isosceles | any triangle, with a warning ([FR-25](SRS.md#35-input-validation)) | the lecturer said the input triangles are isosceles; other triangles are accepted as a small extra, with a warning, because rounding makes the legs slightly unequal anyway |
| sampling | `M[p]` for a point `p` with fractions, not specified further | the nearest voxel ([FR-19](SRS.md#34-projection-geometry)) | the fastest choice; interpolation between voxels can be added later as an option |
| value types | unsigned 8, 16 and 32 bits | signed types too ([FR-6](SRS.md#32-volume-file)) | the lecturer's `MRHead_1.nrrd` is `int16` |
