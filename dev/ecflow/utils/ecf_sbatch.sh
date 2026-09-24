#!/bin/bash

# ecf_sbatch.sh — ecFlow job submission wrapper for Slurm.
#
# Sources config.resources (the same file Rocoto uses) to determine
# per-task Slurm resources, then submits the ecFlow job script via
# sbatch with the correct flags.  This keeps resource definitions
# out of the .def file and out of the .ecf scripts.
#
# Usage (set as ECF_JOB_CMD in the .def):
#   edit ECF_JOB_CMD  '<HOMEglobal>/dev/ecflow/utils/ecf_sbatch.sh %ECF_JOB% %TASK% %EXPDIR% %ACCOUNT% %QUEUE% %ECF_JOBOUT%'
#
# Arguments:
#   $1 — ECF_JOB   : path to the preprocessed job script (.ecf → .job)
#   $2 — TASK      : config.resources step name (e.g. fcst, atmos_products)
#   $3 — EXPDIR    : experiment directory containing config.base / config.resources
#   $4 — ACCOUNT   : Slurm account
#   $5 — QUEUE     : Slurm partition
#   $6 — ECF_JOBOUT: job output path
#
# The script prints the Slurm job ID to stdout (required by ecFlow
# for ECF_RID).  Any diagnostic output goes to stderr.

set -eu

JOB_SCRIPT="${1:?ecf_sbatch.sh: missing ECF_JOB argument}"
TASK="${2:?ecf_sbatch.sh: missing TASK argument}"
EXPDIR="${3:?ecf_sbatch.sh: missing EXPDIR argument}"
ACCOUNT="${4:?ecf_sbatch.sh: missing ACCOUNT argument}"
QUEUE="${5:?ecf_sbatch.sh: missing QUEUE argument}"
ECF_JOBOUT="${6:?ecf_sbatch.sh: missing ECF_JOBOUT argument}"

# ── Source config.base for machine, CASE, RUN, etc. ──────────────
# config.resources reads machine, CASE, RUN, and resolution variables
# that config.base provides.  config.base also references runtime
# variables (PDY, cyc) that J-Jobs normally set before sourcing —
# provide stubs so sourcing succeeds under set -eu.
export PDY="${PDY:-20210323}"
export cyc="${cyc:-00}"
if [[ ! -f "${EXPDIR}/config.base" ]]; then
  echo "ecf_sbatch.sh: config.base not found in ${EXPDIR}" >&2
  exit 1
fi

# shellcheck disable=SC1090,SC1091
source "${EXPDIR}/config.base"

# ── Source config.resources for the task ──────────────────────────
if [[ ! -f "${EXPDIR}/config.resources" ]]; then
  echo "ecf_sbatch.sh: config.resources not found in ${EXPDIR}" >&2
  exit 1
fi

# config.resources sets: walltime, ntasks, tasks_per_node,
# threads_per_task, memory, is_exclusive, prepost
# shellcheck disable=SC1090,SC1091
source "${EXPDIR}/config.resources" "${TASK}"

# ── Compute derived values ────────────────────────────────────────
nodes=$(( (ntasks + tasks_per_node - 1) / tasks_per_node ))

# Build sbatch flags
sbatch_flags=(
  --job-name="${RUN:-gfs}_${TASK}_${cyc:-00}"
  --account="${ACCOUNT}"
  --partition="${QUEUE}"
  --time="${walltime}"
  --nodes="${nodes}"
  --ntasks-per-node="${tasks_per_node}"
  --cpus-per-task="${threads_per_task}"
  --output="${ECF_JOBOUT}"
  --export=NONE
)

# Exclusive mode
if [[ "${is_exclusive:-False}" == "True" ]]; then
  sbatch_flags+=(--exclusive)
fi

# ── Submit ────────────────────────────────────────────────────────
# Ensure the job output directory exists
mkdir -p "$(dirname "${ECF_JOBOUT}")"

# sbatch prints the job ID to stdout; ecFlow captures it as ECF_RID.
exec sbatch "${sbatch_flags[@]}" "${JOB_SCRIPT}"
