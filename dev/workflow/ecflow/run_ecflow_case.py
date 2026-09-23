#!/usr/bin/env python3

"""Generic ecFlow test case entry point.

Loads any CI case YAML into an ecFlow server.  Delegates all work to
``load_ecflow_case.run()``.  The C48_ATM case YAML is the default
when ``--yaml`` is not specified.

Usage::

    # C48_ATM (default)
    python3 dev/workflow/ecflow/c48_atm_ecflow.py

    # Any other case
    python3 dev/workflow/ecflow/c48_atm_ecflow.py \\
        --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml

    # With overrides
    python3 dev/workflow/ecflow/c48_atm_ecflow.py \\
        --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml \\
        --pslot my_gefs_test
"""

import sys
from pathlib import Path

# Ensure dev/workflow/ is on sys.path so that "from ecflow.load_ecflow_case"
# resolves to our ecflow/ package, not the system ecFlow Python bindings.
_SCRIPT_DIR = Path(__file__).resolve().parent          # dev/workflow/ecflow/
_WORKFLOW_DIR = _SCRIPT_DIR.parent                     # dev/workflow/
if str(_WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW_DIR))

from ecflow.load_ecflow_case import HOMEglobal, run  # noqa: E402

C48_ATM_YAML = HOMEglobal / "dev" / "ci" / "cases" / "pr" / "C48_ATM.yaml"


def main() -> None:
    run(default_yaml=C48_ATM_YAML)


if __name__ == "__main__":
    main()
