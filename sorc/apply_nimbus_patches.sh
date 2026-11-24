#! /usr/bin/env bash
#
# Apply the Nimbus platform patches (sorc/nimbus_patches) to the component submodules.
#
# Nimbus support has not been merged into the component repositories yet, so the
# component module files and machine detection changes are carried here.
# Safe to run repeatedly: patches that are already applied are skipped.
#
set -eu

readonly HOMEglobal_sorc="$(cd "$(dirname "$(readlink -f -n "${BASH_SOURCE[0]}")")" && pwd -P)"
readonly patch_dir="${HOMEglobal_sorc}/nimbus_patches"

# patch file -> submodule directory (relative to sorc/)
declare -A patch_targets=(
  ["sorc_gfs_utils.fd.patch"]="gfs_utils.fd"
  ["sorc_ufs_model.fd.patch"]="ufs_model.fd"
  ["sorc_ufs_model.fd_UFSATM_upp.patch"]="ufs_model.fd/UFSATM/upp"
  ["sorc_gdas.cd.patch"]="gdas.cd"
)

declare -A patch_sentinels=(
  ["sorc_gfs_utils.fd.patch"]="modulefiles/gfsutils_nimbus.intel.lua"
)

status=0
for patch_name in "${!patch_targets[@]}"; do
  patch_file="${patch_dir}/${patch_name}"
  target="${HOMEglobal_sorc}/${patch_targets[${patch_name}]}"

  if [[ ! -d "${target}" ]]; then
    echo "ERROR: ${target} does not exist; is the submodule checked out?"
    status=1
    continue
  fi

  sentinel="${patch_sentinels[$patch_name]:-}"
  if [[ -n "${sentinel}" && -f "${target}/${sentinel}" ]]; then
    echo "Nimbus patch already applied: ${patch_name}"
    continue
  fi

  if git -C "${target}" apply --reverse --check "${patch_file}" &> /dev/null; then
    echo "Nimbus patch already applied: ${patch_name}"
  elif git -C "${target}" apply --check "${patch_file}" &> /dev/null; then
    git -C "${target}" apply "${patch_file}"
    echo "Applied Nimbus patch: ${patch_name}"
  else
    echo "ERROR: ${patch_name} does not apply to ${target}"
    status=1
  fi
done

exit "${status}"
