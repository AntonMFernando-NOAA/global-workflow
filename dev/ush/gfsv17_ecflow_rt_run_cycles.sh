#!/usr/bin/env bash
#
# Stage the initial conditions and run a number of GFSv17 ecflow realtime cycles
# one after another.
#
# Steps:
#   1. Run gfsv17_ecflow_rt_stage_ics.sh (same -p/-c rules) to find the cycle whose
#      previous-cycle gdas/enkfgdas data exists and link that data into COMDIR.
#   2. Load and begin the suite in gfs_dev.def if it is not begun yet. All cycle
#      families start suspended, so nothing runs at begin.
#   3. Force the previous cycle family complete, which satisfies the cross-cycle
#      triggers of the first cycle.
#   4. For each of the NCYCLES cycles: set PDY on the cycle family, requeue and
#      resume it, then wait for it to complete before starting the next one.
#      After cycle 18 the PDY moves to the next day, so 6 cycles from 06 are
#      06, 12, 18 on PDY and 00, 06, 12 on PDY+1.
#
# Usage: gfsv17_ecflow_rt_run_cycles.sh [-p PDY -c CYC] [-n NCYCLES] [-d DEF]
#          [--comroot DIR] [--dataroot DIR] [--outputdir DIR] [--expdir DIR] [-h]
#   -p PDY          first cycle date (YYYYMMDD), requires -c
#   -c CYC          first cycle hour (00, 06, 12 or 18), requires -p
#   -n NCYCLES      number of cycles to run (default 1)
#   -d DEF          suite definition to load (default ecf/gfs/defs/gfs_dev.def)
#   --comroot DIR   set COMROOT on /suite/primary; the stage script COMDIR becomes
#                   DIR/gfs/v17.0 unless COMDIR is already set
#   --dataroot DIR  set DATAROOT on /suite/primary
#   --outputdir DIR set OUTPUTDIR on /suite/primary
#   --expdir DIR    set EXPDIR on /suite/primary
#   -h              show this help
# Variables not given keep the values written in the suite definition.
#
# ECF_HOST and ECF_PORT must be set for ecflow_client. A run of many cycles takes
# many hours, so start it with nohup or in a terminal multiplexer.
#
# Environment overrides:
#   SUITE          suite name (default gfs_v17_nco)
#   POLL_SECONDS   seconds between completion checks (default 60)
#   ECFLOW_CLIENT  ecflow client command (default ecflow_client)

set -u

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STAGE_SCRIPT="${SCRIPT_DIR}/gfsv17_ecflow_rt_stage_ics.sh"
DEF_FILE="${SCRIPT_DIR}/../ecf/gfs/defs/gfs_dev.def"
SUITE=${SUITE:-gfs_v17_nco}
POLL_SECONDS=${POLL_SECONDS:-60}
ECFLOW_CLIENT=${ECFLOW_CLIENT:-ecflow_client}
CYCLES=(00 06 12 18)

usage() {
  sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# Print the date and hour (YYYYMMDDHH) 6 hours after the given date and hour
next_cycle() {
  date -u -d "${1} ${2}:00 UTC 6 hours" +%Y%m%d%H
}

ecf() {
  "${ECFLOW_CLIENT}" "$@"
}

suite_state() {
  ecf --query state "/${SUITE}" 2> /dev/null
}

# Wait until the cycle family is complete
wait_for_cycle() {
  local family=$1 state warned=NO
  while true; do
    state=$(ecf --query state "${family}" 2> /dev/null)
    case "${state}" in
      complete) return 0 ;;
      aborted)
        if [[ "${warned}" == "NO" ]]; then
          echo "  WARNING: a task in ${family} aborted; rerun it in ecflow and the cycle will continue"
          warned=YES
        fi
        ;;
      *) warned=NO ;;
    esac
    sleep "${POLL_SECONDS}"
  done
}

req_pdy=""
req_cyc=""
ncycles=1
comroot=""
dataroot=""
outputdir=""
expdir=""
while (($# > 0)); do
  case "$1" in
    -p | -c | -n | -d | --comroot | --dataroot | --outputdir | --expdir)
      if (($# < 2)); then
        echo "ERROR: $1 needs a value" >&2
        exit 2
      fi
      case "$1" in
        -p) req_pdy=$2 ;;
        -c) req_cyc=$2 ;;
        -n) ncycles=$2 ;;
        -d) DEF_FILE=$2 ;;
        --comroot) comroot=$2 ;;
        --dataroot) dataroot=$2 ;;
        --outputdir) outputdir=$2 ;;
        --expdir) expdir=$2 ;;
      esac
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "${ncycles}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: -n needs a positive integer" >&2
  exit 2
fi
if [[ -n "${req_pdy}" || -n "${req_cyc}" ]]; then
  if [[ ! "${req_pdy}" =~ ^[0-9]{8}$ || ! "${req_cyc}" =~ ^(00|06|12|18)$ ]]; then
    echo "ERROR: -p needs YYYYMMDD and -c needs 00, 06, 12 or 18 (both are required)" >&2
    exit 2
  fi
  stage_args=(-p "${req_pdy}" -c "${req_cyc}")
else
  stage_args=()
fi

if [[ -n "${comroot}" ]]; then
  export COMDIR=${COMDIR:-${comroot}/gfs/v17.0}
fi

stage_out=$("${STAGE_SCRIPT}" ${stage_args[@]+"${stage_args[@]}"})
stage_rc=$?
echo "${stage_out}"
if ((stage_rc != 0)); then
  exit "${stage_rc}"
fi
pdy=$(sed -n 's/^PDY=//p' <<< "${stage_out}")
cyc=$(sed -n 's/^CYC=//p' <<< "${stage_out}")
prev_cyc=$(sed -n 's/^PREV_CYC=//p' <<< "${stage_out}")

if ! ecf --ping > /dev/null 2>&1; then
  echo "ERROR: cannot reach the ecflow server; check ECF_HOST and ECF_PORT" >&2
  exit 1
fi

state=$(suite_state)
if [[ -z "${state}" ]]; then
  echo "Loading ${DEF_FILE}"
  ecf --load="${DEF_FILE}" || exit 1
  state=$(suite_state)
fi
if [[ "${state}" == "unknown" ]]; then
  echo "Beginning /${SUITE}"
  ecf --begin="${SUITE}" || exit 1
fi

# Apply the directory options to the suite
for entry in "COMROOT:${comroot}" "DATAROOT:${dataroot}" "OUTPUTDIR:${outputdir}" "EXPDIR:${expdir}"; do
  if [[ -n "${entry#*:}" ]]; then
    ecf --alter=change variable "${entry%%:*}" "${entry#*:}" "/${SUITE}/primary" || exit 1
  fi
done

# Keep every cycle from running until its turn
for family_cyc in "${CYCLES[@]}"; do
  ecf --suspend="/${SUITE}/primary/${family_cyc}" || exit 1
done
ecf --force=complete recursive "/${SUITE}/primary/${prev_cyc}" || exit 1

for ((n = 1; n <= ncycles; n++)); do
  family="/${SUITE}/primary/${cyc}"
  echo "Cycle ${n} of ${ncycles}: ${pdy}${cyc}"
  ecf --alter=change variable PDY "${pdy}" "${family}" || exit 1
  ecf --requeue "${family}" || exit 1
  ecf --resume="${family}" || exit 1
  wait_for_cycle "${family}"
  echo "Cycle ${pdy}${cyc} is complete"
  stamp=$(next_cycle "${pdy}" "${cyc}") || exit 1
  pdy=${stamp:0:8}
  cyc=${stamp:8:2}
done

echo "Finished ${ncycles} cycle(s)"
exit 0
