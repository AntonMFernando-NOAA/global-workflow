#!/bin/bash
# bootstrap_ursa.sh — Load and begin the C48_ATM ecFlow suite on Ursa
#
# Prerequisites:
#   1. ecFlow server running on uecflow01 (see ~/ecflow_ursa.env)
#   2. Experiment created via setup_expt.py (EXPDIR populated with config files)
#   3. Initial conditions staged or ICSDIR set
#
# Usage:
#   source ~/ecflow_ursa.env   # sets ECF_HOST, ECF_PORT, ECF_HOME, HOMEgfs
#   cd $HOMEgfs/dev/ecf/ursa
#   bash bootstrap_ursa.sh [--load-only]
#
# With --load-only, loads the .def but does not begin the suite.

set -eu

# ── Validate environment ──
for var in ECF_HOST ECF_PORT ECF_HOME HOMEgfs; do
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

# ── Ensure output directory exists ──
mkdir -p "${ECF_HOME}/output"

echo "=== ecFlow C48_ATM suite bootstrap (Ursa) ==="
echo "  ECF_HOST:    ${ECF_HOST}"
echo "  ECF_PORT:    ${ECF_PORT}"
echo "  ECF_HOME:    ${ECF_HOME}"
echo "  HOMEgfs:     ${HOMEgfs}"
echo "  DEF_FILE:    ${DEF_FILE}"
echo ""

# ── Verify server is reachable ──
echo "[1/4] Pinging ecFlow server..."
ecflow_client --ping
echo "  Server is alive."

# ── Override edit variables for Ursa paths ──
# These are written into the .def via ecflow_client --alter after loading.
# Adjust EXPDIR, COMROOT, PSLOT, ICSDIR to match your experiment.
PSLOT="${PSLOT:-C48_ATM_ecflow}"
EXPDIR="${EXPDIR:-${HOMEgfs}/RUNTESTS/EXPDIR/${PSLOT}}"
COMROOT="${COMROOT:-${HOMEgfs}/RUNTESTS/COMROOT}"

# ── Load the suite definition ──
echo "[2/4] Loading suite definition..."
# Delete any existing suite of the same name before loading
ecflow_client --delete /C48_ATM_ursa 2> /dev/null || true
ecflow_client --load="${DEF_FILE}"
echo "  Suite C48_ATM_ursa loaded."

# ── Apply runtime variable overrides ──
echo "[3/4] Applying Ursa overrides..."
SUITE="/C48_ATM_ursa"

ecflow_client --alter add variable ECF_HOME    "${ECF_HOME}"    "${SUITE}"
ecflow_client --alter add variable ECF_INCLUDE "${SCRIPT_DIR}/include" "${SUITE}"
ecflow_client --alter add variable ECF_FILES   "${SCRIPT_DIR}/scripts" "${SUITE}"
ecflow_client --alter add variable ECF_LOGHOST "${ECF_HOST}"    "${SUITE}"
ecflow_client --alter add variable ECF_PORT    "${ECF_PORT}"    "${SUITE}"
ecflow_client --alter add variable HOMEglobal  "${HOMEgfs}"     "${SUITE}"
ecflow_client --alter add variable EXPDIR      "${EXPDIR}"      "${SUITE}"
ecflow_client --alter add variable COMROOT     "${COMROOT}"     "${SUITE}"
ecflow_client --alter add variable PSLOT       "${PSLOT}"       "${SUITE}"
ecflow_client --alter add variable ACCOUNT     "${HPC_ACCOUNT:-fv3-cpu}" "${SUITE}"
ecflow_client --alter add variable QUEUE        "${PARTITION_BATCH:-service}" "${SUITE}"

echo "  Variables set."

# ── Begin the suite ──
if ${LOAD_ONLY}; then
  echo "[4/4] --load-only specified, suite NOT started."
  echo "  To begin: ecflow_client --begin=C48_ATM_ursa"
else
  echo "[4/4] Beginning suite..."
  ecflow_client --begin=C48_ATM_ursa
  echo "  Suite C48_ATM_ursa is running."
fi

echo ""
echo "=== Done ==="
echo "Monitor with: ecflow_client --get_state /C48_ATM_ursa"
echo "         or:  ecflow_ui  (if X11 available)"
