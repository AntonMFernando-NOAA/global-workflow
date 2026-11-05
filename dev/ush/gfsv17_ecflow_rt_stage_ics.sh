#!/usr/bin/env bash
#
# Pick the GFSv17 ecflow realtime cycle to start, verify that the previous-cycle
# gdas and enkfgdas data needed by the first gfs/gdas/enkfgdas jobs exist, and stage
# the links in COMDIR (see the "Set-up COM DIR" section of the T2O readme).
#
# Cycle selection:
#   1. If -p PDY and -c CYC are given, that cycle is tried first.
#   2. Otherwise the cycle is chosen from the current UTC time using the gfs
#      tropcy_qc start times in ecf/defs/gfs_prod.def (cycle 00 at 02:41, 06 at 08:41, 12 at 14:41, 18 at 20:41 UTC)
#      and PDY is read from the ops date file, as in ecf/include/head.h:
#        PDY=$(cut -c7-14 /lfs/h1/ops/prod/com/date/t${CYC}z)
#   3. If the previous cycle data is missing, step back one cycle at a time, at most
#      MAX_BACK times. If nothing is found, report that no files are available.
#
# Usage: gfsv17_ecflow_rt_stage_ics.sh [-p PDY -c CYC] [-k] [-h]
#   -p PDY  cycle date to run first (YYYYMMDD), requires -c
#   -c CYC  cycle hour to run first (00, 06, 12 or 18), requires -p
#   -k      check only, do not create links or copy syndat
#   -h      show this help
#
# Environment overrides:
#   DATE_DIR     ops date file directory (default /lfs/h1/ops/prod/com/date)
#   SRC_COMROOT  realtime comroot holding gdas.PDY/CC and enkfgdas.PDY/CC
#   COMDIR       target COM directory (default /lfs/h2/emc/ptmp/${USER}/gfs/ops/para/com/gfs/v17.0)
#   SYNDAT_SRC   operational syndat directory to copy if COMDIR has none
#   NMEM_ENS     number of ensemble members to look for (default 80)
#   MAX_BACK     number of earlier cycles to try (default 2)
#   NOW_UTC      time to use instead of now, for testing (any date -d string)

set -u

DATE_DIR=${DATE_DIR:-/lfs/h1/ops/prod/com/date}
SRC_COMROOT=${SRC_COMROOT:-/lfs/h2/emc/gfstemp/emc.global/comroot/retrov17_01_realtime}
COMDIR=${COMDIR:-/lfs/h2/emc/ptmp/${USER}/gfs/ops/para/com/gfs/v17.0}
SYNDAT_SRC=${SYNDAT_SRC:-/lfs/h1/ops/prod/com/gfs/v16.3/syndat}
NMEM_ENS=${NMEM_ENS:-80}
MAX_BACK=${MAX_BACK:-2}
NOW_UTC=${NOW_UTC:-now}

# HHMM (UTC) when the first gfs job of each cycle is triggered, in ascending order
CYCLE_STARTS=("0241:00" "0841:06" "1441:12" "2041:18")

usage() {
  sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# Set cyc to the latest cycle whose start time has passed (18 before the 00 start)
pick_cycle_from_clock() {
  local now entry
  now=$(date -u -d "${NOW_UTC}" +%H%M)
  cyc=18
  for entry in "${CYCLE_STARTS[@]}"; do
    if ((10#${now} >= 10#${entry%%:*})); then
      cyc=${entry##*:}
    fi
  done
}

# Set pdy from the ops date file for the given cycle
read_pdy_from_ops() {
  local cycle=$1
  local datefile="${DATE_DIR}/t${cycle}z"
  if [[ ! -r "${datefile}" ]]; then
    echo "ERROR: cannot read ${datefile}; use -p and -c to give the cycle" >&2
    return 1
  fi
  pdy=$(cut -c7-14 "${datefile}")
  if [[ ! "${pdy}" =~ ^[0-9]{8}$ ]]; then
    echo "ERROR: PDY '${pdy}' read from ${datefile} is not YYYYMMDD" >&2
    return 1
  fi
}

# Set pdy and cyc to the cycle 6 hours before the one given
previous_cycle() {
  local stamp
  # The explicit UTC keeps date from reading "-6" as a time zone offset
  stamp=$(date -u -d "${1} ${2}:00 UTC 6 hours ago" +%Y%m%d%H) || return 1
  pdy=${stamp:0:8}
  cyc=${stamp:8:2}
}

# Return 0 if the directory exists and has at least one entry
has_content() {
  [[ -n "$(find -H "${1}" -mindepth 1 -print -quit 2> /dev/null)" ]]
}

# Check the data the first jobs of cycle ${tpdy}${tcyc} read from the previous cycle
check_inputs() {
  local ppdy=$1 pcyc=$2
  local gdas="gdas.${ppdy}/${pcyc}"
  local enkf="enkfgdas.${ppdy}/${pcyc}"
  local rel missing=0
  local -a required=(
    "${gdas}/model/atmos/history"
    "${gdas}/model/atmos/restart"
    "${gdas}/model/ocean/restart"
    "${gdas}/model/ice/restart"
    "${enkf}/ensstat"
    "${enkf}/mem001/model/atmos/restart"
    "${enkf}/mem$(printf '%03d' "${NMEM_ENS}")/model/atmos/restart"
  )

  for rel in "${required[@]}"; do
    if ! has_content "${SRC_COMROOT}/${rel}"; then
      echo "    missing or empty: ${SRC_COMROOT}/${rel}"
      missing=$((missing + 1))
    fi
  done
  ((missing == 0))
}

link_cycle() {
  local run=$1 ppdy=$2 pcyc=$3
  local dest="${COMDIR}/${run}.${ppdy}/${pcyc}"
  mkdir -p "${COMDIR}/${run}.${ppdy}"
  if [[ -e "${dest}" && ! -L "${dest}" ]]; then
    echo "WARNING: ${dest} exists and is not a link; leaving it alone"
    return 0
  fi
  ln -sfn "${SRC_COMROOT}/${run}.${ppdy}/${pcyc}" "${dest}"
  echo "  linked ${dest}"
}

stage_inputs() {
  local ppdy=$1 pcyc=$2
  mkdir -p "${COMDIR}"
  link_cycle gdas "${ppdy}" "${pcyc}"
  link_cycle enkfgdas "${ppdy}" "${pcyc}"
  if [[ -d "${COMDIR}/syndat" ]]; then
    echo "  syndat already present in ${COMDIR}"
  elif [[ -d "${SYNDAT_SRC}" ]]; then
    cp -rf "${SYNDAT_SRC}" "${COMDIR}/"
    echo "  copied ${SYNDAT_SRC} to ${COMDIR}"
  else
    echo "WARNING: ${SYNDAT_SRC} not found; copy syndat to ${COMDIR} before running tropcy_qc"
  fi
}

check_only=NO
req_pdy=""
req_cyc=""
while getopts ":p:c:kh" opt; do
  case "${opt}" in
    p) req_pdy=${OPTARG} ;;
    c) req_cyc=${OPTARG} ;;
    k) check_only=YES ;;
    h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "${req_pdy}" || -n "${req_cyc}" ]]; then
  if [[ ! "${req_pdy}" =~ ^[0-9]{8}$ || ! "${req_cyc}" =~ ^(00|06|12|18)$ ]]; then
    echo "ERROR: -p needs YYYYMMDD and -c needs 00, 06, 12 or 18 (both are required)" >&2
    exit 2
  fi
  tpdy=${req_pdy}
  tcyc=${req_cyc}
  echo "Using requested cycle ${tpdy}${tcyc}"
else
  pick_cycle_from_clock
  tcyc=${cyc}
  read_pdy_from_ops "${tcyc}" || exit 1
  tpdy=${pdy}
  echo "Selected cycle ${tpdy}${tcyc} from the clock ($(date -u -d "${NOW_UTC}" '+%Y-%m-%d %H:%M') UTC)"
fi

found=NO
for ((attempt = 0; attempt <= MAX_BACK; attempt++)); do
  previous_cycle "${tpdy}" "${tcyc}" || exit 1
  ppdy=${pdy}
  pcyc=${cyc}
  echo "Trying to run ${tpdy}${tcyc}: needs previous cycle ${ppdy}${pcyc}"
  if check_inputs "${ppdy}" "${pcyc}"; then
    found=YES
    break
  fi
  tpdy=${ppdy}
  tcyc=${pcyc}
done

if [[ "${found}" != "YES" ]]; then
  echo "No files: initial conditions are missing for the last $((MAX_BACK + 1)) cycles under ${SRC_COMROOT}"
  exit 1
fi

echo "Initial conditions found for cycle ${tpdy}${tcyc} (previous cycle ${ppdy}${pcyc})"
if [[ "${check_only}" == "YES" ]]; then
  echo "Check only: nothing staged"
else
  stage_inputs "${ppdy}" "${pcyc}"
fi

echo "PDY=${tpdy}"
echo "CYC=${tcyc}"
echo "PREV_PDY=${ppdy}"
echo "PREV_CYC=${pcyc}"
echo "To start the cycle: ecflow_client --force=complete recursive /gfs_v17_nco/primary/${pcyc}"
echo "If this is not the current ops cycle, add edit PDY '${tpdy}' to the suite (head.h uses it)"
exit 0
