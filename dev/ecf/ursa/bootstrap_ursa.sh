#!/bin/bash
# bootstrap_ursa.sh — Create experiment, load, and begin the C48_ATM ecFlow
# suite on Ursa.
#
# Prerequisites:
#   1. ecFlow server running on uecflow01 (see ~/ecflow_ursa.env)
#   2. global-workflow built and linked (build_all.sh + link_workflow.sh)
#
# Usage:
#   source ~/ecflow_ursa.env
#   bash dev/ecf/ursa/bootstrap_ursa.sh [--load-only]
#
# With --load-only, creates the experiment and loads the .def but does not
# begin the suite.

set -eu

# ── Validate environment ──
for var in ECF_HOST ECF_PORT ECF_HOME HOMEglobal; do
  if [[ -z "${!var:-}" ]]; then
    echo "[ERROR] ${var} is not set. Source ~/ecflow_ursa.env first."
    exit 1
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEF_FILE="${SCRIPT_DIR}/defs/C48_ATM_ursa.def"
LOAD_ONLY=false
if [[ "${1:-}" == "--load-only" ]]; then
  LOAD_ONLY=true
fi

PSLOT="${PSLOT:-C48_ATM_ecflow}"
RUNTESTS="$(cd "${HOMEglobal}/.." && pwd)/RUNTESTS"
EXPDIR="${RUNTESTS}/EXPDIR/${PSLOT}"
COMROOT="${RUNTESTS}/COMROOT"

echo "=== ecFlow C48_ATM suite bootstrap (Ursa) ==="
echo "  ECF_HOST:    ${ECF_HOST}"
echo "  ECF_PORT:    ${ECF_PORT}"
echo "  ECF_HOME:    ${ECF_HOME}"
echo "  HOMEglobal:  ${HOMEglobal}"
echo "  PSLOT:       ${PSLOT}"
echo "  RUNTESTS:    ${RUNTESTS}"
echo "  EXPDIR:      ${EXPDIR}"
echo "  COMROOT:     ${COMROOT}"
echo ""

# ── Step 1: Create the experiment ──
echo "[1/5] Creating experiment via setup_expt.py..."
if [[ -d "${EXPDIR}" ]]; then
  echo "  EXPDIR already exists, recreating with --overwrite."
fi
mkdir -p "${RUNTESTS}"

# Load the workflow setup module (provides jinja2 and other dependencies)
set +eu
source "${HOMEglobal}/dev/ush/gw_setup.sh"
module load ecflow
set -eu

export PYTHONPATH="${HOMEglobal}/sorc/wxflow/src:${HOMEglobal}/ush/python:${HOMEglobal}/dev/workflow${PYTHONPATH:+:${PYTHONPATH}}"

python3 "${HOMEglobal}/dev/workflow/setup_expt.py" \
  gfs forecast-only \
  --app ATM \
  --resdetatmos 48 \
  --idate 2021032312 \
  --edate 2021032312 \
  --pslot "${PSLOT}" \
  --comroot "${COMROOT}" \
  --expdir "${RUNTESTS}/EXPDIR" \
  --overwrite

if [[ ! -f "${EXPDIR}/config.base" ]]; then
  echo "[ERROR] config.base not found in ${EXPDIR}."
  echo "  create_experiment.py may have failed."
  exit 1
fi
echo "  Experiment created in ${EXPDIR}."

# ── Step 2: Verify ecFlow server is reachable ──
echo "[2/5] Pinging ecFlow server..."
ecflow_client --ping
echo "  Server is alive."

# ── Step 3: Load the suite definition ──
echo "[3/5] Loading suite definition..."
mkdir -p "${ECF_HOME}/output"
ecflow_client --delete /C48_ATM_ursa 2> /dev/null || true
ecflow_client --load="${DEF_FILE}"
echo "  Suite C48_ATM_ursa loaded."

# ── Step 4: Apply runtime variable overrides ──
echo "[4/5] Applying Ursa overrides..."
SUITE="/C48_ATM_ursa"

# ecFlow server and file locations
ecflow_client --alter add variable ECF_HOME    "${ECF_HOME}"           "${SUITE}"
ecflow_client --alter add variable ECF_INCLUDE "${SCRIPT_DIR}/include" "${SUITE}"
ecflow_client --alter add variable ECF_FILES   "${SCRIPT_DIR}/scripts" "${SUITE}"
ecflow_client --alter add variable ECF_LOGHOST "${ECF_HOST}"           "${SUITE}"
ecflow_client --alter add variable ECF_PORT    "${ECF_PORT}"           "${SUITE}"

# Experiment paths and identity
ecflow_client --alter add variable HOMEglobal  "${HOMEglobal}"  "${SUITE}"
ecflow_client --alter add variable EXPDIR      "${EXPDIR}"      "${SUITE}"
ecflow_client --alter add variable COMROOT     "${COMROOT}"     "${SUITE}"
ecflow_client --alter add variable PSLOT       "${PSLOT}"       "${SUITE}"

# Slurm account and partition
ecflow_client --alter add variable ACCOUNT     "${HPC_ACCOUNT:-fv3-cpu}" "${SUITE}"
ecflow_client --alter add variable QUEUE       "${PARTITION_BATCH:-u1-service}" "${SUITE}"

# Variables consumed by J-Jobs (exported into the Slurm job environment)
ecflow_client --alter add variable DATAROOT    "${RUNTESTS}/RUNDIRS/${PSLOT}" "${SUITE}"

echo "  Variables set."

# ── Step 5: Begin the suite ──
if ${LOAD_ONLY}; then
  echo "[5/5] --load-only specified, suite NOT started."
  echo "  To begin: ecflow_client --begin=C48_ATM_ursa"
else
  echo "[5/5] Beginning suite..."
  ecflow_client --begin=C48_ATM_ursa
  echo "  Suite C48_ATM_ursa is running."
fi

echo ""
echo "=== Done ==="
echo "Monitor with: ecflow_client --get_state /C48_ATM_ursa"
echo "         or:  ecflow_ui  (if X11 available)"
