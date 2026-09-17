#!/usr/bin/env python3

"""Bootstrap an ecFlow suite on Ursa from a CI case YAML.

Parses a case YAML (e.g. dev/ci/cases/pr/C48_ATM.yaml), creates the
experiment via setup_expt, generates the ecFlow .def via setup_workflow
(ecflow engine), loads the definition into the ecFlow server, and
optionally begins the suite.

The generated .def contains all edit variables (paths, resources,
partitions) baked in from the experiment's config files, so no
``--alter`` overrides are needed after loading.

Prerequisites
-------------
1. ecFlow server running on uecflow01 (see ~/ecflow_ursa.env).
2. global-workflow built and linked (build_all.sh + link_workflow.sh).
3. Environment sourced::

       source ~/ecflow_ursa.env
       python3 dev/ecf/c96/bootstrap_ursa.py --yaml dev/ci/cases/pr/C48_ATM.yaml
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Resolve repo root from this script's location (dev/ecf/c96/bootstrap_ursa.py)
SCRIPT_DIR = Path(__file__).resolve().parent
HOMEglobal = SCRIPT_DIR.parent.parent.parent

# Add workflow and library paths so setup_expt, setup_workflow, and
# wxflow can be imported.
sys.path.insert(0, str(HOMEglobal / "dev" / "workflow"))
sys.path.insert(0, str(HOMEglobal / "sorc" / "wxflow" / "src"))
sys.path.insert(0, str(HOMEglobal / "ush" / "python"))

import setup_expt  # noqa: E402
import setup_workflow  # noqa: E402
from hosts import Host  # noqa: E402
from wxflow import AttrDict, parse_j2yaml  # noqa: E402

# Required environment variables (set by ~/ecflow_ursa.env)
REQUIRED_ENV = ("ECF_HOST", "ECF_PORT", "ECF_HOME", "HOMEglobal")

DEFAULT_YAML = HOMEglobal / "dev" / "ci" / "cases" / "pr" / "C48_ATM.yaml"


def ecflow_client(*args: str) -> subprocess.CompletedProcess:
    """Run ecflow_client with the given arguments."""
    cmd = ["ecflow_client", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def ecflow_client_quiet(*args: str) -> bool:
    """Run ecflow_client, returning True on success and False on failure."""
    cmd = ["ecflow_client", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap an ecFlow suite on Ursa from a CI case YAML."
    )
    parser.add_argument(
        "-y", "--yaml",
        type=Path,
        default=DEFAULT_YAML,
        help=f"Path to the CI case YAML (default: {DEFAULT_YAML.relative_to(HOMEglobal)})",
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
        help="ecFlow suite name (default: derived from pslot in the YAML).",
    )
    return parser.parse_args()


def validate_environment() -> None:
    """Exit with an error if required environment variables are missing."""
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("  Source ~/ecflow_ursa.env first.")
        sys.exit(1)


def load_case_yaml(yaml_path: Path) -> AttrDict:
    """Parse the CI case YAML with host and environment template variables."""
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

    # Build args the same way create_experiment.py does
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
        print("  setup_expt.py may have failed.")
        sys.exit(1)

    return expdir


def generate_ecflow_def(expdir: Path) -> Path:
    """Generate the ecFlow .def file via setup_workflow.main(ecflow).

    setup_workflow sources the experiment's config files, builds an
    AppConfig, and calls GFSForecastOnlyEcFlowSuite.write() which
    writes ``{EXPDIR}/{pslot}.def`` with all variables baked in.

    Returns the path to the generated .def file.
    """
    setup_workflow.main([str(expdir), "ecflow"])

    # Find the generated .def (named after the pslot)
    def_files = list(expdir.glob("*.def"))
    if not def_files:
        print(f"[ERROR] No .def file generated in {expdir}.")
        print("  setup_workflow.py ecflow may have failed.")
        sys.exit(1)

    return def_files[0]


def load_suite(suite_name: str, def_file: Path) -> None:
    """Delete any existing suite and load the .def file."""
    ecflow_client_quiet("--delete", f"/{suite_name}")
    ecflow_client(f"--load={def_file}")


def main() -> None:
    args = parse_args()

    validate_environment()

    # Parse the CI case YAML
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
    ecf_home = os.environ["ECF_HOME"]

    print("=== ecFlow suite bootstrap (Ursa) ===")
    print(f"  Case YAML:   {yaml_path.relative_to(HOMEglobal)}")
    print(f"  Suite:       {suite_name}")
    print(f"  ECF_HOST:    {ecf_host}")
    print(f"  ECF_PORT:    {ecf_port}")
    print(f"  ECF_HOME:    {ecf_home}")
    print(f"  HOMEglobal:  {HOMEglobal}")
    print(f"  PSLOT:       {pslot}")
    print(f"  RUNTESTS:    {runtests}")
    print(f"  EXPDIR:      {expdir_path}")
    print(f"  COMROOT:     {comroot}")
    print()

    # Step 1: Create the experiment (renders config files into EXPDIR)
    print("[1/4] Creating experiment via setup_expt...")
    expdir = create_experiment(testconf, runtests, overwrite=args.overwrite)
    print(f"  Experiment created in {expdir}.")

    # Step 2: Generate the ecFlow .def via setup_workflow (ecflow engine)
    print("[2/4] Generating ecFlow .def via setup_workflow (ecflow engine)...")
    def_file = generate_ecflow_def(expdir)
    print(f"  Suite definition generated: {def_file.name}")

    # Step 3: Verify ecFlow server is reachable, then load the .def
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
