#!/bin/bash
# pbs_to_slurm.sh — Convert #PBS directives to #SBATCH in all .ecf files
#
# PBS → Slurm mapping:
#   -S /bin/bash               → (dropped; ecFlow adds shebang)
#   -N <name>                  → --job-name=<name>
#   -j oe                      → (dropped; Slurm merges by default)
#   -q <queue>                 → --partition=<queue>
#   -A <account>               → --account=<account>
#   -l walltime=<time>         → --time=<time>
#   -l debug=true              → (dropped; no Slurm equivalent)
#   -l place=vscatter:exclhost → --exclusive
#   -l place=vscatter:shared   → (dropped; shared is default)
#   -l place=vscatter          → (dropped)
#   -l select=N:mpiprocs=M:ompthreads=T:ncpus=C[:mem=S]
#       → --nodes=N --ntasks-per-node=M --cpus-per-task=T [--mem=S]
#       ncpus is dropped; Slurm derives it from ntasks × cpus-per-task
#
# Usage:
#   bash pbs_to_slurm.sh [--dry-run]

set -eu

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "[DRY RUN] No files will be modified."
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
count=0
skipped=0

convert_file() {
  local file="$1"
  local tmpfile="${file}.slurm_tmp"

  if grep -q '^#SBATCH' "${file}"; then
    echo "  SKIP (already converted): ${file}"
    skipped=$((skipped + 1))
    return
  fi

  if ! grep -q '^#PBS' "${file}"; then
    return
  fi

  if ${DRY_RUN}; then
    echo "  WOULD CONVERT: ${file}"
    count=$((count + 1))
    return
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" == \#PBS* ]]; then
      # Drop: -S, -j, debug
      if [[ "${line}" == *"-S /bin/bash"* ]]; then continue; fi
      if [[ "${line}" == *"-j oe"* ]]; then continue; fi
      if [[ "${line}" == *"debug=true"* ]]; then continue; fi

      # -N → --job-name
      if [[ "${line}" =~ ^#PBS\ +-N\ +(.*) ]]; then
        echo "#SBATCH --job-name=${BASH_REMATCH[1]}" >>"${tmpfile}"
        continue
      fi
      # -q → --partition
      if [[ "${line}" =~ ^#PBS\ +-q\ +(.*) ]]; then
        echo "#SBATCH --partition=${BASH_REMATCH[1]}" >>"${tmpfile}"
        continue
      fi
      # -A → --account
      if [[ "${line}" =~ ^#PBS\ +-A\ +(.*) ]]; then
        echo "#SBATCH --account=${BASH_REMATCH[1]}" >>"${tmpfile}"
        continue
      fi
      # walltime → --time
      if [[ "${line}" =~ ^#PBS\ +-l\ +walltime=(.*) ]]; then
        echo "#SBATCH --time=${BASH_REMATCH[1]}" >>"${tmpfile}"
        continue
      fi

      # place directives
      if [[ "${line}" == *"place=vscatter:exclhost"* ]]; then
        echo "#SBATCH --exclusive" >>"${tmpfile}"
        continue
      fi
      if [[ "${line}" == *"place=vscatter"* ]]; then
        continue
      fi

      # select= resource specification
      if [[ "${line}" =~ ^#PBS\ +-l\ +select= ]]; then
        local spec="${line##*select=}"
        local nodes mpiprocs ompthreads mem
        nodes="${spec%%:*}"
        mpiprocs=""
        ompthreads=""
        mem=""

        if [[ "${spec}" =~ mpiprocs=([0-9]+) ]]; then
          mpiprocs="${BASH_REMATCH[1]}"
        fi
        if [[ "${spec}" =~ ompthreads=([0-9]+) ]]; then
          ompthreads="${BASH_REMATCH[1]}"
        fi
        if [[ "${spec}" =~ mem=([0-9]+[A-Za-z]+) ]]; then
          mem="${BASH_REMATCH[1]}"
        fi

        {
          echo "#SBATCH --nodes=${nodes}"
          if [[ -n "${mpiprocs}" ]]; then
            echo "#SBATCH --ntasks-per-node=${mpiprocs}"
          fi
          if [[ -n "${ompthreads}" ]]; then
            echo "#SBATCH --cpus-per-task=${ompthreads}"
          fi
          if [[ -n "${mem}" ]]; then
            echo "#SBATCH --mem=${mem}"
          fi
        } >>"${tmpfile}"
        continue
      fi

      # Catch-all: comment out unhandled PBS directives
      echo "# [UNSUPPORTED PBS] ${line}" >>"${tmpfile}"
      continue
    fi

    echo "${line}" >>"${tmpfile}"
  done <"${file}"

  mv "${tmpfile}" "${file}"
  count=$((count + 1))
  echo "  CONVERTED: ${file}"
}

echo "=== PBS to Slurm conversion ==="
echo "Scanning: ${SCRIPT_DIR}"
echo ""

while IFS= read -r -d '' ecf_file; do
  convert_file "${ecf_file}"
done < <(find "${SCRIPT_DIR}" -name '*.ecf' -print0 | sort -z)

echo ""
echo "=== Done ==="
echo "  Converted: ${count}"
echo "  Skipped:   ${skipped}"
