#!/usr/bin/env python3
"""Build dev/ecf/c96/defs/gfs_c96.def from ecf/defs/gfs_prod.def.

Derives a low-resolution 2-cycle ecFlow suite (12Z cold-start + 00Z) from
the production GFSv17 suite by:

  * slicing out only the 12Z and 00Z cycle families,
  * dropping cross-cycle triggers in 12Z (cold-start, no prior cycle),
  * remapping 00Z cross-cycle references from production's 18Z to our 12Z,
  * capping per-forecast-hour events and product tasks at f120,
  * trimming the ENKF ensemble to members 001 and 002,
  * wrapping the result in a fresh ``gfs_c96`` suite header.

This script is the single source of truth for ``gfs_c96.def``; regenerate
the def in place with::

    python3 dev/ecf/c96/build_def.py

The output is overwritten and committed alongside this builder.
"""

from __future__ import annotations

import re
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
# ../../../forecast/jgfs_fcst_fsm:release_<thing>_f###
_TRIGGER_FHR_RE = re.compile(r":release_\S+_f(\d{3})\b")
# task jgfs_atmos_product_f### / jgfs_wave_post_<x>_f### / etc.
_TASK_FHR_RE = re.compile(r"^\s*task\s+\S*_f(\d{3})\s*$")


def _strip_high_fhr(lines: list[str], cap: int) -> list[str]:
    """Drop event/task blocks that target a forecast hour above ``cap``."""
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
            # A per-fhr product task is a 4-line block: task / edit FHR / edit
            # FHR_LIST / trigger.  Skip until we hit a line that starts a new
            # task or a structural keyword at the same or shallower indent.
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

        out.append(line)
        i += 1
    return out


# ---------------------------------------------------------------------------
# ENKF member filtering
# ---------------------------------------------------------------------------

_FAMILY_MEM_RE = re.compile(r"^(\s*)family\s+mem(\d{3})\s*$")


def _strip_unwanted_enkf_members(lines: list[str]) -> list[str]:
    """Drop ``family mem### ... endfamily`` blocks not in :data:`KEEP_ENSMEM`."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _FAMILY_MEM_RE.match(lines[i])
        if m and m.group(2) not in KEEP_ENSMEM:
            indent = len(m.group(1))
            depth = 1
            i += 1
            while i < len(lines) and depth > 0:
                stripped = lines[i].lstrip()
                line_indent = len(lines[i]) - len(stripped)
                if stripped.startswith("family "):
                    depth += 1
                elif stripped.startswith("endfamily") and line_indent == indent:
                    depth -= 1
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


# ---------------------------------------------------------------------------
# Cross-cycle trigger surgery
# ---------------------------------------------------------------------------

# Match a single cross-cycle reference of the form
#   ../../../../<cyc>/<path>==complete
# possibly followed/preceded by `` and `` joiners.
_CROSS_REF = r"\.\./\.\./\.\./\.\./{cyc}/[^\s]+?==complete"


def _drop_cross_cycle(lines: list[str], cyc: str) -> list[str]:
    """Remove every ``../../../../<cyc>/...==complete`` term from triggers.

    A trigger that consists entirely of cross-cycle terms (joined by `` and ``)
    is removed wholesale.  Otherwise the surviving conjuncts are preserved and
    the line is kept.
    """
    pattern = _CROSS_REF.format(cyc=cyc)
    leading_and = re.compile(r"\s+and\s+" + pattern)
    trailing_and = re.compile(pattern + r"\s+and\s+")
    standalone = re.compile(r"^(\s*trigger\s+)" + pattern + r"\s*$")

    out: list[str] = []
    for line in lines:
        if "trigger " not in line:
            out.append(line)
            continue
        if standalone.match(line):
            # Trigger is *only* the cross-cycle ref; check if there are
            # additional conjuncts on the same line.
            stripped = line.strip()
            if re.fullmatch(r"trigger\s+" + pattern, stripped):
                # Pure cross-cycle trigger; drop the whole trigger line.
                continue
        new = trailing_and.sub("", line)
        new = leading_and.sub("", new)
        # If the trigger keyword now has nothing to its right, drop the line.
        if re.match(r"^\s*trigger\s*$", new):
            continue
        out.append(new)
    return out


def _remap_cross_cycle(lines: list[str], src: str, dst: str) -> list[str]:
    pat = re.compile(r"(\.\./\.\./\.\./\.\./)" + src + r"/")
    return [pat.sub(r"\g<1>" + dst + "/", ln) for ln in lines]


# ---------------------------------------------------------------------------
# Reindent / structural rewrites
# ---------------------------------------------------------------------------

def _strip_indent(lines: list[str], n: int) -> list[str]:
    """Strip up to ``n`` leading spaces from each non-empty line."""
    out: list[str] = []
    for ln in lines:
        if not ln:
            out.append(ln)
            continue
        stripped_lead = len(ln) - len(ln.lstrip(" "))
        cut = min(n, stripped_lead)
        out.append(ln[cut:])
    return out


def build_c96_def() -> str:
    prod_lines = _read_lines(PROD_DEF)

    cyc12 = _slice(prod_lines, CYC12_RANGE)
    cyc00 = _slice(prod_lines, CYC00_RANGE)

    # 12Z is the cold-start; remove cross-cycle dependencies on prior 06Z.
    cyc12 = _drop_cross_cycle(cyc12, "06")
    # 00Z follows 12Z in our 2-cycle suite (production has it follow 18Z).
    cyc00 = _remap_cross_cycle(cyc00, "18", "12")

    # Cap product events/tasks at f120 in both cycles.
    cyc12 = _strip_high_fhr(cyc12, FHR_CAP)
    cyc00 = _strip_high_fhr(cyc00, FHR_CAP)

    # Trim ENKF ensemble to the requested members.
    cyc12 = _strip_unwanted_enkf_members(cyc12)
    cyc00 = _strip_unwanted_enkf_members(cyc00)

    # Both cycle blocks were originally indented by 4 spaces inside
    # ``family primary``; strip 2 of those so that, after we re-add a single
    # ``family primary`` wrapper at indent 2, the cycle families sit at indent
    # 4 -- matching production.
    cyc12 = _strip_indent(cyc12, 0)
    cyc00 = _strip_indent(cyc00, 0)

    header = [
        "# Auto-generated by dev/ecf/c96/build_def.py",
        "# Source: ecf/defs/gfs_prod.def (12Z + 00Z, downscaled for C96).",
        "# Do not edit by hand; regenerate via:",
        "#   python3 dev/ecf/c96/build_def.py",
        "suite gfs_c96",
        "  family primary",
        "    edit gfs_ver 'v17.0'",
        "    edit PACKAGEHOME '%HOMEgfs%'",
        "    edit NET 'gfs'",
        "    edit RUN 'gfs'",
        "    edit PROJ 'GFS'",
        "    edit PROJENVIR 'DEV'",
        "    edit MACHINE_SITE 'development'",
        "    edit ENVIR 'prod'",
        "    edit QUEUE 'dev'",
        "    edit QUEUE_ARCH 'dev_transfer'",
        "    edit OUTPUTDIR '%HOMEgfs%/dev/ecf/c96/output'",
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


if __name__ == "__main__":
    main()
