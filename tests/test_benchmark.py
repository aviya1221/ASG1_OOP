"""A quick run of the benchmark script on a small volume, so the script itself keeps working (docs/TESTING.md, section 7.1).

The real benchmark depends on the machine, so it is run by hand: python tools/benchmark.py
"""

import sys

from conftest import PROJECT_ROOT, index_volume

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import benchmark  # noqa: E402


def test_benchmark_runs(write_nrrd, write_csv, capsys):
    volume = write_nrrd(index_volume((40, 40, 40)))
    planes = write_csv("3, 19.5,0,20, 0,39,20, 39,39,20", "4, 0,0,5, 0,39,5, 39,0,5, 39,39,5", "3, 0,0,0, 1,1,1, 2,2,2")
    assert benchmark.main(["--volume", str(volume), "--planes", str(planes), "--rounds", "2", "--types"]) == 0
    out = capsys.readouterr().out
    for words in ("machine:", "uint32", "uint16", "fps median", "result:"):
        assert words in out
