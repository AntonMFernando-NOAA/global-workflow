# Running the C48 GEFS Test Case with ecFlow

This guide covers the forecast-only GEFS test case
(`dev/ci/cases/pr/C48_S2SWA_gefs.yaml`, 2 perturbed members plus the
control) using ecFlow. Server setup, Ursa login and environment
variables are identical to the C48_ATM case and are described in
[README.md](README.md) (sections "Connecting to Ursa" through "ecFlow
Server"). This document only covers what is different for GEFS.

For a step-by-step walk through of what each command does, see
[PROCESS_FLOW_GEFS.md](PROCESS_FLOW_GEFS.md).

## Differences from the C48_ATM case

| Item | C48_ATM (GFS) | C48_S2SWA_gefs (GEFS) |
|------|---------------|-----------------------|
| Case YAML | `C48_ATM.yaml` (default) | `C48_S2SWA_gefs.yaml` (`--yaml` required) |
| Suite generator | `gfs_forecast_only_ecflow.py` | `forecast_only_ecflow.py` |
| Task definitions | `gfs_ecflow_tasks.py` | `gefs_ecflow_tasks.py` |
| Suite hierarchy | `suite/cycle/run/category/task` | `suite/run/cycle/task-or-member-family` |
| Ensemble members | none | `NMEM_ENS` > 0 gives `mem000` .. `memNNN` families |
| Script tree in `EXPDIR/ecf_scripts/` | `scripts/{category}/...` | flat `{name}.ecf` plus `{family}/{label}.ecf` |
| Script categories | `TASK_CATEGORY` map | not used (source found by name) |

## Run the case

```bash
# Environment: see README.md (ECF_HOST, ECF_PORT, ECF_HOME, HOMEglobal,
# MACHINE_ID, HPC_ACCOUNT) and load the setup modules
source ${HOMEglobal}/dev/ush/load_modules.sh setup

python3 dev/workflow/ecflow/run_ecflow_case.py \
    --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml \
    --pslot my_gefs_test

# Start the suite
ecflow_client --begin=my_gefs_test
```

Useful options (all from `load_ecflow_case.py`):

| Option | Purpose |
|--------|---------|
| `--overwrite` | Recreate a previously created experiment |
| `--pslot NAME` | Experiment and suite name (default `<yaml_stem>_ecflow`) |
| `--expdir`, `--comroot`, `--stmp` | Override output locations |
| `--suite-name NAME` | ecFlow suite name (default is the pslot) |

> **Note:** `ECF_INCLUDE` for the GEFS suite defaults to
> `${HOMEglobal}/dev/ecflow/utils`, which does not exist in this
> repository. The header files live in `dev/ecflow/include`. Until the
> default is fixed, export it before running the loader:
>
> ```bash
> export ECF_INCLUDE=${HOMEglobal}/dev/ecflow/include
> ```

## Generated suite hierarchy

With `NMEM_ENS=2` the `.def` looks like this (tasks shown depend on the
app options, here S2SWA):

```
suite my_gefs_test
  family gefs
    family 2021032312
      task stage_ic
      task waveinit / prep_emissions        (when enabled)
      task fcst                             control forecast (mem000)
      family fcst_member                    perturbed members
        family mem001   (task seg0, seg1, ...)
        family mem002
      family atmos_prod                     one family per product
        family mem000   (task f000_f024, ...)
        family mem001
        family mem002
      family ocean_prod / ice_prod / wavepostgridded ...
      task atmos_ensstat                    triggered by all members
      task wave_stat, wave_stat_pnt
      task arch_vrfy, arch_tars, cleanup
```

How tasks are placed (`ForecastOnlyEcFlowSuite._classify_tasks`):

- Tasks before the first `ensemble_task` are **pre-ensemble** and are
  emitted directly under the cycle family.
- `fcst_member` becomes one `family fcst_member` with a family per
  perturbed member and one task per forecast segment (`seg0`, `seg1`).
- Other `ensemble_task` entries become a family per task with a
  `memNNN` sub-family per member (including the control, `mem000`).
  Product tasks emit grouped forecast-hour children (`f000_f024`)
  directly inside each member family.
- Tasks after the ensemble block are **post-ensemble**. Sentinel
  triggers such as `__ALL_MEMBER_ATMOS_PROD__` are rewritten to wait on
  every member's product family.

See `_emit_task` in
[forecast_only_ecflow.py](forecast_only_ecflow.py) for the three task
shapes (simple task, segmented family, product family).

## How scripts are located (nested source tree)

The repository scripts are nested by category:

```
dev/ecflow/scripts/
  init/            stage_ic.ecf    wave/waveinit.ecf
  forecast/        fcst.ecf
  prep/            prep_emissions.ecf
  product/
    atmos/         atmos_prod, atmos_ensstat, extractvars, gempak,
                   postsnd, awips, gen_control_ic
    ocean/         ocean_prod
    ice/           ice_prod
    wave/          wavepostgridded, wave_stat, wave_stat_pnt
  track/           tracker, genesis
  verf/atmos/      metp
  post/            arch_vrfy, arch_tars, globus_arch, cleanup
```

Because the depth varies, generators never hard-code a path.
`EcFlowSuite.index_ecf_sources()` in
[ecflow_suite.py](ecflow_suite.py) scans the tree once and maps each
script name to its relative path:

```python
ecf_index = self.index_ecf_sources(src_dir)
# ecf_index["atmos_prod"] == "product/atmos/atmos_prod"
```

Script names must therefore be unique across the whole tree; a
duplicate raises `ValueError` when the suite is generated.

The experiment copy under `${EXPDIR}/ecf_scripts/` is built from that
index:

```
${EXPDIR}/ecf_scripts/
  stage_ic.ecf  fcst.ecf  atmos_ensstat.ecf  cleanup.ecf ...   task scripts
  fcst/seg0.ecf  fcst/seg1.ecf                                  segments
  atmos_prod/f000_f024.ecf ...                                  fhr groups
  ecf_scripts.manifest
```

Each product family edits `ECF_FILES` to its own subdirectory, so
`mem001/f000_f024` resolves to `atmos_prod/f000_f024.ecf` for every
member.

## Adding or moving a script

1. Put the `.ecf` anywhere under the matching `dev/ecflow/scripts/`
   category (create a sub-directory such as `product/atmos/` if needed).
2. Keep the file name equal to the task name used in
   `gefs_ecflow_tasks.py` (or `gfs_ecflow_tasks.py`).
3. For the GFS generator, also set the task category in
   `GFSForecastOnlyEcFlowSuite.TASK_CATEGORY` to the directory path
   (for example `'postsnd': 'product/atmos'`). GEFS needs no mapping.
4. Re-run the loader with `--overwrite`.

## Monitoring and troubleshooting

```bash
# State of one member forecast
ecflow_client --get_state /my_gefs_test/gefs/2021032312/fcst_member/mem001

# Requeue a failed task
ecflow_client --requeue=aborted /my_gefs_test

# Job output
ls ${ECF_HOME}   # {COMROOT}/{pslot}/logs/
```

| Symptom | Likely cause |
|---------|--------------|
| `Duplicate .ecf source name` | Two scripts with the same file name in `dev/ecflow/scripts/` |
| `head.h` not found in the job | `ECF_INCLUDE` points to a missing directory, see the note above |
| Member product task never starts | Check the rewritten `memNNN` trigger in the `.def` |
| `atmos_ensstat` never starts | One member product family is incomplete |
| Python import errors | Run `source dev/ush/load_modules.sh setup` first |

See the troubleshooting section of [README.md](README.md) for server
and Slurm problems, which are not GEFS specific.
