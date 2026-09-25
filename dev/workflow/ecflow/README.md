# Running Global Workflow with ecFlow

This guide walks through running the C48_ATM forecast-only test case
using ecFlow on Ursa. The same steps apply to other cases and platforms
with minor path adjustments.

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

**PuTTY:** Go to Connection → SSH → X11 → check "Enable X11
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
# ── Step 1a: Load the ecFlow module ──────────────────────────────
module load ecflow

# Remove any stale host file that might redirect ecflow_client
unset ECF_HOSTFILE

# ── Step 1b: Set the global-workflow repo path ───────────────────
# Point this to wherever you cloned the repo.  The loader script
# auto-detects HOMEglobal from its own location, but ecFlow tasks
# read it from the environment during validation.
export HOMEglobal=/scratch3/NCEPDEV/global/${USER}/global-workflow

# ── Step 1b-workaround: Machine detection on ufe nodes ───────────
# The mount-based auto-detection in hosts.py may misidentify some
# Ursa front-end nodes (e.g. ufe12) as Hera.  If you hit unexpected
# platform errors, force the machine identity:
export MACHINE_ID=URSA

# ── Step 1c: Choose an ecFlow server ─────────────────────────────
# Each user runs their own ecFlow server on a unique port.
# Use your UID offset by 1500 to avoid collisions with other users:
export ECF_PORT=$(( $(id -u) + 1500 ))
export ECF_HOST=$(hostname)
echo "Your ecFlow server: ${ECF_HOST}:${ECF_PORT}"

# ── Step 1d: Set the ecFlow job directory ────────────────────────
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

## Day-to-Day Operations (Quick Reference)

Once steps 0–2 are done, this is all you need each day.

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
export HOMEglobal=/scratch3/NCEPDEV/global/${USER}/global-workflow  # adjust to your clone path
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
python3 dev/workflow/ecflow/c48_atm_ecflow.py \
    --pslot my_C48_test \
    --comroot /scratch4/NCEPDEV/stmp/${USER}/COMROOT \
    --expdir /scratch3/NCEPDEV/global/${USER}/EXPDIR \
    --stmp /scratch4/NCEPDEV/stmp/${USER}
```

### CLI options

| Option | Description |
|--------|-------------|
| `--yaml PATH` | Override the case YAML file |
| `--pslot NAME` | Override experiment name (default: `C48_ATM_ecflow`) |
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
ecflow_client --get_state /C48_ATM_ecflow

# Watch a specific task
ecflow_client --get_state /C48_ATM_ecflow/gfs/2021032312/fcst

# View job output for a task
cat ${ECF_HOME}/fcst.1    # .1 = first try number
```

### Log files

Task logs are written to `{ROTDIR}/logs/`:
```bash
ls ${COMROOT}/C48_ATM_ecflow/logs/
```

## 5. Common Operations

### Rerun a failed task

```bash
# In ecflow_ui: right-click task → Rerun
# Or from CLI:
ecflow_client --force=queued /C48_ATM_ecflow/gfs/2021032312/fcst
```

### Suspend / resume the suite

```bash
ecflow_client --suspend /C48_ATM_ecflow
ecflow_client --resume /C48_ATM_ecflow
```

### Delete the suite

```bash
ecflow_client --suspend /C48_ATM_ecflow
ecflow_client --kill /C48_ATM_ecflow
sleep 5
ecflow_client --delete=force yes /C48_ATM_ecflow
```

### Update .ecf scripts without regenerating the .def

```bash
bash dev/workflow/ecflow/sync_ecf_scripts.sh \
    ${EXPDIR}/C48_ATM_ecflow/ecf_scripts
```

### Regenerate the .def from scratch

```bash
python3 dev/workflow/ecflow/c48_atm_ecflow.py --overwrite
```

## 6. Troubleshooting

### "Missing environment variables"

```
[ERROR] Missing environment variables: ECF_HOST, ECF_PORT, ECF_HOME
```

**Fix:** Source the environment variables from step 1. Make sure
`module load ecflow` has been run and `unset ECF_HOSTFILE` is set.

### "Cannot reach ecFlow server"

```
[ERROR] Cannot reach ecFlow server at uecflow01:23385
```

**Fix:** Check that the server is running (`ecflow_client --ping`).
If using a shared server, verify the hostname and port. If running
your own, start it with `ecflow_start.sh`.

### Suite delete times out

```
[WARN] Delete failed: timeout
```

**Fix:** The suite has active jobs that are blocking the delete.
Kill them manually first:
```bash
ecflow_client --suspend /C48_ATM_ecflow
ecflow_client --kill /C48_ATM_ecflow
sleep 20
ecflow_client --delete=force yes /C48_ATM_ecflow
```

### "ecflow_client --load" fails

```
[ERROR] ecflow_client failed: ecflow_client --load=...
  stderr: <error message>
```

**Fix:** The `.def` file has a syntax error. Check the generated file:
```bash
cat ${EXPDIR}/C48_ATM_ecflow/C48_ATM_ecflow.def
```

Common causes:
- Task names with special characters
- Missing `endfamily` or `endsuite` closing tags
- Invalid trigger expressions

You can validate the `.def` before loading:
```bash
ecflow_client --check ${EXPDIR}/C48_ATM_ecflow/C48_ATM_ecflow.def
```

### Tasks stay in "queued" state

**Check triggers:** The task might be waiting for an upstream task.
```bash
ecflow_client --get_state /C48_ATM_ecflow/gfs/2021032312/<task_name>
```

**Check Slurm:** The job might be pending in the Slurm queue.
```bash
squeue -u ${USER}
```

### Tasks abort immediately

**Check the .ecf script exists:**
```bash
ls ${EXPDIR}/C48_ATM_ecflow/ecf_scripts/<task_name>.ecf
```

**Check the job output:**
```bash
cat ${ECF_HOME}/<task_name>.1
```

Common causes:
- `load_modules.sh` failure (missing modules)
- J-Job script not found (HOMEglobal path wrong)
- File permissions

### METplus or archive tasks appear when they shouldn't

If `metp` or `arch_tars` show up in the suite despite being
disabled, check the rendered `config.base`:
```bash
grep DO_METP ${EXPDIR}/C48_ATM_ecflow/config.base
grep DO_ARCHCOM ${EXPDIR}/C48_ATM_ecflow/config.base
```

On Ursa, these should be set to `"NO"` by the platform guards
in `config.base.j2`. If they show `"YES"`, the experiment was
generated before the guards were added — regenerate with
`--overwrite`.

## 7. Directory Layout

After a successful run, the experiment produces:

```
${RUNTESTS}/
  EXPDIR/C48_ATM_ecflow/           ← experiment config
    config.base                     config files
    config.fcst
    config.atmos_products
    ...
    C48_ATM_ecflow.def              generated ecFlow definition
    ecf_scripts/                    copied .ecf files + manifest
  COMROOT/C48_ATM_ecflow/           ← output data
    gfs.20210323/12/                 forecast output
      model_data/atmos/history/      atmospheric history files
    logs/                            task log files
  RUNDIRS/C48_ATM_ecflow/           ← runtime scratch (cleaned up)
```

## 8. Architecture Overview

The ecFlow engine mirrors the Rocoto architecture:

```
Entry point:      c48_atm_ecflow.py
                       │
Orchestrator:     load_ecflow_case.run()
                       │
                  ┌────┴────┐
                  │         │
Experiment:  setup_expt  setup_workflow ──► ecflow_suite_factory
                              │
Task defs:   ecflow_tasks_factory ──► GFSEcFlowTasks
                              │          (one method per task)
Suite gen:   GFSForecastOnlyEcFlowSuite.write()
                              │
Output:      {pslot}.def + ecf_scripts/
                              │
Server:      ecflow_client --load / --begin
                              │
Execution:   .ecf scripts ──► head.h + envir.h + J-Job + tail.h
                              │
Submission:  ecf_sbatch.sh sources config.resources for Slurm flags
```

For a detailed comparison with Rocoto, see
`.kiro/specs/feature-ecflow-c48-atm/ecflow-process-trace.md`.
