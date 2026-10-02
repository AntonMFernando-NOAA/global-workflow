# ecFlow C48 GEFS Test - Process Flow

Companion to [README_GEFS.md](README_GEFS.md). Server startup (Step 0)
is the same as in [PROCESS_FLOW.md](PROCESS_FLOW.md) and is not
repeated here.

## Step 1: Load the case

```
$ python3 dev/workflow/ecflow/run_ecflow_case.py \
      --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml --pslot my_gefs_test

run_ecflow_case.py                         entry point
  |  (dev/workflow/ecflow/run_ecflow_case.py)
  |
  +-- load_ecflow_case.run()               (dev/workflow/ecflow/load_ecflow_case.py)
        |
        +-- validate_environment()         ECF_HOST, ECF_PORT, ECF_HOME, HOMEglobal
        |
        +-- load_case_yaml()               parse C48_S2SWA_gefs.yaml
        |     net=gefs  mode=forecast-only  app=S2SWA  nens=2
        |
        +-- [0/4] cleanup_stale_files()    old logs / COMROOT / RUNDIRS for the pslot
        |
        +-- [1/4] create_experiment()      setup_expt.main(gefs forecast-only ...)
        |     +-- writes EXPDIR/config.*   (config.base has NMEM_ENS=2)
        |
        +-- [2/4] generate_ecflow_def()    setup_workflow.main([EXPDIR, "ecflow"])
        |     (see Step 2)
        |
        +-- [3/4] load_suite()             ecflow_client --load=EXPDIR/my_gefs_test.def
```

## Step 2: Generate the .def

```
setup_workflow.main([EXPDIR, "ecflow"])
  |
  +-- app_config_factory.create("gefs_forecast-only", cfg)     -> GEFSAppConfig
  |     +-- task_names = [stage_ic, ..., fcst, fcst_member, atmos_prod, ..., cleanup]
  |     +-- run_options, configs (one config.* per task)
  |
  +-- ecflow_suite_factory.create("gefs_forecast-only", ...)   -> ForecastOnlyEcFlowSuite
  |     +-- ecflow_tasks_factory.create("gefs", ...)           -> GEFSEcFlowTasks
  |
  +-- ForecastOnlyEcFlowSuite.write()
        |
        +-- get_ecflow_task(name) for every task  -> task dicts
        |     (trigger, resources, product_task, ensemble_task, num_segments)
        |
        +-- _classify_tasks()
        |     pre-ensemble   : before the first ensemble_task
        |     ensemble       : fcst_member + per-member product/simple tasks
        |     post-ensemble  : after the ensemble block
        |
        +-- emit suite / run / cycle families and edit variables
        |
        +-- pre-ensemble   -> _emit_task()  (simple | segmented | product)
        +-- ensemble       -> _emit_fcst_ens_family()   family fcst_member/memNNN/segN
        |                  -> _emit_per_member_task()   family <task>/memNNN/...
        +-- post-ensemble  -> _emit_task() with sentinel triggers resolved
        |
        +-- write EXPDIR/my_gefs_test.def
        +-- _create_ecf_scripts()                       (see Step 3)
```

## Step 3: Build EXPDIR/ecf_scripts

```
_create_ecf_scripts()
  |
  +-- ecf_index = index_ecf_sources(dev/ecflow/scripts)
  |     rglob("*.ecf") -> {name: "product/atmos/atmos_prod", ...}
  |     duplicate name -> ValueError
  |
  +-- copy every indexed script flat:      ecf_scripts/<name>.ecf
  |
  +-- for each (label, source_name) in _copy_map:
  |     label == source_name  -> already copied flat
  |     label != source_name  -> ecf_scripts/<source_name>/<label>.ecf
  |                              e.g. fcst/seg0.ecf, atmos_prod/f000_f024.ecf
  |
  +-- write ecf_scripts.manifest
```

## Step 4: Suite structure on the server

```
my_gefs_test
  gefs
    2021032312
      stage_ic
      fcst                       control member
      fcst_member                trigger: stage_ic complete
        mem001: seg0 -> seg1
        mem002: seg0 -> seg1
      atmos_prod                 ECF_FILES = ecf_scripts/atmos_prod
        mem000: f000_f024 ...    trigger: that member's forecast
        mem001: f000_f024 ...
        mem002: f000_f024 ...
      ocean_prod, ice_prod, wavepostgridded ...   same shape
      atmos_ensstat              trigger: all member atmos_prod complete
      arch_vrfy -> arch_tars -> cleanup
```

## Step 5: Run a task

```
ecflow_client --begin=my_gefs_test
  |
  +-- server finds a queued task whose trigger is complete
  |     (e.g. /my_gefs_test/gefs/2021032312/atmos_prod/mem001/f000_f024)
  |
  +-- resolve script:  ECF_FILES (family scoped) + task name + .ecf
  |     -> ecf_scripts/atmos_prod/f000_f024.ecf
  |
  +-- preprocess %include <head.h>, %FHR_LIST%, %ENSMEM:% ... -> .job
  |
  +-- ECF_JOB_CMD:  sbatch <job>
  |
  +-- on the compute node:
  |     head.h     ecflow_client --init, trap errors
  |     task body  load_modules.sh run, export ENSMEM / MEMDIR,
  |                loop over FHR_LIST, call dev/jobs/JGLOBAL_ATMOS_PRODUCTS
  |     tail.h     ecflow_client --complete
  |
  +-- server marks the task complete and releases dependent triggers
```

## Step 6: Restart a failed piece

```
ecflow_client --requeue=aborted /my_gefs_test      # requeue aborted tasks

# Fresh start after changing scripts or configs
python3 dev/workflow/ecflow/run_ecflow_case.py \
    --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml --pslot my_gefs_test --overwrite
ecflow_client --begin=my_gefs_test
```
