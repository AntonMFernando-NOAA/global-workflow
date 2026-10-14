# Changelog

## 2026-10-14

- Add `ensure_ecflow_server()` to `dev/workflow/ecflow/load_ecflow_case.py`,
  called from `run()` (and therefore `run_ecflow_case.py`). It defaults
  ECF_HOST, ECF_PORT, and ECF_HOME on Gaea C6 and Ursa, starts the server
  on a Gaea C6 login node when none is running, and prints the manual
  start steps on Ursa.
- Document the automatic server start in `dev/workflow/ecflow/README.md`.
