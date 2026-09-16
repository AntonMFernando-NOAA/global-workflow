date
hostname
set -xe

export PS4='+ $SECONDS + '

# Load ecflow module first so variable exports below take precedence
module load ecflow

# ecFlow communication variables
export ECF_NAME=%ECF_NAME%
export ECF_HOST=%ECF_LOGHOST%
export ECF_PORT=%ECF_PORT%
export ECF_PASS=%ECF_PASS%
export ECF_TRYNO=%ECF_TRYNO%
export ECF_RID=${ECF_RID:-${SLURM_JOB_ID:-$(hostname -s).$$}}
export ECF_JOB=%ECF_JOB%
export ECF_JOBOUT=%ECF_JOBOUT%

# Notify ecFlow that the task has started
timeout 300 ecflow_client --init=${ECF_RID}

# Error handler
ERROR() {
  set +ex
  if [ "$1" -eq 0 ]; then
    msg="Killed by signal (likely via scancel)"
  else
    msg="Killed by signal $1"
  fi
  ecflow_client --abort="$msg"
  echo "$msg"
  trap $1
  exit $1
}
trap 'ERROR $?' ERR EXIT
