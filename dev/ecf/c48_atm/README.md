# C48_ATM — Minimum-Viable Forecast-Only ecFlow Test

Mirrors the Rocoto experiment in
[`dev/ci/cases/pr/C48_ATM.yaml`](../../ci/cases/pr/C48_ATM.yaml):

- **mode**: forecast-only
- **app**: ATM
- **resolution**: C48
- **cycles**: one (idate == edate == 2021032312)
- **task chain**: `stage_ic` → `fcst` → `atmos_product` → `arch_vrfy` → `cleanup`

This suite is intentionally minimal: a single linear chain of five tasks in
one cycle, with no analysis, ensemble, wave, marine, or upp components.
Once it runs end-to-end, more complex configurations (cycled / S2SW / ENKF)
can be layered on with confidence that the fundamentals work.

## Layout

```
dev/ecf/c48_atm/
├── build_def.py          # generator, writes def to $EXPDIR
├── include/              # head.h, tail.h, envir-p1.h (self-contained)
├── scripts/              # task wrappers (.ecf)
│   └── gfs/
│       ├── init/jgfs_stage_ic.ecf
│       ├── forecast/jgfs_fcst.ecf
│       ├── product/atmos/jgfs_atmos_product.ecf
│       └── arch/{jgfs_arch_vrfy.ecf, jgfs_cleanup.ecf}
└── (defs/gfs_c48_atm.def is gitignored — lives in $EXPDIR)
```

The include headers (`head.h`, `tail.h`, `envir-p1.h`) live in
`dev/ecf/c48_atm/include/`. `build_def.py` sets `ECF_INCLUDE` to that
absolute path so the suite is self-contained and doesn't depend on
any other ecFlow test directory.

## Usage

```bash
# 1. Generate the def into $EXPDIR (default $DEV_ROOT/c48_atm/expdir/):
python3 dev/ecf/c48_atm/build_def.py

# 2. Create the dev workspace dirs:
mkdir -p /lfs/h2/emc/global/noscrub/${USER}/c48_atm/{tmp,com,logs}

# 3. Load + begin:
EXPDIR_DEF=/lfs/h2/emc/global/noscrub/${USER}/c48_atm/expdir/gfs_c48_atm.def
ecflow_client --delete=force=yes /gfs_c48_atm 2>/dev/null
ecflow_client --load="${EXPDIR_DEF}"
ecflow_client --suspend=/gfs_c48_atm
ecflow_client --resume=/gfs_c48_atm
ecflow_client --begin=gfs_c48_atm
```

## Watch progress

```bash
ecflow_client --get_state /gfs_c48_atm \
  | grep -oE "state:[a-z]+" | sort | uniq -c
qstat -u "${USER}"
```

A healthy run shows tasks transitioning through
`queued` → `submitted` → `active` → `complete` left to right
along the chain.

## ecFlow include resolution gotcha

ecFlow 5.6 resolves `%include <head.h>` against `$ECF_HOME` first, NOT
`$ECF_INCLUDE`, even when `$ECF_INCLUDE` is set on the suite. If
preprocessing aborts with::

    Could not open include file: $ECF_HOME/head.h (No such file or directory)

copy (don't symlink) the three include files into `$ECF_HOME`::

    cp dev/ecf/c48_atm/include/head.h     "${ECF_HOME}/head.h"
    cp dev/ecf/c48_atm/include/tail.h     "${ECF_HOME}/tail.h"
    cp dev/ecf/c48_atm/include/envir-p1.h "${ECF_HOME}/envir-p1.h"

Symlinks in `$ECF_HOME` are not consistently honored by the preprocessor;
real files always work.

## When something aborts

```bash
TASK=/gfs_c48_atm/primary/12/gfs/init/jgfs_stage_ic   # adjust path
ecflow_client --get_state "${TASK}"
ls -lt "${ECF_HOME}${TASK}".*
tail -50 "${ECF_HOME}${TASK}.1"   # job stdout/stderr
```

Common causes (in order of likelihood):

1. **Missing IC files** — `JGLOBAL_STAGE_IC` looks for ICs at the path
   encoded in `idate=2021032312`. If they aren't staged, stage_ic aborts.
2. **`head.h` re-points ECF_HOST** — if the patched `unset ECF_HOSTFILE`
   block isn't in `head.h`, `module load prod_envir` redirects callbacks
   to NCO's production server and tasks hang in `submitted` forever.
3. **PBS account/queue** — `dev` queue + `GFS-DEV` account string must
   be valid for your user.
4. **Module load failures** — `load_modules.sh` may need an updated
   module path on WCOSS2.
