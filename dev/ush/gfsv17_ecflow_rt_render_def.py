#!/usr/bin/env python3
"""Render the GFSv17 ecflow realtime suite definition from gfs_prod.def.

The rendered definition differs from gfs_prod.def as follows:

* PACKAGEHOME, ENVIR, QUEUE, OUTPUTDIR and EXPDIR are set for the user, and
  ECF_INCLUDE, DATAROOT and COMROOT are added.
* ECF_INCLUDE and every ECF_FILES point to <EXPDIR>/ecf.
* The four cycle families 00, 06, 12 and 18 of gfs_prod.def are replaced by one
  family per cycle of the run, named by its PDYCYC (YYYYMMDDCC). With --first-pdy
  20261106 --first-cycle 12 --ncycles 5 the families are 2026110612, 2026110618,
  2026110700, 2026110706 and 2026110712, each a copy of the gfs_prod.def family of
  its cycle hour without the cycle_end task. Every family is suspended and has
  PDYCYC edited to its name.
* The triggers on the previous cycle (../../18/gdas/...) point to the family of the
  previous cycle. The first family has no previous cycle in the suite, so these
  terms are removed from its triggers.
* The jgdas_fcst task of each family but the last has NEXT_FAMILY edited to the
  name of the next family. When it ends, tail.h resumes that family, which is what
  cycle_end does in production. Only the first family is resumed by hand.
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
CROSS_CYCLE = re.compile(r"((?:\.\./)+)(00|06|12|18)/")
TRIGGER = re.compile(r"^(\s*trigger\s+)(.*?)\s*$")
SUITE_LINE = re.compile(r"^suite\s+\S+\s*$")
SUITE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def cycle_pdycycs(first_pdy, first_cycle, ncycles):
    """Return the PDYCYC of each cycle of the run.

    Parameters
    ----------
    first_pdy : str
        Date of the first cycle (YYYYMMDD).
    first_cycle : str
        Hour of the first cycle: 00, 06, 12 or 18.
    ncycles : int
        Number of cycles in the run.

    Returns
    -------
    list of str
        PDYCYC (YYYYMMDDCC) of each cycle, 6 hours apart, starting at the first one.
    """
    start = datetime.strptime(first_pdy + first_cycle, '%Y%m%d%H')
    return [(start + timedelta(hours=6 * i)).strftime('%Y%m%d%H') for i in range(ncycles)]


def render_trigger(line, prev_pdycyc):
    """Point the previous cycle terms of a trigger line to the previous cycle family.

    Parameters
    ----------
    line : str
        A trigger line with references to the previous cycle family.
    prev_pdycyc : str or None
        Name of the previous cycle family, or None for the first family, in which
        case the terms on the previous cycle are removed.

    Returns
    -------
    str or None
        The rendered line, or None when no term is left.

    Raises
    ------
    ValueError
        If a reference is not to the previous cycle hour.
    """
    if prev_pdycyc is not None:
        def repl(match):
            if match.group(2) != prev_pdycyc[8:]:
                raise ValueError(f"trigger on cycle {match.group(2)}, not on the previous cycle: {line.strip()}")
            return f"{match.group(1)}{prev_pdycyc}/"
        return CROSS_CYCLE.sub(repl, line)
    prefix, expr = TRIGGER.match(line).groups()
    terms = [term for term in re.split(r"\s+and\s+", expr) if not CROSS_CYCLE.search(term)]
    if not terms:
        return None
    return prefix + ' and '.join(terms)


def render_cycle(block, pdycyc, prev_pdycyc, next_pdycyc):
    """Render the lines of one cycle family.

    Parameters
    ----------
    block : list of str
        Lines from "family NN" to its "endfamily" in the source.
    pdycyc : str
        Date and hour (YYYYMMDDCC) of the cycle; also the family name.
    prev_pdycyc : str or None
        Name of the previous cycle family, None for the first family.
    next_pdycyc : str or None
        Name of the next cycle family, None for the last family.

    Returns
    -------
    tuple of (list of str, int, int)
        The rendered lines, the number of ECF_FILES edits found and the number of
        jgdas_fcst tasks found.

    Raises
    ------
    ValueError
        If a line other than a trigger refers to another cycle family.
    """
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
        if CYCLE_FAMILY.match(line):
            out.extend([f"    family {pdycyc}",
                        "      defstatus suspended",
                        f"      edit PDYCYC '{pdycyc}'"])
            continue
        if CYCLE_FAMILY_END.match(line):
            out.append(f"    endfamily  //{pdycyc}")
            continue
        if not line.lstrip().startswith('#') and CROSS_CYCLE.search(line):
            if not TRIGGER.match(line):
                raise ValueError(f"reference to another cycle outside a trigger: {line.strip()}")
            line = render_trigger(line, prev_pdycyc)
            if line is None:
                continue
        match = ECF_FILES.match(line)
        if match:
            out.append(f"{match.group(1)}'%EXPDIR%/ecf/scripts'")
            n_ecf_files += 1
            continue
        out.append(line)
        match = FCST_TASK.match(line)
        if match:
            if next_pdycyc is not None:
                out.append(f"{match.group(1)}  edit NEXT_FAMILY '{next_pdycyc}'")
            n_fcst += 1
    return out, n_ecf_files, n_fcst


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
        Number of cycles to run; one family is rendered for each.

    Returns
    -------
    list of str
        Lines of the rendered definition.

    Raises
    ------
    ValueError
        If the source does not have the expected structure.
    """
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

    # Split the source into the lines before the cycle families, the families and the lines after them
    before, after, blocks, seen_header = [], [], {}, set()
    current = None
    for line in lines:
        match = CYCLE_FAMILY.match(line)
        if match:
            current = match.group(1)
            blocks[current] = []
            # Lines between the cycle families of the source are not kept
            after = []
        if current is not None:
            blocks[current].append(line)
            if CYCLE_FAMILY_END.match(line):
                current = None
            continue
        if blocks:
            after.append(line)
            continue
        match = re.match(r"^    edit (\w+) ", line)
        if match and match.group(1) in header:
            seen_header.add(match.group(1))
            before.extend(header[match.group(1)])
        else:
            before.append(line)

    if sorted(blocks) != list(CYCLE_HOURS):
        raise ValueError(f"expected the cycle families {CYCLE_HOURS}, found {sorted(blocks)}")
    missing = set(header) - seen_header
    if missing:
        raise ValueError(f"header edits not found in the source: {sorted(missing)}")

    pdycycs = cycle_pdycycs(first_pdy, first_cycle, ncycles)
    out = list(before)
    n_ecf_files, n_fcst = 0, 0
    for i, pdycyc in enumerate(pdycycs):
        prev_pdycyc = pdycycs[i - 1] if i > 0 else None
        next_pdycyc = pdycycs[i + 1] if i + 1 < len(pdycycs) else None
        rendered, count, fcst = render_cycle(blocks[pdycyc[8:]], pdycyc, prev_pdycyc, next_pdycyc)
        out.extend(rendered)
        n_ecf_files += count
        n_fcst += fcst
    out.extend(after)

    if n_ecf_files != 2 * ncycles:
        raise ValueError(f"expected {2 * ncycles} ECF_FILES edits, found {n_ecf_files}")
    if n_fcst != ncycles:
        raise ValueError(f"expected {ncycles} jgdas_fcst tasks, found {n_fcst}")
    if any(re.match(r"^[^#]*:TIME\b", line) for line in out):
        raise ValueError("a :TIME expression is left that is not a plain trigger line")
    return out


def rename_suite(lines, name):
    """Return the lines with the suite named ``name``.

    Parameters
    ----------
    lines : list of str
        Lines of the definition, without line endings.
    name : str
        New name of the suite.

    Returns
    -------
    list of str
        The lines with the ``suite`` line replaced.
    """
    renamed = []
    count = 0
    for line in lines:
        if SUITE_LINE.match(line):
            line = f"suite {name}"
            count += 1
        renamed.append(line)
    if count != 1:
        raise ValueError(f"expected one suite line, found {count}")
    return renamed


def input_args():
    """Collect the command line arguments."""
    parser = ArgumentParser(description=__doc__.split('\n')[0],
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--src', type=Path, default=DEFAULT_SRC, help='definition to start from')
    parser.add_argument('--out', type=Path, required=True, help='rendered definition to write')
    parser.add_argument('--suite', default='gfs_v17_nco', help='name of the suite')
    parser.add_argument('--packagehome', required=True, help='global-workflow clone')
    parser.add_argument('--comroot', required=True, help='COMROOT')
    parser.add_argument('--dataroot', required=True, help='DATAROOT')
    parser.add_argument('--outputdir', required=True, help='OUTPUTDIR')
    parser.add_argument('--expdir', required=True, help='EXPDIR')
    parser.add_argument('--first-pdy', required=True, help='date (YYYYMMDD) of the first cycle')
    parser.add_argument('--first-cycle', choices=CYCLE_HOURS, required=True, help='hour of the first cycle')
    parser.add_argument('--ncycles', type=int, default=1, help='number of cycles (families) to render')
    return parser.parse_args()


def main():
    """Render the definition and write it to --out."""
    args = input_args()
    try:
        datetime.strptime(args.first_pdy, '%Y%m%d')
    except ValueError:
        print("ERROR: --first-pdy must be YYYYMMDD", file=sys.stderr)
        return 2
    if not SUITE_NAME.match(args.suite):
        print("ERROR: --suite must be letters, digits, underscores and dots, not starting with a digit", file=sys.stderr)
        return 2
    if args.ncycles < 1:
        print("ERROR: --ncycles must be a positive integer", file=sys.stderr)
        return 2
    lines = args.src.read_text().splitlines()
    try:
        out = render(lines, args.packagehome, args.comroot, args.dataroot, args.outputdir, args.expdir,
                     args.first_pdy, args.first_cycle, args.ncycles)
        out = rename_suite(out, args.suite)
    except ValueError as err:
        print(f"ERROR: cannot render {args.src}: {err}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(out) + '\n')
    pdycycs = cycle_pdycycs(args.first_pdy, args.first_cycle, args.ncycles)
    print(f"Rendered {args.out} (suite {args.suite}) with the cycle families {' '.join(pdycycs)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
