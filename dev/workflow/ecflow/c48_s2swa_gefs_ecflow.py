#!/usr/bin/env python3

"""C48_S2SWA_gefs ecFlow test case loader.

Thin entry point that loads the C48_S2SWA GEFS forecast-only test case
into an ecFlow server.  Delegates all work to ``load_ecflow_case.run()``
with the C48_S2SWA_gefs case YAML as the default.

Usage::

    python3 dev/workflow/ecflow/c48_s2swa_gefs_ecflow.py
    python3 dev/workflow/ecflow/c48_s2swa_gefs_ecflow.py --expdir /path/to/expdir
    python3 dev/workflow/ecflow/c48_s2swa_gefs_ecflow.py --yaml /other/case.yaml
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

C48_S2SWA_GEFS_YAML = HOMEglobal / "dev" / "ci" / "cases" / "pr" / "C48_S2SWA_gefs.yaml"


def main() -> None:
    run(default_yaml=C48_S2SWA_GEFS_YAML)


if __name__ == "__main__":
    main()
