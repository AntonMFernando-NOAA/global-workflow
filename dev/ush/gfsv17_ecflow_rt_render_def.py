#!/usr/bin/env python3
"""Render the GFSv17 ecflow realtime suite definition from gfs_prod.def.

The rendered definition differs from gfs_prod.def as follows:

* PACKAGEHOME, ENVIR, QUEUE, OUTPUTDIR and EXPDIR are set for the user, and
  ECF_INCLUDE, DATAROOT and COMROOT are added.
* ECF_INCLUDE and every ECF_FILES point to <EXPDIR>/ecf.
* The suite keeps the four cycle families 00, 06, 12 and 18, and the cycle_end
  task of each one. cycle_end resets its family for the next day and moves its PDY
  forward, so the suite cycles by itself as in production.
* Every cycle family has an edited PDY. The cycle families of the run get the PDY
  of their first run: with --first-pdy 20260105 --first-cycle 12 the families 12
  and 18 get 20260105 and 00 gets 20260106. The family of the cycle before the
  first one (06) gets 20260105; it is to be forced complete when the suite starts.
* A task that waited only on the clock (``trigger :TIME ...``) waits for the
  cycle_end task of its own family to be complete instead, so a cycle prepares
  its input after cycle_end has reset it and not at once when the suite begins.
* The first cycle family starts suspended, so that the start steps can be done
  before it runs.
"""

import re
import sys
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime, timedelta
from pathlib import Path

CYCLE_HOURS = ('00', '06', '12', '18')
DEFAULT_SRC = Path(__file__).resolve().parent.parent / 'ecf' / 'gfs' / 'defs' / 'gfs_prod.def'

SUITE = re.compile(r"^suite\s+(\S+)\s*$")
CYCLE_FAMILY = re.compile(r"^    family (00|06|12|18)\s*$")
CYCLE_FAMILY_END = re.compile(r"^    endfamily\b")
TIME_TRIGGER = re.compile(r"^(\s*)trigger\s+:TIME\b")
ECF_FILES = re.compile(r"^(\s*edit ECF_FILES )'[^']*'\s*$")


def cycle_pdys(first_pdy, first_cycle):
    """Return the PDY that each cycle family has when the suite is loaded.

    Parameters
    ----------
    first_pdy : str
        Date of the first cycle (YYYYMMDD).
    first_cycle : str
        Hour of the first cycle: 00, 06, 12 or 18.

    Returns
    -------
    dict of str to str
        PDY of each cycle hour. The three cycles after the first one, and the first
        one, have the PDY of their first run; the cycle before the first one has the
        PDY it had before the run starts.
    """
    start = datetime.strptime(first_pdy + first_cycle, '%Y%m%d%H')
    pdys = {}
    for i in range(-1, 3):
        stamp = (start + timedelta(hours=6 * i)).strftime('%Y%m%d%H')
        pdys[stamp[8:]] = stamp[:8]
    return pdys


def render_cycle(block, hour, pdy, suite, suspended):
    """Render the lines of one cycle family block.

    Parameters
    ----------
    block : list of str
        Lines from "family NN" to its "endfamily".
    hour : str
        Cycle hour of the family.
    pdy : str
        Date set as PDY on the family.
    suite : str
        Name of the suite, used in the path of the cycle_end task.
    suspended : bool
        Whether the family starts suspended.

    Returns
    -------
    tuple of (list of str, int)
        The rendered lines and the number of ECF_FILES edits found.
    """
    out = []
    n_ecf_files = 0
    for line in block:
        match = TIME_TRIGGER.match(line)
        if match:
            out.append(f"{match.group(1)}trigger /{suite}/primary/{hour}/cycle_end == complete")
            continue
        match = ECF_FILES.match(line)
        if match:
            out.append(f"{match.group(1)}'%EXPDIR%/ecf/scripts'")
            n_ecf_files += 1
            continue
        out.append(line)
        if CYCLE_FAMILY.match(line):
            if suspended:
                out.append("      defstatus suspended")
            out.append(f"      edit PDY '{pdy}'")
    return out, n_ecf_files


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
    pdys = cycle_pdys(first_pdy, first_cycle)
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
    out, seen_header, suite = [], set(), None
    n_ecf_files, n_families, current = 0, 0, None
    for line in lines:
        match = SUITE.match(line)
        if match:
            suite = match.group(1)
        match = CYCLE_FAMILY.match(line)
        if match:
            current = (match.group(1), [])
            n_families += 1
        if current is not None:
            current[1].append(line)
            if CYCLE_FAMILY_END.match(line):
                hour, block = current
                rendered, count = render_cycle(block, hour, pdys[hour], suite, hour == first_cycle)
                out.extend(rendered)
                n_ecf_files += count
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
    if suite is None:
        raise ValueError("suite name not found in the source")
    if n_ecf_files != 2 * len(CYCLE_HOURS):
        raise ValueError(f"expected {2 * len(CYCLE_HOURS)} ECF_FILES edits, found {n_ecf_files}")
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
