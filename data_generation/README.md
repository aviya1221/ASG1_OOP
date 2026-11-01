# Data generation

The scripts that made the data set in [DATA/](../DATA/) and its planes files.
They are kept so the files can be made again; the program and the tests do not need them.
The data set itself is described in [docs/DATA.md](../docs/DATA.md).

| Script | Writes |
|---|---|
| `generate_foods.py` | the four food scans in `DATA/`, from the models in `onion.py`, `biscuit_cake.py`, `swiss_roll.py` and `croissant.py` |
| `generate_datasets.py` | the test volumes in `DATA/synthetic/`, from the models in `cake.py` and `tomato.py`, and the die |
| `make_demo_planes.py` | the planes files of the demo, each next to its volume |
| `make_previews.py` | the preview images in `DATA/images/` |

`head_style.py` holds what the food scans copy from `MRHead_1.nrrd`, `scan_simulation.py` the MRI effects they share,
and `garnish.py` the strawberries of the cake and the roll.

```
python data_generation/generate_foods.py         # about five minutes, for the 500³ croissant
python data_generation/generate_datasets.py
python data_generation/make_demo_planes.py
python data_generation/make_previews.py
```
