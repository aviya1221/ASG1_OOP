# Data

The data set, with the planes files that the demo and the tests run on next to their volumes.
It is described in [docs/DATA.md](../docs/DATA.md), and the planes files in the [testing strategy](../docs/TESTING.md#61-demo-planes-files).
The scripts that made it are in [data_generation/](../data_generation/).

| Volume | Planes files |
|---|---|
| `MRHead_1.nrrd`, the lecturer's MRI | `head.csv` |
| `onion.nrrd` | `onion.csv` |
| `biscuit_cake.nrrd` | `biscuit_cake.csv` |
| `swiss_roll.nrrd` | `swiss_roll.csv` |
| `croissant.nrrd` | `croissant.csv`, the speed benchmark, and `lecturer_example.csv`, the lecturer's example |
| `synthetic/dice.nrrd` | `synthetic/edge_cases.csv` |

`synthetic/` also holds the cake and the tomato with their label files, which the tests read.
`images/` holds a preview of every volume.
