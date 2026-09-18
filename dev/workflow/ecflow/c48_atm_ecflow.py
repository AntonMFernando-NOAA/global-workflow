#!/usr/bin/env python3

"""C48_ATM ecFlow test case loader.

Thin entry point that loads the C48_ATM forecast-only test case into
an ecFlow server.  Delegates all work to ``load_ecflow_case.run()``
with the C48_ATM case YAML as the default.

Usage::

    python3 dev/workflow/ecflow/c48_atm_ecflow.py
    python3 dev/workflow/ecflow/c48_atm_ecflow.py --load-only
    python3 dev/workflow/ecflow/c48_atm_ecflow.py --yaml /other/case.yaml
"""

from pathlib import Path

from ecflow.load_ecflow_case import HOMEglobal, run

C48_ATM_YAML = HOMEglobal / "dev" / "ci" / "cases" / "pr" / "C48_ATM.yaml"


def main() -> None:
    run(default_yaml=C48_ATM_YAML)


if __name__ == "__main__":
    main()
