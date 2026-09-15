#!/bin/bash
# bootstrap_ursa.sh — Load and start the c96_s2sw ecFlow suite on Ursa
#
# Prerequisites:
#   1. ecFlow server running on uecflow01 (see ~/ecflow_ursa.env)
#   2. pbs_to_slurm.sh already run on c96/scripts/
#   3. Ursa-adapted head.h and envir-p1.h in c96/include/
#
# Usage (from a login node, after ssh to uecflow01 or with ECF_HOST set):
#   source ~/ecflow_ursa.env
#   bash dev/ecf/c96/bootstrap_ursa.sh [--load-only]
#
# Options:
#   --load-only   Load the suite definition but do not begin it.
#                 Useful for inspecting the suite in ecflow_ui first.

set -eu

# ── Resolve paths ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECF_DIR="${SCRIPT_DIR}"
DEF_FILE="${ECF_DIR}/defs/c96_s2sw.def"
HOMEgfs="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

SUITE_NAME="c96_s2sw"
LOAD_ONLY=false
if [[ "${1:-}" == "--load-only" ]]; then
  LOAD_ONLY=true
fi

# ── Validate environment ──
for var in ECF_HOST ECF_PORT ECF_HOME; do
  if [[ -z "${!var:-}" ]]; then
    echo "[ERROR] ${var} is not set. Source ~/ecflow_ursa.env first." >&2
    exit 1
  fi
done

echo "=== c96_s2sw bootstrap for Ursa ==="
echo "  ECF_HOST:  ${ECF_HOST}"
echo "  ECF_PORT:  ${ECF_PORT}"
echo "  ECF_HOME:  ${ECF_HOME}"
echo "  HOMEgfs:   ${HOMEgfs}"
echo "  DEF_FILE:  ${DEF_FILE}"
echo ""

# ── Verify server is reachable ──
if ! ecflow_client --ping 2> /dev/null; then
  echo "[ERROR] Cannot reach ecFlow server at ${ECF_HOST}:${ECF_PORT}" >&2
  exit 1
fi
echo "[OK] ecFlow server is reachable."

# ── Create output directories ──
OUTPUTDIR="/scratch3/NCEPDEV/global/noscrub/${USER}/ecflow_c96/output"
mkdir -p "${OUTPUTDIR}"
mkdir -p "${ECF_HOME}/output"
echo "[OK] Output directories created."

# ── Set up ECF_FILES symlink so ecFlow finds the .ecf scripts ──
# The .def references %PACKAGEHOME%/ecf/scripts which resolves to
# ${HOMEgfs}/ecf/scripts. Create that path pointing to c96/scripts.
ECF_SCRIPTS_LINK="${HOMEgfs}/ecf/scripts"
if [[ ! -e "${ECF_SCRIPTS_LINK}" ]]; then
  mkdir -p "$(dirname "${ECF_SCRIPTS_LINK}")"
  ln -sfn "${ECF_DIR}/scripts" "${ECF_SCRIPTS_LINK}"
  echo "[OK] Symlinked ecf/scripts -> c96/scripts"
elif [[ -L "${ECF_SCRIPTS_LINK}" ]]; then
  echo "[OK] ecf/scripts symlink already exists: $(readlink "${ECF_SCRIPTS_LINK}")"
else
  echo "[WARN] ${ECF_SCRIPTS_LINK} exists but is not a symlink. .ecf resolution may fail."
fi

# ── Set up ECF_INCLUDE symlink for head.h, envir-p1.h, tail.h ──
ECF_INCLUDE_LINK="${HOMEgfs}/ecf/include"
if [[ ! -e "${ECF_INCLUDE_LINK}" ]]; then
  ln -sfn "${ECF_DIR}/include" "${ECF_INCLUDE_LINK}"
  echo "[OK] Symlinked ecf/include -> c96/include"
elif [[ -L "${ECF_INCLUDE_LINK}" ]]; then
  echo "[OK] ecf/include symlink already exists: $(readlink "${ECF_INCLUDE_LINK}")"
else
  echo "[WARN] ${ECF_INCLUDE_LINK} exists but is not a symlink."
fi

# ── Delete suite if it already exists (re-run safe) ──
if ecflow_client --get_state "/${SUITE_NAME}" 2> /dev/null | grep -q "suite"; then
  echo "  Suite /${SUITE_NAME} already loaded. Deleting for reload..."
  ecflow_client --delete "/${SUITE_NAME}" force
fi

# ── Load the suite definition ──
echo "  Loading ${DEF_FILE}..."
ecflow_client --load="${DEF_FILE}"
echo "[OK] Suite loaded."

# ── Override variables via ecflow_client --alter ──
S="/${SUITE_NAME}"

# User and ecFlow server
ecflow_client --alter add variable EMC_USER "${USER}" "${S}"
ecflow_client --alter add variable ECF_LOGHOST "${ECF_HOST}" "${S}"
ecflow_client --alter add variable ECF_PORT "${ECF_PORT}" "${S}"
ecflow_client --alter add variable ECF_HOME "${ECF_HOME}" "${S}"
ecflow_client --alter add variable ECF_INCLUDE "${ECF_DIR}/include" "${S}"
ecflow_client --alter add variable ecflow_ver "5.11.4" "${S}"

# Slurm job commands (replaces PBS qsub/qdel/qstat)
ecflow_client --alter add variable ECF_JOB_CMD "sbatch %ECF_JOB% 2>&1" "${S}"
ecflow_client --alter add variable ECF_KILL_CMD "scancel %ECF_RID%" "${S}"
ecflow_client --alter add variable ECF_STATUS_CMD "squeue -j %ECF_RID%" "${S}"

# WCOSS2 → Ursa path overrides
ecflow_client --alter add variable PACKAGEHOME "${HOMEgfs}" "${S}"
ecflow_client --alter add variable OUTPUTDIR "${OUTPUTDIR}" "${S}"
ecflow_client --alter add variable EXPDIR "${HOMEgfs}/parm/config/gfs" "${S}"
ecflow_client --alter add variable DATAROOT "/scratch3/NCEPDEV/stmp1/${USER}/ecflow_c96/dataroot" "${S}"
ecflow_client --alter add variable COMROOT "/scratch3/NCEPDEV/global/noscrub/${USER}/ecflow_c96/com" "${S}"
ecflow_client --alter add variable MACHINE_SITE "ursa" "${S}"

# Ursa Slurm queue names (replace WCOSS2 PBS queues)
ecflow_client --alter add variable QUEUE "batch" "${S}"
ecflow_client --alter add variable QUEUE_ARCH "batch" "${S}"

# Slurm account (Ursa uses project names, not PROJ-PROJENVIR)
ecflow_client --alter add variable PROJ "global" "${S}"
ecflow_client --alter add variable PROJENVIR "DEV" "${S}"

# PDY: set to today's date (YYYYMMDD) for initial testing
PDY=$(date +%Y%m%d)
ecflow_client --alter add variable PDY "${PDY}" "${S}"

echo "[OK] Suite variables set for Ursa/Slurm."
echo "  PACKAGEHOME: ${HOMEgfs}"
echo "  OUTPUTDIR:   ${OUTPUTDIR}"
echo "  EXPDIR:      ${HOMEgfs}/parm/config/gfs"
echo "  QUEUE:       batch"
echo "  PDY:         ${PDY}"

# ── Optionally begin the suite ──
if ${LOAD_ONLY}; then
  echo ""
  echo "Suite loaded but NOT started (--load-only)."
  echo "Inspect in ecflow_ui, then run:"
  echo "  ecflow_client --begin=${SUITE_NAME}"
else
  ecflow_client --begin="${SUITE_NAME}"
  echo "[OK] Suite ${SUITE_NAME} started."
fi

echo ""
echo "=== Monitor ==="
echo "  ecflow_client --get_state /${SUITE_NAME}"
echo "  ecflow_ui  (with X11 forwarding via PuTTY)"
