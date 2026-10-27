date
hostname
set -xe

export PS4='+ $SECONDS + '

# Make ecflow_client available.  Use the module when the host has one and
# fall back to the client location recorded when the suite was generated.
load_ecflow() {
  if type module &> /dev/null; then
    module load ecflow 2> /dev/null || true
  fi
  if [[ -n "%ECFLOW_BINDIR%" && ":${PATH}:" != *":%ECFLOW_BINDIR%:"* ]]; then
    export PATH="%ECFLOW_BINDIR%:${PATH}"
  fi
}
# Load ecflow first so variable exports below take precedence
load_ecflow

# ecFlow communication variables
export ECF_NAME=%ECF_NAME%
export ECF_HOST=%ECF_HOST%
export ECF_PORT=%ECF_PORT%
export ECF_PASS=%ECF_PASS%
export ECF_TRYNO=%ECF_TRYNO%
export ECF_RID=${ECF_RID:-${SLURM_JOB_ID:-$(hostname -s).$$}}
export ECF_JOB=%ECF_JOB%
export ECF_JOBOUT=%LOGDIR%/%LOG_NAME%.log.%ECF_TRYNO%

# Preserve ECF_HOST/ECF_PORT for use after load_modules.sh resets modules
readonly _ECF_HOST_SAVED=%ECF_HOST%
readonly _ECF_PORT_SAVED=%ECF_PORT%

# Notify ecFlow that the task has started
timeout 300 ecflow_client --init=${ECF_RID}

# Error handler — restores ecflow_client and server coordinates
ERROR() {
  set +ex
  load_ecflow
  export ECF_HOST="${_ECF_HOST_SAVED}"
  export ECF_PORT="${_ECF_PORT_SAVED}"
  if [ "$1" -eq 0 ]; then
    msg="Killed by signal (likely via scancel)"
  else
    msg="Killed by signal $1"
  fi
  ecflow_client --abort="$msg"
  echo "$msg"
  trap 0
  exit $1
}
trap 'ERROR $?' ERR EXIT
