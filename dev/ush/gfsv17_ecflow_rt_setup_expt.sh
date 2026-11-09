#!/usr/bin/env bash
#
# Set up a GFSv17 ecflow realtime experiment in separate steps. Each of these options does
# only its own step; when several are given they run in this order. With none, this help
# is shown.
#
#   --ecf-server-setup find your ecflow server and ping it; only if it does not answer, set it
#                      up over ssh and ping it again. You do not need to know the values:
#                      the host follows the login node, the port and ECF_ROOT are read from
#                      your ecflow_server running on that host (default port id -u + 2000,
#                      default ECF_ROOT ${HOME}/ecflow), and each one is printed with where
#                      it came from
#   --build-link       run "sorc/build_all.sh gfs gdas gsi" and "sorc/link_workflow.sh"
#   --check-data       tell whether the previous cycle gdas/enkfgdas data exist for the cycle
#                      -p/-c, or for the current cycle when they are omitted
#   --stage            do the --check-data check, then ask whether to link gdas/enkfgdas into
#                      <comroot>/gfs/v17.0 and copy syndat there (-y does not ask). No other
#                      directory is created and ICSDIR is not used.
#   --setup            set up everything up to, but not including, loading the suite on the
#                      ecflow server, in the steps below
#   --copy-config      render the experiment config files again (or copy them again from
#                      --expdir-src) over those in an existing EXPDIR, and keep its other files
#                      (ecf, gfs_dev.def). Requires --expdir. It asks first, because your edits 
#                      to the config files are lost (-y does not ask). With --setup it does this 
#                      in step 3 also when the config files already exist.
#   --copy-ecf         copy dev/ecf/gfs/scripts and dev/ecf/gfs/include to <expdir>/ecf again and
#                      rerun setup_ecf_links.sh there (use it after changing head.h, tail.h or a
#                      .ecf file). Requires --expdir. With --setup it does this in step 4 also 
#                      when <expdir>/ecf exists. The suite on the ecflow server does not need to 
#                      be loaded again: tasks read these files when they are submitted.
#
# Steps of --setup:
#   0. Check that the data of the cycle are staged; when they are not, do what --stage does
#      (ask first, -y does not ask). Then check that the ecflow server answers. If something
#      is still missing, every problem is listed with the command that fixes it and nothing
#      is created.
#   1. If --expdir (the pslot directory) already exists, ask whether to delete it (-y deletes
#      it without asking). COMROOT, DATAROOT and OUTPUTDIR are never deleted because other
#      experiments share them. When it is deleted, everything below is created from scratch
#      and the run script replaces the suite on the ecflow server (as with --replace). When it
#      is kept, only what is missing is created.
#   2. Create COMROOT, DATAROOT and OUTPUTDIR if they do not exist.
#   3. Create the high resolution experiment described in the experiment block of the config
#      file in --expdir with
#      dev/workflow/setup_expt.py, starting at the first cycle (-p, -c). COMROOT
#      and EXPDIR in its config.base are the ones given here. With --expdir-src a
#      rendered EXPDIR is copied to --expdir instead. An existing --expdir that is
#      kept in step 0 is not overwritten, so your edits are kept, unless --copy-config is given.
#   4. Copy dev/ecf/gfs/scripts and dev/ecf/gfs/include to <expdir>/ecf and run
#      setup_ecf_links.sh there, so the per forecast hour .ecf files are created
#      outside the repository. The rendered definition reads ECF_FILES and ECF_INCLUDE from
#      %EXPDIR%/ecf. An existing <expdir>/ecf is not overwritten unless --copy-ecf or --replace
#      is given (use them after changing dev/ecf/gfs/include/head.h or tail.h).
#   5. Render the suite definition from dev/ecf/gfs/defs/gfs_prod.def into
#      <expdir>/gfs_dev.def (gfsv17_ecflow_rt_render_def.py), with the directories
#      above. The definition has one family per cycle (-n of them), named by its PDYCYC:
#      -p 20261106 -c 12 -n 5 gives 2026110612, 2026110618, 2026110700, 2026110706 and
#      2026110712. There is no cycle_end task: the tail.h of the jgdas_fcst task of a
#      cycle resumes the family of the next cycle. It is rendered again on every run.
#   6. Print the commands that load the suite and start the cycles; the run script
#      gfsv17_ecflow_rt_run_cycles.sh can do that.
#
# Usage: gfsv17_ecflow_rt_setup_expt.sh [--ecf-server-setup] [--build-link] [--check-data] [--stage]
#          [--setup] [--copy-config] [--copy-ecf] [-p PDY -c CYC] [-n NCYCLES] [-y] [--replace] [--config FILE]
#          [--pslot NAME] [--suite NAME] [--comroot DIR]
#          [--dataroot DIR] [--outputdir DIR] [--expdir DIR] [--expdir-src DIR] [--icsdir DIR] [--ecf-role]
#          [--ecf-host HOST] [--ecf-port PORT] [--ecf-users USER[,USER...]] [--set SECTION.KEY=VALUE] [-h]
#   --config FILE      yaml file with the defaults of the options below and of the experiment
#                      (default dev/ci/cases/gfsv17/ecflow_rt_highres.yaml, which is not meant to be
#                      edited: override its values with the options below, --set or ECFRT_ variables)
#   --set SECTION.KEY=VALUE
#                      override one setting of the config file, for example experiment.pslot=my_test
#                      or experiment.nens=30; it can be repeated
#   --pslot NAME       experiment name, the last part of --expdir (default experiment.pslot);
#                      ignored when --expdir is given, whose last part is then the name
#   --suite NAME       name of the suite on the ecflow server (default ecflow.suite)
#   --comroot DIR      COMROOT (default experiment.comroot)
#   --dataroot DIR     DATAROOT (default ecflow.dataroot)
#   --outputdir DIR    OUTPUTDIR (default ecflow.outputdir)
#   --expdir DIR       experiment directory to create; its name is the pslot
#                      (default experiment.expdir/experiment.pslot)
#   --expdir-src DIR   copy this already rendered EXPDIR (or the one pslot directory in it)
#                      to --expdir instead of creating the experiment
#   --icsdir DIR       ICSDIR given to setup_expt.py (default experiment.icsdir)
#   -p PDY -c CYC      first cycle; also the start date of the experiment that is created, and
#                      the first cycle the suite starts. When both are omitted they are chosen
#                      as gfsv17_ecflow_rt_stage_ics.sh does (clock and ops date file)
#   -n NCYCLES         number of cycles (families) in the suite; the suite stops by itself after
#                      them (default ecflow.ncycles)
#   -y, --yes          with --stage and --copy-config, do not ask; with --setup, delete the existing
#                      EXPDIR without asking
#   --replace          start over: recreate <expdir>/ecf from the repository (as --copy-ecf) and have
#                      the run script delete the suite on the ecflow server and load the new definition
#   --ecf-role         use the role account ECF_ROOT instead of ${HOME}/ecflow
#   --ecf-host HOST    ecflow server host (default ECF_HOST, then ecflow.host, otherwise
#                      cdecflow02 on Cactus and ddecflow02 on Dogwood)
#   --ecf-port PORT    ecflow server port (default ECF_PORT, then ecflow.port, otherwise the port
#                      of your running server on the host, otherwise id -u + 2000)
#   --ecf-users LIST   users to add to the server access list after the restart
#   -h                 show this help
#
# Run it after loading the workflow environment (source dev/ush/gw_setup.sh) so that
# the config file can be read and setup_expt.py finds wxflow.
#
# The settings of the config file can be loaded into your environment first with
#   source dev/ush/gfsv17_ecflow_rt_env.sh [CONFIG_FILE]
# which exports them as ECFRT_<SECTION>_<KEY> (experiment.pslot is ECFRT_EXPERIMENT_PSLOT).
# A value is taken from the first of: its command line option (--set, --comroot, ...), the
# ECFRT_ variable, the config file. A loaded or exported ECFRT_ variable therefore also wins
# over --config FILE; source the env file again with the other file to change them.
#
# Environment overrides:
#   ECF_ROOT_ROLE  role account ecflow root (default /lfs/h2/emc/global/noscrub/emc.global/ecflow)
#   EDATE          end date of the created experiment (default experiment.edate)
#   SRC_COMROOT    realtime comroot with the first cycle data (default ecflow.src_comroot)

set -u

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RUN_SCRIPT="${SCRIPT_DIR}/gfsv17_ecflow_rt_run_cycles.sh"
STAGE_SCRIPT="${SCRIPT_DIR}/gfsv17_ecflow_rt_stage_ics.sh"
HOMEgfs=$(cd "${SCRIPT_DIR}/../.." && pwd)
ECF_ROOT_ROLE=${ECF_ROOT_ROLE:-/lfs/h2/emc/global/noscrub/emc.global/ecflow}

config="${HOMEgfs}/dev/ci/cases/gfsv17/ecflow_rt_highres.yaml"
comroot=""
dataroot=""
outputdir=""
expdir=""
expdir_src=""
icsdir=""
edate=${EDATE:-}
exp_net=""
exp_mode=""
exp_pslot=""
exp_parent=""
exp_app=""
exp_resdetatmos=""
exp_resensatmos=""
exp_resdetocean=""
exp_nens=""
exp_interval=""
exp_start=""
exp_yaml=""
pdy=""
run_args=()
first_cycle=""
ncycles=""
suite=""
prev_pdy=""
prev_cyc=""
check_data=NO
stage=NO
setup=NO
assume_yes=NO
replace=NO
copy_config=NO
copy_ecf=NO
build_link=NO
server_setup=NO
expdir_explicit=NO
ecf_role=NO
ecf_host=${ECF_HOST:-}
ecf_port=${ECF_PORT:-}
ecf_users=""
host_from="ECF_HOST"
port_from="ECF_PORT"
root_from=""

usage() {
  sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# Fill the values not given on the command line from the ECFRT_ variables (see
# gfsv17_ecflow_rt_env.sh), and those from the config file
load_config() {
  local out line name value
  if [[ ! -r "${config}" ]]; then
    echo "ERROR: cannot read the config file ${config}" >&2
    return 1
  fi
  if ! out=$(python3 "${SCRIPT_DIR}/gfsv17_ecflow_rt_config.py" "${config}" "${HOMEgfs}"); then
    echo "ERROR: cannot parse ${config}; source dev/ush/gw_setup.sh first" >&2
    return 1
  fi
  while IFS='=' read -r line value; do
    name=${line^^}
    name=ECFRT_${name//./_}
    if [[ -z "${!name:-}" ]]; then
      export "${name}=${value}"
    fi
  done <<< "${out}"
  for name in $(compgen -v ECFRT_); do
    value=${!name}
    case "${name}" in
      ECFRT_EXPERIMENT_NET) exp_net=${value} ;;
      ECFRT_EXPERIMENT_MODE) exp_mode=${value} ;;
      ECFRT_EXPERIMENT_PSLOT) exp_pslot=${value} ;;
      ECFRT_EXPERIMENT_EXPDIR) exp_parent=${value} ;;
      ECFRT_EXPERIMENT_APP) exp_app=${value} ;;
      ECFRT_EXPERIMENT_RESDETATMOS) exp_resdetatmos=${value} ;;
      ECFRT_EXPERIMENT_RESENSATMOS) exp_resensatmos=${value} ;;
      ECFRT_EXPERIMENT_RESDETOCEAN) exp_resdetocean=${value} ;;
      ECFRT_EXPERIMENT_NENS) exp_nens=${value} ;;
      ECFRT_EXPERIMENT_INTERVAL) exp_interval=${value} ;;
      ECFRT_EXPERIMENT_START) exp_start=${value} ;;
      ECFRT_EXPERIMENT_YAML) exp_yaml=${value} ;;
      ECFRT_EXPERIMENT_COMROOT) : "${comroot:=${value}}" ;;
      ECFRT_EXPERIMENT_ICSDIR) : "${icsdir:=${value}}" ;;
      ECFRT_EXPERIMENT_EDATE) : "${edate:=${value}}" ;;
      ECFRT_ECFLOW_DATAROOT) : "${dataroot:=${value}}" ;;
      ECFRT_ECFLOW_OUTPUTDIR) : "${outputdir:=${value}}" ;;
      ECFRT_ECFLOW_NCYCLES) : "${ncycles:=${value}}" ;;
      ECFRT_ECFLOW_SUITE) suite=${value} ;;
      ECFRT_ECFLOW_SRC_COMROOT) export SRC_COMROOT=${SRC_COMROOT:-${value}} ;;
      ECFRT_ECFLOW_HOST)
        if [[ -z "${ecf_host}" ]]; then
          ecf_host=${value}
          host_from="ECFRT_ECFLOW_HOST or the config file"
        fi
        ;;
      ECFRT_ECFLOW_PORT)
        if [[ -z "${ecf_port}" ]]; then
          ecf_port=${value}
          port_from="ECFRT_ECFLOW_PORT or the config file"
        fi
        ;;
      *) ;;
    esac
  done
  if [[ -z "${expdir}" && -n "${exp_parent}" && -n "${exp_pslot}" ]]; then
    expdir=${exp_parent}/${exp_pslot}
  fi
  : "${ncycles:=1}"
  : "${suite:=gfs_v17_nco}"
  local missing=()
  for name in comroot dataroot outputdir expdir; do
    if [[ -z "${!name}" ]]; then
      missing+=("${name}")
    fi
  done
  if ((${#missing[@]} > 0)); then
    echo "ERROR: ${missing[*]} not set; give them as options or with --set" >&2
    return 1
  fi
}

# Print the commands that set up the ecflow server by hand
print_server_instructions() {
  local ecf_root=$1
  cat >&2 << EOF

The values used above:
  host     ${ecf_host}: ${host_from}
  port     ${ecf_port}: ${port_from}
  ECF_ROOT ${ecf_root}: ${root_from}
To see your servers on the host: ssh ${ecf_host} pgrep -u ${USER} -a ecflow_server
Their logs are named <host>.<port>.ecf.log in ECF_ROOT.

To set up the ecflow server by hand:
  ssh ${ecf_host}
  module load ecflow
  export ECF_ROOT=${ecf_root} ECF_HOST=${ecf_host} ECF_PORT=${ecf_port}
  export ECF_OUTPUTDIR=\${ECF_ROOT}/output LFS_OUTPUTDIR=\${ECF_ROOT}/submit ECF_COMDIR=\${ECF_ROOT}/com
  mkdir -p \${ECF_OUTPUTDIR} \${LFS_OUTPUTDIR} \${ECF_COMDIR}
  server_check.sh \${ECF_ROOT}
  ecflow_client --restart
  exit
Then check it from the login node:
  ecflow_client --host=${ecf_host} --port=${ecf_port} --ping
If the server runs on another port, give it with --ecf-port.
EOF
}

# Set ecf_port and ecf_root from the user's running ecflow_server on ecf_host, if there is one
find_running_server() {
  local info
  info=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "${ecf_host}" bash -s 2> /dev/null << 'EOF'
for pid in $(pgrep -u "${USER}" ecflow_server); do
  tr '\0' '\n' < "/proc/${pid}/environ" | grep -E '^(ECF_PORT|ECF_ROOT)='
  break
done
EOF
  )
  local port root
  port=$(sed -n 's/^ECF_PORT=//p' <<< "${info}")
  root=$(sed -n 's/^ECF_ROOT=//p' <<< "${info}")
  if [[ -n "${port}" && -z "${ecf_port}" ]]; then
    ecf_port=${port}
    port_from="your ecflow_server running on ${ecf_host}"
  fi
  if [[ -n "${root}" && "${ecf_role}" == "NO" ]]; then
    ecf_root=${root}
    root_from="your ecflow_server running on ${ecf_host}"
  fi
}

# Run the ecflow server steps on the server host
setup_ecflow_server() {
  local ecf_root=${HOME}/ecflow
  root_from="default \${HOME}/ecflow"
  if [[ "${ecf_role}" == "YES" ]]; then
    ecf_root=${ECF_ROOT_ROLE}
    root_from="--ecf-role (ECF_ROOT_ROLE)"
  fi
  if [[ -z "${ecf_host}" ]]; then
    echo "ERROR: the ecflow server host is unknown on $(hostname -s); give --ecf-host HOST" >&2
    echo "       (cdecflow02 on Cactus, ddecflow02 on Dogwood)" >&2
    return 1
  fi
  if command -v module > /dev/null 2>&1; then
    module load ecflow
  fi
  find_running_server
  if [[ -z "${ecf_port}" ]]; then
    ecf_port=$(($(id -u) + 2000))
    port_from="default: your user id ($(id -u)) + 2000"
  fi
  echo "ecflow server:"
  echo "  host     ${ecf_host} (${host_from})"
  echo "  port     ${ecf_port} (${port_from})"
  echo "  ECF_ROOT ${ecf_root} (${root_from})"
  if ecflow_client --host="${ecf_host}" --port="${ecf_port}" --ping; then
    echo "The ecflow server on ${ecf_host} port ${ecf_port} is already running"
    return 0
  fi
  echo "The ecflow server on ${ecf_host} port ${ecf_port} does not answer"
  echo "Setting up the ecflow server on ${ecf_host} port ${ecf_port} with ECF_ROOT ${ecf_root}"

  if ! ssh "${ecf_host}" env \
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
  then
    echo "ERROR: the ecflow server setup on ${ecf_host} failed" >&2
    print_server_instructions "${ecf_root}"
    return 1
  fi
  if ! ecflow_client --host="${ecf_host}" --port="${ecf_port}" --ping; then
    echo "ERROR: the ecflow server on ${ecf_host} port ${ecf_port} does not answer after the setup" >&2
    print_server_instructions "${ecf_root}"
    return 1
  fi
  echo "The ecflow server on ${ecf_host} port ${ecf_port} is running"
}

# Build all executables and link them
build_and_link() {
  (
    cd "${HOMEgfs}/sorc" || exit 1
    ./build_all.sh gfs gdas gsi || exit 1
    ./link_workflow.sh || exit 1
  )
}

# Ask a yes/no question; -y answers yes, and without a terminal the answer is no
confirm() {
  local answer
  if [[ "${assume_yes}" == "YES" ]]; then
    return 0
  elif [[ -t 0 ]]; then
    read -r -p "$1 [y/N]: " answer
    [[ "${answer}" =~ ^[Yy]([Ee][Ss])?$ ]]
  else
    echo "WARNING: not asked (no terminal) and -y not given; answering no" >&2
    return 1
  fi
}

# Copy the ecf scripts and include files to the EXPDIR and create the per forecast hour files there.
# They are made in <expdir>/ecf.new and moved into place, so a loaded suite never sees a half made ecf
setup_ecf_scripts() {
  local ecf_dir=${expdir}/ecf new_dir=${expdir}/ecf.new old_dir=${expdir}/ecf.old
  if [[ "${replace}" == "NO" && "${copy_ecf}" == "NO" && -d "${ecf_dir}/scripts" && -d "${ecf_dir}/include" ]]; then
    echo "${ecf_dir} already exists; not overwritten"
    return 0
  fi
  rm -rf "${new_dir}" "${old_dir}"
  mkdir -p "${new_dir}" || return 1
  cp -a "${HOMEgfs}/dev/ecf/gfs/scripts" "${HOMEgfs}/dev/ecf/gfs/include" "${new_dir}/" || return 1
  if ! (cd "${new_dir}" && bash "${HOMEgfs}/dev/ecf/gfs/setup_ecf_links.sh") > "${new_dir}/setup_ecf_links.log" 2>&1; then
    echo "ERROR: setup_ecf_links.sh failed; the log is ${new_dir}/setup_ecf_links.log" >&2
    tail -n 20 "${new_dir}/setup_ecf_links.log" >&2
    return 1
  fi
  if [[ -d "${ecf_dir}" ]]; then
    mv "${ecf_dir}" "${old_dir}" || return 1
  fi
  mv "${new_dir}" "${ecf_dir}" || return 1
  rm -rf "${old_dir}"
  echo "Created ${ecf_dir}"
}

# Print the commands that start the cases once the setup is done
print_start_instructions() {
  local fam="/${suite}/primary/${pdy}${first_cycle}"
  cat << EOF

To start the case by hand (the ecflow server must be running):
  module load ecflow
  export ECF_HOST=${ecf_host:-<ecflow server host>}
  export ECF_PORT=${ecf_port:-$(($(id -u) + 2000))}
  ecflow_client --restart                       # only if the server is halted
  ecflow_client --load=${expdir}/gfs_dev.def
  ecflow_client --begin=${suite}                # every cycle family starts suspended
  ecflow_client --resume=${fam}                 # runs cycle ${pdy}${first_cycle}
Check it with: ecflow_client --query state ${fam}   (or ecflow_ui)
After that the suite runs by itself: when the jgdas_fcst task of a cycle ends, its tail.h resumes
the family of the next cycle. To stop it: ecflow_client --suspend=/${suite}

To let a script do all of this (the suite stops by itself after ${ncycles} cycle(s)):
  ${RUN_SCRIPT} -p ${pdy} -c ${first_cycle} --suite ${suite} ${run_args[*]-} -d ${expdir}/gfs_dev.def
EOF
}

# Run setup_expt.py for the experiment $1 with its EXPDIR in the directory $2 and the start date $3 (YYYYMMDDHH)
run_setup_expt() {
  mkdir -p "$2" || return 1
  PYTHONPATH="${HOMEgfs}/sorc/wxflow/src${PYTHONPATH:+:${PYTHONPATH}}" \
    "${HOMEgfs}/dev/workflow/setup_expt.py" "${exp_net}" "${exp_mode}" \
    --pslot "$1" --app "${exp_app}" \
    --resdetatmos "${exp_resdetatmos}" --resensatmos "${exp_resensatmos}" \
    --resdetocean "${exp_resdetocean}" --nens "${exp_nens}" \
    --interval "${exp_interval}" --start "${exp_start}" \
    --comroot "${comroot}" --expdir "$2" \
    --idate "$3" --edate "${edate}" --icsdir "${icsdir}" \
    --yaml "${exp_yaml}"
}

# Render the config files again in a scratch experiment with another pslot, then copy them over those
# in EXPDIR. setup_expt.py never runs on the existing EXPDIR because it would delete it with its ROTDIR.
# The start date is -p/-c, otherwise the SDATE of the existing config.base.
refresh_config() {
  local pslot parent tmp_pslot idate out
  pslot=$(basename "${expdir}")
  parent=$(dirname "${expdir}")
  tmp_pslot=${pslot}_copycfg_$$
  if [[ -n "${pdy}" && -n "${first_cycle}" ]]; then
    idate=${pdy}${first_cycle}
  else
    idate=$(sed -n 's/^export SDATE="\([0-9]\{10\}\)".*/\1/p' "${expdir}/config.base")
  fi
  if [[ ! "${idate}" =~ ^[0-9]{10}$ ]]; then
    echo "ERROR: no start date: give -p PDY -c CYC; SDATE was not found in ${expdir}/config.base" >&2
    return 1
  fi
  if ! out=$(run_setup_expt "${tmp_pslot}" "${parent}" "${idate}" 2>&1); then
    echo "${out}" >&2
    echo "ERROR: setup_expt.py failed; the config files in ${expdir} are unchanged" >&2
    rm -rf "${parent:?}/${tmp_pslot:?}"
    rmdir "${comroot}/${tmp_pslot}" 2> /dev/null
    return 1
  fi
  grep -rlI -- "${tmp_pslot}" "${parent}/${tmp_pslot}" | xargs -r sed -i "s#${tmp_pslot}#${pslot}#g"
  cp -a "${parent}/${tmp_pslot}/." "${expdir}/"
  local status=$?
  rm -rf "${parent:?}/${tmp_pslot:?}"
  rmdir "${comroot}/${tmp_pslot}" 2> /dev/null
  if ((status != 0)); then
    echo "ERROR: cannot copy the rendered config files to ${expdir}" >&2
    return 1
  fi
  echo "Rendered the config files again in ${expdir} for the start ${idate}"
}

# Create the high resolution experiment in ${expdir}; with --copy-config render its config files again
create_expdir() {
  if [[ -f "${expdir}/config.base" ]]; then
    if [[ "${copy_config}" == "NO" ]]; then
      echo "EXPDIR ${expdir} already exists; not overwritten"
      return 0
    fi
    if ! confirm "Render the config files again over those in ${expdir} (your edits to them are lost)?"; then
      echo "Keeping the config files in ${expdir}"
      return 0
    fi
    refresh_config
    return
  fi
  if [[ -z "${pdy}" || -z "${first_cycle}" ]]; then
    echo "ERROR: give -p PDY -c CYC (the experiment start) or --expdir-src DIR" >&2
    return 1
  fi
  run_setup_expt "$(basename "${expdir}")" "$(dirname "${expdir}")" "${pdy}${first_cycle}" || return 1
  if [[ ! -f "${expdir}/config.base" ]]; then
    echo "ERROR: setup_expt.py did not create ${expdir}/config.base" >&2
    return 1
  fi
  echo "Created ${expdir}"
}

# Copy the rendered EXPDIR; when the destination already has one, only with --copy-config
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
    if [[ "${copy_config}" == "NO" ]]; then
      echo "EXPDIR ${expdir} already exists; not overwritten"
      return 0
    fi
    if ! confirm "Copy ${src} over the config files in ${expdir} (your edits to them are lost)?"; then
      echo "Keeping the config files in ${expdir}"
      return 0
    fi
  fi
  mkdir -p "${expdir}" || return 1
  cp -r "${src}/." "${expdir}/" || return 1
  echo "Copied ${src} to ${expdir}"
}

# Ask whether to delete the EXPDIR (the pslot directory) when it already exists, so the setup
# starts from scratch; with -y it is deleted without asking. COMROOT, DATAROOT and OUTPUTDIR are
# shared by other experiments and are never deleted.
clean_existing() {
  local resolved answer
  if [[ ! -e "${expdir}" ]]; then
    return 0
  fi
  resolved=$(realpath -m "${expdir}")
  # Refuse paths that are too close to the root or the home directory to be an experiment
  if [[ "${resolved}" == "/" || "${resolved}" == "$(realpath -m "${HOME}")" || "${resolved}" =~ ^/[^/]+(/[^/]+)?$ ]]; then
    echo "ERROR: refusing to delete ${expdir}; give a dedicated experiment directory" >&2
    return 1
  fi
  if [[ -n "${expdir_src}" && "$(realpath -m "${expdir_src}")/" == "${resolved}/"* ]]; then
    echo "ERROR: --expdir-src ${expdir_src} is inside ${expdir}, which would be deleted" >&2
    return 1
  fi
  echo "This directory already exists: ${expdir}"
  if [[ "${assume_yes}" == "YES" ]]; then
    answer=y
  elif [[ -t 0 ]]; then
    read -r -p "Delete it and set up from scratch? [y/N]: " answer
  else
    echo "WARNING: not asked (no terminal) and -y not given; the existing files are kept"
    return 0
  fi
  if [[ ! "${answer}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo "Keeping the existing files; only the missing ones are created"
    return 0
  fi
  echo "Deleting ${expdir}"
  rm -rf "${expdir}" || return 1
  # The suite on the ecflow server belongs to the deleted setup, so load the new one
  if [[ "${replace}" == "NO" ]]; then
    replace=YES
    run_args+=(--replace)
  fi
}

# Run the stage script in check mode for -p/-c, or for the current cycle when they are not given;
# sets pdy, first_cycle, prev_pdy and prev_cyc
select_cycle() {
  local args=() out rc
  if [[ -n "${pdy}" || -n "${first_cycle}" ]]; then
    args=(-p "${pdy}" -c "${first_cycle}")
  fi
  out=$("${STAGE_SCRIPT}" -k ${args[@]+"${args[@]}"})
  rc=$?
  echo "${out}"
  if ((rc != 0)); then
    echo "ERROR: no usable cycle; use --check-data or give -p PDY -c CYC" >&2
    return "${rc}"
  fi
  pdy=$(sed -n 's/^PDY=//p' <<< "${out}")
  first_cycle=$(sed -n 's/^CYC=//p' <<< "${out}")
  prev_pdy=$(sed -n 's/^PREV_PDY=//p' <<< "${out}")
  prev_cyc=$(sed -n 's/^PREV_CYC=//p' <<< "${out}")
}

# Return 0 when the previous cycle data or syndat are missing from COMDIR
data_missing() {
  local comdir=${COMDIR:-${comroot}/gfs/v17.0} run
  for run in gdas enkfgdas; do
    [[ -e "${comdir}/${run}.${prev_pdy}/${prev_cyc}" ]] || return 0
  done
  [[ -d "${comdir}/syndat" ]] || return 0
  return 1
}

# Check the data, then ask whether to link them into COMDIR and copy syndat
stage_data() {
  select_cycle || return 1
  link_data
}

# Ask whether to link the data of the selected cycle into COMDIR and copy syndat
link_data() {
  local answer
  if [[ "${assume_yes}" == "YES" ]]; then
    answer=y
  elif [[ -t 0 ]]; then
    read -r -p "Create the links and copy syndat in ${COMDIR:-${comroot}/gfs/v17.0}? [y/N]: " answer
  else
    echo "ERROR: no terminal to ask; use -y to stage without asking" >&2
    return 1
  fi
  if [[ ! "${answer}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo "Nothing staged"
    return 0
  fi
  COMDIR=${COMDIR:-${comroot}/gfs/v17.0} "${STAGE_SCRIPT}" -p "${pdy}" -c "${first_cycle}"
}

# List what is not ready for --setup, with the command that fixes each; return 1 if anything
check_prerequisites() {
  local problems=() run
  local comdir=${COMDIR:-${comroot}/gfs/v17.0}
  local port=${ecf_port:-$(($(id -u) + 2000))}
  for run in gdas enkfgdas; do
    if [[ ! -e "${comdir}/${run}.${prev_pdy}/${prev_cyc}" ]]; then
      problems+=("${comdir}/${run}.${prev_pdy}/${prev_cyc} is missing: run ${0} --stage -p ${pdy} -c ${first_cycle}")
    fi
  done
  if [[ ! -d "${comdir}/syndat" ]]; then
    problems+=("${comdir}/syndat is missing: run ${0} --stage -p ${pdy} -c ${first_cycle}")
  fi
  if command -v module > /dev/null 2>&1; then
    module load ecflow
  fi
  if ! command -v ecflow_client > /dev/null 2>&1; then
    problems+=("ecflow_client is not found: module load ecflow")
  elif [[ -z "${ecf_host}" ]]; then
    problems+=("the ecflow server host is not set: give --ecf-host HOST or set ECF_HOST")
  elif ! ECF_HOST=${ecf_host} ECF_PORT=${port} ecflow_client --ping > /dev/null 2>&1; then
    problems+=("the ecflow server ${ecf_host} port ${port} does not answer: run ${0} --ecf-server-setup --ecf-host ${ecf_host}")
  fi
  if ((${#problems[@]} > 0)); then
    echo "ERROR: the setup cannot start yet:" >&2
    printf '  - %s\n' "${problems[@]}" >&2
    return 1
  fi
}

# Copy the config files and/or the ecf files again into an existing EXPDIR (--copy-config, --copy-ecf without --setup)
recopy_expdir() {
  if [[ "${expdir_explicit}" != "YES" && "${copy_config}${copy_ecf}" == *YES* ]]; then
    echo "ERROR: --copy-config or --copy-ecf requires explicit --expdir to specify which experiment to update" >&2
    return 1
  fi
  if [[ ! -f "${expdir}/config.base" ]]; then
    echo "ERROR: ${expdir} has no config.base; create it first with --setup" >&2
    return 1
  fi
  if [[ "${copy_config}" == "YES" ]]; then
    if [[ -n "${expdir_src}" ]]; then
      copy_expdir || return 1
    else
      create_expdir || return 1
    fi
  fi
  if [[ "${copy_ecf}" == "YES" ]]; then
    setup_ecf_scripts || return 1
    echo "Tasks submitted from now on use the new ecf files; the suite on the ecflow server is not reloaded"
  fi
}

# Create everything up to loading the suite on the ecflow server
setup_all() {
  select_cycle || return 1
  if data_missing; then
    link_data || return 1
  fi
  check_prerequisites || return 1
  clean_existing || return 1
  mkdir -p "${comroot}" "${dataroot}" "${outputdir}" || return 1
  if [[ -n "${expdir_src}" ]]; then
    copy_expdir || return 1
  else
    create_expdir || return 1
  fi
  setup_ecf_scripts || return 1
  "${SCRIPT_DIR}/gfsv17_ecflow_rt_render_def.py" --out "${expdir}/gfs_dev.def" --suite "${suite}" --packagehome "${HOMEgfs}" \
    --comroot "${comroot}" --dataroot "${dataroot}" --outputdir "${outputdir}" --expdir "${expdir}" \
    --first-pdy "${pdy}" --first-cycle "${first_cycle}" --ncycles "${ncycles}" || return 1
  echo "Setup done; the suite is not loaded on the ecflow server"
  print_start_instructions
}

while (($# > 0)); do
  case "$1" in
    --check-data)
      check_data=YES
      shift
      ;;
    --stage)
      stage=YES
      shift
      ;;
    --setup)
      setup=YES
      shift
      ;;
    --copy-config)
      copy_config=YES
      shift
      ;;
    --copy-ecf)
      copy_ecf=YES
      shift
      ;;
    -y | --yes)
      assume_yes=YES
      shift
      ;;
    --replace)
      replace=YES
      run_args+=("$1")
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
    --pslot | --suite)
      if (($# < 2)); then
        echo "ERROR: $1 needs a value" >&2
        exit 2
      fi
      if [[ "$1" == "--pslot" ]]; then
        export ECFRT_EXPERIMENT_PSLOT=$2
      else
        export ECFRT_ECFLOW_SUITE=$2
      fi
      shift 2
      ;;
    --set)
      if [[ "${2:-}" != *.*=* ]]; then
        echo "ERROR: --set needs section.key=value, for example experiment.pslot=my_test" >&2
        exit 2
      fi
      set_key=${2%%=*}
      set_key=ECFRT_${set_key^^}
      export "${set_key//./_}=${2#*=}"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --config | --comroot | --dataroot | --outputdir | --expdir | --expdir-src | --icsdir | --ecf-host | --ecf-port | --ecf-users | -p | -c | -n)
      if (($# < 2)); then
        echo "ERROR: $1 needs a value" >&2
        exit 2
      fi
      case "$1" in
        --config) config=$2 ;;
        --comroot) comroot=$2 ;;
        --dataroot) dataroot=$2 ;;
        --outputdir) outputdir=$2 ;;
        --expdir)
          expdir=$2
          expdir_explicit=YES
          ;;
        --expdir-src) expdir_src=$2 ;;
        --icsdir) icsdir=$2 ;;
        -p) pdy=$2 ;;
        --ecf-host)
          ecf_host=$2
          host_from="--ecf-host"
          ;;
        --ecf-port)
          ecf_port=$2
          port_from="--ecf-port"
          ;;
        --ecf-users) ecf_users=$2 ;;
        -c) first_cycle=$2 ;;
        -n) ncycles=$2 ;;
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

if [[ "${server_setup}${build_link}${check_data}${stage}${setup}${copy_config}${copy_ecf}" != *YES* ]]; then
  usage >&2
  exit 2
fi

load_config || exit 1

if [[ -z "${ecf_host}" ]]; then
  case "$(hostname -s)" in
    c*) ecf_host=cdecflow02 ;;
    d*) ecf_host=ddecflow02 ;;
    *) ;;
  esac
  host_from="default for the login node $(hostname -s)"
fi

if [[ "${server_setup}" == "YES" ]]; then
  setup_ecflow_server || exit 1
fi

if [[ "${build_link}" == "YES" ]]; then
  build_and_link || exit 1
fi

if [[ "${check_data}" == "YES" ]]; then
  select_cycle || exit 1
fi

if [[ "${stage}" == "YES" ]]; then
  stage_data || exit 1
fi

if [[ "${setup}" == "YES" ]]; then
  setup_all || exit 1
elif [[ "${copy_config}${copy_ecf}" == *YES* ]]; then
  recopy_expdir || exit 1
fi
