#!/bin/bash
# Refresh the ecf_scripts directory from the repo source .ecf files.
#
# Reads ecf_scripts.manifest (written by the .def generator) and
# reassembles each .ecf in the ECF_FILES directory.  Scripts that already
# carry #SBATCH directives keep them: shebang + existing #SBATCH lines +
# source body (minus shebang).  Scripts without #SBATCH lines are copied
# as is.
#
# Run this after editing an .ecf template in the repo to pick up
# changes without regenerating the full .def.
#
# Usage:
#   sync_ecf_scripts.sh <ecf_scripts_dir>
#
# The manifest at <ecf_scripts_dir>/ecf_scripts.manifest contains:
#   - Header line: # ECF_SRC_DIR=<path to repo dev/ecflow/scripts>
#   - One line per file: <dest path>\t<source path>, both relative to
#     their directories and without the .ecf extension
#
# Example:
#   sync_ecf_scripts.sh /scratch3/.../EXPDIR/my_C48_test/ecf_scripts

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
while IFS=$'\t' read -r dest_path source_path; do
    [[ "${dest_path}" =~ ^#.*$ || -z "${dest_path}" ]] && continue

    src="${src_dir}/${source_path}.ecf"
    dest="${ecf_dir}/${dest_path}.ecf"

    if [[ ! -f "${src}" ]]; then
        echo "[WARN] Source not found, skipping: ${src}" >&2
        continue
    fi

    mkdir -p "$(dirname "${dest}")"

    # Directives written by the generator directly follow the shebang
    sbatch_lines=""
    if [[ -f "${dest}" ]]; then
        sbatch_lines=$(awk 'NR > 1 { if ($0 ~ /^#SBATCH/) print; else exit }' "${dest}")
    fi

    if [[ -n "${sbatch_lines}" ]]; then
        tmp="${dest}.tmp"
        {
            echo '#!/bin/bash'
            echo "${sbatch_lines}"
            if head -1 "${src}" | grep -q '^#!/bin/bash'; then
                tail -n +2 "${src}"
            else
                cat "${src}"
            fi
        } > "${tmp}"
        mv "${tmp}" "${dest}"
    else
        cp "${src}" "${dest}"
    fi

    count=$((count + 1))
done < "${manifest}"

echo "[OK] Synced ${count} .ecf files to ${ecf_dir}"
