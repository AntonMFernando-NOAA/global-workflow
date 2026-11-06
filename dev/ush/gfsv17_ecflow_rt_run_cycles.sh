#!/usr/bin/env bash
#
# Stage the initial conditions and start the GFSv17 ecflow realtime suite, then follow
# a number of cycles.
#
# Steps:
#   1. Run gfsv17_ecflow_rt_stage_ics.sh (same -p/-c rules) to find the cycle whose
#      previous-cycle gdas/enkfgdas data exists and link that data into COMDIR.
#   2. Load and begin the suite in gfs_dev.def if it is not begun yet. When it is begun
#      here, also start the first cycle: force the cycle before it complete (which
#      satisfies the cross-cycle triggers) and resume the first cycle family.
#   3. From there the suite cycles by itself: when the jgdas_fcst task of a cycle ends,
#      tail.h gives the next cycle family its PDYCYC, requeues it and resumes it.
#   4. Wait until each of the NCYCLES cycles is complete (family complete with the PDYCYC
#      of that cycle), then suspend the suite. The cycles that already started by
#      then stay in the state they are in until the suite is resumed.
#
# Usage: gfsv17_ecflow_rt_run_cycles.sh [-p PDY -c CYC] [-n NCYCLES] [-d DEF]
#          [--comroot DIR] [--dataroot DIR] [--outputdir DIR] [--expdir DIR] [-h]
#   -p PDY          first cycle date (YYYYMMDD), requires -c
#   -c CYC          first cycle hour (00, 06, 12 or 18), requires -p
#   -n NCYCLES      number of cycles to wait for before suspending the suite (default 1)
#   -d DEF          suite definition to load (default EXPDIR/gfs_dev.def, which the setup
#                   script renders for the first cycle -p/-c; needs --expdir when -d is not given)
#   --comroot DIR   set COMROOT on /suite/primary; the stage script COMDIR becomes
#                   DIR/gfs/v17.0 unless COMDIR is already set
#   --dataroot DIR  set DATAROOT on /suite/primary
#   --outputdir DIR set OUTPUTDIR on /suite/primary
#   --expdir DIR    set EXPDIR on /suite/primary; the suite reads its ecf scripts and
#                   include files from DIR/ecf
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
DEF_FILE=""
SUITE=${SUITE:-gfs_v17_nco}
POLL_SECONDS=${POLL_SECONDS:-60}
ECFLOW_CLIENT=${ECFLOW_CLIENT:-ecflow_client}

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

# Wait until the cycle family is complete for the given PDYCYC
wait_for_cycle() {
  local family=$1 pdycyc=$2 state family_pdycyc warned=NO
  while true; do
    state=$(ecf --query state "${family}" 2> /dev/null)
    family_pdycyc=$(ecf --query variable "${family}:PDYCYC" 2> /dev/null)
    case "${state}" in
      complete)
        # The family stays complete from the day before until the previous cycle requeues it
        if [[ "${family_pdycyc}" == "${pdycyc}" ]]; then
          return 0
        fi
        ;;
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

if [[ -z "${DEF_FILE}" && -n "${expdir}" ]]; then
  DEF_FILE="${expdir}/gfs_dev.def"
fi
if [[ -z "${DEF_FILE}" ]]; then
  echo "ERROR: give -d DEF or --expdir DIR (DIR/gfs_dev.def is used)" >&2
  exit 2
fi
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
started=NO
if [[ -z "${state}" ]]; then
  echo "Loading ${DEF_FILE}"
  ecf --load="${DEF_FILE}" || exit 1
  state=$(suite_state)
fi
if [[ "${state}" == "unknown" ]]; then
  echo "Beginning /${SUITE}"
  ecf --begin="${SUITE}" || exit 1
  started=YES
fi

# Apply the directory options to the suite
for entry in "COMROOT:${comroot}" "DATAROOT:${dataroot}" "OUTPUTDIR:${outputdir}" "EXPDIR:${expdir}"; do
  if [[ -n "${entry#*:}" ]]; then
    ecf --alter=change variable "${entry%%:*}" "${entry#*:}" "/${SUITE}/primary" || exit 1
  fi
done

first_family="/${SUITE}/primary/${cyc}"
if [[ "${started}" == "YES" ]]; then
  def_pdycyc=$(ecf --query variable "${first_family}:PDYCYC" 2> /dev/null)
  if [[ "${def_pdycyc}" != "${pdy}${cyc}" ]]; then
    echo "ERROR: ${DEF_FILE} has PDYCYC ${def_pdycyc:-none} for cycle ${cyc}, not ${pdy}${cyc}; render it again with the setup script (-p ${pdy} -c ${cyc})" >&2
    exit 1
  fi
  echo "Starting cycle ${pdy}${cyc}"
  ecf --force=complete recursive "/${SUITE}/primary/${prev_cyc}" || exit 1
  ecf --resume="${first_family}" || exit 1
else
  echo "/${SUITE} is already begun; only waiting for the cycles"
fi

for ((n = 1; n <= ncycles; n++)); do
  family="/${SUITE}/primary/${cyc}"
  echo "Waiting for cycle ${n} of ${ncycles}: ${pdy}${cyc}"
  wait_for_cycle "${family}" "${pdy}${cyc}"
  echo "Cycle ${pdy}${cyc} is complete"
  stamp=$(next_cycle "${pdy}" "${cyc}") || exit 1
  pdy=${stamp:0:8}
  cyc=${stamp:8:2}
done

ecf --suspend="/${SUITE}" || exit 1
echo "Finished ${ncycles} cycle(s); /${SUITE} is suspended (ecflow_client --resume=/${SUITE} continues it)"
exit 0
