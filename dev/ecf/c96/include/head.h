date
hostname
set -xe

export PS4='+ $SECONDS + '

# ecFlow communication variables
export ECF_NAME=%ECF_NAME%
export ECF_HOST=%ECF_LOGHOST%
export ECF_PORT=%ECF_PORT%
export ECF_PASS=%ECF_PASS%
export ECF_TRYNO=%ECF_TRYNO%
export ECF_RID=${ECF_RID:-${SLURM_JOB_ID:-$(hostname -s).$$}}
export ECF_JOB=%ECF_JOB%
export ECF_JOBOUT=%ECF_JOBOUT%
export ecflow_ver=%ecflow_ver%

# Model package location
modelhome=%PACKAGEHOME:%
eval "export HOME${model:?'model undefined'}=$modelhome"
eval "versionfile=\$HOME${model}/versions/run.ver"
if [ -f "$versionfile" ]; then . "$versionfile"; fi
modelver=$(echo "${modelhome}" | perl -pe "s:.*?/${model}\.(v[\d\.a-z]+).*:\1:")
eval "export ${model}_ver=$modelver"

export envir=%ENVIR%
export MACHINE_SITE=%MACHINE_SITE%
export RUN_ENVIR=${RUN_ENVIR:-nco}
export SENDECF=${SENDECF:-YES}
export SENDCOM=${SENDCOM:-YES}
if [ -n "%PDY:%" ]; then export PDY=${PDY:-%PDY:%}; fi
if [ -n "%PARATEST:%" ]; then export PARATEST=${PARATEST:-%PARATEST:%}; fi
if [ -n "%COMPATH:%" ]; then export COMPATH=${COMPATH:-%COMPATH:%}; fi
if [ -n "%MAILTO:%" ]; then export MAILTO=${MAILTO:-%MAILTO:%}; fi
if [ -n "%DBNLOG:%" ]; then export DBNLOG=${DBNLOG:-%DBNLOG:%}; fi
export KEEPDATA=NO
export SENDDBN=${SENDDBN:-%SENDDBN:YES%}
export DBNLOG=${DBNLOG:-%DBNLOG:YES%}
export SENDDBN_NTC=${SENDDBN_NTC:-%SENDDBN_NTC:YES%}

if [ -n "%DATAROOT:%" ]; then export DATAROOT="%DATAROOT:%"; fi
if [ -n "%EXPDIR:%" ]; then export EXPDIR="%EXPDIR:%"; fi
if [ -n "%COMROOT:%" ]; then export COMROOT="%COMROOT:%"; fi
if [ -n "%DCOMROOT:%" ]; then export DCOMROOT="%DCOMROOT:%"; fi

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
  trap "$1"; exit "$1"
}
trap 'ERROR $?' ERR EXIT
