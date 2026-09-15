# envir-p1.h — Ursa/Slurm variant
export job=${job:-${SLURM_JOB_NAME:-$(basename "${ECF_JOB:-.}")}}
export jobid=${jobid:-${job}.${SLURM_JOB_ID:-$$}}

export RUN_ENVIR=${RUN_ENVIR:-emc}
export envir=%ENVIR%
export MACHINE_SITE=%MACHINE_SITE%
export RUN=%RUN%

export SENDCANNEDDBN=${SENDCANNEDDBN:-"NO"}
export SIPHONROOT=${UTILROOT:-/dev/null}/fakedbn
export DBNROOT=$SIPHONROOT
