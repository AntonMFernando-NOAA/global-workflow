# Transfer C96C48mx500 S2SW Case Data from Ursa to GCS

This guide describes how to package, upload, verify, download, and extract the
data required for the `C96C48mx500_S2SW_cyc_gfs` case.

Do not package the entire
`/scratch3/NCEPDEV/global/role.glopara/data` directory. It contains unrelated
datasets and some directories that may be inaccessible.

The source data are:

| Data | Ursa location | Archive |
|---|---|---|
| Initial conditions | `/scratch3/NCEPDEV/global/role.glopara/data/ICSDIR/C96C48/20250808` | `gfs_v17_c48_ics.tar.gz` |
| FIX data | `/scratch3/NCEPDEV/global/role.glopara/fix` | `gfs_v17_c48_fix.tar.gz` |
| Atmospheric dumps | `/scratch3/NCEPDEV/global/role.glopara/dump` | `gfs_v17_c48_obs.tar.gz` |

The GCS destination is:

```text
gs://wcoss-anton-space1
```

Use a Slurm compute node for all tar creation, downloads, and uploads. Login
nodes are not appropriate for large or CPU-intensive transfers.

## 1. Check source and output space

On Ursa, check the source size and available scratch capacity:

```bash
ICROOT=/scratch3/NCEPDEV/global/role.glopara/data/ICSDIR
FIXROOT=/scratch3/NCEPDEV/global/role.glopara/fix
OBSROOT=/scratch3/NCEPDEV/global/role.glopara/dump

du -sh "${ICROOT}/C96C48/20250808"
du -sh "${FIXROOT}"
du -sh "${OBSROOT}"

df -h /scratch3 /scratch4
quota -s
lfs quota -u "${USER}" /scratch3 2>/dev/null || true
```

Create a user-owned temporary archive directory:

```bash
mkdir -p /scratch4/NCEPDEV/stmp/${USER}/case-tars
```

Keep enough scratch space for:

- the source FIX or IC directories being read,
- the generated tar files,
- temporary compression data,
- and the final GCS transfer.

If the data or generated tar files are larger than the available scratch quota,
check quota and capacity before continuing:

```bash
df -h /scratch3 /scratch4
quota -s
lfs quota -u "${USER}" /scratch3 2>/dev/null || true
```

Also check the size of the source and archive directories:

```bash
du -sh /scratch3/NCEPDEV/global/role.glopara/data/ICSDIR/C96C48/20250808
du -sh /scratch3/NCEPDEV/global/role.glopara/fix
du -sh /scratch3/NCEPDEV/global/role.glopara/dump
du -sh /scratch4/NCEPDEV/stmp/${USER}/case-tars
```

Do not create tar files if the source size plus the uncompressed copy and
generated archive would exceed the scratch quota. Ask a Ursa administrator or
project lead for additional quota, or reduce the archive to the minimum
required files before proceeding. Temporary tar files may be removed after
their GCS uploads and SHA-256 hashes have been verified.

Do not remove or modify files in the shared `role.glopara` directories.

## 2. Install or load the Google Cloud CLI on Ursa

First check whether Google Cloud is provided by the Ursa module system:

```bash
module spider google-cloud 2>&1
module spider gcloud 2>&1
module spider google-cloud-sdk 2>&1
module spider google-cloud-cli 2>&1
```

If a module is available, load it according to the module search output.
Examples may include:

```bash
module load google-cloud-sdk
module load google-cloud-cli
```

Confirm the installation:

```bash
command -v gcloud
gcloud version
```

If no module is available, install the Google Cloud CLI in a user-owned
directory. Do not use `sudo`.

```bash
cd /scratch3/NCEPDEV/global/${USER}

curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz

tar -xzf google-cloud-cli-linux-x86_64.tar.gz

./google-cloud-sdk/install.sh \
  --quiet \
  --path-update=true \
  --command-completion=true
```

Activate the installation for the current shell:

```bash
source /scratch3/NCEPDEV/global/${USER}/google-cloud-sdk/path.bash.inc
source /scratch3/NCEPDEV/global/${USER}/google-cloud-sdk/completion.bash.inc
```

Make this permanent by adding the following to `~/.bashrc`:

```bash
if [[ -f /scratch3/NCEPDEV/global/${USER}/google-cloud-sdk/path.bash.inc ]]; then
  source /scratch3/NCEPDEV/global/${USER}/google-cloud-sdk/path.bash.inc
fi
```

Then reopen the shell or run:

```bash
source ~/.bashrc
command -v gcloud
gcloud version
```

The user installation under scratch is temporary scratch storage. Back it up or
reinstall it if Ursa purges the user directory.

## 3. Authenticate gcloud

Authenticate with browser login:

```bash
gcloud auth login --no-launch-browser
```

Follow the URL and enter the verification code using a browser where access to
the GCP project is permitted.

Set the project:

```bash
gcloud config set project wcoss-eae-project-1
```

Verify bucket access:

```bash
gcloud storage ls gs://wcoss-anton-space1
```

Do not place service-account key files in source-code repositories or scripts.
Use the approved organization authentication method if browser login is not
available.

## 4. Create a minimal initial-condition archive

Create `tar_c48_ics.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=tar_c48_ics
#SBATCH --account=fv3-cpu
#SBATCH --partition=u1-compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-ics-%j.out
#SBATCH --error=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-ics-%j.err

set -euo pipefail

ICROOT=/scratch3/NCEPDEV/global/role.glopara/data/ICSDIR
OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars

mkdir -p "${OUT}"
test -d "${ICROOT}/C96C48/20250808"

tar -I 'pigz -p 16' -cf \
  "${OUT}/gfs_v17_c48_ics.tar.gz" \
  -C "${ICROOT}" C96C48/20250808

gzip -t "${OUT}/gfs_v17_c48_ics.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_ics.tar.gz"
ls -lh "${OUT}/gfs_v17_c48_ics.tar.gz"
```

Submit:

```bash
chmod 0755 tar_c48_ics.sh
sbatch tar_c48_ics.sh
```

## 5. Create a minimal FIX archive

The workflow links a selected FIX version for each FIX category. Do not archive
the entire `role.glopara/fix` tree. Include the versions from
`versions/fix.ver` used by the workflow:

```text
aer/20250529
am/20220805
chem/20220805
cice/20240416
cpl/20230526
datm/20220805
gsi/20251105
lut/20220805
mom6/20250128
orog/20240917
sfc_climo/20220805
ugwd/20240624
verif/20220805
wave/20260622
gdas/fv3jedi/20241115
gdas/gsibec/20250505
gdas/obs/20240213
gdas/soca/20250519
gdas/aero/20240806
gdas/snow/20241210
```

Create `tar_c48_fix.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=tar_c48_fix
#SBATCH --account=fv3-cpu
#SBATCH --partition=u1-compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-fix-%j.out
#SBATCH --error=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-fix-%j.err

set -euo pipefail

FIXPARENT=/scratch3/NCEPDEV/global/role.glopara
OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars
mkdir -p "${OUT}"

FIX_ITEMS=(
  fix/aer/20250529
  fix/am/20220805
  fix/chem/20220805
  fix/cice/20240416
  fix/cpl/20230526
  fix/datm/20220805
  fix/gsi/20251105
  fix/lut/20220805
  fix/mom6/20250128
  fix/orog/20240917
  fix/sfc_climo/20220805
  fix/ugwd/20240624
  fix/verif/20220805
  fix/wave/20260622
  fix/gdas/fv3jedi/20241115
  fix/gdas/gsibec/20250505
  fix/gdas/obs/20240213
  fix/gdas/soca/20250519
  fix/gdas/aero/20240806
  fix/gdas/snow/20241210
)

for item in "${FIX_ITEMS[@]}"; do
  test -d "${FIXPARENT}/${item}" ||
    { echo "Missing FIX directory: ${FIXPARENT}/${item}" >&2; exit 1; }
done

tar -I 'pigz -p 16' -cf \
  "${OUT}/gfs_v17_c48_fix.tar.gz" \
  -C "${FIXPARENT}" "${FIX_ITEMS[@]}"

gzip -t "${OUT}/gfs_v17_c48_fix.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_fix.tar.gz"
tar -tzf "${OUT}/gfs_v17_c48_fix.tar.gz" | head
ls -lh "${OUT}/gfs_v17_c48_fix.tar.gz"
```

Submit:

```bash
chmod 0755 tar_c48_fix.sh
sbatch tar_c48_fix.sh
```

The `crtm`, `gldas`, `glwu`, `raw`, `reg2grb2`, and unrelated FIX versions are
not needed for this case.

## 6. Create a minimal observation archive

The case spans `2021122012` through `2021122100`. Package the existing
atmospheric dump directories needed for preparation and cycling:

```text
gdas.20211220/06/atmos
gdas.20211220/12/atmos
gdas.20211220/18/atmos
gdas.20211221/00/atmos
gfs.20211220/18/atmos
gfs.20211221/00/atmos
```

Create `tar_c48_obs.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=tar_c48_obs
#SBATCH --account=fv3-cpu
#SBATCH --partition=u1-compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-obs-%j.out
#SBATCH --error=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-obs-%j.err

set -euo pipefail

OBSROOT=/scratch3/NCEPDEV/global/role.glopara/dump
OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars
MANIFEST="${OUT}/obs_manifest.txt"

mkdir -p "${OUT}"
: > "${MANIFEST}"

dirs=(
  gdas.20211220/06/atmos
  gdas.20211220/12/atmos
  gdas.20211220/18/atmos
  gdas.20211221/00/atmos
  gfs.20211220/18/atmos
  gfs.20211221/00/atmos
)

for dir in "${dirs[@]}"; do
  if [[ -d "${OBSROOT}/${dir}" ]]; then
    echo "${dir}" >> "${MANIFEST}"
  else
    echo "Missing OBS directory: ${OBSROOT}/${dir}" >&2
  fi
done

test -s "${MANIFEST}"

tar -I 'pigz -p 16' -cf \
  "${OUT}/gfs_v17_c48_obs.tar.gz" \
  -C "${OBSROOT}" -T "${MANIFEST}"

gzip -t "${OUT}/gfs_v17_c48_obs.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_obs.tar.gz"
cat "${MANIFEST}"
tar -tzf "${OUT}/gfs_v17_c48_obs.tar.gz" | head
ls -lh "${OUT}/gfs_v17_c48_obs.tar.gz"
```

Submit:

```bash
chmod 0755 tar_c48_obs.sh
sbatch tar_c48_obs.sh
```

The case enables marine observation preparation and may require experimental
marine data. Check for the required source before deciding whether to create an
additional marine-observation archive:

```bash
find /scratch3/NCEPDEV/global/role.glopara/data/experimental_obs \
  -maxdepth 3 -type d 2>/dev/null | head
```

Do not include the old dump directories shown in the Ursa dump listing. They
are not needed by this 20211220-20211221 test.

## 7. Validate all Ursa archives

```bash
OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars

ls -lh "${OUT}"/*.tar.gz
sha256sum "${OUT}/gfs_v17_c48_ics.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_fix.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_obs.tar.gz"

gzip -t "${OUT}/gfs_v17_c48_ics.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_fix.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_obs.tar.gz"
```

Save the SHA-256 values for comparison after transfer.

## 8. Upload the archives to GCS

Create `upload_c48_archives.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=upload_c48_archives
#SBATCH --account=fv3-cpu
#SBATCH --partition=u1-compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=06:00:00
#SBATCH --output=/scratch3/NCEPDEV/global/Anton.Fernando/upload-c48-%j.out
#SBATCH --error=/scratch3/NCEPDEV/global/Anton.Fernando/upload-c48-%j.err

set -euo pipefail

OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars
BUCKET=gs://wcoss-anton-space1

gcloud storage cp \
  "${OUT}/gfs_v17_c48_ics.tar.gz" \
  "${BUCKET}/gfs_v17_c48_ics.tar.gz"

gcloud storage cp \
  "${OUT}/gfs_v17_c48_fix.tar.gz" \
  "${BUCKET}/gfs_v17_c48_fix.tar.gz"

gcloud storage cp \
  "${OUT}/gfs_v17_c48_obs.tar.gz" \
  "${BUCKET}/gfs_v17_c48_obs.tar.gz"
```

Submit:

```bash
chmod 0755 upload_c48_archives.sh
sbatch upload_c48_archives.sh
```

Verify the GCS objects:

```bash
gcloud storage ls -l gs://wcoss-anton-space1/gfs_v17_c48_*.tar.gz
```

## 9. Verify GCS hashes

Get the GCS hash for each uploaded object:

```bash
gcloud storage hash gs://wcoss-anton-space1/gfs_v17_c48_ics.tar.gz
gcloud storage hash gs://wcoss-anton-space1/gfs_v17_c48_fix.tar.gz
gcloud storage hash gs://wcoss-anton-space1/gfs_v17_c48_obs.tar.gz
```

Compare each GCS SHA-256 value with the matching Ursa SHA-256 value:

```bash
sha256sum /scratch4/NCEPDEV/stmp/${USER}/case-tars/gfs_v17_c48_*.tar.gz
```

Do not begin the WCOSS download until all local and GCS hash pairs match.

## 10. Download to WCOSS Lustre

On WCOSS3, create the Lustre destination:

```bash
sudo -A install -d -o "${USER}" -g "${USER}" -m 0775 \
  /work/global_workflow_data
```

Download the archives with a WCOSS Slurm job:

```bash
#!/bin/bash
#SBATCH --job-name=download_c48_archives
#SBATCH --account=fv3-cpu
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --output=/work/global_workflow_data/download-c48-%j.out
#SBATCH --error=/work/global_workflow_data/download-c48-%j.err

set -euo pipefail

DEST=/work/global_workflow_data
BUCKET=gs://wcoss-anton-space1

gcloud storage cp \
  "${BUCKET}/gfs_v17_c48_ics.tar.gz" \
  "${DEST}/gfs_v17_c48_ics.tar.gz"

gcloud storage cp \
  "${BUCKET}/gfs_v17_c48_fix.tar.gz" \
  "${DEST}/gfs_v17_c48_fix.tar.gz"

gcloud storage cp \
  "${BUCKET}/gfs_v17_c48_obs.tar.gz" \
  "${DEST}/gfs_v17_c48_obs.tar.gz"
```

## 11. Extract on WCOSS Lustre

Create `extract_c48_archives.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=extract_c48_archives
#SBATCH --account=fv3-cpu
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH --output=/work/global_workflow_data/extract-c48-%j.out
#SBATCH --error=/work/global_workflow_data/extract-c48-%j.err

set -euo pipefail

DEST=/work/global_workflow_data
ARCHIVE="${DEST}/gfs_v17_c48_archive"

mkdir -p "${ARCHIVE}"

tar -xzf "${DEST}/gfs_v17_c48_ics.tar.gz" \
  -C "${ARCHIVE}"

tar -xzf "${DEST}/gfs_v17_c48_fix.tar.gz" \
  -C "${ARCHIVE}"

tar -xzf "${DEST}/gfs_v17_c48_obs.tar.gz" \
  -C "${DEST}"
```

Submit:

```bash
sbatch extract_c48_archives.sh
```

The extracted layout is:

```text
/work/global_workflow_data/gfs_v17_c48_archive/C96C48/20250808
/work/global_workflow_data/gfs_v17_c48_archive/fix
/work/global_workflow_data/gdas.20211220
/work/global_workflow_data/gdas.20211221
/work/global_workflow_data/gfs.20211220
/work/global_workflow_data/gfs.20211221
```

## 12. Configure the experiment

Set:

```bash
export ICSDIR_ROOT=/work/global_workflow_data/gfs_v17_c48_archive
export RUNTESTS=/work/global_workflow_data/run
export DMPDIR=/work/global_workflow_data
export pslot=C96C48mx500_S2SW_cyc_gfs

mkdir -p "${RUNTESTS}"
test -d "${ICSDIR_ROOT}/C96C48/20250808"
test -d "${ICSDIR_ROOT}/fix"
test -d "${DMPDIR}/gdas.20211220"
test -d "${DMPDIR}/gdas.20211221"
```

Set up the experiment from the repository:

```bash
cd /home/anton_fernando_hpc_noaa_gov/global-workflow

source ush/detect_machine.sh
source dev/ush/load_modules.sh run

dev/ci/scripts/utils/ci_utils.sh create_experiment \
  dev/ci/cases/pr/C96C48mx500_S2SW_cyc_gfs.yaml \
  "${pslot}"
```

Verify that the experiment was created:

```bash
find "${RUNTESTS}/EXPDIR" -maxdepth 2 -type f \
  \( -name "*.xml" -o -name "config.base" \)
```

## 13. Cleanup

After successful GCS upload and checksum verification, remove temporary Ursa
archives only if no other user or process needs them:

```bash
rm -f /scratch4/NCEPDEV/stmp/${USER}/case-tars/gfs_v17_c48_*.tar.gz
rm -f /scratch4/NCEPDEV/stmp/${USER}/case-tars/obs_manifest.txt
```

Do not use broad recursive deletion. Remove only the named archive and
manifest files.
