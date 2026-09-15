#!/bin/bash
# Create per-forecast-hour and per-member .ecf files from master templates
# for the C96 S2SW ecFlow test suite.
#
# Usage:
#   cd dev/ecf/c96
#   bash setup_ecf_links.sh
set -eux

ECF_DIR=$(pwd)

################################################################################################
# GFS atmos product files (f000-f120 hourly)
cd "${ECF_DIR}/scripts/gfs/product/atmos/product"
echo "Copy gfs atmos product files ..."
rm -f jgfs_atmos_product_f*.ecf
fhr_start=0
fhr_end=120
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jgfs_atmos_product_master.ecf "jgfs_atmos_product_f${head_3d}.ecf"
  fhr_start=$((fhr_start + 1))
done

################################################################################################
# GFS ocean product files (every 6h from f006-f120)
cd "${ECF_DIR}/scripts/gfs/product/ocean"
echo "Copy gfs ocean product files ..."
rm -f jgfs_ocean_product_f*.ecf
fhr_start=6
fhr_end=120
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jgfs_ocean_product_master.ecf "jgfs_ocean_product_f${head_3d}.ecf"
  fhr_start=$((fhr_start + 6))
done

################################################################################################
# GFS ice product files (every 6h from f006-f120)
cd "${ECF_DIR}/scripts/gfs/product/ice"
echo "Copy gfs ice product files ..."
rm -f jgfs_ice_product_f*.ecf
fhr_start=6
fhr_end=120
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jgfs_ice_product_master.ecf "jgfs_ice_product_f${head_3d}.ecf"
  fhr_start=$((fhr_start + 6))
done

################################################################################################
# GFS wave post gridded files (f000-f120 hourly)
cd "${ECF_DIR}/scripts/gfs/product/wave/gridded"
echo "Copy gfs wave post gridded files ..."
rm -f jgfs_wave_post_gridded_f*.ecf
fhr_start=0
fhr_end=120
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jgfs_wave_post_gridded_master.ecf "jgfs_wave_post_gridded_f${head_3d}.ecf"
  fhr_start=$((fhr_start + 1))
done

################################################################################################
# GDAS atmos product files (f000-f009 hourly)
cd "${ECF_DIR}/scripts/gdas/product/atmos/product"
echo "Copy gdas atmos product files ..."
rm -f jgdas_atmos_product_f*.ecf
fhr_start=0
fhr_end=9
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jgdas_atmos_product_master.ecf "jgdas_atmos_product_f${head_3d}.ecf"
  fhr_start=$((fhr_start + 1))
done

################################################################################################
# GDAS wave post gridded files (f000-f009 hourly)
cd "${ECF_DIR}/scripts/gdas/product/wave/gridded"
echo "Copy gdas wave post gridded files ..."
rm -f jgdas_wave_post_gridded_f*.ecf
fhr_start=0
fhr_end=9
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jgdas_wave_post_gridded_master.ecf "jgdas_wave_post_gridded_f${head_3d}.ecf"
  fhr_start=$((fhr_start + 1))
done

################################################################################################
# EnKFGDAS atmos recenter files (000, 001, 002)
cd "${ECF_DIR}/scripts/enkfgdas/analysis/recenter"
echo "Copy enkfgdas ecen files ..."
rm -f jenkfgdas_atmos_ens_recenter[0-9][0-9][0-9].ecf
fhr_start=0
fhr_end=2
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jenkfgdas_atmos_ens_recenter_master.ecf "jenkfgdas_atmos_ens_recenter${head_3d}.ecf"
  fhr_start=$((fhr_start + 1))
done

################################################################################################
# EnKFGDAS forecast member files (mem001, mem002)
cd "${ECF_DIR}/scripts/enkfgdas/forecast"
echo "Copy enkfgdas fcst files ..."
rm -f jenkfgdas_fcst_mem*.ecf
mem_start=1
mem_end=2
while [[ "${mem_start}" -le "${mem_end}" ]]; do
  head_3d=$(printf "%03d" "${mem_start}")
  cp jenkfgdas_fcst_master.ecf "jenkfgdas_fcst_mem${head_3d}.ecf"
  mem_start=$((mem_start + 1))
done

################################################################################################
# EnKFGDAS ensemble post files (000-006 for fhr 3-9)
cd "${ECF_DIR}/scripts/enkfgdas/ensstat"
echo "Copy enkfgdas post files ..."
rm -f jenkfgdas_ens_post[0-9][0-9][0-9].ecf
fhr_start=0
fhr_end=6
while [[ "${fhr_start}" -le "${fhr_end}" ]]; do
  head_3d=$(printf "%03d" "${fhr_start}")
  cp jenkfgdas_ens_post_master.ecf "jenkfgdas_ens_post${head_3d}.ecf"
  fhr_start=$((fhr_start + 1))
done

echo ""
echo "=== setup_ecf_links.sh complete ==="
echo "Generated per-hour and per-member .ecf files from master templates."
