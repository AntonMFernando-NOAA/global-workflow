#!/usr/bin/env bash
#
# Load and start the GFSv17 ecflow realtime suite rendered by gfsv17_ecflow_rt_setup_expt.sh.
#
# Steps:
#   1. Load the suite in gfs_dev.def on the ecflow server. If a suite of the same name is
#      already there it is kept, and DEF is not loaded, unless --replace deletes it first.
#   2. Begin the suite if it is not begun yet. The definition has one suspended family per
#      cycle, named by its PDYCYC (e.g. 2026110612).
#   3. Resume the family of the first cycle. From there the suite runs by itself: when the
#      jgdas_fcst task of a cycle ends, tail.h resumes the family of the next cycle, and
#      the last family has no next cycle, so the suite stops after the cycles of DEF.
#
# Usage: gfsv17_ecflow_rt_run_cycles.sh -p PDY -c CYC [-d DEF | --expdir DIR] [--suite NAME]
#          [--replace] [-h]
#   -p PDY          first cycle date (YYYYMMDD)
#   -c CYC          first cycle hour (00, 06, 12 or 18)
#   -d DEF          suite definition to load (default EXPDIR/gfs_dev.def)
#   --expdir DIR    experiment directory with gfs_dev.def, used when -d is not given
#   --suite NAME    suite name in DEF (default the SUITE environment variable, then gfs_v17_nco)
#   --replace       if the suite is already on the server, delete it (also its running
#                   tasks) and load DEF; without it the suite on the server is kept and
#                   DEF is not loaded
#   -h              show this help
#
# ECF_HOST and ECF_PORT must be set for ecflow_client.
#
# Environment overrides:
#   SUITE          suite name (default gfs_v17_nco); --suite overrides it
#   ECFLOW_CLIENT  ecflow client command (default ecflow_client)

set -u

DEF_FILE=""
SUITE=${SUITE:-gfs_v17_nco}
ECFLOW_CLIENT=${ECFLOW_CLIENT:-ecflow_client}

usage() {
  sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

ecf() {
  "${ECFLOW_CLIENT}" "$@"
}

suite_state() {
  ecf --query state "/${SUITE}" 2> /dev/null
}

req_pdy=""
req_cyc=""
expdir=""
replace=NO
while (($# > 0)); do
  case "$1" in
    --replace)
      replace=YES
      shift
      ;;
    -p | -c | -d | --suite | --expdir)
      if (($# < 2)); then
        echo "ERROR: $1 needs a value" >&2
        exit 2
      fi
      case "$1" in
        -p) req_pdy=$2 ;;
        -c) req_cyc=$2 ;;
        -d) DEF_FILE=$2 ;;
        --suite) SUITE=$2 ;;
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
if [[ ! "${req_pdy}" =~ ^[0-9]{8}$ || ! "${req_cyc}" =~ ^(00|06|12|18)$ ]]; then
  echo "ERROR: -p needs YYYYMMDD and -c needs 00, 06, 12 or 18" >&2
  exit 2
fi

if ! ecf --ping > /dev/null 2>&1; then
  echo "ERROR: cannot reach the ecflow server; check ECF_HOST and ECF_PORT" >&2
  exit 1
fi

state=$(suite_state)
started=NO
if [[ -n "${state}" && "${replace}" == "YES" ]]; then
  echo "Deleting /${SUITE} from the server (--replace)"
  ecf --delete=force yes "/${SUITE}" || exit 1
  state=""
elif [[ -n "${state}" ]]; then
  echo "WARNING: /${SUITE} is already on the server, so ${DEF_FILE} is not loaded and its changes are not seen;"
  echo "         use --replace to delete the suite and load ${DEF_FILE}"
fi
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

first_family="/${SUITE}/primary/${req_pdy}${req_cyc}"
if [[ -z "$(ecf --query state "${first_family}" 2> /dev/null)" ]]; then
  echo "ERROR: /${SUITE} has no family ${req_pdy}${req_cyc}; render the definition again with the setup script (-p ${req_pdy} -c ${req_cyc}) and use --replace" >&2
  exit 1
fi

if [[ "${started}" == "YES" ]]; then
  echo "Starting cycle ${req_pdy}${req_cyc}"
  ecf --resume="${first_family}" || exit 1
else
  echo "/${SUITE} is already begun; cycle ${req_pdy}${req_cyc} was not resumed"
fi
exit 0
