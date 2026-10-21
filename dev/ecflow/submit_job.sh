#! /usr/bin/env bash
#
# Submit an ecFlow job with sbatch and keep the log of the latest run as
# <LOGDIR>/<LOG_NAME>.log. The log of an earlier try is renamed to
# <LOG_NAME>.log.0, <LOG_NAME>.log.1, ... before the new job is submitted,
# because Slurm truncates the output file when the job starts.
#
# Usage: submit_job.sh <job_file> <logdir> <log_name>

set -eu

job="${1:?job file}"
logdir="${2:?log directory}"
log_name="${3:?log name}"

log="${logdir}/${log_name}.log"
if [[ -e "${log}" ]]; then
  n=0
  while [[ -e "${log}.${n}" ]]; do
    n=$((n + 1))
  done
  mv "${log}" "${log}.${n}"
fi

sbatch "${job}"
