#!/bin/bash
# run_stage_ic.sh — Bootstrap and run stage_ic on Ursa
#
# Sets up a minimal C48 ATM GFS forecast-only experiment, then runs
# the stage_ic job via the Rocoto job card.  Designed to be run
# interactively on an Ursa login node (ufe01–ufe16).
#
# Prerequisites:
#   - Ursa login node (MACHINE_ID=ursa detected automatically)
#   - HPC_ACCOUNT env var set (e.g. export HPC_ACCOUNT=global)
#   - ICs available at /scratch3/NCEPDEV/global/role.glopara/data/ICSDIR
#
# Usage:
#   bash dev/ecf/ursa/run_stage_ic.sh

set -eux

# ── User-configurable settings ──
PSLOT="${PSLOT:-ecflow_test}"
IDATE="${IDATE:-2021032312}"
RES="${RES:-48}"
APP="${APP:-ATM}"
HPC_ACCOUNT="${HPC_ACCOUNT:-global}"

# ── Derived paths ──
HOMEglobal="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../../.. && pwd)"
export HOMEglobal
COMROOT="/scratch4/NCEPDEV/stmp/${USER}/COMROOT"
EXPDIR="/scratch3/NCEPDEV/global/${USER}/expdir"

echo "============================================"
echo "  stage_ic bootstrap for Ursa"
echo "============================================"
echo "  HOMEglobal: ${HOMEglobal}"
echo "  PSLOT:      ${PSLOT}"
echo "  IDATE:      ${IDATE}"
echo "  RES:        C${RES}"
echo "  APP:        ${APP}"
echo "  COMROOT:    ${COMROOT}"
echo "  EXPDIR:     ${EXPDIR}"
echo "============================================"

# ── Step 1: Set up the experiment ──
echo ""
echo ">>> Step 1: Setting up experiment via setup_expt.py"

export HPC_ACCOUNT

# Ensure wxflow is on PYTHONPATH for setup_expt.py
PYTHONPATH="${HOMEglobal}/sorc/wxflow/src${PYTHONPATH:+:${PYTHONPATH}}"
PYTHONPATH="${PYTHONPATH}:${HOMEglobal}/ush/python"
PYTHONPATH="${PYTHONPATH}:${HOMEglobal}/dev/workflow"
export PYTHONPATH

python3 "${HOMEglobal}/dev/workflow/setup_expt.py" \
  gfs forecast-only \
  --pslot "${PSLOT}" \
  --resdetatmos "${RES}" \
  --idate "${IDATE}" \
  --app "${APP}" \
  --comroot "${COMROOT}" \
  --expdir "${EXPDIR}" \
  --overwrite

EXPDIR_FULL="${EXPDIR}/${PSLOT}"
ROTDIR="${COMROOT}/${PSLOT}"

echo "  EXPDIR_FULL: ${EXPDIR_FULL}"
echo "  ROTDIR:      ${ROTDIR}"

# Verify config files were created
if [[ ! -f "${EXPDIR_FULL}/config.base" ]]; then
  echo "FATAL: config.base not found in ${EXPDIR_FULL}"
  echo "  setup_expt.py may have failed to render templates."
  exit 1
fi

# ── Step 2: Set environment variables for the job ──
echo ""
echo ">>> Step 2: Setting environment for stage_ic"

# Extract PDY and cyc from IDATE (YYYYMMDDHH)
export PDY="${IDATE:0:8}"
export cyc="${IDATE:8:2}"

# Core variables expected by jjob_header.sh
export EXPDIR="${EXPDIR_FULL}"
export DATAROOT="/scratch4/NCEPDEV/stmp/${USER}/RUNDIRS/${PSLOT}"
export ROTDIR
export machine="URSA"
export NET="gfs"
export RUN="gfs"
export CDUMP="gfs"

# Job identity
export job="stage_ic"
export jobid="${job}.$$"

# Ensure DATAROOT exists
mkdir -p "${DATAROOT}"

# ── Step 3: Run stage_ic via the Rocoto job card ──
echo ""
echo ">>> Step 3: Running stage_ic"
echo "  PDY=${PDY}  cyc=${cyc}"
echo "  DATAROOT=${DATAROOT}"
echo "  EXPDIR=${EXPDIR}"

"${HOMEglobal}/dev/job_cards/rocoto/stage_ic.sh"
rc=$?

echo ""
if [[ ${rc} -eq 0 ]]; then
  echo "============================================"
  echo "  stage_ic completed successfully (rc=0)"
  echo "============================================"
  echo ""
  echo "  Staged ICs should be in: ${ROTDIR}"
  echo "  Check: ls -la ${ROTDIR}/gfs.${PDY}/${cyc}/"
else
  echo "============================================"
  echo "  stage_ic FAILED (rc=${rc})"
  echo "============================================"
  echo ""
  echo "  Check logs in: ${DATAROOT}/${jobid}/"
fi

exit ${rc}
