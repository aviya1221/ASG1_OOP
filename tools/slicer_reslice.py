"""Reslice planes with vtkImageReslice inside 3D Slicer, for the comparison of the experiment (tools/run_experiment.py).

vtkImageReslice is the VTK filter that 3D Slicer uses to draw its slice views. This script runs inside Slicer's own
Python, loads the volume the way Slicer loads it, and samples each plane on the same pixel grid as our program:
pixel (r, c) at corner + c·right + r·down, in voxel indices. It shares no code with the package.

Each plane is sampled twice: with the nearest voxel, as our program does, and with linear interpolation, as Slicer
shows a slice by default. The images are saved as nearest0, linear0, nearest1, linear1, ... in an .npz file.

Usage (run by tools/run_experiment.py):
    Slicer.exe --no-splash --no-main-window --python-script tools/slicer_reslice.py VOLUME PLANES.json OUT.npz
"""

import json
import sys

import numpy as np
import slicer
import vtk
from vtk.util import numpy_support


def reslice(image, plane, nearest: bool) -> np.ndarray:
    corner, right, down = plane["corner"], plane["right"], plane["down"]
    normal = np.cross(right, down)
    axes = vtk.vtkMatrix4x4()
    for row in range(3):
        axes.SetElement(row, 0, right[row])
        axes.SetElement(row, 1, down[row])
        axes.SetElement(row, 2, normal[row])
        axes.SetElement(row, 3, corner[row])
    filter = vtk.vtkImageReslice()
    filter.SetInputData(image)
    filter.SetResliceAxes(axes)
    filter.SetOutputSpacing(1, 1, 1)
    filter.SetOutputOrigin(0, 0, 0)
    filter.SetOutputExtent(0, plane["cols"] - 1, 0, plane["rows"] - 1, 0, 0)
    filter.SetBackgroundLevel(0)
    if nearest:
        filter.SetInterpolationModeToNearestNeighbor()
    else:
        filter.SetInterpolationModeToLinear()
    filter.Update()
    values = numpy_support.vtk_to_numpy(filter.GetOutput().GetPointData().GetScalars())
    return values.reshape(plane["rows"], plane["cols"]).copy()


def main() -> None:
    volume_path, planes_path, out_path = sys.argv[1:4]
    node = slicer.util.loadVolume(volume_path)
    image = node.GetImageData()               # in voxel indices: origin 0, spacing 1
    planes = json.loads(open(planes_path, encoding="utf-8").read())
    images = {}
    for number, plane in enumerate(planes):
        images[f"nearest{number}"] = reslice(image, plane, nearest=True)
        images[f"linear{number}"] = reslice(image, plane, nearest=False)
    np.savez_compressed(out_path, **images)
    print(f"resliced {len(planes)} planes of {volume_path}, VTK {vtk.vtkVersion.GetVTKVersion()}, "
          f"3D Slicer {slicer.app.applicationVersion}")


try:
    main()
finally:
    slicer.app.exit(0)
