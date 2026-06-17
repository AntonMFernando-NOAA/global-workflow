#!/usr/bin/env python3
"""Downscale PBS resources in the C96 ecFlow .ecf scripts.

Applies the resource table from issue #2879 to specific scripts under
``dev/ecf/c96/scripts/``.  Each entry rewrites the `#PBS -l select=...`
and `#PBS -l walltime=...` directives to the C96 target values; all other
scripts are left untouched (they are already small enough at production
sizing).

Mapping (from the issue):

    job                       prod                       C96
    ------------------------- -------------------------- ----------------------------
    GFS forecast              295 nodes / 6h             1 node (82 ranks) / 3h
    GDAS forecast             95 nodes / 1h50m           1 node (82 ranks) / 20min
    ENKF forecast             8 nodes / 30min            1 node (70 ranks) / 20min
    Atmos analysis (GFS+GDAS) 75-100 nodes               4 nodes
    Marine analysis           8 nodes / 500GB            1 node / 24GB
    ENKF marine recenter      6 nodes / 45min            1 node / 10min

Usage::

    python3 dev/ecf/c96/downscale_resources.py        # apply edits in place
    python3 dev/ecf/c96/downscale_resources.py --check # report without writing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "dev" / "ecf" / "c96" / "scripts"

# Map of relative script path -> (new select line, new walltime line).
# Both lines include the leading "#PBS -l " prefix and no trailing newline.
DOWNSCALES: dict[str, tuple[str, str]] = {
    # GFS forecast: 1 node, 82 MPI ranks, 3h walltime.
    "gfs/forecast/jgfs_fcst.ecf": (
        "#PBS -l select=1:mpiprocs=82:ompthreads=1:ncpus=128",
        "#PBS -l walltime=03:00:00",
    ),
    # GDAS forecast: 1 node, 82 MPI ranks, 20m walltime.
    "gdas/forecast/jgdas_fcst.ecf": (
        "#PBS -l select=1:mpiprocs=82:ompthreads=1:ncpus=128",
        "#PBS -l walltime=00:20:00",
    ),
    # ENKF forecast (per member): 1 node, 70 MPI ranks, 20m walltime.
    "enkfgdas/forecast/jenkfgdas_fcst_master.ecf": (
        "#PBS -l select=1:mpiprocs=70:ompthreads=1:ncpus=128",
        "#PBS -l walltime=00:20:00",
    ),
    # GFS atmos analysis: 4 nodes (keep mpiprocs/ompthreads ratio).
    "gfs/analysis/atmos/jgfs_atmos_anal.ecf": (
        "#PBS -l select=4:mpiprocs=16:ompthreads=8:ncpus=128",
        "#PBS -l walltime=01:20:00",
    ),
    # GDAS atmos analysis: 4 nodes.
    "gdas/analysis/atmos/jgdas_atmos_anal.ecf": (
        "#PBS -l select=4:mpiprocs=16:ompthreads=8:ncpus=128",
        "#PBS -l walltime=01:40:00",
    ),
    # GFS marine analysis variational: 1 node / 24GB.
    "gfs/analysis/marine/jgfs_marine_analvar.ecf": (
        "#PBS -l select=1:mpiprocs=64:ompthreads=1:ncpus=64:mem=24GB",
        "#PBS -l walltime=00:30:00",
    ),
    # GDAS marine analysis variational: 1 node / 24GB.
    "gdas/analysis/marine/jgdas_marine_analvar.ecf": (
        "#PBS -l select=1:mpiprocs=64:ompthreads=1:ncpus=64:mem=24GB",
        "#PBS -l walltime=00:30:00",
    ),
    # GFS marine bmat: same downscale as analvar.
    "gfs/analysis/marine/jgfs_marine_bmat.ecf": (
        "#PBS -l select=1:mpiprocs=64:ompthreads=1:ncpus=64:mem=24GB",
        "#PBS -l walltime=00:30:00",
    ),
    "gdas/analysis/marine/jgdas_marine_bmat.ecf": (
        "#PBS -l select=1:mpiprocs=64:ompthreads=1:ncpus=64:mem=24GB",
        "#PBS -l walltime=00:30:00",
    ),
    # ENKF marine recenter: 1 node / 10min.
    "enkfgdas/analysis/recenter/jenkfgdas_marine_ens_recenter.ecf": (
        "#PBS -l select=1:mpiprocs=32:ompthreads=1:ncpus=32:mem=24GB",
        "#PBS -l walltime=00:10:00",
    ),
}

_SELECT_RE = re.compile(r"^#PBS\s+-l\s+select=.*$")
_WALLTIME_RE = re.compile(r"^#PBS\s+-l\s+walltime=.*$")


def downscale_one(path: Path, new_select: str, new_walltime: str,
                  *, write: bool) -> tuple[bool, list[str]]:
    """Rewrite ``select`` and ``walltime`` directives in ``path``.

    Returns ``(changed, messages)`` where ``changed`` is True if either
    line differed from the target (regardless of ``write``), and
    ``messages`` is a list of human-readable diff lines.
    """
    lines = path.read_text().splitlines(keepends=False)
    msgs: list[str] = []
    out: list[str] = []
    saw_select = False
    saw_walltime = False
    changed = False

    for ln in lines:
        if _SELECT_RE.match(ln):
            saw_select = True
            if ln != new_select:
                msgs.append(f"  select : '{ln}' -> '{new_select}'")
                changed = True
            out.append(new_select)
        elif _WALLTIME_RE.match(ln):
            saw_walltime = True
            if ln != new_walltime:
                msgs.append(f"  wall   : '{ln}' -> '{new_walltime}'")
                changed = True
            out.append(new_walltime)
        else:
            out.append(ln)

    if not saw_select:
        msgs.append("  WARN: no '#PBS -l select=' line found")
    if not saw_walltime:
        msgs.append("  WARN: no '#PBS -l walltime=' line found")

    if write and changed:
        # Preserve trailing newline only if the source had one.
        trailing = "\n" if path.read_text().endswith("\n") else ""
        path.write_text("\n".join(out) + trailing)

    return changed, msgs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="report differences without modifying files")
    args = parser.parse_args()

    rc = 0
    for rel, (sel, wall) in sorted(DOWNSCALES.items()):
        target = SCRIPTS_DIR / rel
        if not target.is_file():
            print(f"MISSING {rel}", file=sys.stderr)
            rc = 1
            continue
        changed, msgs = downscale_one(target, sel, wall, write=not args.check)
        status = "EDIT" if changed else "OK  "
        print(f"{status}    {rel}")
        for m in msgs:
            print(m)
    return rc


if __name__ == "__main__":
    sys.exit(main())
