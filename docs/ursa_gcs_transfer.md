# Transferring Data to and from Google Cloud Storage (GCS)

This guide explains how to move data between an NOAA HPC system (for example
Ursa or WCOSS) and a Google Cloud Storage bucket. It covers:

1. checking space and setting up a staging directory,
2. installing and authenticating the Google Cloud CLI (`gcloud`),
3. creating a bucket,
4. transferring data from login nodes only,
5. transferring larger data with Slurm batch jobs,
6. verifying transfers,
7. cleaning up.

Section 9 is a worked example that moves the data for the
`C96C48mx500_S2SW_cyc_gfs` case. Read the general sections first.

Each step states where it runs. The `gcloud` CLI runs on the HPC system (Ursa
or WCOSS), not on a Google Cloud VM. The location labels mean:

- **HPC login node**: a shared login node on Ursa or WCOSS. Use it only for
  short commands and moderate transfers.
- **HPC compute node**: a Slurm batch job, submitted from a login node with
  `sbatch`.
- **Your browser**: the Google sign-in page, opened on your own computer.
- **Google Cloud console**: the web interface, used only where a step says so.

The commands use these placeholders. Set them with `export` before running
the commands in this guide:

| Variable | Meaning | Example |
|---|---|---|
| `PROJECT` | Google Cloud project ID | `wcoss-eae-project-1` |
| `BUCKET` | Bucket URL | `gs://wcoss-anton-space1` |
| `LOCATION` | Bucket region | `us-central1` |
| `STAGING` | Scratch directory for archives and temporary files | `/scratch4/NCEPDEV/stmp/${USER}/transfers` |

Do not place service-account key files in source-code repositories or scripts.
Use the approved organization authentication method if browser login is not
available.

## 1. Check space and set up a staging directory

**Where:** HPC login node (Ursa or WCOSS).

Check the available scratch space and your quota:

```bash
df -h /scratch3 /scratch4
quota -s
lfs quota -u "${USER}" /scratch3 2>/dev/null || true
```

Create a staging directory on scratch for archives and temporary files:

```bash
export STAGING=/scratch4/NCEPDEV/stmp/${USER}/transfers
mkdir -p "${STAGING}"
```

Keep enough space for the source data being read, any archives you create, and
the transfer itself. Do not run `du` on large shared directory trees from a
login node. Check the size of the files you plan to transfer instead:

```bash
du -sh "${STAGING}"
```

Do not modify files in shared project directories. Remove only the temporary
archives you created, and only after their transfers are verified.

## 2. Install or load the Google Cloud CLI

**Where:** HPC login node. The installer is downloaded from `dl.google.com`
to the HPC system.

First check whether the module system provides the Google Cloud CLI:

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
directory with space for the installation. Do not use `sudo`. The examples below
use `/scratch3/NCEPDEV/global/${USER}`; use any directory you own.

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

To make this permanent, add the following to `~/.bashrc`:

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

A user installation under scratch is temporary storage. Back it up or reinstall
it if the system purges your user directory.

## 3. Authenticate gcloud

**Where:** HPC login node for the commands, and **your browser** for the sign-in.
The sign-in URL is opened on your own computer, and the verification code is
pasted back into the login-node terminal.

Run authentication on a login node. It needs an interactive browser step:

```bash
gcloud auth login --no-launch-browser
```

The command prints an authorization URL and waits for a verification code. Open
the URL in a browser where access to the GCP project is permitted, complete
Google sign-in and consent, copy the verification code, and paste it into the
terminal.

Set the project:

```bash
export PROJECT=wcoss-eae-project-1
gcloud config set project "${PROJECT}"
gcloud auth print-access-token >/dev/null
```

If the token has expired, run `gcloud auth login` again.

## 4. Create a GCS bucket (first time only)

**Where:** HPC login node, running the `gcloud` commands below. You can also
check the bucket in the **Google Cloud console** (Cloud Storage > Buckets).

Skip this section if the bucket already exists. Bucket names are unique across
all of Google Cloud, so choose a name that is not in use. Creating a bucket
requires permission to create buckets in the project.

Set the bucket name and location, then create the bucket:

```bash
export BUCKET=gs://wcoss-anton-space1
export LOCATION=us-central1

gcloud storage buckets create "${BUCKET}" \
  --project="${PROJECT}" \
  --location="${LOCATION}" \
  --uniform-bucket-level-access \
  --public-access-prevention
```

The options used here:

- `--uniform-bucket-level-access` applies IAM permissions to the whole bucket
  and disables per-object ACLs.
- `--public-access-prevention` blocks public access to the bucket. Keep it
  enabled for restricted data.

Confirm the bucket settings:

```bash
gcloud storage buckets describe "${BUCKET}" \
  --format="yaml(name,location,storage_class,iam_configuration)"
```

Verify access:

```bash
gcloud storage ls "${BUCKET}"
```

## 5. Transfer data from login nodes only

**Where:** HPC login node only.

Use the login-node path for moderate transfers, for example a few gigabytes.
For larger transfers, or any step that needs heavy compression or checksumming,
use section 6.

### 5.1 Login-node guidelines

- Run one transfer at a time. Do not start many parallel copy loops.
- Run the transfer inside `tmux` or `screen`, so it continues if your SSH
  session drops:

  ```bash
  tmux new -s transfer
  ```

  Detach with `Ctrl-b d`, and reattach with `tmux attach -t transfer`.

- Keep other login-node work light: about one minute, one core, and under 2 GB
  of memory per command.
- Do not create large compressed archives or compute many large checksums on a
  login node. Use section 6 for those.
- `gcloud storage` runs transfers in parallel for large files on its own. If a
  transfer is slow or the login node limits it, move the job to a compute node
  (section 6).

### 5.2 Upload files or directories

Upload a single file:

```bash
gcloud storage cp "${STAGING}/my_archive.tar.gz" "${BUCKET}/"
```

Upload a directory:

```bash
gcloud storage cp --recursive "${LOCAL_DIR}" "${BUCKET}/"
```

To upload a directory that was partly copied before, use `rsync`. It skips
files that already match and copies the rest:

```bash
gcloud storage rsync --recursive "${LOCAL_DIR}" "${BUCKET}/${REMOTE_DIR}"
```

### 5.3 Download files or directories

Download a single object:

```bash
gcloud storage cp "${BUCKET}/my_archive.tar.gz" "${LOCAL_DEST}/"
```

Download a directory:

```bash
gcloud storage cp --recursive "${BUCKET}/${REMOTE_DIR}" "${LOCAL_DEST}/"
```

### 5.4 List objects

```bash
gcloud storage ls -l "${BUCKET}/"
gcloud storage ls -l "${BUCKET}/${REMOTE_DIR}/**"
```

Check the transferred data as described in section 7.

## 6. Transfer larger data with Slurm batch jobs

**Where:** HPC compute node. Save the script on a login node, and submit it
there with `sbatch`.

Use a batch job when the data are large, when archives must be created first,
or when checksums must be computed. Edit the account, partition, and paths for
your system:

```bash
#!/bin/bash
#SBATCH --job-name=gcs_transfer
#SBATCH --account=<account>
#SBATCH --partition=<partition>
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=<log_dir>/gcs-transfer-%j.out
#SBATCH --error=<log_dir>/gcs-transfer-%j.err

set -euo pipefail

# Make gcloud available: load the module, or source your installation.
# source /scratch3/NCEPDEV/global/${USER}/google-cloud-sdk/path.bash.inc

PROJECT=wcoss-eae-project-1
BUCKET=gs://wcoss-anton-space1
STAGING=/scratch4/NCEPDEV/stmp/${USER}/transfers

mkdir -p "${STAGING}"

tar -I 'pigz -p 16' -cf "${STAGING}/my_archive.tar.gz" -C "${SRC_PARENT}" "${SRC_ITEM}"
gzip -t "${STAGING}/my_archive.tar.gz"
sha256sum "${STAGING}/my_archive.tar.gz" > "${STAGING}/my_archive.sha256"

gcloud storage cp "${STAGING}/my_archive.tar.gz" "${STAGING}/my_archive.sha256" "${BUCKET}/"
```

Notes:

- Authenticate on a login node first (section 3). The credentials are stored in
  your home directory, so batch jobs can use them when the home directory is
  shared across nodes. If a job fails with an authentication error, run
  `gcloud auth login` again on a login node.
- Do not run interactive login in a batch job. It needs a browser step.
- Submit the script with `sbatch`, and check the output file in `<log_dir>`.
- Use `tar -h` when the source contains symbolic links that must be stored as
  regular files.

## 7. Verify transfers

Verify every transfer before deleting its source or the staged copy.

### 7.1 Check local archives

**Where:** HPC login node for small archives. HPC compute node for large ones.

Check that each archive is a valid gzip file and record its SHA-256 value:

```bash
gzip -t "${STAGING}/my_archive.tar.gz"
sha256sum "${STAGING}/my_archive.tar.gz" | tee "${STAGING}/my_archive.sha256"
```

Compute SHA-256 values for large files on a compute node (section 6). Save the
SHA-256 values to compare them after transfer.

### 7.2 Compare with the GCS copy

**Where:** HPC login node for small files. HPC compute node for large local
files (the hash is slow there otherwise).

`gcloud storage` checks hashes automatically during `cp` and `rsync`. The
explicit comparison below gives you a record. It compares the CRC32C hash of the
local file with the hash stored for the object in GCS:

```bash
gcloud storage hash "${STAGING}/my_archive.tar.gz"
gcloud storage hash "${BUCKET}/my_archive.tar.gz"
```

The two CRC32C values must match. Local hashing is slow without the
`google-crc32c` package, so run `gcloud storage hash` on a compute node for
large local files.

### 7.3 Check a checksum file

**Where:** HPC login node.

If you copied a SHA-256 file to GCS, check that the copy matches the local file:

```bash
gcloud storage cp "${BUCKET}/my_archive.sha256" /tmp/my_archive.gcs.sha256
cmp -s "${STAGING}/my_archive.sha256" /tmp/my_archive.gcs.sha256
echo $?
rm -f /tmp/my_archive.gcs.sha256
```

Exit status `0` means the files match.

## 8. Clean up

**Where:** HPC login node (Ursa or WCOSS), on the HPC staging directory.

After the transfer is verified, remove temporary local archives only if no other
user or process needs them. Remove only the named files, and do not use broad
recursive deletion:

```bash
rm -f "${STAGING}/my_archive.tar.gz" "${STAGING}/my_archive.sha256"
```

## 9. Example: C96C48mx500 S2SW case data

**Where:** Ursa for 9.1 to 9.6 and 9.10, and WCOSS3 for 9.7 to 9.9. Each
subsection states its location.

This example packages, uploads, verifies, downloads, and extracts the data for
the `C96C48mx500_S2SW_cyc_gfs` case, from Ursa to GCS and then to WCOSS Lustre.
Use it as a model. The file lists are specific to this case and to the versions
in `versions/fix.ver`.

Do not package the entire `/scratch3/NCEPDEV/global/role.glopara/data`
directory. It contains unrelated datasets and some directories that may be
inaccessible.

The source data are:

| Data | Ursa location | Archive |
|---|---|---|
| Initial conditions (54 files, about 2.4 GB) | `/scratch3/NCEPDEV/global/role.glopara/data/ICSDIR/C96C48/20250808` | `gfs_v17_c48_ics.tar.gz` |
| FIX data (selected subdirectories, about 25 GB) | `/scratch3/NCEPDEV/global/role.glopara/fix` | `gfs_v17_c48_fix.tar.gz` |
| Atmospheric dumps (4 cycles, about 25 GB) | `/scratch3/NCEPDEV/global/role.glopara/dump` | `gfs_v17_c48_obs.tar.gz` |
| Marine observations (4 cycles, about 9 GB) | `/scratch3/NCEPDEV/global/role.glopara/data/experimental_obs` | `gfs_v17_c48_marine_obs.tar.gz` |

The file lists in this example were taken from the files staged and read by an
earlier successful run of this case, and checked against `link_workflow.sh`,
`parm/stage/*.j2`, and `ush/forecast_predet.sh`. Sizes are before compression.
Section 9.11 shows how each list was verified and how to repeat the checks.

Some of the data are restricted (group `rstprod`): the radiance
`gdas.t12z.radstat` in the initial conditions and several PREPBUFR and BUFR
dump files such as `adpsfc`. Confirm that copying them to GCS and WCOSS is
permitted before uploading.

The four archives total roughly 60 GB before compression. The FIX archive alone
is about 25 GB, mostly `aer` and `mom6`. Do not run `du` on the whole
`role.glopara` trees on a login node: `fix/aer/20250529` alone is 144 GB, and
the full `ICSDIR` and `dump` trees are very large. Check the generated archives
instead:

```bash
du -sh /scratch4/NCEPDEV/stmp/${USER}/case-tars
```

Do not create tar files if the generated archives would exceed your scratch
quota. Ask a system administrator or project lead for more quota, or reduce the
archives to the minimum required files.

Create the archive directory:

```bash
mkdir -p /scratch4/NCEPDEV/stmp/${USER}/case-tars
```

Use a Slurm compute node for all tar creation, downloads, and large uploads.

### 9.1 Create a minimal initial-condition archive

**Where:** Ursa compute node (Slurm batch job, `sbatch`).

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

### 9.2 Create a minimal FIX archive

**Where:** Ursa compute node (Slurm batch job, `sbatch`).

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
  (see section 9.9).
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

### 9.3 Create a minimal observation archive

**Where:** Ursa compute node (Slurm batch jobs, `sbatch`).

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

#### Marine observations

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

Do not include the other dump or experimental_obs dates in the archives.
They are not needed by this 20211220-20211221 test.

### 9.4 Validate the archives

**Where:** Ursa login node for `ls`. Ursa compute node for `gzip -t` and
`sha256sum`, because they read the full archives (section 7.1).

Use section 7 for the general checks. For this case, list the four archives and
their SHA-256 values, and check each gzip file:

```bash
OUT=/scratch4/NCEPDEV/stmp/${USER}/case-tars

ls -lh "${OUT}"/*.tar.gz
sha256sum "${OUT}"/gfs_v17_c48_*.tar.gz

gzip -t "${OUT}/gfs_v17_c48_ics.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_fix.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_obs.tar.gz"
gzip -t "${OUT}/gfs_v17_c48_marine_obs.tar.gz"
```

Save the SHA-256 values, and record them in `gfs_v17_c48_SHA256SUMS.txt`, for
comparison after transfer.

### 9.5 Upload the archives to GCS

**Where:** Ursa login node, running `gcloud` against the bucket. If the upload
hits session limits, run the same commands in a compute-node job (section 6).

The archives can be transferred directly from an Ursa login node if their
combined size fits the network and session limits. Authenticate on the login
node (section 3) and set the project:

```bash
export PROJECT=wcoss-eae-project-1
export BUCKET=gs://wcoss-anton-space1
gcloud config set project "${PROJECT}"
gcloud auth print-access-token >/dev/null
```

Upload the four archives and the checksum file:

```bash
OUT=/scratch3/NCEPDEV/global/Anton.Fernando

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

List the uploaded objects:

```bash
gcloud storage ls -l "${BUCKET}/gfs_v17_c48_*.tar.gz"
gcloud storage ls -l "${BUCKET}/gfs_v17_c48_SHA256SUMS.txt"
```

### 9.6 Verify the GCS copies

**Where:** Ursa login node for the checks. Run the `gcloud storage hash` on the
local archives on a compute node (section 7.2).

First verify the local archives against their recorded SHA-256 values. All four
checksum lines should end in `OK`:

```bash
cd /scratch3/NCEPDEV/global/Anton.Fernando
sha256sum -c gfs_v17_c48_SHA256SUMS.txt
```

Then compare the CRC32C value of each local archive with the stored value for
its GCS object (section 7.2):

```bash
for f in gfs_v17_c48_ics.tar.gz gfs_v17_c48_fix.tar.gz \
         gfs_v17_c48_obs.tar.gz gfs_v17_c48_marine_obs.tar.gz; do
  echo "local  ${f}: $(gcloud storage hash "${f}" | grep -i crc32c)"
  echo "gcs    ${f}: $(gcloud storage hash "${BUCKET}/${f}" | grep -i crc32c)"
done
```

Check the checksum file itself (section 7.3):

```bash
gcloud storage cp \
  "${BUCKET}/gfs_v17_c48_SHA256SUMS.txt" \
  /tmp/gfs_v17_c48_SHA256SUMS.gcs.txt

cmp -s \
  /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_SHA256SUMS.txt \
  /tmp/gfs_v17_c48_SHA256SUMS.gcs.txt
echo $?
```

Exit status `0` means the GCS checksum file matches the local file. Do not begin
the WCOSS download until the local SHA-256 checks, gzip checks, object listing,
CRC32C comparison, and checksum-file comparison all pass.

The four uploads made on 2026-11-24 have these GCS CRC32C values:

```text
gfs_v17_c48_ics.tar.gz:         cOrpTg==
gfs_v17_c48_fix.tar.gz:         LjT5mA==
gfs_v17_c48_obs.tar.gz:         EiKPOA==
gfs_v17_c48_marine_obs.tar.gz:  grAkyQ==
```

### 9.7 Download to WCOSS Lustre

**Where:** WCOSS3 login node for the `install` command. WCOSS3 compute node for
the download (Slurm batch job, `sbatch`).

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

### 9.8 Extract on WCOSS Lustre

**Where:** WCOSS3 compute node (Slurm batch job, `sbatch`).

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
ICSDIR="${DEST}/ICSDIR"
mkdir -p "${ICSDIR}"

tar -xzf "${DEST}/gfs_v17_c48_ics.tar.gz" \
  -C "${ICSDIR}"

tar -xzf "${DEST}/gfs_v17_c48_fix.tar.gz" \
  -C "${DEST}"

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
/work/global_workflow_data/ICSDIR/C96C48/20250808
/work/global_workflow_data/fix
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

### 9.9 Configure the experiment

**Where:** WCOSS3 login node, from a checkout of this repository.

Set:

```bash
export ICSDIR_ROOT=/work/global_workflow_data/ICSDIR
export RUNTESTS=/work/global_workflow_data/run
export DMPDIR=/work/global_workflow_data
export BASE_DATA=/work/global_workflow_data
export CRTM_FIX=/work/global_workflow_data/fix/crtm/v2.4.0.2
export pslot=C96C48mx500_S2SW_cyc_gfs

mkdir -p "${RUNTESTS}"
test -d "${ICSDIR_ROOT}/C96C48/20250808"
test -d "/work/global_workflow_data/fix"
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

### 9.10 Clean up the case archives

**Where:** Ursa login node.

After the GCS upload and checksum verification, remove the temporary Ursa
archives (section 8) only if no other user or process needs them. Remove only
the named files:

```bash
rm -f /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_*.tar.gz
rm -f /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_SHA256SUMS.txt
rm -f /scratch3/NCEPDEV/global/Anton.Fernando/gfs_v17_c48_ics_manifest.txt
```

### 9.11 How the file lists were verified

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

#### 9.11.1 Case settings

From the case YAMLs: cycled GFS, app `S2SW`, `C96` deterministic and `C48`
ensemble, `mx500` ocean, `2021122012` to `2021122100`, 2 ensemble members,
cold start from `ICSDIR_ROOT/C96C48/20250808`. `DO_JEDIOCNVAR=YES` (marine
DA), `DO_JEDIATMVAR=NO` and `DO_JEDIATMENS=NO` (GSI hybrid atmospheric DA).

#### 9.11.2 Initial conditions (54 files)

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

#### 9.11.3 FIX

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

#### 9.11.4 Atmospheric dumps

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
gfs 00). The archives include whole directories, which are about 25 GiB, to
avoid missing a file that a different run might read.

#### 9.11.5 Marine observations

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

#### 9.11.6 Checks on the generated scripts

Every path in `tar_c48_ics.sh`, `tar_c48_fix.sh`, `tar_c48_obs.sh`, and
`tar_c48_marine_obs.sh` was tested with `[[ -e <path> ]]` against the Ursa
source trees and all exist. The scripts also repeat that test at run time and
stop on the first missing item. The document was checked for non-ASCII
characters and trailing whitespace:

```bash
grep -nP '[^\x00-\x7F]| +$' docs/ursa_gcs_transfer.md   # prints nothing
```

#### 9.11.7 Not verified

- Whether the restricted (`rstprod`) files may be copied. This is a policy
  decision.
- Whether `gdas.t12z.radstat.tar` is required on the first cycle. It is
  staged when present, and `USE_RADSTAT` is `NO` for `RUN=gfs` in
  `parm/config/gfs/config.anal`. It is kept to match the reference run.
- The tar jobs themselves, the uploads, and the WCOSS-side run have not been
  executed. Run the section 9.4 and 9.6 checks and a short WCOSS test after
  transfer.
