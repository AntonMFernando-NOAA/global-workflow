#!/bin/bash
# bootstrap.sh -- set up the C96 ecFlow suite on WCOSS2 (one-shot).
#
# Idempotent: safe to re-run.  Creates the dev directories the J-scripts
# expect, symlinks any required external paths into the dev tree, and
# applies the suite-level variable overrides on the running ecFlow server.
#
# Usage:
#   1. Start the ecFlow server on dlogin01 (see Chapter 1.2 of
#      General-Knowledge for the full procedure).
#   2. Make sure ECF_HOST and ECF_PORT are set in this shell (typically by
#      sourcing ~/ecflow_c96.env).
#   3. Run:
#        bash dev/ecf/c96/bootstrap.sh
#
# Safe to run multiple times.  Each --alter is "change" (idempotent) so a
# second run just overwrites the same values.

set -eu

# ----------------------------------------------------------------------
# Required env -- fail loudly if missing
# ----------------------------------------------------------------------
: "${HOMEgfs:?set HOMEgfs to the global-workflow_gfsv17 checkout root}"
: "${ECF_HOST:?set ECF_HOST (typically dlogin01)}"
: "${ECF_PORT:?set ECF_PORT (typically 2137)}"

ECF_USER_HOME="${ECF_HOME:-/lfs/h2/emc/global/noscrub/${USER}/ecflow_c96}"
SUITE_NAME="gfs_c96"

# Dev workspace roots -- all under your noscrub area, never under ops paths.
DEV_ROOT="/lfs/h2/emc/global/noscrub/${USER}/c96_run"
DATAROOT="${DEV_ROOT}/tmp"
COMROOT="${DEV_ROOT}/com"
LOGROOT="${DEV_ROOT}/logs"

echo "==> Bootstrapping C96 suite under ${DEV_ROOT}"

# ----------------------------------------------------------------------
# 1. Create dev directories the J-scripts will write into
# ----------------------------------------------------------------------
mkdir -p "${DATAROOT}"
mkdir -p "${COMROOT}"
mkdir -p "${LOGROOT}"
echo "    DATAROOT  = ${DATAROOT}"
echo "    COMROOT   = ${COMROOT}"
echo "    LOGROOT   = ${LOGROOT}"

# ----------------------------------------------------------------------
# 2. Apply suite-level variable overrides on the running server
# ----------------------------------------------------------------------
echo "==> Applying suite variable overrides on ${ECF_HOST}:${ECF_PORT}"

# alter_var <NAME> <VALUE>  -- adds the variable if missing, otherwise
#                              changes it. Idempotent.
alter_var() {
  local name="$1" value="$2" path="${3:-/${SUITE_NAME}}"
  if ecflow_client --host="${ECF_HOST}" --port="${ECF_PORT}" \
       --query variable "${path}":"${name}" > /dev/null 2>&1; then
    ecflow_client --host="${ECF_HOST}" --port="${ECF_PORT}" \
       --alter change variable "${name}" "${value}" "${path}"
  else
    ecflow_client --host="${ECF_HOST}" --port="${ECF_PORT}" \
       --alter add variable "${name}" "${value}" "${path}"
  fi
}

# Connection / job submission
alter_var ECF_LOGHOST    "${ECF_HOST}"
alter_var ECF_JOB_CMD    "qsub %ECF_JOB% 1> %ECF_JOBOUT% 2>&1"
alter_var ECF_KILL_CMD   "qdel %ECF_RID%"
alter_var ECF_STATUS_CMD "qstat %ECF_RID% > %ECF_JOB%.stat 2>&1"

# Repo / build paths
alter_var HOMEgfs        "${HOMEgfs}"
alter_var HOMEglobal     "${HOMEgfs}"

# Production-style version metadata (placeholders, not consumed by C96)
alter_var ecflow_ver     5.6.0
alter_var PDY            "$(date +%Y%m%d)"
alter_var PARATEST       NO
alter_var COMPATH        ""
alter_var MAILTO         ""
alter_var DBNLOG         NO
alter_var SENDDBN        NO
alter_var SENDDBN_NTC    NO
alter_var SENDCANNEDDBN  NO
alter_var rrfs_ver       ""

# Dev workspace overrides -- this is the part that diverges from production.
alter_var DATAROOT       "${DATAROOT}"
alter_var COMROOT        "${COMROOT}"
alter_var LOGROOT        "${LOGROOT}"
alter_var KEEPDATA       YES

# Pin the ECF_FILES / ECF_INCLUDE absolute (sometimes substitution leaks).
alter_var ECF_FILES      "${HOMEgfs}/dev/ecf/c96/scripts" "/${SUITE_NAME}/primary"
alter_var ECF_INCLUDE    "${HOMEgfs}/dev/ecf/c96/include" "/${SUITE_NAME}/primary"

echo "==> Bootstrap complete."
echo
echo "Next steps:"
echo "  ecflow_client --host=${ECF_HOST} --port=${ECF_PORT} --suspend=/${SUITE_NAME}/primary/00"
echo "  ecflow_client --host=${ECF_HOST} --port=${ECF_PORT} --resume=/${SUITE_NAME}"
echo "  ecflow_client --host=${ECF_HOST} --port=${ECF_PORT} --resume=/${SUITE_NAME}/primary/12"
echo "  ecflow_client --host=${ECF_HOST} --port=${ECF_PORT} --begin=${SUITE_NAME}"
