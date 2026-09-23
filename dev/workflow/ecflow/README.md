# Running Global Workflow with ecFlow

This guide covers running forecast-only test cases (GFS, GEFS, SFS)
using ecFlow on Ursa. The same steps apply to other platforms with
minor path adjustments.

## Prerequisites

- NOAA RDHPCS account with Ursa access
- PuTTY (Windows) or SSH client (Mac/Linux)
- Global-workflow repo checked out and built on Ursa
- Slurm scheduler access for job submission

## 0. Connecting to Ursa

### From Windows (PuTTY)

1. Open PuTTY
2. Enter the hostname: `ursa.rdhpcs.noaa.gov`
3. Port: `22`
4. Connection type: SSH
5. Click **Open**
6. Login with your RDHPCS username and RSA token + PIN

To save this for future use:
- In the **Session** panel, type a name (e.g. `Ursa`) in
  "Saved Sessions" and click **Save**
- Next time, double-click the saved session to connect

### From Mac/Linux (terminal)

```bash
ssh <username>@ursa.rdhpcs.noaa.gov
```

### Forwarding X11 for ecflow_ui (GUI)

ecflow_ui requires X11 forwarding to display the GUI on your
local machine.

**PuTTY:** Go to Connection > SSH > X11 > check "Enable X11
forwarding". You also need an X server running locally
(install [VcXsrv](https://sourceforge.net/projects/vcxsrv/)
or [Xming](https://sourceforge.net/projects/xming/) on Windows).

**Mac/Linux:**
```bash
ssh -X <username>@ursa.rdhpcs.noaa.gov
```

Verify X11 works after logging in:
```bash
xterm &    # a small terminal window should appear on your screen
```

### After logging in

```bash
# Check you are on Ursa
hostname
# Expected: ulogin01 or similar

# Navigate to your workspace
cd /scratch3/NCEPDEV/global/${USER}
```

## 1. Environment Setup

Set these variables before running any ecFlow scripts. Add them to
your `~/.bashrc` or source them in each session.

```bash
# ── Step 1a: Load workflow modules (provides jinja2, pyyaml, etc.) ─
source ${HOMEglobal}/dev/ush/load_modules.sh setup

# ── Step 1b: Load the ecFlow module ──────────────────────────────
module load ecflow

# Remove any stale host file that might redirect ecflow_client
unset ECF_HOSTFILE

# ── Step 1c: Set the global-workflow repo path ───────────────────
export HOMEglobal=/scratch3/NCEPDEV/global/${USER}/global-workflow

# ── Step 1d: Choose an ecFlow server ─────────────────────────────
# Each user runs their own ecFlow server on a unique port.
# Use your UID offset by 1500 to avoid collisions with other users:
export ECF_PORT=$(( $(id -u) + 1500 ))
export ECF_HOST=$(hostname)
echo "Your ecFlow server: ${ECF_HOST}:${ECF_PORT}"

# ── Step 1e: Set the ecFlow job directory ────────────────────────
# This is where ecFlow writes .job files and captures .jobout output.
# Create it if it doesn't exist.
export ECF_HOME=/scratch3/NCEPDEV/global/${USER}/ecflow
mkdir -p "${ECF_HOME}"
```

Verify everything is set:
```bash
echo "ECF_HOST   = ${ECF_HOST}"
echo "ECF_PORT   = ${ECF_PORT}"
echo "ECF_HOME   = ${ECF_HOME}"
echo "HOMEglobal = ${HOMEglobal}"
ecflow_client --ping   # should say "ping ... succeeded"
```

## 2. ecFlow Server

### Check if a server is already running

```bash
ecflow_client --ping
```

If it responds with `ping server(...) succeeded`, the server is up.
Skip to step 3.

### Start your own server from scratch

```bash
# 1. Pick a port unique to you (UID + 1500 avoids collisions)
export ECF_PORT=$(( $(id -u) + 1500 ))
echo "Starting ecFlow server on port ${ECF_PORT}"

# 2. Create the job directory
export ECF_HOME=/scratch3/NCEPDEV/global/${USER}/ecflow
mkdir -p "${ECF_HOME}"

# 3. Start the server
ecflow_start.sh -p ${ECF_PORT} -d ${ECF_HOME}

# 4. Verify it's running
export ECF_HOST=$(hostname)
ecflow_client --ping
```

### Stop the server (when completely done)

```bash
ecflow_client --halt=yes       # stop scheduling
ecflow_client --check_pt       # save server state
ecflow_client --terminate=yes  # shut down the server process
```

## 3. Run a Test Case

A single entry point handles all forecast-only cases. The case YAML
drives everything (NET, mode, app, ensemble count, etc.).

### Available cases

| Case | Command |
|------|---------|
| C48_ATM (GFS, default) | `python3 dev/workflow/ecflow/run_ecflow_case.py` |
| C48_S2SWA GEFS | `python3 dev/workflow/ecflow/run_ecflow_case.py --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml` |
| Any other case | `python3 dev/workflow/ecflow/run_ecflow_case.py --yaml dev/ci/cases/pr/<CASE>.yaml` |

### Quick start

```bash
cd ${HOMEglobal}

# GFS forecast-only (default)
python3 dev/workflow/ecflow/run_ecflow_case.py

# GEFS forecast-only with S2SWA app and 2 ensemble members
python3 dev/workflow/ecflow/run_ecflow_case.py \
    --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml
```

This will:
1. Clean up any previous run directories (with prompt)
2. Create the experiment via `setup_expt`
3. Generate the `.def` file and copy `.ecf` scripts
4. Load the suite into the ecFlow server (with prompt if it already exists)

The suite is loaded but **not started**. The script prints the
`ecflow_client --begin` command to run when you are ready.

### With custom paths

```bash
python3 dev/workflow/ecflow/run_ecflow_case.py \
    --yaml dev/ci/cases/pr/C48_S2SWA_gefs.yaml \
    --pslot my_gefs_test \
    --comroot /scratch4/NCEPDEV/stmp/${USER}/COMROOT \
    --stmp /scratch4/NCEPDEV/stmp/${USER}
```

### CLI options

| Option | Description |
|--------|-------------|
| `--yaml PATH` | Case YAML file (default: C48_ATM) |
| `--pslot NAME` | Override experiment name |
| `--comroot PATH` | Override output data directory |
| `--expdir PATH` | Override experiment config directory |
| `--stmp PATH` | Override runtime scratch directory |
| `--suite-name NAME` | Override ecFlow suite name |
| `--overwrite` | Overwrite a previously created experiment |

## 4. Monitoring

### ecflow_ui (GUI)

```bash
ecflow_ui &
```

Connect to `${ECF_HOST}:${ECF_PORT}`. The suite tree shows task
states: queued (blue), submitted (cyan), active (green),
complete (yellow), aborted (red).

### Command line

```bash
# Suite status overview
ecflow_client --get_state /<suite_name>

# Watch a specific task
ecflow_client --get_state /<suite_name>/gefs/2021032312/fcst

# View job output for a task
cat ${ECF_HOME}/<task_name>.1    # .1 = first try number
```

### Log files

Task logs are written to `{ROTDIR}/logs/`:
```bash
ls ${COMROOT}/<suite_name>/logs/
```

## 5. Updating and Rerunning

### After editing .ecf scripts (J-Job wrappers)

Sync the updated scripts to the experiment directory. No server
restart needed:

```bash
bash dev/workflow/ecflow/reload_ecflow_def.sh \
    ${RUNTESTS}/EXPDIR/<suite_name> sync
```

Then rerun the failed task:
```bash
ecflow_client --force=queued /<suite_name>/<path_to_task>
```

### After editing Python suite generator or task definitions

Regenerate the `.def`, sync scripts, and replace the suite on the
server (preserves all task states):

```bash
bash dev/workflow/ecflow/reload_ecflow_def.sh \
    ${RUNTESTS}/EXPDIR/<suite_name> reload
```

Then rerun the failed task:
```bash
ecflow_client --force=queued /<suite_name>/<path_to_task>
```

### Rerun a failed task (no code changes)

```bash
# In ecflow_ui: right-click task -> Rerun
# Or from CLI:
ecflow_client --force=queued /<suite_name>/<path_to_task>
```

### Skip a task that already completed

```bash
ecflow_client --force=complete /<suite_name>/<path_to_task>
```

### Rerun the whole suite from scratch

```bash
python3 dev/workflow/ecflow/run_ecflow_case.py \
    --yaml dev/ci/cases/pr/<CASE>.yaml --overwrite
```

## 6. Common Operations

### Suspend / resume the suite

```bash
ecflow_client --suspend /<suite_name>
ecflow_client --resume /<suite_name>
```

### Delete the suite

```bash
ecflow_client --suspend /<suite_name>
ecflow_client --kill /<suite_name>
sleep 5
ecflow_client --delete=force yes /<suite_name>
```

### End of day

The ecFlow server persists across sessions. You can log out and
come back tomorrow. Just re-source your environment variables when
you reconnect.

## 7. Troubleshooting

### "No module named 'jinja2'"

```
ModuleNotFoundError: No module named 'jinja2'
```

**Fix:** Load workflow modules before running:
```bash
source ${HOMEglobal}/dev/ush/load_modules.sh setup
```

### "Missing environment variables"

```
[ERROR] Missing environment variables: ECF_HOST, ECF_PORT, ECF_HOME
```

**Fix:** Source the environment variables from step 1.

### "Cannot reach ecFlow server"

**Fix:** Check that the server is running (`ecflow_client --ping`).
If running your own, start it with `ecflow_start.sh`.

### Tasks stay in "queued" state

**Check triggers:** The task might be waiting for an upstream task.
```bash
ecflow_client --get_state /<suite_name>/<path_to_task>
```

**Check Slurm:** The job might be pending in the Slurm queue.
```bash
squeue -u ${USER}
```

### Tasks abort immediately

**Check the .ecf script exists:**
```bash
ls ${EXPDIR}/<suite_name>/ecf_scripts/<task_name>.ecf
```

**Check the job output:**
```bash
cat ${ECF_HOME}/<task_name>.1
```

Common causes:
- `load_modules.sh` failure (missing modules)
- J-Job script not found (HOMEglobal path wrong)
- File permissions

### "Warm start detected" error on segmented forecast rerun

The previous run left restart files in DATA. Clean the member's
DATA directory before rerunning:
```bash
rm -rf /scratch4/NCEPDEV/stmp/${USER}/RUNDIRS/<suite_name>/gefs*<member>*
ecflow_client --force=queued /<suite_name>/<path_to_seg0>
```

## 8. Directory Layout

After a successful run, the experiment produces:

```
${RUNTESTS}/
  EXPDIR/<suite_name>/              experiment config
    config.base                      config files
    config.fcst
    config.atmos_products
    ...
    <suite_name>.def                 generated ecFlow definition
    ecf_scripts/                     copied .ecf files + manifest
  COMROOT/<suite_name>/              output data
    gefs.20210323/12/                forecast output (or gfs.* for GFS)
      model_data/atmos/history/      atmospheric history files
    logs/                            task log files
  RUNDIRS/<suite_name>/              runtime scratch (cleaned up)
```

## 9. Architecture Overview

```
Entry point:      run_ecflow_case.py --yaml <case>.yaml
                       |
Orchestrator:     load_ecflow_case.run()
                       |
                  +----+----+
                  |         |
Experiment:  setup_expt  setup_workflow --> ecflow_suite_factory
                              |
Task defs:   ecflow_tasks_factory --> GFSEcFlowTasks / GEFSEcFlowTasks
                              |          (one method per task)
Suite gen:   ForecastOnlyEcFlowSuite.write()
                              |
Output:      {pslot}.def + ecf_scripts/
                              |
Server:      ecflow_client --load / --begin
                              |
Execution:   .ecf scripts --> head.h + slurm.h + J-Job + tail.h
```

### Adding a new forecast system

To add ecFlow support for a new NET (e.g. SFS):

1. Create `sfs_ecflow_tasks.py` with per-task methods
2. Register in `ecflow_tasks_factory.py`: `register('sfs', SFSEcFlowTasks)`
3. Register in `ecflow_suite_factory.py`: `register('sfs_forecast-only', ForecastOnlyEcFlowSuite)`
4. Add any new `.ecf` scripts to `dev/ecflow/scripts/`
5. Create a case YAML under `dev/ci/cases/pr/`

The unified `ForecastOnlyEcFlowSuite` handles both single-member
(GFS) and ensemble (GEFS) runs automatically based on `NMEM_ENS`.
