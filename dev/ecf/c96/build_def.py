#!/usr/bin/env python3
"""Build dev/ecf/c96/defs/gfs_c96.def from ecf/defs/gfs_prod.def.

Derives a low-resolution 2-cycle ecFlow suite (12Z cold-start + 00Z) from
the production GFSv17 suite by:

  * slicing out only the 12Z and 00Z cycle families,
  * dropping cross-cycle triggers in 12Z (cold-start, no prior cycle),
  * remapping 00Z cross-cycle references from production's 18Z to our 12Z,
  * capping per-forecast-hour events and product tasks at f120 and clamping
    surviving trigger references that point above f120 to point at f120,
  * trimming the ENKF forecast ensemble (``task jenkfgdas_fcst_memNNN``)
    to members 001 and 002,
  * dropping the production trigger reference to
    ``analysis/recenter/jenkfgdas_atmos_ens_anal_sfc_regrid`` (the task
    actually lives under ``analysis/create/`` in production -- the trigger
    path is wrong upstream),
  * rewriting each cycle's ``cycle_end`` trigger so 12Z has no prior-cycle
    dependency and 00Z waits on 12Z,
  * dropping in-block ``edit ECF_FILES`` overrides so the suite-level setting
    takes effect for the C96 scripts directory,
  * stripping ``trigger :TIME >= ... and :TIME < ...`` wall-clock gates on
    the prep_fsm tasks so the suite runs purely on cross-cycle task deps
    (mirroring the C96C48mx500_S2SW_cyc_gfs Rocoto experiment),
  * inlining all suite-level variable overrides (HOMEgfs, ECF_FILES,
    ECF_JOB_CMD, DATAROOT, COMROOT, ...) that previously had to be applied
    by ``dev/ecf/c96/bootstrap.sh`` after every load -- the def file is
    now self-contained and a single ``--load`` is enough,
  * wrapping the result in a fresh ``gfs_c96`` suite header.

This script is the single source of truth for ``gfs_c96.def``; regenerate
the def in place with::

    python3 dev/ecf/c96/build_def.py

The output is overwritten and committed alongside this builder.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_DEF = REPO_ROOT / "ecf" / "defs" / "gfs_prod.def"
OUT_DEF = REPO_ROOT / "dev" / "ecf" / "c96" / "defs" / "gfs_c96.def"

# Cycle-family line ranges in gfs_prod.def (1-indexed, inclusive).
# These match ``family 00`` / ``family 12`` / closing ``endfamily`` blocks.
CYC00_RANGE = (14, 5899)
CYC12_RANGE = (11786, 17671)

# Forecast-hour cap for the C96 suite.
FHR_CAP = 120

# ---------------------------------------------------------------------------
# Suite-level variable defaults (formerly applied by dev/ecf/c96/bootstrap.sh)
# ---------------------------------------------------------------------------
# Inlining these into the def file means a single ``--load`` is enough to
# get a runnable suite -- no separate ``--alter`` step required.  The values
# below mirror the bootstrap script and are resolved at build time.

USER = os.environ.get("USER", "anton.fernando")
HOMEgfs_ABS = str(REPO_ROOT)
DEV_ROOT = f"/lfs/h2/emc/global/noscrub/{USER}/c96_run"
ECF_LOGHOST = "dlogin01"   # the login node where the dev ecflow_server lives
ECF_PORT = "2137"

# ENKF members to keep (production has 001-080).
KEEP_ENSMEM = {"001", "002"}


def _read_lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def _slice(lines: list[str], rng: tuple[int, int]) -> list[str]:
    start, end = rng
    return lines[start - 1:end]


# ---------------------------------------------------------------------------
# Forecast-hour filtering
# ---------------------------------------------------------------------------

# event N release_<thing>_f###
_EVENT_FHR_RE = re.compile(r"^\s*event\s+\d+\s+release_\S+_f(\d{3})\s*$")
# task jgfs_atmos_product_f### / jgfs_wave_post_<x>_f### / etc.
_TASK_FHR_RE = re.compile(r"^\s*task\s+\S*_f(\d{3})\s*$")
# Any token ending in _f### inside a trigger expression.
_FHR_TOKEN_RE = re.compile(r"_f(\d{3})\b")


def _strip_high_fhr(lines: list[str], cap: int) -> list[str]:
    """Drop event/task blocks above ``cap`` and clamp surviving triggers.

    Surviving trigger references that name an fhr above ``cap`` are
    rewritten to reference ``cap`` (the highest fhr that exists in the
    truncated suite), which keeps downstream tasks runnable.
    """
    cap_str = f"{cap:03d}"
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        m = _EVENT_FHR_RE.match(line)
        if m and int(m.group(1)) > cap:
            i += 1
            continue

        m = _TASK_FHR_RE.match(line)
        if m and int(m.group(1)) > cap:
            # A per-fhr product task is a small block (task / edit / edit /
            # trigger).  Skip until we hit the next sibling or structural
            # keyword at the same or shallower indent.
            base_indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(lines):
                nxt = lines[i]
                stripped = nxt.lstrip()
                indent = len(nxt) - len(stripped)
                if stripped and indent <= base_indent and (
                    stripped.startswith(("task ", "family ", "endfamily",
                                          "endsuite"))
                ):
                    break
                i += 1
            continue

        if "trigger " in line:
            line = _FHR_TOKEN_RE.sub(
                lambda mt: f"_f{cap_str}" if int(mt.group(1)) > cap
                                          else mt.group(0),
                line,
            )

        out.append(line)
        i += 1
    return out


# ---------------------------------------------------------------------------
# ENKF member filtering
# ---------------------------------------------------------------------------

_TASK_ENKF_FCST_MEM_RE = re.compile(
    r"^(?P<lead>\s*)task\s+jenkfgdas_fcst_mem(?P<mem>\d{3})\s*$")


def _strip_unwanted_enkf_members(lines: list[str]) -> list[str]:
    """Drop ``task jenkfgdas_fcst_memNNN`` blocks not in :data:`KEEP_ENSMEM`.

    Each task block is the ``task`` line plus its trailing ``edit`` lines
    (ENSMEM, MEMDIR), terminated by the next sibling task / family /
    endfamily / endsuite at the same or shallower indent.
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _TASK_ENKF_FCST_MEM_RE.match(lines[i])
        if m and m.group("mem") not in KEEP_ENSMEM:
            base_indent = len(m.group("lead"))
            i += 1
            while i < len(lines):
                nxt = lines[i]
                stripped = nxt.lstrip()
                indent = len(nxt) - len(stripped)
                if stripped and indent <= base_indent and (
                    stripped.startswith(("task ", "family ", "endfamily",
                                          "endsuite"))
                ):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


# ---------------------------------------------------------------------------
# Wall-clock trigger removal
# ---------------------------------------------------------------------------

# Lines like:  "              trigger :TIME >= 0300 and :TIME < 0630"
# These gate prep_fsm tasks on wall-clock time, which is a production
# proxy for "wait until obs are normally available".  For a C96 test we
# want the suite to flow as soon as cross-cycle task deps are met, so
# strip them entirely.  The release events on prep_fsm still fire when
# the (now trigger-free) fsm task completes.
_TIME_TRIGGER_RE = re.compile(r"^\s*trigger\s+:TIME\b")


def _strip_time_triggers(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not _TIME_TRIGGER_RE.match(ln)]


# ---------------------------------------------------------------------------
# Trigger-expression surgery
# ---------------------------------------------------------------------------

_TRIGGER_RE = re.compile(r"^(?P<lead>\s*trigger\s+)(?P<expr>.*\S)\s*$")


def _drop_terms_from_triggers(lines: list[str], should_drop) -> list[str]:
    """Remove trigger conjuncts where ``should_drop(term)`` is true.

    Triggers are split on `` and ``.  ``or`` is left untouched; none of the
    triggers we modify in this builder mix ``or`` with the dropped paths.
    """
    out: list[str] = []
    for line in lines:
        m = _TRIGGER_RE.match(line)
        if not m:
            out.append(line)
            continue
        terms = re.split(r"\s+and\s+", m.group("expr"))
        kept = [t for t in terms if not should_drop(t.strip())]
        if not kept:
            continue
        out.append(f"{m.group('lead')}{' and '.join(kept)}")
    return out


def _drop_cross_cycle(lines: list[str], cyc: str) -> list[str]:
    """Remove cross-cycle terms referencing ``../../../../<cyc>/...``."""
    cross = re.compile(r"^\.\./\.\./\.\./\.\./" + cyc + r"/")
    return _drop_terms_from_triggers(
        lines, lambda term: bool(cross.match(term)))


def _drop_terms_matching(lines: list[str], pattern: str) -> list[str]:
    """Remove trigger conjuncts whose text matches ``pattern``."""
    rx = re.compile(pattern)
    return _drop_terms_from_triggers(
        lines, lambda term: bool(rx.search(term)))


def _remap_cross_cycle(lines: list[str], src: str, dst: str) -> list[str]:
    """Rewrite ``../../../../<src>/...`` to ``../../../../<dst>/...``."""
    pat = re.compile(r"(\.\./\.\./\.\./\.\./)" + src + r"/")
    return [pat.sub(r"\g<1>" + dst + "/", ln) for ln in lines]


def _rewrite_cycle_end_trigger(lines: list[str], prev_cyc: str | None
                               ) -> list[str]:
    """Replace ``cycle_end``'s ``trigger ../<prev>/gdas/forecast == ...`` line.

    For ``prev_cyc=None`` (the cold-start cycle) the trigger is dropped
    entirely.  For ``prev_cyc='12'`` (used in the 00Z cycle) the trigger
    is rewritten to reference the 12Z gdas/forecast family.
    """
    out: list[str] = []
    rx = re.compile(
        r"^(\s*)trigger\s+\.\./\d{2}/gdas/forecast\s*==\s*active\s+or\s+"
        r"\.\./\d{2}/gdas/forecast\s*==\s*complete\s*$")
    for line in lines:
        m = rx.match(line)
        if not m:
            out.append(line)
            continue
        if prev_cyc is None:
            continue
        indent = m.group(1)
        out.append(
            f"{indent}trigger ../{prev_cyc}/gdas/forecast == active or "
            f"../{prev_cyc}/gdas/forecast == complete")
    return out


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_c96_def() -> str:
    prod_lines = _read_lines(PROD_DEF)

    cyc12 = _slice(prod_lines, CYC12_RANGE)
    cyc00 = _slice(prod_lines, CYC00_RANGE)

    # In-cycle ECF_FILES overrides; the suite header sets ECF_FILES once
    # for the C96 scripts directory and we don't want it shadowed.
    drop_ecf_files = lambda lns: [
        ln for ln in lns if not re.match(r"\s*edit\s+ECF_FILES\b", ln)]
    cyc12 = drop_ecf_files(cyc12)
    cyc00 = drop_ecf_files(cyc00)

    # Cross-cycle triggers.
    cyc12 = _drop_cross_cycle(cyc12, "06")
    cyc00 = _remap_cross_cycle(cyc00, "18", "12")

    # Production references a recenter-path task that actually lives in
    # analysis/create/; drop that single term from any triggers that name it.
    bad_term = (r"analysis/recenter/jenkfgdas_atmos_ens_anal_sfc_regrid"
                r"==complete")
    cyc12 = _drop_terms_matching(cyc12, bad_term)
    cyc00 = _drop_terms_matching(cyc00, bad_term)

    # Per-cycle cycle_end task: 12Z is cold-start so drop its trigger;
    # 00Z waits on 12Z's gdas/forecast.
    cyc12 = _rewrite_cycle_end_trigger(cyc12, prev_cyc=None)
    cyc00 = _rewrite_cycle_end_trigger(cyc00, prev_cyc="12")

    # Cap per-fhr events/tasks at f120 and clamp surviving triggers.
    cyc12 = _strip_high_fhr(cyc12, FHR_CAP)
    cyc00 = _strip_high_fhr(cyc00, FHR_CAP)

    # Trim ENKF forecast members.
    cyc12 = _strip_unwanted_enkf_members(cyc12)
    cyc00 = _strip_unwanted_enkf_members(cyc00)

    # Strip wall-clock triggers (`trigger :TIME >= ... and :TIME < ...`)
    # so the test suite runs purely on cross-cycle task dependencies,
    # mirroring the C96C48mx500_S2SW_cyc_gfs Rocoto experiment.
    cyc12 = _strip_time_triggers(cyc12)
    cyc00 = _strip_time_triggers(cyc00)

    header = [
        "# Auto-generated by dev/ecf/c96/build_def.py",
        "# Source: ecf/defs/gfs_prod.def (12Z + 00Z, downscaled for C96).",
        "# Do not edit by hand; regenerate via:",
        "#   python3 dev/ecf/c96/build_def.py",
        "#",
        "# This file is SELF-CONTAINED -- all the variables that used to be",
        "# applied by dev/ecf/c96/bootstrap.sh are now inlined below.  After",
        "# loading this def, the only manual step is to ensure DATAROOT,",
        "# COMROOT, and LOGROOT exist on disk:",
        f"#   mkdir -p {DEV_ROOT}/{{tmp,com,logs}}",
        "suite gfs_c96",
        "  family primary",
        "    # ---- repo / build paths (resolved at build_def.py runtime) ----",
        f"    edit HOMEgfs '{HOMEgfs_ABS}'",
        f"    edit HOMEglobal '{HOMEgfs_ABS}'",
        "    edit PACKAGEHOME '%HOMEgfs%'",
        "    edit gfs_ver 'v17.0'",
        "    # ---- ecflow client / job submission ----",
        f"    edit ECF_LOGHOST '{ECF_LOGHOST}'",
        f"    edit ECF_PORT '{ECF_PORT}'",
        "    edit ECF_FILES '%HOMEgfs%/dev/ecf/c96/scripts'",
        "    edit ECF_INCLUDE '%HOMEgfs%/dev/ecf/c96/include'",
        "    edit ECF_JOB_CMD 'qsub %ECF_JOB% 1> %ECF_JOBOUT% 2>&1'",
        "    edit ECF_KILL_CMD 'qdel %ECF_RID%'",
        "    edit ECF_STATUS_CMD 'qstat %ECF_RID% > %ECF_JOB%.stat 2>&1'",
        f"    edit ecflow_ver '5.6.0'",
        "    # ---- env / project metadata ----",
        "    edit NET 'gfs'",
        "    edit RUN 'gfs'",
        "    edit PROJ 'GFS'",
        "    edit PROJENVIR 'DEV'",
        "    edit MACHINE_SITE 'development'",
        "    edit ENVIR 'prod'",
        "    edit QUEUE 'dev'",
        "    edit QUEUE_ARCH 'dev_transfer'",
        f"    edit PDY '{date.today().strftime('%Y%m%d')}'",
        "    # ---- dev workspace (resolved at build_def.py runtime) ----",
        f"    edit DATAROOT '{DEV_ROOT}/tmp'",
        f"    edit COMROOT '{DEV_ROOT}/com'",
        f"    edit LOGROOT '{DEV_ROOT}/logs'",
        f"    edit OUTPUTDIR '{HOMEgfs_ABS}/dev/ecf/c96/output'",
        "    edit KEEPDATA 'YES'",
        "    # ---- production-flag stubs (test mode -- never push to NCO) ----",
        "    edit PARATEST 'NO'",
        "    edit DBNLOG 'NO'",
        "    edit SENDDBN 'NO'",
        "    edit SENDDBN_NTC 'NO'",
        "    edit SENDCANNEDDBN 'NO'",
        "    edit COMPATH ' '",
        "    edit MAILTO ' '",
        "    edit rrfs_ver ' '",
    ]
    body = cyc12 + cyc00
    footer = [
        "  endfamily                       //primary",
        "endsuite                          //gfs_c96",
    ]

    return "\n".join(header + body + footer) + "\n"


def main() -> None:
    OUT_DEF.parent.mkdir(parents=True, exist_ok=True)
    OUT_DEF.write_text(build_c96_def())
    n = sum(1 for _ in OUT_DEF.read_text().splitlines())
    print(f"Wrote {OUT_DEF} ({n} lines)")
    print()
    print("Next steps (no bootstrap.sh needed):")
    print(f"  mkdir -p {DEV_ROOT}/{{tmp,com,logs}}")
    print("  ecflow_client --delete=force=yes /gfs_c96 2>/dev/null")
    print(f"  ecflow_client --load={OUT_DEF.relative_to(REPO_ROOT)}")
    print("  ecflow_client --suspend=/gfs_c96")
    print("  ecflow_client --resume=/gfs_c96")
    print("  ecflow_client --begin=gfs_c96")


if __name__ == "__main__":
    main()
