# Changelog

## 2026-10-16

- Fix the ecFlow `arch_tars` tarball list in
  `dev/workflow/ecflow/ecflow_tasks.py` to match Rocoto: drop the
  nonexistent `gfsb` and `gfs_flux_1p00` types that caused
  `TemplateNotFound: gfsb.yaml.j2` in `JGLOBAL_ARCHIVE_TARS`.

## 2026-10-14

- Add `ensure_ecflow_server()` to `dev/workflow/ecflow/load_ecflow_case.py`,
  called from `run()` (and therefore `run_ecflow_case.py`). It defaults
  ECF_HOST, ECF_PORT, and ECF_HOME on Gaea C6 and Ursa, starts the server
  on a Gaea C6 login node when none is running, and prints the manual
  start steps on Ursa.
- Document the automatic server start in `dev/workflow/ecflow/README.md`.

- Extend the C48_ATM ecFlow test to Gaea C6:
  - `.ecf` scripts use `%MACHINE%` instead of a hardcoded `URSA`.
  - `head.h`/`tail.h` fall back to the ecFlow client location recorded at
    suite generation when `module load ecflow` is not available.
  - Suite generator adds `--qos`, multi-cluster `scancel`/`squeue`, and a
    per-machine default account.
  - Enable `C48_ATM_ecflow` for `gaeac6` in the case YAML and CI matrix.
