#!/usr/bin/env bash
#
# Load the GFSv17 ecflow realtime config file into your shell environment. Source it, do not run it:
#
#   source dev/ush/gw_setup.sh
#   source dev/ush/gfsv17_ecflow_rt_env.sh [CONFIG_FILE]
#
# Every setting is exported as ECFRT_<SECTION>_<KEY>, for example experiment.pslot becomes
# ECFRT_EXPERIMENT_PSLOT and ecflow.dataroot becomes ECFRT_ECFLOW_DATAROOT. Check them with
# "env | grep ^ECFRT_" and change one with "export ECFRT_EXPERIMENT_PSLOT=my_test".
#
# gfsv17_ecflow_rt_setup_expt.sh takes its values in this order: command line options (including
# --set section.key=value), then these ECFRT_ variables, then the config file.
# CONFIG_FILE defaults to dev/ci/cases/gfsv17/ecflow_rt_highres.yaml. Sourcing the file again
# replaces the values of the keys it contains.

_ecfrt_home=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
_ecfrt_file=${1:-${_ecfrt_home}/dev/ci/cases/gfsv17/ecflow_rt_highres.yaml}
_ecfrt_status=0

if [[ ! -r "${_ecfrt_file}" ]]; then
  echo "ERROR: cannot read the config file ${_ecfrt_file}" >&2
  _ecfrt_status=1
elif ! _ecfrt_out=$(python3 "${_ecfrt_home}/dev/ush/gfsv17_ecflow_rt_config.py" "${_ecfrt_file}" "${_ecfrt_home}"); then
  echo "ERROR: cannot parse ${_ecfrt_file}; source dev/ush/gw_setup.sh first" >&2
  _ecfrt_status=1
else
  while IFS='=' read -r _ecfrt_key _ecfrt_value; do
    _ecfrt_key=${_ecfrt_key^^}
    export "ECFRT_${_ecfrt_key//./_}=${_ecfrt_value}"
  done <<< "${_ecfrt_out}"
  echo "Loaded ${_ecfrt_file} into ECFRT_* variables"
fi

unset _ecfrt_home _ecfrt_file _ecfrt_out _ecfrt_key _ecfrt_value
# shellcheck disable=SC2317
return "${_ecfrt_status}" 2> /dev/null || exit "${_ecfrt_status}"
