"""Plane projection of a 3D volume: the package behind Ex0.py.

The modules follow the steps of the pipeline (docs/ALGORITHM.md, section 9):

    volume      read the NRRD volume
    planes      read the planes file
    geometry    set up and check each plane
    projector   sample the volume on a plane
    frames      frame size, gray levels and placement
    video       write the MP4 video
"""
