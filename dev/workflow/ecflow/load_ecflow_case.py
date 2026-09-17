#!/usr/bin/env python3

"""Create an experiment and load its ecFlow suite from a CI case YAML.

Parses a case YAML (e.g. dev/ci/cases/pr/C48_ATM.yaml), creates the
experiment via setup_expt, generates the ecFlow .def via setup_workflow
(ecflow engine), loads the definition into the ecFlow server, and
optionally begins the suite.

The generated .def contains all edit variables (paths, resources,
partitions) baked in from the experiment's config files, so no
``--alter`` overrides are needed after loading.

Prerequisites
-------------
1. ecFlow server running (ECF_HOST / ECF_PORT set).
2. global-workflow built and linked.
3. Environment sourced with ECF_HOST, ECF_PORT, ECF_HOME, HOMEglobal::

       python3 dev/workflow/ecflow/load_ecflow_case.py \\
           --yaml dev/ci/cases/pr/C48_ATM.yaml
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Resolve repo root from this script's location (dev/workflow/ecflow/)
SCRIPT_DIR = Path(__file__).resolve().parent
HOMEglobal = SCRIPT_DIR.parent.parent.parent

# Add workflow and library paths for imports
sys.path.insert(0, str(HOMEglobal / "dev" / "workflow"))
sys.path.insert(0, str(HOMEglobal / "sorc" / "wxflow" / "src"))
sys.path.insert(0, str(HOMEglobal / "ush" / "python"))

import setup_expt  # noqa: E402
import setup_workflow  # noqa: E402
from hosts import Host  # noqa: E402
from wxflow import AttrDict, parse_j2yaml  # noqa: E402

REQUIRED_ENV = ("ECF_HOST", "ECF_PORT", "HOMEglobal")

DEFAULT_YAML = HOMEglobal / "dev" / "ci" / "cases" / "pr" / "C48_ATM.yaml"


def ecflow_client(*args: str) -> subprocess.CompletedProcess:
    """Run ecflow_client with the given arguments."""
    cmd = ["ecflow_client", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          timeout=30)


def ecflow_client_quiet(*args: str) -> bool:
    """Run ecflow_client, returning True on success and False on failure."""
    cmd = ["ecflow_client", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=30)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an experiment and load its ecFlow suite "
                    "from a CI case YAML."
    )
    parser.add_argument(
        "-y", "--yaml",
        type=Path,
        default=DEFAULT_YAML,
        help=f"CI case YAML (default: {DEFAULT_YAML.relative_to(HOMEglobal)})",
    )
    parser.add_argument(
        "--load-only",
        action="store_true",
        help="Load the suite definition but do not begin it.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite a previously created experiment.",
    )
    parser.add_argument(
        "--suite-name",
        default=None,
        help="ecFlow suite name (default: pslot from the YAML).",
    )
    return parser.parse_args()


def validate_environment() -> None:
    """Exit with an error if required environment variables are missing."""
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("  Set ECF_HOST, ECF_PORT, and HOMEglobal before running.")
        sys.exit(1)


def load_case_yaml(yaml_path: Path) -> AttrDict:
    """Parse the CI case YAML with host and environment template variables.

    Sets default values for ``pslot`` and ``RUNTESTS`` in ``os.environ``
    when not already present, so that Jinja2 ``getenv`` filters resolve
    to usable paths instead of the literal string ``UNDEFINED``.
    """
    if not os.environ.get('pslot'):
        os.environ['pslot'] = yaml_path.stem + '_ecflow'
    if not os.environ.get('RUNTESTS'):
        os.environ['RUNTESTS'] = str(HOMEglobal.parent / 'RUNTESTS')

    host = Host()
    data = AttrDict(HOMEglobal=str(HOMEglobal))
    data.update(host.info)
    data.update(os.environ)
    return parse_j2yaml(path=yaml_path, data=data)


def create_experiment(testconf: AttrDict, runtests: Path,
                      overwrite: bool = False) -> Path:
    """Create the experiment via setup_expt.main() and return the EXPDIR."""
    exp = testconf.experiment
    pslot = exp.pslot
    expdir = runtests / "EXPDIR" / pslot

    runtests.mkdir(parents=True, exist_ok=True)

    if expdir.is_dir():
        print("  EXPDIR already exists, recreating with --overwrite.")

    setup_expt_args = [exp.net, exp.mode]
    skip_keys = {"net", "mode", "yaml"}
    for key, val in exp.items():
        if key in skip_keys:
            continue
        setup_expt_args.extend([f"--{key}", str(val)])

    if overwrite:
        setup_expt_args.append("--overwrite")

    setup_expt.main(setup_expt_args)

    config_base = expdir / "config.base"
    if not config_base.is_file():
        print(f"[ERROR] config.base not found in {expdir}.")
        sys.exit(1)

    return expdir


def generate_ecflow_def(expdir: Path) -> Path:
    """Generate the ecFlow .def file via setup_workflow.main(ecflow).

    Returns the path to the generated .def file.
    """
    # Configuration.parse_config diffs env before/after sourcing config
    # files.  Variables already in os.environ are excluded from the
    # result.  Temporarily remove workflow-specific vars so parse_config
    # captures them from the rendered config.base.
    _saved_env = {}
    for var in ('HOMEglobal', 'EXPDIR', 'COMROOT', 'DATAROOT',
                'ROTDIR', 'PSLOT', 'NET', 'RUN',
                'ACCOUNT', 'PARTITION_BATCH', 'PARTITION_SERVICE',
                'QUEUE', 'QUEUE_SERVICE'):
        if var in os.environ:
            _saved_env[var] = os.environ.pop(var)

    try:
        setup_workflow.main([str(expdir), "ecflow"])
    finally:
        os.environ.update(_saved_env)

    def_files = list(expdir.glob("*.def"))
    if not def_files:
        print(f"[ERROR] No .def file generated in {expdir}.")
        sys.exit(1)

    return def_files[0]


def load_suite(suite_name: str, def_file: Path) -> None:
    """Delete any existing suite and load the .def file."""
    ecflow_client_quiet("--delete", f"/{suite_name}")
    ecflow_client(f"--load={def_file}")


def cleanup_stale_files(pslot: str, comroot: Path, runtests: Path) -> None:
    """Remove all runtime directories from a previous run of this case.

    Lists directories to be removed and prompts for confirmation.
    """
    dirs_to_clean = []

    candidates = [
        ("COMROOT", comroot / pslot),
        ("RUNDIRS", runtests / "RUNDIRS" / pslot),
        ("EXPDIR", runtests / "EXPDIR" / pslot),
        # Old ECF_HOME dirs that may have been created inside the repo
        ("repo/ecf (stale)", HOMEglobal / "dev" / "ecf" / "ursa" / pslot),
        ("repo/ecf (stale)", HOMEglobal / "dev" / "ecf" / "ursa" / "output"),
    ]

    for label, d in candidates:
        if d.is_dir():
            dirs_to_clean.append((label, d))

    if not dirs_to_clean:
        print("  No previous run directories found.")
        return

    print("  The following directories will be removed:")
    for label, d in dirs_to_clean:
        print(f"    [{label}] {d}")

    answer = input("  Proceed? [y/N] ").strip().lower()
    if answer not in ('y', 'yes'):
        print("  Skipping cleanup.")
        return

    for label, d in dirs_to_clean:
        print(f"  Removing {d}")
        shutil.rmtree(d)
    print("  Clean.")


def main() -> None:
    args = parse_args()

    validate_environment()

    yaml_path = args.yaml.resolve()
    if not yaml_path.is_file():
        print(f"[ERROR] Case YAML not found: {yaml_path}")
        sys.exit(1)

    testconf = load_case_yaml(yaml_path)
    exp = testconf.experiment
    pslot = exp.pslot
    comroot = Path(exp.comroot)
    runtests = comroot.parent
    expdir_path = runtests / "EXPDIR" / pslot

    suite_name = args.suite_name or pslot

    ecf_host = os.environ["ECF_HOST"]
    ecf_port = os.environ["ECF_PORT"]

    print("=== Load ecFlow case ===")
    print(f"  Case YAML:   {yaml_path.relative_to(HOMEglobal)}")
    print(f"  Suite:       {suite_name}")
    print(f"  ECF_HOST:    {ecf_host}")
    print(f"  ECF_PORT:    {ecf_port}")
    print(f"  HOMEglobal:  {HOMEglobal}")
    print(f"  PSLOT:       {pslot}")
    print(f"  RUNTESTS:    {runtests}")
    print(f"  EXPDIR:      {expdir_path}")
    print(f"  COMROOT:     {comroot}")
    print()

    # Step 0: Clean up stale ecFlow runtime files
    print("[0/4] Cleaning up previous ecFlow runtime files...")
    cleanup_stale_files(pslot, comroot, runtests)

    # Step 1: Create the experiment
    print("[1/4] Creating experiment via setup_expt...")
    expdir = create_experiment(testconf, runtests, overwrite=args.overwrite)
    print(f"  Experiment created in {expdir}.")

    # Step 2: Generate the ecFlow .def
    print("[2/4] Generating ecFlow .def via setup_workflow (ecflow engine)...")
    def_file = generate_ecflow_def(expdir)
    print(f"  Suite definition generated: {def_file.name}")

    # Restore ecFlow server vars — config parsing inside setup_workflow
    # may alter the module environment, unsetting ECF_HOST/ECF_PORT.
    os.environ['ECF_HOST'] = ecf_host
    os.environ['ECF_PORT'] = ecf_port

    # Step 3: Load into ecFlow server
    print("[3/4] Loading suite into ecFlow server...")
    if not ecflow_client_quiet("--ping"):
        print(f"[ERROR] Cannot reach ecFlow server at {ecf_host}:{ecf_port}")
        sys.exit(1)
    print("  Server is alive.")
    load_suite(suite_name, def_file)
    print(f"  Suite {suite_name} loaded.")

    # Step 4: Begin the suite (or stop at load-only)
    if args.load_only:
        print("[4/4] --load-only specified, suite NOT started.")
        print(f"  Inspect in ecflow_ui, then run:")
        print(f"    ecflow_client --begin={suite_name}")
    else:
        print("[4/4] Beginning suite...")
        ecflow_client(f"--begin={suite_name}")
        print(f"  [OK] Suite {suite_name} started.")

    print()
    print("=== Done ===")
    print(f"Monitor with: ecflow_client --get_state /{suite_name}")
    print("         or:  ecflow_ui  (if X11 available)")


if __name__ == "__main__":
    main()
