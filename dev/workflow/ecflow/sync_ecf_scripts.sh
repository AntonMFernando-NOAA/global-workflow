#!/bin/bash
# Copy all .ecf scripts from the repo source directory into the
# experiment's ecf_scripts/ directory used by ecFlow.
#
# Usage:
#   sync_ecf_scripts.sh <ecf_scripts_dir>
#
# Copies every .ecf file from ECF_SRC_DIR (recorded in the manifest
# header) into <ecf_scripts_dir>.  ecFlow resolves .ecf files by
# task name, so all product families sharing the same task name (f000)
# use the same .ecf file — the TASK edit variable on the parent family
# identifies the J-Job.

set -eu

if [[ $# -ne 1 ]]; then
  echo "Usage: ${0##*/} <ecf_scripts_dir>" >&2
  exit 1
fi

ecf_dir="$1"
manifest="${ecf_dir}/ecf_scripts.manifest"

if [[ ! -f "${manifest}" ]]; then
  echo "[ERROR] Manifest not found: ${manifest}" >&2
  echo "  Run run_ecflow_case.py first to generate it." >&2
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

# Copy all .ecf files from source to experiment directory.
count=0
for src in "${src_dir}"/*.ecf; do
  [[ -f "${src}" ]] || continue
  cp -f "${src}" "${ecf_dir}/"
  ((count++)) || true
done

echo "[OK] Synced ${count} .ecf files from ${src_dir} to ${ecf_dir}"
