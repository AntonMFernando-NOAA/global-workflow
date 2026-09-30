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
# Expected: ufe01 or similar

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

# ── Step 1b: Set the global-workflow repo path ───────────────────
export HOMEglobal=/scratch3/NCEPDEV/global/${USER}/global-workflow

# ── Step 1b-workaround: Machine detection on ufe nodes ───────────
# The mount-based auto-detection in hosts.py may misidentify some
# Ursa front-end nodes (e.g. ufe12) as Hera.  If you hit unexpected
# platform errors, force the machine identity:
export MACHINE_ID=URSA

# ── Step 1d: Choose an ecFlow server ─────────────────────────────
# Each user runs their own ecFlow server on a unique port.
# Use your UID offset by 1500 to avoid collisions with other users:
export ECF_PORT=$(( $(id -u) + 1500 ))
export ECF_HOST=uecflow01
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

If `ecflow_client --ping` fails, go to [section 2](#2-ecflow-server)
to start the server first, then come back here.

## 2. ecFlow Server

### Check if a server is already running

From any login node, check if your server on `uecflow01` is alive:

```bash
export ECF_HOST=uecflow01
export ECF_PORT=$(( $(id -u) + 1500 ))
ecflow_client --ping
```

If it responds with `ping server(...) succeeded`, the server is up.
Skip to step 3.

### Find your server port

If someone gave you a server to use, they will have given you the
host and port. Otherwise:

```bash
# See if you already have a server running under your user
ecflow_client --host=$(hostname) --port=${ECF_PORT} --ping

# Or check all ecflow_server processes on this host
ps -u ${USER} -f | grep ecflow_server
# Output shows: ecflow_server --port=23385 --ecf_home=...
# The --port value is your ECF_PORT
```

### Start your own server from scratch

```bash
ssh uecflow01
module load ecflow
export ECF_PORT=$(( $(id -u) + 1500 ))
export ECF_HOME=/scratch3/NCEPDEV/global/${USER}/ecflow

# Check if it's still running
ps -u ${USER} -f | grep ecflow_server

# If not running, restart
ecflow_start.sh -p ${ECF_PORT} -d ${ECF_HOME}

# The server restores state from its checkpoint file.
# Previously loaded suites reappear with their last known state.
ecflow_client --ping
# Expected: ping server(<hostname>:<port>) succeeded in 00:00:00.00...

# 5. Save these values for future sessions
echo "Add to your ~/.bashrc:"
echo "  export ECF_HOST=${ECF_HOST}"
echo "  export ECF_PORT=${ECF_PORT}"
echo "  export ECF_HOME=${ECF_HOME}"
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

### Starting a new session

```bash
# 1. SSH into Ursa
ssh -X <username>@ursa.rdhpcs.noaa.gov

# 2. Source your environment (or add to ~/.bashrc once)
module load ecflow
unset ECF_HOSTFILE
export ECF_PORT=$(( $(id -u) + 1500 ))
export ECF_HOST=$(hostname)
export ECF_HOME=/scratch3/NCEPDEV/global/${USER}/ecflow
export HOMEglobal=/scratch3/NCEPDEV/global/${USER}/global-workflow

# 3. Verify the server is alive
ecflow_client --ping
```

### Run a case

```bash
cd ${HOMEglobal}
python3 dev/workflow/ecflow/c48_atm_ecflow.py
```

Answer `y` to the cleanup and delete prompts. The suite starts
automatically. Monitor with:

```bash
ecflow_ui &                    # GUI (needs X11 forwarding)
# or
ecflow_client --get_state /C48_ATM_ecflow   # CLI
```

### Check task progress

```bash
# See all tasks and their states
ecflow_client --get_state /C48_ATM_ecflow

# Check if a specific task is done
ecflow_client --get_state /C48_ATM_ecflow/gfs/2021032312/fcst
```

### If a task fails (red/aborted)

```bash
# 1. Check the job output for the error
cat ${ECF_HOME}/<task_name>.1

# 2. Fix the issue (edit .ecf, fix paths, etc.)

# 3. Rerun the task
ecflow_client --force=queued /C48_ATM_ecflow/gfs/2021032312/<task_name>
```

### Rerun the whole suite from scratch

```bash
python3 dev/workflow/ecflow/c48_atm_ecflow.py --overwrite
```

### Clean up after a run

```bash
# Delete the suite from the server
ecflow_client --suspend /C48_ATM_ecflow
ecflow_client --kill /C48_ATM_ecflow
sleep 5
ecflow_client --delete=force yes /C48_ATM_ecflow

# Optionally remove the experiment directories
rm -rf ${RUNTESTS}/EXPDIR/C48_ATM_ecflow
rm -rf ${RUNTESTS}/COMROOT/C48_ATM_ecflow
```

### Update .ecf scripts after editing (without regenerating)

```bash
bash dev/workflow/ecflow/sync_ecf_scripts.sh \
    ${RUNTESTS}/EXPDIR/C48_ATM_ecflow/ecf_scripts
```

### End of day

The ecFlow server persists across sessions. You can log out and
come back tomorrow — the suite continues running (or waiting) on
the server. Just re-source your environment variables when you
reconnect.

## 3. Run the C48_ATM Case

### Quick start (all defaults)

```bash
cd ${HOMEglobal}
python3 dev/workflow/ecflow/c48_atm_ecflow.py
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
ecflow_client --force=queued /C48_ATM_ecflow/gfs/2021032312/fcst
```

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
ecflow_client --delete=force yes /C48_ATM_ecflow
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

### Jinja2 or other Python imports not found

```
ModuleNotFoundError: No module named 'jinja2'
```

**Fix:** The workflow's Python dependencies (Jinja2, PyYAML, etc.)
are provided by the build modules. Load them before running any
ecFlow or setup script:
```bash
module use ${HOMEglobal}/modulefiles
module load module_gwsetup.ursa
```

If `module_gwsetup.ursa` is not available, load the stack that was
used to build the workflow (e.g. `module load intel`, `module load
spack-stack`) — the exact modules depend on your build.

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
                              │
Execution:   .ecf scripts ──► head.h + slurm.h + J-Job + tail.h
```

For a detailed comparison with Rocoto, see
`.kiro/specs/feature-ecflow-c48-atm/ecflow-process-trace.md`.
