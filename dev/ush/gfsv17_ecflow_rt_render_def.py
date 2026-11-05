#!/usr/bin/env python3
"""Render the GFSv17 ecflow realtime suite definition from gfs_prod.def.

The rendered definition differs from gfs_prod.def as follows:

* PACKAGEHOME, ENVIR, QUEUE, OUTPUTDIR and EXPDIR are set for the user, and
  ECF_INCLUDE, DATAROOT and COMROOT are added.
* ECF_INCLUDE and every ECF_FILES point to <EXPDIR>/ecf.
* All ``trigger :TIME`` lines are removed, so no job waits for the clock.
* The cycle_end tasks are removed. They cycle the suite by themselves (setpdy.sh,
  requeue and resume), which the run script does instead.
* There is one cycle family per cycle of the run, named PDYCYC and in run order:
  with --first-pdy 20260105 --first-cycle 12 --ncycles 3 the suite has the families
  2026010512, 2026010518 and 2026010600, each with its own PDY and CYC. Triggers
  that wait on the previous cycle point to the previous PDYCYC family. Triggers
  that wait on the cycle before the first one are removed.
* Every cycle family starts suspended; the run script releases them one by one.
"""

import re
import sys
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime, timedelta
from pathlib import Path

CYCLE_HOURS = ('00', '06', '12', '18')
DEFAULT_SRC = Path(__file__).resolve().parent.parent / 'ecf' / 'gfs' / 'defs' / 'gfs_prod.def'

CYCLE_FAMILY = re.compile(r"^    family (00|06|12|18)\s*$")
CYCLE_FAMILY_END = re.compile(r"^    endfamily\b")
TIME_TRIGGER = re.compile(r"^\s*trigger\s+:TIME\b")
CYCLE_END_TASK = re.compile(r"^(\s*)task cycle_end\s*$")
ECF_FILES = re.compile(r"^(\s*edit ECF_FILES )'[^']*'\s*$")
TRIGGER = re.compile(r"^(\s*)trigger\s+([^#]*?)\s*(#.*)?$")
CYCLE_REF = re.compile(r"(?:\.\./)+(00|06|12|18)/")


def run_cycles(first_pdy, first_cycle, ncycles):
    """Return the cycles of the run, in run order.

    Parameters
    ----------
    first_pdy : str
        Date of the first cycle (YYYYMMDD).
    first_cycle : str
        Hour of the first cycle: 00, 06, 12 or 18.
    ncycles : int
        Number of cycles to run.

    Returns
    -------
    list of tuple of (str, str, str)
        PDY, cycle hour and family name (PDYCYC) of each cycle, for example
        [('20260105', '12', '2026010512'), ('20260105', '18', '2026010518')] for
        ('20260105', '12', 2).
    """
    start = datetime.strptime(first_pdy + first_cycle, '%Y%m%d%H')
    cycles = []
    for i in range(ncycles):
        stamp = (start + timedelta(hours=6 * i)).strftime('%Y%m%d%H')
        cycles.append((stamp[:8], stamp[8:], stamp))
    return cycles


def drop_missing_cycle_waits(line, available):
    """Remove the trigger clauses that wait on a cycle family that is not kept.

    Parameters
    ----------
    line : str
        One line of the definition.
    available : list of str
        Cycle hours that a trigger can wait on.

    Returns
    -------
    str or None
        The line, the line without the removed clauses, or None if nothing
        is left of a trigger.

    Raises
    ------
    ValueError
        If a clause that cannot be split on "and" waits on a missing cycle.
    """
    match = TRIGGER.match(line)
    if not match or not any(ref not in available for ref in CYCLE_REF.findall(match.group(2))):
        return line
    kept = []
    for clause in re.split(r"\s+and\s+", match.group(2)):
        refs = CYCLE_REF.findall(clause)
        if all(ref in available for ref in refs):
            kept.append(clause)
        elif re.search(r"\sor\s|[()]", clause):
            raise ValueError(f"cannot remove a cycle wait from: {line.strip()}")
    if not kept:
        return None
    return f"{match.group(1)}trigger {' and '.join(kept)}"


def render_cycle(block, name, pdy, previous):
    """Render the lines of one cycle family block.

    Parameters
    ----------
    block : list of str
        Lines from "family NN" to its "endfamily".
    name : str
        Name of the family in the rendered definition (PDYCYC).
    pdy : str
        Date of the cycle, set as PDY on the family.
    previous : tuple of (str, str) or None
        Hour and family name of the cycle before this one, or None for the first cycle.

    Returns
    -------
    tuple of (list of str, int)
        The rendered lines and the number of ECF_FILES edits found.
    """
    available = [previous[0]] if previous else []
    out = []
    n_ecf_files = 0
    skip_below = None
    for line in block:
        if skip_below is not None:
            if line.strip() == '' or len(line) - len(line.lstrip()) > skip_below:
                continue
            skip_below = None
        match = CYCLE_END_TASK.match(line)
        if match:
            skip_below = len(match.group(1))
            continue
        if TIME_TRIGGER.match(line):
            continue
        match = ECF_FILES.match(line)
        if match:
            out.append(f"{match.group(1)}'%EXPDIR%/ecf/scripts'")
            n_ecf_files += 1
            continue
        line = drop_missing_cycle_waits(line, available)
        if line is None:
            continue
        if TRIGGER.match(line) and previous:
            line = CYCLE_REF.sub(lambda ref: ref.group(0).replace(f"/{previous[0]}/", f"/{previous[1]}/"), line)
        if CYCLE_FAMILY.match(line):
            out.extend([f"    family {name}", "      defstatus suspended", f"      edit PDY '{pdy}'"])
        else:
            out.append(line)
    return out, n_ecf_files


def render(lines, packagehome, comroot, dataroot, outputdir, expdir, first_pdy, first_cycle, ncycles):
    """Apply the development changes to the lines of gfs_prod.def.

    Parameters
    ----------
    lines : list of str
        Lines of the source definition, without line endings.
    packagehome : str
        Path of the global-workflow clone (PACKAGEHOME).
    comroot : str
        COMROOT of the experiment.
    dataroot : str
        DATAROOT of the experiment.
    outputdir : str
        OUTPUTDIR of the experiment.
    expdir : str
        EXPDIR of the experiment; the ecf scripts and include files are
        read from <expdir>/ecf.
    first_pdy : str
        Date of the first cycle to run (YYYYMMDD).
    first_cycle : str
        Hour of the first cycle to run.
    ncycles : int
        Number of cycles to run.

    Returns
    -------
    list of str
        Lines of the rendered definition.

    Raises
    ------
    ValueError
        If the source does not have the expected structure.
    """
    cycles = run_cycles(first_pdy, first_cycle, ncycles)
    header = {
        'PACKAGEHOME': [f"    edit PACKAGEHOME '{packagehome}'"],
        'ENVIR': ["    edit ENVIR 'para'"],
        'QUEUE': ["    edit QUEUE 'dev'"],
        'OUTPUTDIR': ["    edit ECF_INCLUDE '%EXPDIR%/ecf/include'",
                      f"    edit OUTPUTDIR '{outputdir}'",
                      f"    edit DATAROOT '{dataroot}'",
                      f"    edit COMROOT '{comroot}'"],
        'EXPDIR': [f"    edit EXPDIR '{expdir}'"],
    }

    # Split the source into the lines before, the cycle families, and the lines after
    head, tail, blocks, current = [], [], {}, None
    for line in lines:
        match = CYCLE_FAMILY.match(line)
        if match:
            current = blocks.setdefault(match.group(1), [])
            tail = []
        if current is not None:
            current.append(line)
            if CYCLE_FAMILY_END.match(line):
                current = None
        elif blocks:
            tail.append(line)
        else:
            head.append(line)
    if sorted(blocks) != sorted(CYCLE_HOURS):
        raise ValueError(f"expected the cycle families {CYCLE_HOURS}, found {sorted(blocks)}")

    out, seen_header = [], set()
    for line in head:
        match = re.match(r"^    edit (\w+) ", line)
        if match and match.group(1) in header:
            seen_header.add(match.group(1))
            out.extend(header[match.group(1)])
        else:
            out.append(line)
    missing = set(header) - seen_header
    if missing:
        raise ValueError(f"header edits not found in the source: {sorted(missing)}")

    n_ecf_files = 0
    previous = None
    for pdy, hour, name in cycles:
        rendered, count = render_cycle(blocks[hour], name, pdy, previous)
        out.extend(rendered)
        n_ecf_files += count
        previous = (hour, name)
    if n_ecf_files != 2 * len(cycles):
        raise ValueError(f"expected {2 * len(cycles)} ECF_FILES edits, found {n_ecf_files}")
    out.extend(tail)
    if any(re.match(r"^[^#]*:TIME\b", line) for line in out):
        raise ValueError("a :TIME expression is left that is not a plain trigger line")
    return out


def input_args():
    """Collect the command line arguments."""
    parser = ArgumentParser(description=__doc__.split('\n')[0],
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--src', type=Path, default=DEFAULT_SRC, help='definition to start from')
    parser.add_argument('--out', type=Path, required=True, help='rendered definition to write')
    parser.add_argument('--packagehome', required=True, help='global-workflow clone')
    parser.add_argument('--comroot', required=True, help='COMROOT')
    parser.add_argument('--dataroot', required=True, help='DATAROOT')
    parser.add_argument('--outputdir', required=True, help='OUTPUTDIR')
    parser.add_argument('--expdir', required=True, help='EXPDIR')
    parser.add_argument('--first-pdy', required=True, help='date (YYYYMMDD) of the first cycle')
    parser.add_argument('--first-cycle', choices=CYCLE_HOURS, required=True, help='hour of the first cycle')
    parser.add_argument('--ncycles', type=int, default=1, help='number of cycles to run')
    return parser.parse_args()


def main():
    """Render the definition and write it to --out."""
    args = input_args()
    if args.ncycles < 1:
        print("ERROR: --ncycles must be at least 1", file=sys.stderr)
        return 2
    try:
        datetime.strptime(args.first_pdy, '%Y%m%d')
    except ValueError:
        print("ERROR: --first-pdy must be YYYYMMDD", file=sys.stderr)
        return 2
    lines = args.src.read_text().splitlines()
    try:
        out = render(lines, args.packagehome, args.comroot, args.dataroot, args.outputdir, args.expdir,
                     args.first_pdy, args.first_cycle, args.ncycles)
    except ValueError as err:
        print(f"ERROR: cannot render {args.src}: {err}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(out) + '\n')
    names = ' '.join(name for _, _, name in run_cycles(args.first_pdy, args.first_cycle, args.ncycles))
    print(f"Rendered {args.out} with the cycle families {names}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
