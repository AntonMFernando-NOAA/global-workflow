#!/usr/bin/env python3
"""Render the GFSv17 ecflow realtime suite definition from gfs_prod.def.

The rendered definition differs from gfs_prod.def as follows:

* PACKAGEHOME, ENVIR, QUEUE, OUTPUTDIR and EXPDIR are set for the user, and
  ECF_INCLUDE, DATAROOT and COMROOT are added.
* ECF_INCLUDE and every ECF_FILES point to <EXPDIR>/ecf.
* The suite keeps the four cycle families 00, 06, 12 and 18 but not their cycle_end
  tasks. Every family is suspended and has an edited PDYCYC (YYYYMMDDCC), the date
  of the run it holds. The cycle families of the run get the PDYCYC of their first
  run: with --first-pdy 20260105 --first-cycle 12 the families 12 and 18 get
  2026010512 and 2026010518 and 00 gets 2026010600. The family of the cycle before
  the first one (06) gets 2026010506; it is to be forced complete when the suite starts.
* The jgdas_fcst task of each family has NEXT_CYC edited to the hour of the next
  cycle. When it ends, tail.h gives that family its PDYCYC (the one of this cycle plus
  6 hours), requeues it and resumes it, which is what cycle_end does in production.
  Only the first cycle is resumed by hand.
* A task that waited only on the clock (``trigger :TIME ...``) has no trigger: it
  runs once its family is resumed.
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
CYCLE_END_TASK = re.compile(r"^      task cycle_end\s*$")
FCST_TASK = re.compile(r"^(\s*)task jgdas_fcst\s*$")
ECF_FILES = re.compile(r"^(\s*edit ECF_FILES )'[^']*'\s*$")


def cycle_pdycycs(first_pdy, first_cycle):
    """Return the PDYCYC that each cycle family has when the suite is loaded.

    Parameters
    ----------
    first_pdy : str
        Date of the first cycle (YYYYMMDD).
    first_cycle : str
        Hour of the first cycle: 00, 06, 12 or 18.

    Returns
    -------
    dict of str to str
        PDYCYC (YYYYMMDDCC) of each cycle hour. The three cycles after the first one,
        and the first one, have the PDYCYC of their first run; the cycle before the
        first one has the PDYCYC it had before the run starts.
    """
    start = datetime.strptime(first_pdy + first_cycle, '%Y%m%d%H')
    pdycycs = {}
    for i in range(-1, 3):
        stamp = (start + timedelta(hours=6 * i)).strftime('%Y%m%d%H')
        pdycycs[stamp[8:]] = stamp
    return pdycycs


def render_cycle(block, hour, pdycyc):
    """Render the lines of one cycle family block.

    Parameters
    ----------
    block : list of str
        Lines from "family NN" to its "endfamily".
    hour : str
        Cycle hour of the family.
    pdycyc : str
        Date and hour (YYYYMMDDCC) set as PDYCYC on the family.

    Returns
    -------
    tuple of (list of str, int, int)
        The rendered lines, the number of ECF_FILES edits found and the number of
        jgdas_fcst tasks found.
    """
    next_hour = f"{(int(hour) + 6) % 24:02d}"
    out = []
    n_ecf_files = 0
    n_fcst = 0
    in_cycle_end = False
    for line in block:
        if CYCLE_END_TASK.match(line):
            in_cycle_end = True
            continue
        if in_cycle_end:
            # The lines of the cycle_end task are indented deeper than the task
            if line.startswith("        "):
                continue
            in_cycle_end = False
        if TIME_TRIGGER.match(line):
            continue
        match = ECF_FILES.match(line)
        if match:
            out.append(f"{match.group(1)}'%EXPDIR%/ecf/scripts'")
            n_ecf_files += 1
            continue
        out.append(line)
        if CYCLE_FAMILY.match(line):
            out.append("      defstatus suspended")
            out.append(f"      edit PDYCYC '{pdycyc}'")
        match = FCST_TASK.match(line)
        if match:
            out.append(f"{match.group(1)}  edit NEXT_CYC '{next_hour}'")
            n_fcst += 1
    return out, n_ecf_files, n_fcst


def render(lines, packagehome, comroot, dataroot, outputdir, expdir, first_pdy, first_cycle):
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

    Returns
    -------
    list of str
        Lines of the rendered definition.

    Raises
    ------
    ValueError
        If the source does not have the expected structure.
    """
    pdycycs = cycle_pdycycs(first_pdy, first_cycle)
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

    # Walk the source and render each line, keeping the cycle families in their place
    out, seen_header = [], set()
    n_ecf_files, n_fcst, n_families, current = 0, 0, 0, None
    for line in lines:
        match = CYCLE_FAMILY.match(line)
        if match:
            current = (match.group(1), [])
            n_families += 1
        if current is not None:
            current[1].append(line)
            if CYCLE_FAMILY_END.match(line):
                hour, block = current
                rendered, count, fcst = render_cycle(block, hour, pdycycs[hour])
                out.extend(rendered)
                n_ecf_files += count
                n_fcst += fcst
                current = None
            continue
        match = re.match(r"^    edit (\w+) ", line)
        if match and match.group(1) in header:
            seen_header.add(match.group(1))
            out.extend(header[match.group(1)])
        else:
            out.append(line)

    if n_families != len(CYCLE_HOURS):
        raise ValueError(f"expected the cycle families {CYCLE_HOURS}, found {n_families} families")
    missing = set(header) - seen_header
    if missing:
        raise ValueError(f"header edits not found in the source: {sorted(missing)}")
    if n_ecf_files != 2 * len(CYCLE_HOURS):
        raise ValueError(f"expected {2 * len(CYCLE_HOURS)} ECF_FILES edits, found {n_ecf_files}")
    if n_fcst != len(CYCLE_HOURS):
        raise ValueError(f"expected {len(CYCLE_HOURS)} jgdas_fcst tasks, found {n_fcst}")
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
    return parser.parse_args()


def main():
    """Render the definition and write it to --out."""
    args = input_args()
    try:
        datetime.strptime(args.first_pdy, '%Y%m%d')
    except ValueError:
        print("ERROR: --first-pdy must be YYYYMMDD", file=sys.stderr)
        return 2
    lines = args.src.read_text().splitlines()
    try:
        out = render(lines, args.packagehome, args.comroot, args.dataroot, args.outputdir, args.expdir,
                     args.first_pdy, args.first_cycle)
    except ValueError as err:
        print(f"ERROR: cannot render {args.src}: {err}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(out) + '\n')
    print(f"Rendered {args.out}; the first cycle is {args.first_pdy}{args.first_cycle}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
