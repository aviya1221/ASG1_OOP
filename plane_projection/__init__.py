"""Plane projection of a 3D volume: the package behind Ex0.py.

The modules follow the steps of the pipeline (docs/ALGORITHM.md, section 9). The modules here compute the image of
each plane, and the subpackage video turns the images into the frames of the video:

    errors      the error of a bad input file
    volume      read the NRRD volume
    planes      read the planes file
    geometry    set up and check each plane
    projector   sample the volume on a plane
    video/      the frames and the MP4 video
"""
