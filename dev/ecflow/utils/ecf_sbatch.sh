#!/bin/bash

# ecf_sbatch.sh — ecFlow job submission wrapper for Slurm.
#
# Sources config.resources (the same file Rocoto uses) to determine
# per-task Slurm resources, then submits the ecFlow job script via
# sbatch with the correct flags.  This keeps resource definitions
# out of the .def file and out of the .ecf scripts.
#
# Usage (set as ECF_JOB_CMD in the .def):
#   edit ECF_JOB_CMD  '<HOMEglobal>/dev/ecflow/utils/ecf_sbatch.sh %STEP% %EXPDIR% %ECF_JOBOUT% %ECF_JOB%'
#
# Arguments:
#   $1 — STEP     : config.resources step name (e.g. fcst, atmos_products)
#   $2 — EXPDIR    : experiment directory containing config.base / config.resources
#   $3 — ECF_JOBOUT: job output path
#   $4 — ECF_JOB   : path to the preprocessed job script (.ecf → .job)
#
# ACCOUNT and PARTITION are read from config.base (platform-aware),
# not passed as arguments.  ACCOUNT falls back to HPC_ACCOUNT if
# config.base has UNDEFINED.
#
# The script prints the Slurm job ID to stdout (required by ecFlow
# for ECF_RID).  Any diagnostic output goes to stderr.

set -e

STEP="${1:?ecf_sbatch.sh: missing STEP argument}"
EXPDIR="${2:?ecf_sbatch.sh: missing EXPDIR argument}"
_ECF_JOBOUT="${3:?ecf_sbatch.sh: missing ECF_JOBOUT argument}"
JOB_SCRIPT="${4:?ecf_sbatch.sh: missing ECF_JOB argument}"

# ── Source config.base for machine, CASE, RUN, ACCOUNT, etc. ─────
# config.base also references runtime variables (PDY, cyc) that are
# not needed for resource computation — provide stubs so sourcing
# succeeds under set -e.
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
# threads_per_task, memory, is_exclusive, prepost.
# The fcst step depends on variables from config.fcst (via config.ufs)
# that are not in config.base — source the task config chain first.
if [[ "${STEP}" == "fcst" && -f "${EXPDIR}/config.fcst" ]]; then
  # shellcheck disable=SC1090,SC1091
  source "${EXPDIR}/config.fcst"
fi
# shellcheck disable=SC1090,SC1091
source "${EXPDIR}/config.resources" "${STEP}"

# ── Resolve ACCOUNT ───────────────────────────────────────────────
# ACCOUNT comes from config.base; fall back to HPC_ACCOUNT.
if [[ "${ACCOUNT:-UNDEFINED}" == "UNDEFINED" ]]; then
  ACCOUNT="${HPC_ACCOUNT:?ecf_sbatch.sh: ACCOUNT is UNDEFINED and HPC_ACCOUNT is not set}"
fi

# ── Compute derived values ────────────────────────────────────────
nodes=$(( (ntasks + tasks_per_node - 1) / tasks_per_node ))

sbatch_flags=(
  --job-name="${RUN:-gfs}_${STEP}_${cyc:-00}"
  --account="${ACCOUNT}"
  --partition="${PARTITION_BATCH}"
  --time="${walltime}"
  --nodes="${nodes}"
  --ntasks-per-node="${tasks_per_node}"
  --cpus-per-task="${threads_per_task}"
  --output="${_ECF_JOBOUT}"
  --export=NONE
)

if [[ "${is_exclusive:-False}" == "True" ]]; then
  sbatch_flags+=(--exclusive)
fi

# ── Submit ────────────────────────────────────────────────────────
mkdir -p "$(dirname "${_ECF_JOBOUT}")"

# sbatch prints the job ID to stdout; ecFlow captures it as ECF_RID.
exec sbatch "${sbatch_flags[@]}" "${JOB_SCRIPT}"
