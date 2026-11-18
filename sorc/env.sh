#!/bin/bash
# -------------------------------------------------------------
# Setup script to load GFSv17 modules on GCP Nimbus
# Usage: source ~/load_modules.sh
# -------------------------------------------------------------

echo "----------------------------------------------------"
echo "Initializing GFSv17 Spack-Stack Environment..."
echo "----------------------------------------------------"

# 1. Source Intel compiler paths
echo "Sourcing Intel Compiler variables..."
source /opt/intel/oneapi/compiler/2026.1/env/vars.sh

# 2. Expose the required module folders
echo "Exposing Spack-stack & Dusan's local modules..."
module use /opt/intel/oneapi/modulefiles
module use /lfs/work/alexander_richert/stack/spack-stack/envs/nco-sci-oneapi-2026.1.0/modules_flat/Core
module use /lfs-c1b/home/dusan_jovic_hpc_noaa_gov/ufs/develop/ufs-weather-model/modulefiles

# 3. Load Python and PyYAML dependencies in order
echo "Loading Python & PyYAML dependencies..."
module load python/3.11.15
module load python-venv/1.0
module load py-pyyaml/6.0.3

# 4. Load the custom Nimbus module
echo "Loading ufs_nimbus.oneapi..."
module load ufs_nimbus.oneapi

# 5. Load MPI and scientific libraries
echo "Loading MPI & UFS libraries (ESMF, NetCDF, FMS)..."
module load mpi/2021.18
module load hdf5/1.14.5 netcdf-c/4.9.2 netcdf-fortran/4.6.1 parallelio/2.6.2 bacio/2.4.1 sp/2.5.0 ip/5.4.0 w3emc/2.13.0 g2/3.5.1 g2tmpl/1.17.0 esmf/8.8.0 fms/2025.03-gfs-constants

echo "----------------------------------------------------"
echo "Success! All GFSv17 modules successfully loaded."
echo "----------------------------------------------------"
module list

