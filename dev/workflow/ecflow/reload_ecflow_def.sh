#!/usr/bin/env bash
set -eu

# Update a running ecFlow suite after editing .ecf scripts or
# Python suite generator code.
#
# Usage:
#   reload_ecflow_def.sh <EXPDIR> sync     # sync .ecf scripts only
#   reload_ecflow_def.sh <EXPDIR> reload   # regenerate .def and replace suite
#
# Both modes preserve the state of completed/active tasks.
#
# "sync"   — copies updated .ecf files from the repo into the
#            experiment's ecf_scripts/ directory.  No server restart.
#
# "reload" — regenerates the .def file, syncs .ecf scripts, and
#            replaces the suite on the ecFlow server via --replace.

EXPDIR="${1:?Usage: $0 <EXPDIR> <sync|reload>}"
MODE="${2:?Usage: $0 <EXPDIR> <sync|reload>}"

if [[ ! -d "${EXPDIR}" ]]; then
  echo "[ERROR] EXPDIR not found: ${EXPDIR}"
  exit 1
fi

PSLOT=$(basename "${EXPDIR}")
HOMEglobal=$(cd "$(dirname "$0")/../../.." && pwd)
ECF_SCRIPTS="${EXPDIR}/ecf_scripts"

echo "=== ecFlow Update (${MODE}) ==="
echo "  EXPDIR:     ${EXPDIR}"
echo "  PSLOT:      ${PSLOT}"
echo "  HOMEglobal: ${HOMEglobal}"
echo ""

sync_ecf_scripts() {
  echo "[sync] Copying .ecf scripts to ${ECF_SCRIPTS}..."
  if [[ -x "${HOMEglobal}/dev/workflow/ecflow/sync_ecf_scripts.sh" ]]; then
    bash "${HOMEglobal}/dev/workflow/ecflow/sync_ecf_scripts.sh" \
      "${ECF_SCRIPTS}"
  elif [[ -f "${ECF_SCRIPTS}/ecf_scripts.manifest" ]]; then
    local src_dir count=0
    src_dir=$(head -1 "${ECF_SCRIPTS}/ecf_scripts.manifest" | sed 's/# ECF_SRC_DIR=//')
    while IFS=$'\t' read -r dest src; do
      [[ "${dest}" == \#* ]] && continue
      if [[ -f "${src_dir}/${src}.ecf" ]]; then
        cp -f "${src_dir}/${src}.ecf" "${ECF_SCRIPTS}/${dest}.ecf"
        ((count++)) || true
      fi
    done < "${ECF_SCRIPTS}/ecf_scripts.manifest"
    echo "  Copied ${count} .ecf files."
  else
    echo "  [WARN] No manifest found. Skipping."
  fi
}

case "${MODE}" in
  sync)
    sync_ecf_scripts
    echo ""
    echo "=== Done ==="
    echo "Rerun a failed task with:"
    echo "  ecflow_client --force=queued /${PSLOT}/<task_path>"
    ;;

  reload)
    echo "[1/3] Regenerating .def and .ecf scripts..."
    source "${HOMEglobal}/dev/ush/load_modules.sh" setup 2> /dev/null

    cd "${HOMEglobal}/dev/workflow"
    python3 -c "
import sys; sys.path.insert(0, '.')
from ecflow.load_ecflow_case import generate_ecflow_def
from pathlib import Path
generate_ecflow_def(Path('${EXPDIR}'))
"

    echo "[2/3] Syncing .ecf scripts..."
    sync_ecf_scripts

    echo "[3/3] Replacing suite on server (preserving task states)..."
    ecflow_client --replace "/${PSLOT}" "${EXPDIR}/${PSLOT}.def"
    echo ""
    echo "=== Done ==="
    echo "Suite /${PSLOT} replaced. Task states preserved."
    echo "Rerun a failed task with:"
    echo "  ecflow_client --force=queued /${PSLOT}/<task_path>"
    ;;

  *)
    echo "[ERROR] Unknown mode: ${MODE}"
    echo "  Use 'sync' or 'reload'"
    exit 1
    ;;
esac
