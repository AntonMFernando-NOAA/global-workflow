# Forecast Manager — chat session 2026-06-12

Branch: `dev/gfs.v17` (PR #4984 / issue #5003)

## Topics covered

1. Why `${RUN}` == "gfs" guard exists for OCN/ICE in JGLOBAL_FORECAST_MANAGER
2. Investigation of MOM6 sentinel logs for GDAS
3. f330 ocean_prod false-trigger root-cause analysis
4. ecflow vs Rocoto architecture and operational flow
5. Issue #5003 fix: ecflow trigger update for `jgfs_wave_postpnt`

---

## Why the `${RUN}` == "gfs" guard exists for OCN/ICE

The forecast manager polls for **per-period sentinel logs** that the
model writes after each history file is fully flushed.

| Component | use_mgr for | Why |
|---|---|---|
| ATM (FV3) | gfs, gdas, enkfgdas | All produce `log.atm.fHHH` |
| WW3 | gfs, gdas, enkfgdas | All produce `log.YYYYMMDD.HH0000.out_*.ww3.txt` |
| OCN (MOM6) | **gfs only** | MOM6 doesn't write per-period `mom6.HHh` logs for gdas/enkfgdas |
| ICE (CICE) | **gfs only** | TODO — needs verification before enabling for gdas |

Without the guard, the manager would wait 7200s for OCN/ICE product
tables that GDAS never produces, then fatal-exit.

For GDAS, ocean files are still copied — via `cmdfile_mom6_hist`
(MPMD batch copy) inside `MOM6_out()` after the model finishes.

---

## MOM6 sentinel log gap (Daniel/Dan email thread)

- CICE writes `log.ice.fHHHH` per period for GDAS — works.
- MOM6 does **NOT** write per-period `mom6.HHh` logs for GDAS.
- Daniel suggested logs are tied to `restart_interval`, but
  `restart_interval_gdas=3` matches `FHOUT_OCN=3` — the issue is
  MOM6 isn't writing them at all in the GDAS run dir.
- Workaround proposed: chain on the **next forecast hour's `.nc`**
  as the sentinel for the previous hour. The manager already supports
  this pattern (data-file-trigger branch in `forecast_manager.sh`).

Run dir reference:
```
/lfs/h2/emc/stmp/anton.fernando/RUNDIRS/C96C48mx500_S2SW_cyc_gfs_t/\
gdas.2021122012/gdas_forecast.2021122012/
```

In `MOM6_OUTPUT/`: only `ocn_da_*.nc` data files, `MOM_parameter_doc.*`,
`ocean.stats[.nc]`, `Vertical_coordinate.nc`. **No `*.mom6.HHh`.**

---

## f330 false-trigger root cause analysis

Symptom: `ocean_prod` task triggered for f330, then failed because
`gdas.t00z.6hr_avg.f330.nc` wasn't in COM yet.

Likely cause: manager fallback path writes a synthetic com_log even
when local_data isn't fully flushed. Three failure modes identified:

1. **NFS metadata lag** — `[[ -f local_data ]]` returns true on
   metadata before data is committed. Normal path runs a
   size-stability check; **fallback path does not**.
2. **Synthetic-log fallback** — when model log absent, manager
   writes fabricated com_log without verifying .nc fully usable.
3. **Stale com_log on rerun** — manager's RERUN safety branch
   skips a row if com_log already exists, even if .nc is missing.

Recommended fixes:
- (a) Apply size-stability check to fallback path
- (b) RERUN safety should require both `-f com_log` AND `-f com_data`
- (c) Bounded retry on local_data presence in fallback
- (d) Don't trust `fcst_done_seg` as flush guarantee on Lustre/NFS

---

## ecflow vs Rocoto

| | Rocoto | ecflow |
|---|---|---|
| Used by | Developers / parallels | Operations (NCO) |
| Definition | Generated XML from `gfs_tasks.py` | Hand-edited `gfs_prod.def` |
| Server | None — `rocotorun` driven | Long-lived daemon |
| Iteration | Edit Python → regen XML → rerun | Edit `.def` → reload → rebegin |
| Per-cycle | Date-range driven | Time-of-day triggered |
| Failure | Auto-retry up to maxtries | Human-supervised |
| Operational gfs.v17 | dev experiments | NCO production |

Both call the same `J*` jobs from `jobs/`. Not auto-synced; maintained
in parallel.

### Production cycle flow (12Z example)

```
09:00Z  jgfs_atmos_prep_fsm time-trigger
10:30Z  jgfs_atmos_prep complete → analysis
11:15Z  jgfs_fcst submits, jgfs_fcst_fsm submits in parallel
11:30Z+ FSM emits release_gfs_atmos_product_fHHH events
        → product tasks trigger immediately
13:00Z  Forecast complete → release_gfs_fcst_manager event fires
        → jgfs_fcst_manager runs (final cleanup/copy)
13:30Z  Wave post, gempak, awips, archive, etc.
```

---

## Issue #5003 fix: ecflow trigger update

### Scope

Search for tasks waiting on `jgfs_fcst==complete` that should wait on
`jgfs_fcst_manager==complete` (for files in COM).

### Found

| Trigger | Task | Action |
|---|---|---|
| `jgfs_fcst==active or jgfs_fcst==complete` (4 cycles) | `jgfs_fcst_fsm` | **Keep** — FSM runs in parallel with forecast |
| `../../../forecast/jgfs_fcst==complete` (4 cycles) | `jgfs_wave_postpnt` | **Change** — needs WW3 point output in COM |

Other downstream tasks already use FSM-emitted per-fhour events:
- `jgfs_atmos_product_fHHH` → `jgfs_fcst_fsm:release_gfs_atmos_product_fHHH`
- `jgfs_wave_post_gridded_*` → `jgfs_fcst_fsm:release_gfs_wave_post_gridded_*`
- `jgfs_ice_product_*` → `jgfs_fcst_fsm:release_gfs_ice_product_*`
- `jgfs_atmos_postsnd` → `./product/jgfs_atmos_product_f180==complete`
- `jgfs_atmos_fbwind` → `jgfs_fcst_fsm:release_gfs_atmos_product_f032`

### Applied change

```diff
 task jgfs_wave_postpnt
-  trigger ../../../forecast/jgfs_fcst==complete
+  trigger ../../../forecast/jgfs_fcst_manager==complete
```

In all 4 cycles (00, 06, 12, 18): lines 5149, 11038, 16927, 22816.

---

## Related work outside this PR (deferred)

These were discussed but reverted because gdas/enkfgdas forecast
manager extension isn't part of dev/gfs.v17 yet:

- Adding `jgdas_fcst_manager` task to ecflow def (4 cycles)
- Adding `jenkfgdas_fcst_manager_master` per ensemble member
- Updating prev-cycle triggers (jgfs_atmos_prep, analsnow, etc.)
- Conditional `_fcst_manager` deps in `gfs_tasks.py` for prep,
  aeroanlgenb, echgres, epos
- Extending OCN manager to gdas via next-`.nc`-trigger approach
- Extending ICE manager to gdas (use_mgr_ice for gfs|gdas|enkfgdas)

Future PR work for develop branch / gdas.v17 extension.


---

# Continued session — 2026-06-15

## MOM6 ocean filename rename (`ocn_da` → `ocn`)

### Problem

MOM6's sentinel-logging code (`mom_cap_outputFile.F90`) is hardcoded to
look for output files named `ocn_<timestamp>.nc`. But the GDAS diag
table (`diag_table_da`) names them `ocn_da_<timestamp>.nc`. The mismatch
means MOM6 never recognizes the output → never writes per-period
`YYYYMMDD.HHMMSS.mom6.HHh` sentinel logs → forecast manager has nothing
to poll on for GDAS ocean.

### Dan Sarmiento email discussion — Option 1 chosen

Three options proposed by Dan. Dave chose option 1: rename `ocn_da_` →
`ocn_` in GW. Dan's UFSWM change enables hourly sentinel checks.

### GW-side changes applied

- `parm/ufs/fv3/diag_table_da` — all `ocn_da%4yr%2mo%2dy%2hr` →
  `ocn%4yr%2mo%2dy%2hr`
- `ush/forecast_postdet.sh` — NLN symlink source: `ocn_da_${vdatestr}.nc`
  → `ocn_${vdatestr}.nc`

Both gdas and enkfgdas use the same `diag_table_da` (confirmed via
`config.efcs` and `config.fcst`), so one change covers both.

### Waiting on

Dan's UFSWM PR to enable hourly/3-hourly sentinel checks in
`mom_cap_outputFile.F90`.

---

## ecflow module load standardization

Replaced per-script partial module loads in 30 ecf scripts (under
`gfs/`, `gdas/`, `enkfgdas/` in `init/` and `product/` directories)
with the full set from `modulefiles/gw_run.wcoss2.lua`.

---

## ecflow updates for forecast manager (addressing Jessica's review)

### New `.ecf` job scripts

| File | Purpose |
|---|---|
| `ecf/scripts/gdas/forecast/jgdas_fcst_manager.ecf` | GDAS forecast manager |
| `ecf/scripts/enkfgdas/forecast/jenkfgdas_fcst_manager_master.ecf` | enkfGDAS per-member forecast manager (template for 80 members) |

### `gfs_prod.def` additions (4 cycles)

**GDAS:**
```
task jgdas_fcst
  trigger ...
  event 210 release_gdas_fcst_manager
task jgdas_fcst_manager
  trigger jgdas_fcst:release_gdas_fcst_manager
```

**enkfGDAS** — 80 per-member manager tasks:
```
task jenkfgdas_fcst_manager_mem001
  edit ENSMEM '001'
  edit MEMDIR 'mem001'
  trigger jenkfgdas_fcst_mem001==complete
```

**GFS trigger fix** (issue #5003):
```diff
 task jgfs_wave_postpnt
-  trigger ../../../forecast/jgfs_fcst==complete
+  trigger ../../../forecast/jgfs_fcst_manager==complete
```

---

## ecflow concepts learned

### Family
A grouping container (like a folder). Holds tasks. Has aggregate state —
`family==complete` when ALL children complete. Not a metatask — doesn't
expand or parameterize.

### Event
A named binary signal a running task can fire mid-execution via
`ecflow_client --event <name>`. Other tasks trigger on it without
waiting for the source task to finish.

### Trigger path navigation
Paths use `../` to go up, then named families to go down:
```
../../../../18/gdas/forecast/jgdas_fcst==complete
```
Goes up 4 levels from current position, then down into sibling cycle
`18` → `gdas` → `forecast` → task `jgdas_fcst`.

### FSM (File Service Manager) — `exglobal_fsm.sh`
Long-running batch job that polls COM for files in a loop (every 30s).
When it sees a file appear, fires an ecflow event. Downstream product
tasks trigger on those events. Does NOT copy files — just watches and
signals. Runs in parallel with the forecast for up to 6 hours.

### FSM vs forecast manager
| | FSM (`exglobal_fsm.sh`) | Forecast manager |
|---|---|---|
| Polls | COM (files already there) | Run dir (sentinel logs) |
| Copies files | No | Yes (run dir → COM) |
| Fires ecflow events | Yes (per-fhour) | No |
| Both run in parallel | Yes | Yes |

They're complementary: manager copies, FSM watches COM and signals ecflow.

### Future consideration
FSM should switch from polling raw `.nc` files to polling **log sentinels**
in COM (which the manager writes last). This eliminates the Lustre
metadata-lag race condition that caused the f330 false trigger.
