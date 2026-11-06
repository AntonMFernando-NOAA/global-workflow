#!/usr/bin/env bash
#
# Set up a GFSv17 ecflow realtime experiment and optionally run its cycles.
#
# Steps:
#   1. With --ecf-server-setup: (re)start the ecflow server on ECF_HOST over ssh
#      (first time use, or when the role account server needs a restart).
#   2. Create COMROOT, DATAROOT and OUTPUTDIR.
#   3. Create the high resolution experiment (C1152 atmosphere, 0.25 degree ocean,
#      80 members, the retrov17_realtime.yaml configuration) in --expdir with
#      dev/workflow/setup_expt.py, starting at the first cycle (-p, -c). COMROOT
#      and EXPDIR in its config.base are the ones given here. With --expdir-src a
#      rendered EXPDIR is copied to --expdir instead. An existing --expdir is never
#      overwritten, so your edits are kept.
#   4. Copy dev/ecf/gfs/scripts and dev/ecf/gfs/include to <expdir>/ecf and run
#      setup_ecf_links.sh there, so the per forecast hour .ecf files are created
#      outside the repository. The rendered definition reads ECF_FILES and ECF_INCLUDE from
#      %EXPDIR%/ecf. An existing <expdir>/ecf is never overwritten; remove it to
#      regenerate. The cycle_end.ecf script from dev/ecf/common/scripts is added to it.
#   5. Render the suite definition from dev/ecf/gfs/defs/gfs_prod.def into
#      <expdir>/gfs_dev.def (gfsv17_ecflow_rt_render_def.py), with the directories
#      above. The definition has the four cycle families 00, 06, 12 and 18, each with
#      its cycle_end task and an edited PDY, as in production: cycle_end resets each
#      family for the next day and moves its PDY forward. It is rendered again on every run.
#   6. Unless --setup-only is given, run gfsv17_ecflow_rt_run_cycles.sh, which runs
#      gfsv17_ecflow_rt_stage_ics.sh (links gdas/enkfgdas into <comroot>/gfs/v17.0 and
#      copies syndat) and then the requested cycles. With --setup-only and -p/-c, the
#      stage script is run here and no cycle is started.
#
# Usage: gfsv17_ecflow_rt_setup_expt.sh [--build-link] [--comroot DIR] [--dataroot DIR]
#          [--outputdir DIR] [--expdir DIR] [--expdir-src DIR] [--icsdir DIR] [-p PDY -c CYC] [-n NCYCLES]
#          [--setup-only] [--ecf-server-setup] [--ecf-role] [--ecf-host HOST]
#          [--ecf-port PORT] [--ecf-users USER[,USER...]] [-h]
#   --build-link       first run "sorc/build_all.sh gfs gdas gsi" and "sorc/link_workflow.sh"
#   --comroot DIR      COMROOT (default /lfs/h2/emc/stmp/${USER}/RUNTESTS/COMROOT)
#   --dataroot DIR     DATAROOT (default /lfs/h2/emc/stmp/${USER}/RUNTESTS/RUNDIR)
#   --outputdir DIR    OUTPUTDIR (default /lfs/h2/emc/stmp/${USER}/RUNTESTS/OUTPUT)
#   --expdir DIR       experiment directory to create; its name is the pslot
#                      (default /lfs/h2/emc/stmp/${USER}/RUNTESTS/EXPDIR/rt17_ecflow_highres)
#   --expdir-src DIR   copy this already rendered EXPDIR (or the one pslot directory in it)
#                      to --expdir instead of creating the experiment
#   --icsdir DIR       ICSDIR given to setup_expt.py (default /lfs/h2/emc/gfstemp/emc.global/comroot/rt17_upd03_realtime)
#   -p PDY -c CYC      first cycle (required); also the start date of the experiment that is
#                      created, and the first cycle the suite starts
#   -n NCYCLES         number of cycles the run script waits for before it suspends the suite (default 1)
#   --setup-only       create the directories and EXPDIR, do not run any cycle
#   --ecf-server-setup run the ecflow server steps on ECF_HOST first
#   --ecf-role         use the role account ECF_ROOT instead of ${HOME}/ecflow
#   --ecf-host HOST    ecflow server host (default ECF_HOST, e.g. cdecflow02 or ddecflow02)
#   --ecf-port PORT    ecflow server port (default id -u + 2000)
#   --ecf-users LIST   users to add to the server access list after the restart
#   -h                 show this help
#
# Run it after loading the workflow environment (source dev/ush/gw_setup.sh) so that
# setup_expt.py finds wxflow.
#
# Environment overrides:
#   ECF_ROOT_ROLE  role account ecflow root (default /lfs/h2/emc/global/noscrub/emc.global/ecflow)
#   EDATE          end date of the created experiment (default 2027011600)

set -u

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RUN_SCRIPT="${SCRIPT_DIR}/gfsv17_ecflow_rt_run_cycles.sh"
STAGE_SCRIPT="${SCRIPT_DIR}/gfsv17_ecflow_rt_stage_ics.sh"
HOMEgfs=$(cd "${SCRIPT_DIR}/../.." && pwd)
ECF_ROOT_ROLE=${ECF_ROOT_ROLE:-/lfs/h2/emc/global/noscrub/emc.global/ecflow}
EDATE=${EDATE:-2027011600}
ICSDIR_DEFAULT=/lfs/h2/emc/gfstemp/emc.global/comroot/rt17_upd03_realtime
RUNTESTS="/lfs/h2/emc/stmp/${USER}/RUNTESTS"

comroot="${RUNTESTS}/COMROOT"
dataroot="${RUNTESTS}/RUNDIR"
outputdir="${RUNTESTS}/OUTPUT"
expdir="${RUNTESTS}/EXPDIR/rt17_ecflow_highres"
expdir_src=""
icsdir="${ICSDIR_DEFAULT}"
pdy=""
run_args=()
first_cycle=""
ncycles=1
setup_only=NO
build_link=NO
server_setup=NO
ecf_role=NO
ecf_host=${ECF_HOST:-}
ecf_port=""
ecf_users=""

usage() {
  sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# Run the ecflow server steps on the server host
setup_ecflow_server() {
  local ecf_root=${HOME}/ecflow
  if [[ "${ecf_role}" == "YES" ]]; then
    ecf_root=${ECF_ROOT_ROLE}
  fi
  if [[ -z "${ecf_host}" ]]; then
    echo "ERROR: --ecf-server-setup needs --ecf-host or ECF_HOST" >&2
    return 1
  fi
  : "${ecf_port:=$(($(id -u) + 2000))}"
  echo "Setting up the ecflow server on ${ecf_host} port ${ecf_port} with ECF_ROOT ${ecf_root}"

  ssh "${ecf_host}" env \
    "ECF_ROOT=${ecf_root}" "ECF_HOST=${ecf_host}" "ECF_PORT=${ecf_port}" "ECF_USERS=${ecf_users}" \
    bash -l -s << 'EOF'
set -eu
module load ecflow
export ECF_LISTS="${ECF_ROOT}/submit/submit/${ECF_HOST}.${ECF_PORT}.ecf.lists"
export ECF_OUTPUTDIR="${ECF_ROOT}/output"
export LFS_OUTPUTDIR="${ECF_ROOT}/submit"
export ECF_COMDIR="${ECF_ROOT}/com"
mkdir -p "${ECF_OUTPUTDIR}" "${LFS_OUTPUTDIR}" "${ECF_COMDIR}"

# Do not use ecflow_start.sh; it starts the server on the wrong port
server_check.sh "${ECF_ROOT}"
ecflow_client --restart

# server_check.sh overwrites the access list, so add the users again and reload it
if [[ -n "${ECF_USERS}" ]]; then
  mkdir -p "$(dirname "${ECF_LISTS}")"
  touch "${ECF_LISTS}"
  for user in ${ECF_USERS//,/ }; do
    grep -qx "${user}" "${ECF_LISTS}" || echo "${user}" >> "${ECF_LISTS}"
  done
  ecflow_client --reloadwsfile
fi
EOF
}

# Build all executables and link them
build_and_link() {
  (
    cd "${HOMEgfs}/sorc" || exit 1
    ./build_all.sh gfs gdas gsi || exit 1
    ./link_workflow.sh || exit 1
  )
}

# Copy the ecf scripts and include files to the EXPDIR and create the per forecast hour files there
setup_ecf_scripts() {
  local ecf_dir=${expdir}/ecf
  local cycle_end=${HOMEgfs}/dev/ecf/common/scripts/cycle_end.ecf
  if [[ -d "${ecf_dir}/scripts" && -d "${ecf_dir}/include" ]]; then
    echo "${ecf_dir} already exists; not overwritten"
    [[ -e "${ecf_dir}/scripts/cycle_end.ecf" ]] || cp "${cycle_end}" "${ecf_dir}/scripts/" || return 1
    return 0
  fi
  rm -rf "${ecf_dir}"
  mkdir -p "${ecf_dir}" || return 1
  cp -a "${HOMEgfs}/dev/ecf/gfs/scripts" "${HOMEgfs}/dev/ecf/gfs/include" "${ecf_dir}/" || return 1
  cp "${cycle_end}" "${ecf_dir}/scripts/" || return 1
  if ! (cd "${ecf_dir}" && bash "${HOMEgfs}/dev/ecf/gfs/setup_ecf_links.sh") > "${ecf_dir}/setup_ecf_links.log" 2>&1; then
    echo "ERROR: setup_ecf_links.sh failed; see ${ecf_dir}/setup_ecf_links.log" >&2
    tail -n 20 "${ecf_dir}/setup_ecf_links.log" >&2
    rm -rf "${ecf_dir}"
    return 1
  fi
  echo "Created ${ecf_dir}"
}

# Print the commands that start the cases once the setup is done
print_start_instructions() {
  local suite=gfs_v17_nco
  local fam="/${suite}/primary/${first_cycle}"
  local prev
  prev=$(printf '%02d' $(((10#${first_cycle} + 18) % 24)))
  cat << EOF

To start the case by hand (the ecflow server must be running):
  module load ecflow
  export ECF_HOST=${ecf_host:-<ecflow server host>}
  export ECF_PORT=${ecf_port:-$(($(id -u) + 2000))}
  ecflow_client --restart                       # only if the server is halted
  ecflow_client --load=${expdir}/gfs_dev.def
  ecflow_client --begin=${suite}                # the first cycle family (${first_cycle}) starts suspended
  ecflow_client --force=complete recursive /${suite}/primary/${prev}   # the cycle before the first one
  ecflow_client --force=complete ${fam}/cycle_end
  ecflow_client --resume=${fam}                 # runs cycle ${pdy}${first_cycle}
Check it with: ecflow_client --query state ${fam}   (or ecflow_ui)
After that the suite cycles by itself: the cycle_end task of each family resets it for the
next day and moves its PDY forward. To stop it: ecflow_client --suspend=/${suite}

To let a script do all of this, wait for ${ncycles} cycle(s) and suspend the suite:
  nohup ${RUN_SCRIPT} ${run_args[*]-} \\
    --comroot ${comroot} --dataroot ${dataroot} --outputdir ${outputdir} --expdir ${expdir} \\
    -d ${expdir}/gfs_dev.def > ${expdir}/run_cycles.log 2>&1 &
  tail -f ${expdir}/run_cycles.log
EOF
}

# Create the high resolution experiment in ${expdir} unless it already exists
create_expdir() {
  if [[ -f "${expdir}/config.base" ]]; then
    echo "EXPDIR ${expdir} already exists; not overwritten"
    return 0
  fi
  if [[ -z "${pdy}" || -z "${first_cycle}" ]]; then
    echo "ERROR: give -p PDY -c CYC (the experiment start) or --expdir-src DIR" >&2
    return 1
  fi
  mkdir -p "$(dirname "${expdir}")" || return 1
  PYTHONPATH="${HOMEgfs}/sorc/wxflow/src${PYTHONPATH:+:${PYTHONPATH}}" \
    "${HOMEgfs}/dev/workflow/setup_expt.py" gfs cycled \
    --pslot "$(basename "${expdir}")" --app S2SW \
    --resdetatmos 1152 --resensatmos 384 --resdetocean 0.25 --nens 80 \
    --interval 6 --start warm \
    --comroot "${comroot}" --expdir "$(dirname "${expdir}")" \
    --idate "${pdy}${first_cycle}" --edate "${EDATE}" --icsdir "${icsdir}" \
    --yaml "${HOMEgfs}/dev/ci/cases/gfsv17/s2sw_realtime.yaml" || return 1
  if [[ ! -f "${expdir}/config.base" ]]; then
    echo "ERROR: setup_expt.py did not create ${expdir}/config.base" >&2
    return 1
  fi
  echo "Created ${expdir}"
}

# Copy the rendered EXPDIR unless the destination already has one
copy_expdir() {
  local src=${expdir_src} sub
  if [[ ! -f "${src}/config.base" ]]; then
    # setup_expt.py puts the configs in EXPDIR/<pslot>; accept a single pslot directory
    for sub in "${src}"/*/; do
      if [[ -f "${sub}config.base" ]]; then
        src=${sub%/}
        break
      fi
    done
  fi
  if [[ ! -f "${src}/config.base" ]]; then
    echo "ERROR: no config.base found in ${expdir_src}; give a rendered EXPDIR with --expdir-src" >&2
    return 1
  fi
  if [[ -f "${expdir}/config.base" ]]; then
    echo "EXPDIR ${expdir} already exists; not overwritten"
    return 0
  fi
  mkdir -p "${expdir}" || return 1
  cp -r "${src}/." "${expdir}/" || return 1
  echo "Copied ${src} to ${expdir}"
}

while (($# > 0)); do
  case "$1" in
    --setup-only)
      setup_only=YES
      shift
      ;;
    --build-link)
      build_link=YES
      shift
      ;;
    --ecf-server-setup)
      server_setup=YES
      shift
      ;;
    --ecf-role)
      ecf_role=YES
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --comroot | --dataroot | --outputdir | --expdir | --expdir-src | --icsdir | --ecf-host | --ecf-port | --ecf-users | -p | -c | -n)
      if (($# < 2)); then
        echo "ERROR: $1 needs a value" >&2
        exit 2
      fi
      case "$1" in
        --comroot) comroot=$2 ;;
        --dataroot) dataroot=$2 ;;
        --outputdir) outputdir=$2 ;;
        --expdir) expdir=$2 ;;
        --expdir-src) expdir_src=$2 ;;
        --icsdir) icsdir=$2 ;;
        -p)
          pdy=$2
          run_args+=("$1" "$2")
          ;;
        --ecf-host) ecf_host=$2 ;;
        --ecf-port) ecf_port=$2 ;;
        --ecf-users) ecf_users=$2 ;;
        -c)
          first_cycle=$2
          run_args+=("$1" "$2")
          ;;
        -n)
          ncycles=$2
          run_args+=("$1" "$2")
          ;;
        *) run_args+=("$1" "$2") ;;
      esac
      shift 2
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "${pdy}" =~ ^[0-9]{8}$ || ! "${first_cycle}" =~ ^(00|06|12|18)$ ]]; then
  echo "ERROR: give -p PDY (YYYYMMDD) and -c CYC (00, 06, 12 or 18), the first cycle to run" >&2
  exit 2
fi

if [[ "${server_setup}" == "YES" ]]; then
  setup_ecflow_server || exit 1
fi

if [[ "${build_link}" == "YES" ]]; then
  build_and_link || exit 1
fi

mkdir -p "${comroot}" "${dataroot}" "${outputdir}" || exit 1
if [[ -n "${expdir_src}" ]]; then
  copy_expdir || exit 1
else
  create_expdir || exit 1
fi
setup_ecf_scripts || exit 1
"${SCRIPT_DIR}/gfsv17_ecflow_rt_render_def.py" --out "${expdir}/gfs_dev.def" --packagehome "${HOMEgfs}" \
  --comroot "${comroot}" --dataroot "${dataroot}" --outputdir "${outputdir}" --expdir "${expdir}" \
  --first-pdy "${pdy}" --first-cycle "${first_cycle}" || exit 1

if [[ "${setup_only}" == "YES" ]]; then
  # The run script stages the initial conditions otherwise
  COMDIR=${COMDIR:-${comroot}/gfs/v17.0} "${STAGE_SCRIPT}" -p "${pdy}" -c "${first_cycle}" || exit 1
  echo "Setup done; not running any cycle"
  print_start_instructions
  exit 0
fi

if command -v module > /dev/null 2>&1; then
  module load ecflow
fi
if [[ -n "${ecf_host}" ]]; then
  export ECF_HOST=${ecf_host}
fi
export ECF_PORT=${ecf_port:-$(($(id -u) + 2000))}
exec "${RUN_SCRIPT}" ${run_args[@]+"${run_args[@]}"} \
  --comroot "${comroot}" --dataroot "${dataroot}" --outputdir "${outputdir}" --expdir "${expdir}" \
  -d "${expdir}/gfs_dev.def"
