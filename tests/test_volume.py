"""Reading the volume (docs/TESTING.md, section 4.1)."""

import gzip

import numpy as np
import pytest

from plane_projection.errors import InputError
from plane_projection.volume import read_volume


def values(shape, dtype):
    """A small volume whose values tell the voxels apart: x + 10·y + 100·z."""
    x, y, z = np.indices(shape)
    return (x + 10 * y + 100 * z).astype(dtype)


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16, np.uint32])
def test_unsigned_types_keep_type_and_values(write_nrrd, dtype):
    """FR-5, FR-6"""
    data = values((4, 3, 2), dtype)
    volume = read_volume(write_nrrd(data))
    assert volume.data.dtype == dtype
    assert np.array_equal(volume.data, data)


@pytest.mark.parametrize("dtype", [np.int8, np.int16, np.int32])
def test_signed_types_read_negative_values_as_zero(write_nrrd, dtype):
    """FR-6"""
    data = values((4, 3, 2), dtype) - 5
    volume = read_volume(write_nrrd(data))
    assert volume.data.dtype == dtype
    assert np.array_equal(volume.data, np.maximum(data, 0))


@pytest.mark.parametrize("dtype", [np.float32, np.float64, np.int64, np.uint64])
def test_other_types_are_fatal(write_nrrd, dtype):
    """FR-4, FR-6"""
    path = write_nrrd(values((4, 3, 2), dtype))
    with pytest.raises(InputError) as error:
        read_volume(path)
    assert error.value.path == str(path)
    assert "type" in error.value.cause


def test_raw_and_gzip_give_the_same_array(write_nrrd):
    """FR-5"""
    data = values((5, 4, 3), np.uint16)
    raw = read_volume(write_nrrd(data, "raw.nrrd", encoding="raw"))
    packed = read_volume(write_nrrd(data, "gzip.nrrd", encoding="gzip"))
    assert np.array_equal(raw.data, packed.data)


def test_ascii_encoding_is_fatal(write_nrrd):
    """FR-4, FR-5"""
    with pytest.raises(InputError, match="encoding"):
        read_volume(write_nrrd(values((2, 2, 2), np.uint8), encoding="ascii"))


def test_detached_header_is_fatal(write_nrrd):
    """FR-4, FR-5"""
    path = write_nrrd(values((2, 2, 2), np.uint8), "volume.nhdr", detached=True)
    with pytest.raises(InputError, match="detached"):
        read_volume(path)


@pytest.mark.parametrize("shape", [(4, 3), (4, 3, 2, 2)])
def test_other_dimensions_are_fatal(write_nrrd, shape):
    """FR-4, FR-5"""
    with pytest.raises(InputError, match="dimensions"):
        read_volume(write_nrrd(np.zeros(shape, np.uint8)))


@pytest.mark.parametrize("shape", [(1, 1, 1), (1023, 1, 1), (1, 1023, 1), (1, 1, 1023)])
def test_sizes_from_1_to_1023_are_read(write_nrrd, shape):
    """FR-7"""
    assert read_volume(write_nrrd(np.ones(shape, np.uint8))).shape == shape


@pytest.mark.parametrize("shape", [(1024, 1, 1), (1, 1024, 1), (1, 1, 1024)])
def test_size_1024_is_fatal(write_nrrd, shape):
    """FR-4, FR-7"""
    with pytest.raises(InputError, match="1023"):
        read_volume(write_nrrd(np.ones(shape, np.uint8)))


def test_first_axis_is_x(write_nrrd):
    """FR-8"""
    data = values((5, 4, 3), np.uint16)
    volume = read_volume(write_nrrd(data))
    assert volume.shape == (5, 4, 3)
    assert volume.data[3, 2, 1] == 3 + 10 * 2 + 100 * 1


def test_flat_view_shares_memory_and_indexing(write_nrrd):
    """FR-8, NFR-6"""
    volume = read_volume(write_nrrd(values((5, 4, 3), np.uint16)))
    sx, sy, _ = volume.shape
    assert np.shares_memory(volume.flat, volume.data)
    for x, y, z in [(0, 0, 0), (4, 3, 2), (1, 2, 1), (3, 0, 2)]:
        assert volume.flat[x + sx * (y + sy * z)] == volume.data[x, y, z]


def test_header_geometry_does_not_change_the_array(write_nrrd):
    """FR-9"""
    data = values((4, 3, 2), np.uint8)
    plain = read_volume(write_nrrd(data, "plain.nrrd"))
    placed = read_volume(write_nrrd(
        data, "placed.nrrd", space="left-posterior-superior",
        **{"space origin": np.array([86.6, -133.9, 116.8]),
           "space directions": np.array([[0.0, 1.0, 0.0], [0.0, 0.0, -1.3], [-2.0, 0.0, 0.0]])}))
    assert np.array_equal(plain.data, placed.data)


def test_lo_and_hi_after_negatives_are_zero(write_nrrd):
    """FR-32"""
    data = np.array([-7, 3, 300, 12], np.int16).reshape(2, 2, 1)
    volume = read_volume(write_nrrd(data))
    assert (volume.lo, volume.hi) == (0, 300)


def test_lo_and_hi_of_unsigned_volume(write_nrrd):
    """FR-32"""
    data = np.array([40, 7, 250, 12], np.uint8).reshape(2, 2, 1)
    volume = read_volume(write_nrrd(data))
    assert (volume.lo, volume.hi) == (7, 250)


def test_missing_file_is_fatal(tmp_path):
    """FR-4"""
    path = tmp_path / "missing.nrrd"
    with pytest.raises(InputError) as error:
        read_volume(path)
    assert error.value.path == str(path)


def test_file_that_is_not_nrrd_is_fatal(tmp_path):
    """FR-4"""
    path = tmp_path / "notes.nrrd"
    path.write_text("just some notes\n")
    with pytest.raises(InputError) as error:
        read_volume(path)
    assert error.value.path == str(path)


def test_cut_off_gzip_data_is_fatal(write_nrrd):
    """FR-4"""
    path = write_nrrd(values((20, 20, 20), np.uint16))
    content = path.read_bytes()
    header_end = content.index(b"\n\n") + 2
    assert gzip.decompress(content[header_end:])           # the data part is gzip
    path.write_bytes(content[:header_end + (len(content) - header_end) // 2])
    with pytest.raises(InputError):
        read_volume(path)
