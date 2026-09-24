#!/bin/bash
# Refresh the ecf_scripts directory from the repo source .ecf files.
#
# Reads ecf_scripts.manifest (written by the .def generator) and
# copies each source .ecf into the ECF_FILES directory used by ecFlow.
# Run this after editing an .ecf file in the repo to pick up changes
# without regenerating the full .def.
#
# Usage:
#   sync_ecf_scripts.sh <ecf_scripts_dir>
#
# The manifest lives inside <ecf_scripts_dir>/ecf_scripts.manifest
# and contains:
#   - A header line: # ECF_SRC_DIR=<path to repo .ecf sources>
#   - One line per file: <child_name>\t<source_name>
#
# Example:
#   sync_ecf_scripts.sh /scratch3/.../EXPDIR/C48_ATM_ecflow/ecf_scripts

set -eu

if [[ $# -ne 1 ]]; then
  echo "Usage: ${0##*/} <ecf_scripts_dir>" >&2
  exit 1
fi

ecf_dir="$1"
manifest="${ecf_dir}/ecf_scripts.manifest"

if [[ ! -f "${manifest}" ]]; then
  echo "[ERROR] Manifest not found: ${manifest}" >&2
  echo "  Run load_ecflow_case.py first to generate it." >&2
  exit 1
fi

# Read source directory from manifest header
src_dir=$(grep '^# ECF_SRC_DIR=' "${manifest}" | head -1 | cut -d= -f2-)
if [[ -z "${src_dir}" ]]; then
  echo "[ERROR] ECF_SRC_DIR not found in manifest header." >&2
  exit 1
fi

if [[ ! -d "${src_dir}" ]]; then
  echo "[ERROR] Source directory does not exist: ${src_dir}" >&2
  exit 1
fi

count=0
while IFS=$'\t' read -r child_name source_name; do
  # Skip comments and blank lines
  [[ "${child_name}" =~ ^#.*$ || -z "${child_name}" ]] && continue

  src="${src_dir}/${source_name}.ecf"
  dest="${ecf_dir}/${child_name}.ecf"

  if [[ ! -f "${src}" ]]; then
    echo "[WARN] Source not found, skipping: ${src}" >&2
    continue
  fi

  cp -f "${src}" "${dest}"
  count=$((count + 1))
done < "${manifest}"

echo "[OK] Synced ${count} .ecf files to ${ecf_dir}"
