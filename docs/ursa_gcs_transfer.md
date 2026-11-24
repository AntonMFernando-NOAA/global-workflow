# Transfer C96C48mx500 S2SW Case Data from Ursa to GCS

This guide describes how to package, upload, verify, download, and extract the
data required for the `C96C48mx500_S2SW_cyc_gfs` case.

Do not package the entire
`/scratch3/NCEPDEV/global/role.glopara/data` directory. It contains unrelated
datasets and some directories that may be inaccessible.

The source data are:

| Data | Ursa location | Archive |
|---|---|---|
| Initial conditions (54 files, about 2.4 GB) | `/scratch3/NCEPDEV/global/role.glopara/data/ICSDIR/C96C48/20250808` | `gfs_v17_c48_ics.tar.gz` |
| FIX data (selected subdirectories, about 25 GB) | `/scratch3/NCEPDEV/global/role.glopara/fix` | `gfs_v17_c48_fix.tar.gz` |
| Atmospheric dumps (4 cycles, about 25 GB) | `/scratch3/NCEPDEV/global/role.glopara/dump` | `gfs_v17_c48_obs.tar.gz` |
| Marine observations (4 cycles, about 9 GB) | `/scratch3/NCEPDEV/global/role.glopara/data/experimental_obs` | `gfs_v17_c48_marine_obs.tar.gz` |

The file lists in this guide were taken from the files staged and read by an
earlier successful run of this case, and checked against `link_workflow.sh`,
`parm/stage/*.j2`, and `ush/forecast_predet.sh`. Sizes are before compression.
Section 14 shows how each list was verified and how to repeat the checks.

Some of the data are restricted (group `rstprod`): the radiance
`gdas.t12z.radstat` in the initial conditions and several PREPBUFR and BUFR
dump files such as `adpsfc`. Confirm that copying them to GCS and WCOSS is
permitted before uploading.

The GCS destination is:

```text
gs://wcoss-anton-space1
```

Use a Slurm compute node for all tar creation, downloads, and uploads. Login
nodes are not appropriate for large or CPU-intensive transfers.

## 1. Check source and output space

On Ursa, check the source size and available scratch capacity:

```bash
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

The four archives total roughly 60 GB before compression (the FIX archive
alone is about 25 GB, mostly `aer` and `mom6`). Do not run `du` on the whole
`role.glopara` trees on a login node: `fix/aer/20250529` alone is 144 GB, and
the full `ICSDIR` and `dump` trees are very large. Check the size of the
generated archives instead:

```bash
du -sh /scratch4/NCEPDEV/stmp/${USER}/case-tars
```

Do not create tar files if the generated archives would exceed the scratch
quota. Ask a Ursa administrator or
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

The case cold starts at `2021122012` with `NMEM_ENS=2`. Only 54 files from
`C96C48/20250808` are staged: the `gdas.20211220` control and
`enkfgdas.20211220` members `mem001` and `mem002`. The other dates (`20220515`,
`20240223`, `20250327`), the 18z cycle, and the remaining ensemble members are
not needed.

Many files in `ICSDIR` are symlinks (for example `gdas.t12z.abias.txt` points
to `gdas.t12z.abias`), and `stage_ic` requests the link names. The archive uses
`tar -h` so the link names are stored as regular files.

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
MANIFEST="${OUT}/ics_manifest.txt"

mkdir -p "${OUT}"
cd "${ICROOT}"

{
  echo "C96C48/20250808/gdas.20211220/06/model/ocean/restart/20211220.120000.MOM.res.nc"
  echo "C96C48/20250808/gdas.20211220/06/model/wave/restart/20211220.120000.restart.ww3"
  for f in abias.txt abias_air.txt abias_int.txt abias_pc.txt radstat.tar; do
    echo "C96C48/20250808/gdas.20211220/12/analysis/atmos/gdas.t12z.${f}"
  done
  echo "C96C48/20250808/gdas.20211220/12/analysis/ice/20211220.120000.analysis.cice_model.res.nc"
  echo "C96C48/20250808/gdas.20211220/12/analysis/ocean/gdas.t12z.mom6_increment.i006.nc"

  atm=C96C48/20250808/gdas.20211220/12/model/atmos/input
  echo "${atm}/gfs_ctrl.nc"
  for t in 1 2 3 4 5 6; do
    echo "${atm}/gfs_data.tile${t}.nc"
    echo "${atm}/sfc_data.tile${t}.nc"
  done

  for mem in mem001 mem002; do
    ens=C96C48/20250808/enkfgdas.20211220
    echo "${ens}/06/${mem}/model/ocean/restart/20211220.120000.MOM.res.nc"
    echo "${ens}/12/${mem}/analysis/ice/20211220.120000.analysis.cice_model.res.nc"
    echo "${ens}/12/${mem}/analysis/ocean/enkfgdas.t12z.mom6_increment.i006.nc"
    echo "${ens}/12/${mem}/model/atmos/input/gfs_ctrl.nc"
    for t in 1 2 3 4 5 6; do
      echo "${ens}/12/${mem}/model/atmos/input/gfs_data.tile${t}.nc"
      echo "${ens}/12/${mem}/model/atmos/input/sfc_data.tile${t}.nc"
    done
  done
} > "${MANIFEST}"

# Expect 54 files
wc -l "${MANIFEST}"
while read -r f; do
  test -e "${ICROOT}/${f}" || { echo "Missing IC file: ${f}" >&2; exit 1; }
done < "${MANIFEST}"

tar -h -I 'pigz -p 16' -cf \
  "${OUT}/gfs_v17_c48_ics.tar.gz" \
  -C "${ICROOT}" -T "${MANIFEST}"

gzip -t "${OUT}/gfs_v17_c48_ics.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_ics.tar.gz"
ls -lh "${OUT}/gfs_v17_c48_ics.tar.gz"
```

`gdas.t12z.radstat.tar` is 1.8 GB and restricted (`rstprod`). It is staged only
if it exists, and it is the guess radstat read by the GSI analysis when
`USE_RADSTAT=YES`. If it may not be copied, remove `radstat.tar` from the loop
above and set `USE_RADSTAT=NO` in the experiment.

Submit:

```bash
chmod 0755 tar_c48_ics.sh
sbatch tar_c48_ics.sh
```

## 5. Create a minimal FIX archive

`sorc/link_workflow.sh` links a FIX version for each category, but this case
reads only part of each version directory. Do not archive whole FIX versions:
`aer/20250529` alone is 144 GB, and `mom6/20250128` is 17 GB. Archive only:

```text
aer/20250529/merra2.aerclim.2014-2023.m01..m12.nc   (IAER=1011, MERRA2_6ym off)
am/20220805
cice/20240416/500
cpl/20230526/aC48o500, aC96o500
gsi/20251105
lut/20220805
mom6/20250128/500
orog/20240917/C48, C96
ugwd/20240624/C48, C96, ugwp_limb_tau.nc
verif/20220805
wave/20260622
crtm/v2.4.0.2
gdas/fv3jedi/20241115
gdas/obs/20240213
gdas/soca/20250519
gdas/snow/20241210
```

Notes:

- `crtm/v2.4.0.2` is not in `versions/fix.ver`. It is the `CRTM_FIX` set by
  `modulefiles/gw_run.<machine>.lua` and is required by the GSI analysis. There
  is no `gw_run.nimbus` modulefile, so `CRTM_FIX` must be set by hand on WCOSS3
  (see section 12).
- `chem`, `datm`, `sfc_climo`, `gdas/gsibec`, and `gdas/aero` are linked by
  `link_workflow.sh` but are not read by this case (no aerosol or JEDI
  atmospheric DA, cold start from existing ICs). The links will dangle, which is
  harmless.
- Keep the `fix/<category>/<version>/...` layout so `link_workflow.sh` finds
  `${FIX_DIR}/<category>/<version>`.
- `fix.ver` versions must match the directories above. If `versions/fix.ver`
  changes, update this list.

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

FIX_ITEMS=()
for month in 01 02 03 04 05 06 07 08 09 10 11 12; do
  FIX_ITEMS+=("fix/aer/20250529/merra2.aerclim.2014-2023.m${month}.nc")
done

FIX_ITEMS+=(
  fix/am/20220805
  fix/cice/20240416/500
  fix/cpl/20230526/aC48o500
  fix/cpl/20230526/aC96o500
  fix/gsi/20251105
  fix/lut/20220805
  fix/mom6/20250128/500
  fix/orog/20240917/C48
  fix/orog/20240917/C96
  fix/ugwd/20240624/C48
  fix/ugwd/20240624/C96
  fix/ugwd/20240624/ugwp_limb_tau.nc
  fix/verif/20220805
  fix/wave/20260622
  fix/crtm/v2.4.0.2
  fix/gdas/fv3jedi/20241115
  fix/gdas/obs/20240213
  fix/gdas/soca/20250519
  fix/gdas/snow/20241210
)

for item in "${FIX_ITEMS[@]}"; do
  test -e "${FIXPARENT}/${item}" ||
    { echo "Missing FIX item: ${FIXPARENT}/${item}" >&2; exit 1; }
done

tar -h -I 'pigz -p 16' -cf \
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

## 6. Create a minimal observation archive

The case spans `2021122012` through `2021122100`. The atmospheric dump files
read by the case are in these directories (the `atmos` entry in each cycle
directory is a symlink to `./`, so the files sit directly under `HH/`):

```text
gdas.20211220/18
gdas.20211221/00
gfs.20211220/18
gfs.20211221/00
gdas.20211220/12/gdas.t12z.updated.status.tm00.bufr_d   (single file)
```

The `06` cycles and the rest of `gdas.20211220/12` are not read. The four
directories are about 25 GB. Many of the PREPBUFR/BUFR files are restricted
(`rstprod`).

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

mkdir -p "${OUT}"

items=(
  gdas.20211220/18
  gdas.20211221/00
  gfs.20211220/18
  gfs.20211221/00
  gdas.20211220/12/gdas.t12z.updated.status.tm00.bufr_d
)

for item in "${items[@]}"; do
  test -e "${OBSROOT}/${item}" ||
    { echo "Missing OBS item: ${OBSROOT}/${item}" >&2; exit 1; }
done

tar -I 'pigz -p 16' -cf \
  "${OUT}/gfs_v17_c48_obs.tar.gz" \
  -C "${OBSROOT}" "${items[@]}"

gzip -t "${OUT}/gfs_v17_c48_obs.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_obs.tar.gz"
tar -tzf "${OUT}/gfs_v17_c48_obs.tar.gz" | head
ls -lh "${OUT}/gfs_v17_c48_obs.tar.gz"
```

Submit:

```bash
chmod 0755 tar_c48_obs.sh
sbatch tar_c48_obs.sh
```

### Marine observations

The case sets `DO_JEDIOCNVAR=YES`, so `prepoceanobs` reads marine
observations from `${BASE_DATA}/experimental_obs` (`dmpdir_exp` in
`dev/parm/config/gfs/yaml/defaults.yaml`). The `gdas.*` and `gfs.*` copies are
separate files and both are read. Only `adt`, `icec`, `sss`, and `sst`, plus the
status log, hold data (about 9 GB); the empty `insitu` directory is kept so the
layout matches. `atmos` is not read.

Create `tar_c48_marine_obs.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=tar_c48_marine_obs
#SBATCH --account=fv3-cpu
#SBATCH --partition=u1-compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-marine-%j.out
#SBATCH --error=/scratch3/NCEPDEV/global/Anton.Fernando/tar-c48-marine-%j.err

set -euo pipefail

MARINEROOT=/scratch3/NCEPDEV/global/role.glopara/data/experimental_obs
OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars

mkdir -p "${OUT}"

items=()
for run in gdas gfs; do
  for cyc in 20211220/18 20211221/00; do
    pdy=${cyc%/*}
    hh=${cyc#*/}
    base="${run}.${pdy}/${hh}/ocean"
    for sub in adt icec insitu sss sst; do
      items+=("${base}/${sub}")
    done
    items+=("${base}/${run}.t${hh}z.obsforge_marine_status.log")
  done
done

for item in "${items[@]}"; do
  test -e "${MARINEROOT}/${item}" ||
    { echo "Missing marine item: ${MARINEROOT}/${item}" >&2; exit 1; }
done

tar -h -I 'pigz -p 16' -cf \
  "${OUT}/gfs_v17_c48_marine_obs.tar.gz" \
  -C "${MARINEROOT}" "${items[@]}"

gzip -t "${OUT}/gfs_v17_c48_marine_obs.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_marine_obs.tar.gz"
tar -tzf "${OUT}/gfs_v17_c48_marine_obs.tar.gz" | head
ls -lh "${OUT}/gfs_v17_c48_marine_obs.tar.gz"
```

Submit:

```bash
chmod 0755 tar_c48_marine_obs.sh
sbatch tar_c48_marine_obs.sh
```

Do not include the other dump or experimental_obs dates in the Ursa listings.
They are not needed by this 20211220-20211221 test.

## 7. Validate all Ursa archives

```bash
OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars

ls -lh "${OUT}"/*.tar.gz
sha256sum "${OUT}/gfs_v17_c48_ics.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_fix.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_obs.tar.gz"
sha256sum "${OUT}/gfs_v17_c48_marine_obs.tar.gz"

gzip -t "${OUT}/gfs_v17_c48_ics.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_fix.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_obs.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_marine_obs.tar.gz"
```

Save the SHA-256 values for comparison after transfer.

## 8. Upload the archives to GCS

The archives can be transferred directly from an Ursa login node if their
combined size fits the network/session limits. Authenticate from the terminal:

```bash
gcloud auth login anton.fernando@hpc.noaa.gov --no-launch-browser
gcloud config set project wcoss-eae-project-1
gcloud auth print-access-token >/dev/null
```

The login command prints an authorization URL and then waits for a verification
code. Open the URL in a browser, complete Google sign-in and consent, copy the
verification code, and paste it into the terminal. Do not run this command in a
Slurm job: it requires interactive browser authentication.

If the active token has expired, run `gcloud auth login` again. Then upload the
four archives and checksum file:

```bash
OUT=/scratch3/NCEPDEV/global/Anton.Fernando
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

gcloud storage cp \
  "${OUT}/gfs_v17_c48_marine_obs.tar.gz" \
  "${BUCKET}/gfs_v17_c48_marine_obs.tar.gz"

gcloud storage cp \
  "${OUT}/gfs_v17_c48_SHA256SUMS.txt" \
  "${BUCKET}/gfs_v17_c48_SHA256SUMS.txt"
```

Verify the GCS objects:

```bash
gcloud storage ls -l gs://wcoss-anton-space1/gfs_v17_c48_*.tar.gz
gcloud storage ls -l gs://wcoss-anton-space1/gfs_v17_c48_SHA256SUMS.txt
```

## 9. Verify GCS hashes

First verify the local archives and their recorded SHA-256 values:

```bash
cd /scratch3/NCEPDEV/global/Anton.Fernando
sha256sum -c gfs_v17_c48_SHA256SUMS.txt
gzip -t gfs_v17_c48_ics.tar.gz
gzip -t gfs_v17_c48_fix.tar.gz
gzip -t gfs_v17_c48_obs.tar.gz
gzip -t gfs_v17_c48_marine_obs.tar.gz
```

All four checksum lines should end in `OK`, and each `gzip -t` should return
without an error.

Get the GCS CRC32C hash for each uploaded object:

```bash
gcloud storage hash gs://wcoss-anton-space1/gfs_v17_c48_ics.tar.gz
gcloud storage hash gs://wcoss-anton-space1/gfs_v17_c48_fix.tar.gz
gcloud storage hash gs://wcoss-anton-space1/gfs_v17_c48_obs.tar.gz
gcloud storage hash gs://wcoss-anton-space1/gfs_v17_c48_marine_obs.tar.gz
```

The successful upload and GCS CRC32C digest provide GCS-side integrity
verification. GCS `gcloud storage hash` reports CRC32C and, when available,
MD5; it does not report SHA-256. To verify the checksum file itself was copied
byte-for-byte:

```bash
gcloud storage cp \
  gs://wcoss-anton-space1/gfs_v17_c48_SHA256SUMS.txt \
  /tmp/gfs_v17_c48_SHA256SUMS.gcs.txt

cmp -s \
  /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_SHA256SUMS.txt \
  /tmp/gfs_v17_c48_SHA256SUMS.gcs.txt
echo $?
```

Exit status `0` means the GCS checksum file matches the local file. Do not begin
the WCOSS download until the local SHA-256 checks, gzip checks, object listing,
and checksum-file comparison all pass.

The four uploads made on 2026-11-24 have these GCS CRC32C values:

```text
gfs_v17_c48_ics.tar.gz:         cOrpTg==
gfs_v17_c48_fix.tar.gz:         LjT5mA==
gfs_v17_c48_obs.tar.gz:         EiKPOA==
gfs_v17_c48_marine_obs.tar.gz:  grAkyQ==
```

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

gcloud storage cp \
  "${BUCKET}/gfs_v17_c48_marine_obs.tar.gz" \
  "${DEST}/gfs_v17_c48_marine_obs.tar.gz"
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

mkdir -p "${DEST}/experimental_obs"
tar -xzf "${DEST}/gfs_v17_c48_marine_obs.tar.gz" \
  -C "${DEST}/experimental_obs"
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
/work/global_workflow_data/experimental_obs/gdas.20211220
/work/global_workflow_data/experimental_obs/gdas.20211221
/work/global_workflow_data/experimental_obs/gfs.20211220
/work/global_workflow_data/experimental_obs/gfs.20211221
```

`dev/workflow/hosts/nimbus.yaml` sets `DMPDIR` and `BASE_DATA` to
`/work/global_workflow_data`, so the dump directories and `experimental_obs`
must sit directly under it.

## 12. Configure the experiment

Set:

```bash
export ICSDIR_ROOT=/work/global_workflow_data/gfs_v17_c48_archive
export RUNTESTS=/work/global_workflow_data/run
export DMPDIR=/work/global_workflow_data
export BASE_DATA=/work/global_workflow_data
export CRTM_FIX=${ICSDIR_ROOT}/fix/crtm/v2.4.0.2
export pslot=C96C48mx500_S2SW_cyc_gfs

mkdir -p "${RUNTESTS}"
test -d "${ICSDIR_ROOT}/C96C48/20250808"
test -d "${ICSDIR_ROOT}/fix"
test -d "${CRTM_FIX}"
test -d "${DMPDIR}/gdas.20211220"
test -d "${DMPDIR}/gdas.20211221"
test -d "${BASE_DATA}/experimental_obs/gdas.20211221"
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
rm -f /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_*.tar.gz
rm -f /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_SHA256SUMS.txt
rm -f /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_ics_manifest.txt
```

Do not use broad recursive deletion. Remove only the named archive and
manifest files.

## 14. How the file lists were verified

The lists above were not guessed. Each one was derived from an earlier
successful run of this case on Ursa and cross-checked against the workflow
code. All checks were short, read-only commands (`ls`, `stat`, `grep`, and
`du` limited with `timeout`) and none were run on whole data trees.

Reference run:

```bash
RUN=/scratch3/NCEPDEV/global/Anton.Fernando/RUNTESTS/COMROOT/C96C48mx500_S2SW_cyc_gfs
```

Limits of this evidence: it shows what the run staged and read, not what a
different configuration might need. The reference experiment's `config.base`
was from an older checkout, so the case switches were taken from
`dev/ci/cases/pr/C96C48mx500_S2SW_cyc_gfs.yaml` and
`dev/ci/cases/yamls/gfs_cyc_defaults_ci.yaml` instead. Re-run the checks below
if the case YAML or `versions/fix.ver` changes.

### 14.1 Case settings

From the case YAMLs: cycled GFS, app `S2SW`, `C96` deterministic and `C48`
ensemble, `mx500` ocean, `2021122012` to `2021122100`, 2 ensemble members,
cold start from `ICSDIR_ROOT/C96C48/20250808`. `DO_JEDIOCNVAR=YES` (marine
DA), `DO_JEDIATMVAR=NO` and `DO_JEDIATMENS=NO` (GSI hybrid atmospheric DA).

### 14.2 Initial conditions (54 files)

The `stage_ic` task links its inputs from `ICSDIR` into `COMROOT`. List the
links that point at `ICSDIR`, and confirm each target exists:

```bash
cd "${RUN}"
find . -type l -lname '*ICSDIR*' -printf '%l\n' |
  sed 's#.*/C96C48/20250808/##' | sort > /tmp/ic_list.txt
wc -l /tmp/ic_list.txt        # 54
ICS=/scratch3/NCEPDEV/global/role.glopara/data/ICSDIR/C96C48/20250808
while read -r f; do [[ -e "${ICS}/${f}" ]] || echo "MISSING ${f}"; done \
  < /tmp/ic_list.txt          # prints nothing
rm -f /tmp/ic_list.txt
```

Result: 54 links, none dangling, covering exactly the `gdas.20211220` and
`enkfgdas.20211220` (`mem001`, `mem002`) files in `tar_c48_ics.sh`. This agrees
with `parm/stage/{master_gfs,analysis,atmosphere_cold,ocean,ice,wave}.yaml.j2`.
The same links, resolved with `stat -L`, total 2.43 GiB.

### 14.3 FIX

Find the FIX paths the run actually opened, by category:

```bash
cd "${RUN}/logs"
for k in aer am gsi lut orog ugwd mom6 cice cpl wave verif; do
  echo "== ${k}"
  grep -rhoE "/fix/${k}/[0-9]+/[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?" . |
    sort | uniq -c | sort -rn | head -8
done
grep -rh "crtm/v2.4.0.2" . | head -1
```

Results and the code that explains them:

- `mom6/500` and `cice/500` were the only mom6 and cice subdirectories used.
- `aer`: `ush/forecast_predet.sh` copies only
  `merra2.aerclim.2014-2023.m01..m12.nc` when `IAER=1011` and
  `MERRA2_6ym` is off. The `y*` directories are used only when
  `MERRA2_6ym=.true.`.
- `orog` and `ugwd`: `ush/forecast_predet.sh` reads `${CASE}` subdirectories,
  so only `C48` and `C96`, plus `ugwd/ugwp_limb_tau.nc`.
- `cpl`: `${FIXglobal}/cpl/a${CASE}o${OCNRES}`, so `aC48o500` and `aC96o500`.
- `crtm`: `modulefiles/gw_run.ursa.lua` sets `CRTM_FIX` to
  `fix/crtm/v2.4.0.2`, and the GSI analysis log shows 2812 references to it.
  It is not in `versions/fix.ver`.
- Dropped as unreferenced: the logs have zero references to `sfc_climo`,
  `datm`, `gdas/gsibec`, and `gdas/aero`. `chem` appears only as the
  `FIXchem` environment variable string, not as a file that was opened.

The size claims were checked per directory with
`du -shL <path>` under `timeout`, for example `aer/20250529` 144G,
`mom6/20250128` 17G, `orog/20240917/C96` 399M, `crtm/v2.4.0.2` 3.4G.

### 14.4 Atmospheric dumps

```bash
cd "${RUN}/logs"
grep -rhoE "role.glopara/dump/(gdas|gfs)\.[0-9]{8}/[0-9]{2}/atmos/[A-Za-z0-9_.+-]+" . |
  sed 's#role.glopara/dump/##; s#/atmos/#/#' | sort -u > /tmp/dump_used.txt
awk -F/ '{print $1"/"$2}' /tmp/dump_used.txt | sort | uniq -c
rm -f /tmp/dump_used.txt
```

Result: 79 files in `gdas.20211220/18`, 75 in `gdas.20211221/00`, 77 in
`gfs.20211220/18`, 75 in `gfs.20211221/00`, and one file in
`gdas.20211220/12` (`gdas.t12z.updated.status.tm00.bufr_d`). No `06` cycle was
read.

The `atmos` entry in each cycle directory is a symlink to `./`:

```bash
ls -ld /scratch3/NCEPDEV/global/role.glopara/dump/gdas.20211220/18/atmos
# lrwxrwxrwx ... atmos -> ./
```

So the data files sit directly under `HH/`, and tarring `.../atmos` would store
only the link.

Sizes, summed with `stat -L -c %s`: the files read total 25.4 GiB, and the
whole directories are 7.6, 7.1, 5.2, and 5.5 GiB (gdas 18, gdas 00, gfs 18,
gfs 00). The doc archives whole directories, which are about 25 GiB, to avoid
missing a file that a different run might read.

### 14.5 Marine observations

```bash
cd "${RUN}/logs"
grep -rhoE "experimental_obs/(gdas|gfs)\.[0-9]{8}/[0-9]{2}/ocean/[a-z]+" . |
  sort | uniq -c
```

Result: `icec`, `sss`, and `sst` were read for both `20211220/18` and
`20211221/00`, and `adt` only for `20211221/00`, in both the `gdas.*` and
`gfs.*` trees. `insitu` was not read, and the directory is empty (4.0K). The
`gdas.*` and `gfs.*` files have different inodes, so they are separate copies
and both must be archived.

The path comes from `dmpdir_exp` in
`dev/parm/config/gfs/yaml/defaults.yaml` (`${BASE_DATA}/experimental_obs`),
which `dev/parm/config/gfs/config.prepoceanobs.j2` uses as `DMPDIR`.

### 14.6 Checks on the generated scripts

Every path in `tar_c48_ics.sh`, `tar_c48_fix.sh`, `tar_c48_obs.sh`, and
`tar_c48_marine_obs.sh` was tested with `[[ -e <path> ]]` against the Ursa
source trees and all exist. The scripts also repeat that test at run time and
stop on the first missing item. The document was checked for non-ASCII
characters and trailing whitespace:

```bash
grep -nP '[^\x00-\x7F]| +$' docs/ursa_gcs_transfer.md   # prints nothing
```

### 14.7 Not verified

- Whether the restricted (`rstprod`) files may be copied. This is a policy
  decision.
- Whether `gdas.t12z.radstat.tar` is required on the first cycle. It is
  staged when present, and `USE_RADSTAT` is `NO` for `RUN=gfs` in
  `parm/config/gfs/config.anal`. It is kept to match the reference run.
- The tar jobs themselves, the uploads, and the WCOSS-side run have not been
  executed. Run the section 7 checks and a short WCOSS test after transfer.
