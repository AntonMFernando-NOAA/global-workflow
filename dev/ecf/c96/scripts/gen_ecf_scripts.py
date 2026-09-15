#!/usr/bin/env python3
"""Generate all .ecf task scripts for the C96 S2SW ecFlow test suite.

Produces .ecf files with hardcoded WCOSS2 #PBS resources sized for C96
resolution. Uses the same module loading patterns, J-script calls, and
variable exports as the production gfs/scripts/ .ecf files.

Resource scaling from production (C768/C1152) to C96:
  - Forecast: GFS 295→6 nodes, GDAS 95→4, EnKF member 8→2
  - Analysis (GSI): 100→6 nodes
  - EnKF update: 35→4
  - EnKF observer: 4→2
  - Most single-node tasks: unchanged
"""

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


# ── Helpers ─────────────────────────────────────────────────

def write_ecf(relpath, pbs_name, walltime, select, place, module_type,
              jscript, exports=None, manual_text="", direct_modules=None):
    """Write a single .ecf file.

    Parameters
    ----------
    relpath : str
        Path relative to SCRIPT_DIR (e.g. "gdas/analysis/atmos/jgdas_atmos_anal.ecf")
    pbs_name : str
        PBS job name pattern (with %CYC% etc.)
    walltime : str
        Walltime (HH:MM:SS)
    select : str
        PBS select= resource string
    place : str
        PBS place= string
    module_type : str or None
        Argument to load_modules.sh (run, gsi, ufswm, ufsda, upp) or None for no modules
    jscript : str
        Path to the J-script (e.g. "${HOMEgfs}/jobs/JGLOBAL_FORECAST")
    exports : list of str or None
        Extra export lines to include before the J-script call
    manual_text : str
        Content for the %manual section
    direct_modules : list of str or None
        Direct module load commands (for FSM tasks that don't use load_modules.sh)
    """
    filepath = SCRIPT_DIR / relpath
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"#PBS -S /bin/bash")
    lines.append(f"#PBS -N {pbs_name}")
    lines.append(f"#PBS -j oe")
    lines.append(f"#PBS -q %QUEUE%")
    lines.append(f"#PBS -A %PROJ%-%PROJENVIR%")
    lines.append(f"#PBS -l walltime={walltime}")
    lines.append(f"#PBS -l select={select}")
    lines.append(f"#PBS -l place={place}")
    lines.append(f"#PBS -l debug=true")
    lines.append(f"")
    lines.append(f"model=gfs")
    lines.append(f'export cyc="%CYC%"')
    lines.append(f"%include <head.h>")
    lines.append(f"%include <envir-p1.h>")
    lines.append(f"")
    lines.append(f"############################################################")
    lines.append(f"# Load modules")
    lines.append(f"############################################################")

    if direct_modules:
        for m in direct_modules:
            lines.append(m)
    elif module_type:
        lines.append(f"source ${{HOMEgfs}}/dev/ush/load_modules.sh {module_type}")

    lines.append(f"")
    lines.append(f"module list")

    if exports:
        for exp in exports:
            lines.append(exp)

    lines.append(f"############################################################")
    lines.append(f"# CALL executable job script here")
    lines.append(f"############################################################")
    lines.append(f"export HOMEglobal=${{HOMEgfs}}")
    lines.append(f"")
    lines.append(f"{jscript}")
    lines.append(f"if [ $? -ne 0 ]; then")
    lines.append(f'   ecflow_client --msg="***JOB ${{ECF_NAME}} ERROR RUNNING J-SCRIPT ***"')
    lines.append(f"   ecflow_client --abort")
    lines.append(f"   exit")
    lines.append(f"fi")
    lines.append(f"")
    lines.append(f"%include <tail.h>")

    if manual_text:
        lines.append(f"%manual")
        lines.append(f"")
        lines.append(manual_text)
        lines.append(f"")
        lines.append(f"%end")

    lines.append(f"")

    filepath.write_text("\n".join(lines))
    return filepath


def write_master_ecf(relpath, pbs_name, walltime, select, place, module_type,
                     jscript, exports=None, manual_text=""):
    """Write a master template .ecf file (per-FHR or per-member)."""
    return write_ecf(relpath, pbs_name, walltime, select, place, module_type,
                     jscript, exports, manual_text)


# ── GFS tasks ───────────────────────────────────────────────

def gen_gfs_scripts():
    """Generate all GFS .ecf scripts."""

    # prep/atmos
    write_ecf(
        "gfs/prep/atmos/jgfs_atmos_emcsfc_sfc_prep.ecf",
        "%RUN%_atmos_emcsfc_sfc_prep_%CYC%", "00:07:00",
        "1:ncpus=1:mem=10GB", "vscatter",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_PREP_SFC",
    )

    # prep/marine
    write_ecf(
        "gfs/prep/marine/jgfs_marine_obs_bufr_dump.ecf",
        "%RUN%_marine_obs_bufr_dump_%CYC%", "00:15:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=3GB", "vscatter:shared",
        "run", "${HOMEgfs}/jobs/JGLOBAL_MARINE_OBS_BUFR_DUMP",
    )
    write_ecf(
        "gfs/prep/marine/jgfs_marine_obs_dump.ecf",
        "%RUN%_marine_obs_dump_%CYC%", "00:30:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=48GB", "vscatter:shared",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_MARINE_OBS_PREP",
    )

    # init/wave
    write_ecf(
        "gfs/init/wave/jgfs_wave_init.ecf",
        "gfs_wave_init_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=4GB", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_INIT",
    )

    # analysis/atmos
    write_ecf(
        "gfs/analysis/atmos/jgfs_atmos_anal.ecf",
        "gfs_atmos_anal_%CYC%", "00:30:00",
        "6:mpiprocs=16:ompthreads=8:ncpus=128", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_ANALYSIS",
    )
    write_ecf(
        "gfs/analysis/atmos/jgfs_atmos_anal_sfc_gcycle.ecf",
        "gfs_atmos_anal_sfc_gcycle_%CYC%", "00:10:00",
        "1:mpiprocs=32:ompthreads=4:ncpus=128", "vscatter:exclhost",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_SFCANL_GCYCLE",
    )
    write_ecf(
        "gfs/analysis/atmos/jgfs_atmos_anal_calc.ecf",
        "gfs_atmos_anal_calc_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_ANALYSIS_CALC",
    )
    write_ecf(
        "gfs/analysis/atmos/jgfs_atmos_analupp.ecf",
        "gfs_atmos_analupp_%CYC%", "00:10:00",
        "1:mpiprocs=120:ompthreads=1:ncpus=120:mem=128GB", "vscatter:exclhost",
        "upp", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_UPP",
        exports=["export FORECAST_HOUR='0'", "export FHR3='000'",
                 "export UPP_RUN='analysis'"],
    )

    # analysis/marine
    for task, jscript, wall, sel, plc in [
        ("jgfs_marine_bmat_init", "JGLOBAL_MARINE_BMAT_INITIALIZE", "00:15:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=24GB", "vscatter:shared"),
        ("jgfs_marine_bmat", "JGLOBAL_MARINE_BMAT", "00:15:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
        ("jgfs_marine_anal_init", "JGLOBAL_MARINE_ANALYSIS_INITIALIZE", "00:15:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
        ("jgfs_marine_analvar", "JGLOBAL_MARINE_ANALYSIS_VARIATIONAL", "00:20:00",
         "4:mpiprocs=64:ompthreads=1:ncpus=64:mem=500GB", "vscatter:exclhost"),
        ("jgfs_marine_analchkpt", "JGLOBAL_MARINE_ANALYSIS_CHECKPOINT", "00:10:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
        ("jgfs_marine_analfinal", "JGLOBAL_MARINE_ANALYSIS_FINALIZE", "00:10:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
    ]:
        write_ecf(
            f"gfs/analysis/marine/{task}.ecf",
            f"{task.replace('jgfs_', 'gfs_')}_%CYC%", wall, sel, plc,
            "ufsda", f"${{HOMEgfs}}/jobs/{jscript}",
        )

    # analysis/snow
    write_ecf(
        "gfs/analysis/snow/jgfs_atmos_analsnow.ecf",
        "gfs_atmos_analsnow_%CYC%", "00:10:00",
        "2:mpiprocs=64:ompthreads=2:ncpus=128", "vscatter:shared",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_SNOW_ANALYSIS",
    )

    # forecast
    write_ecf(
        "gfs/forecast/jgfs_fcst.ecf",
        "gfs_fcst_%CYC%", "01:30:00",
        "6:mpiprocs=128:ompthreads=1:ncpus=128", "vscatter:exclhost",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_FORECAST",
        exports=["export FCST_SEGMENT='0'"],
    )
    write_ecf(
        "gfs/forecast/jgfs_fcst_manager.ecf",
        "gfs_fcst_manager_%CYC%", "01:30:00",
        "1:ncpus=14:ompthreads=1:mem=20GB", "vscatter:shared",
        "run", "${HOMEglobal}/jobs/JGLOBAL_FORECAST_MANAGER",
        exports=["export FCST_SEGMENT='0'"],
    )
    write_ecf(
        "gfs/forecast/jgfs_fcst_fsm.ecf",
        "gfs_fcst_fsm_%CYC%", "01:30:00",
        "1:ncpus=1:ompthreads=1:mem=20GB", "vscatter:shared",
        None, "${HOMEgfs}/jobs/JGLOBAL_FSM",
        exports=["export RJN='%RJN%'"],
        direct_modules=["module load intel/${intel_ver}", "module load craype/${craype_ver}"],
    )

    # product/atmos
    write_master_ecf(
        "gfs/product/atmos/product/jgfs_atmos_product_master.ecf",
        "gfs_atmos_product_%CYC%_f%FHR%", "00:30:00",
        "1:mpiprocs=24:ompthreads=1:ncpus=24", "vscatter:exclhost",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_PRODUCTS",
        exports=['export WGF="%WGF%"', 'export FHR="%FHR%"',
                 'export FHR_LIST="%FHR_LIST%"',
                 'export FORECAST_HOUR="${FHR_LIST}"',
                 'export COMPONENT=${WGF}'],
    )
    write_ecf(
        "gfs/product/atmos/jgfs_atmos_analprod.ecf",
        "gfs_atmos_analprod_%CYC%", "00:10:00",
        "1:mpiprocs=24:ompthreads=1:ncpus=24", "vscatter:exclhost",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_PRODUCTS",
        exports=["export FORECAST_HOUR='-1'", "export FHR_LIST='-1'"],
    )

    # product/ocean
    write_master_ecf(
        "gfs/product/ocean/jgfs_ocean_product_master.ecf",
        "gfs_ocean_product_%CYC%_f%FHR%", "00:30:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=96GB", "vscatter:shared",
        "run", "${HOMEgfs}/jobs/JGLOBAL_OCEANICE_PRODUCTS",
        exports=['export WGF="%WGF%"', 'export FHR="%FHR%"',
                 'export FHR_LIST="%FHR_LIST%"',
                 'export FORECAST_HOUR="${FHR_LIST}"',
                 'export COMPONENT=${WGF}'],
    )

    # product/ice
    write_master_ecf(
        "gfs/product/ice/jgfs_ice_product_master.ecf",
        "gfs_ice_product_%CYC%_f%FHR%", "00:30:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=96GB", "vscatter:shared",
        "run", "${HOMEgfs}/jobs/JGLOBAL_OCEANICE_PRODUCTS",
        exports=['export WGF="%WGF%"', 'export FHR="%FHR%"',
                 'export FHR_LIST="%FHR_LIST%"',
                 'export FORECAST_HOUR="${FHR_LIST}"',
                 'export COMPONENT=ice'],
    )

    # product/wave
    write_master_ecf(
        "gfs/product/wave/gridded/jgfs_wave_post_gridded_master.ecf",
        "gfs_wave_post_gridded_%CYC%_f%FHR%", "00:30:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=20GB", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_POST_GRIDDED",
        exports=['export WGF="%WGF%"', 'export FHR="%FHR%"',
                 'export FHR_LIST="%FHR_LIST%"',
                 'export FORECAST_HOUR="${FHR_LIST}"'],
    )
    write_ecf(
        "gfs/product/wave/station/jgfs_wave_postpnt.ecf",
        "gfs_wave_postpnt_%CYC%", "00:20:00",
        "1:mpiprocs=40:ompthreads=1:ncpus=40", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_POST_PNT",
    )
    write_ecf(
        "gfs/product/wave/station/jgfs_wave_postbndpnt.ecf",
        "gfs_wave_postbndpnt_%CYC%", "00:20:00",
        "1:mpiprocs=40:ompthreads=1:ncpus=40", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_POST_BNDPNT",
    )
    write_ecf(
        "gfs/product/wave/station/jgfs_wave_postbndpntbll.ecf",
        "gfs_wave_postbndpntbll_%CYC%", "00:10:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=6G", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_POST_BNDPNTBLL",
    )

    # verf
    write_ecf(
        "gfs/verf/atmos/jgfs_tracker.ecf",
        "gfs_tracker_%CYC%", "00:20:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=6G", "vscatter:shared",
        "run", "${HOMEgfs}/jobs/JGFS_ATMOS_CYCLONE_TRACKER",
    )
    write_ecf(
        "gfs/verf/atmos/jgfs_genesis.ecf",
        "gfs_genesis_%CYC%", "00:20:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=6G", "vscatter:shared",
        "run", "${HOMEgfs}/jobs/JGFS_ATMOS_CYCLONE_GENESIS",
    )
    write_ecf(
        "gfs/verf/atmos/jgfs_vminmon.ecf",
        "gfs_vminmon_%CYC%", "00:05:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=1G", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_VMINMON",
    )


# ── GDAS tasks ──────────────────────────────────────────────

def gen_gdas_scripts():
    """Generate all GDAS .ecf scripts."""

    # prep/atmos
    write_ecf(
        "gdas/prep/atmos/jgdas_atmos_emcsfc_sfc_prep.ecf",
        "%RUN%_atmos_emcsfc_sfc_prep_%CYC%", "00:07:00",
        "1:ncpus=1:mem=10GB", "vscatter",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_PREP_SFC",
    )

    # prep/marine
    write_ecf(
        "gdas/prep/marine/jgdas_marine_obs_bufr_dump.ecf",
        "%RUN%_marine_obs_bufr_dump_%CYC%", "00:15:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=3GB", "vscatter:shared",
        "run", "${HOMEgfs}/jobs/JGLOBAL_MARINE_OBS_BUFR_DUMP",
    )
    write_ecf(
        "gdas/prep/marine/jgdas_marine_obs_dump.ecf",
        "%RUN%_marine_obs_dump_%CYC%", "00:30:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=48GB", "vscatter:shared",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_MARINE_OBS_PREP",
    )

    # init/wave
    write_ecf(
        "gdas/init/wave/jgdas_wave_init.ecf",
        "gdas_wave_init_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=4GB", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_INIT",
    )

    # analysis/atmos
    write_ecf(
        "gdas/analysis/atmos/jgdas_atmos_anal.ecf",
        "gdas_atmos_anal_%CYC%", "00:40:00",
        "6:mpiprocs=16:ompthreads=8:ncpus=128", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_ANALYSIS",
    )
    write_ecf(
        "gdas/analysis/atmos/jgdas_atmos_analdiag.ecf",
        "gdas_atmos_analdiag_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=48GB", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_ANALYSIS_DIAG",
    )
    write_ecf(
        "gdas/analysis/atmos/jgdas_atmos_anal_sfc_regrid.ecf",
        "gdas_atmos_anal_sfc_regrid_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_SFCANL_REGRID",
    )
    write_ecf(
        "gdas/analysis/atmos/jgdas_atmos_anal_sfc_gcycle.ecf",
        "gdas_atmos_anal_sfc_gcycle_%CYC%", "00:10:00",
        "1:mpiprocs=32:ompthreads=4:ncpus=128", "vscatter:exclhost",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_SFCANL_GCYCLE",
    )
    write_ecf(
        "gdas/analysis/atmos/jgdas_atmos_anal_calc.ecf",
        "gdas_atmos_anal_calc_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_ANALYSIS_CALC",
    )
    write_ecf(
        "gdas/analysis/atmos/jgdas_atmos_analupp.ecf",
        "gdas_atmos_analupp_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:exclhost",
        "upp", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_UPP",
        exports=["export FORECAST_HOUR='0'", "export FHR3='000'",
                 "export UPP_RUN='analysis'"],
    )

    # analysis/marine
    for task, jscript, wall, sel, plc in [
        ("jgdas_marine_bmat_init", "JGLOBAL_MARINE_BMAT_INITIALIZE", "00:15:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=24GB", "vscatter:shared"),
        ("jgdas_marine_bmat", "JGLOBAL_MARINE_BMAT", "00:15:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
        ("jgdas_marine_anal_init", "JGLOBAL_MARINE_ANALYSIS_INITIALIZE", "00:15:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
        ("jgdas_marine_analvar", "JGLOBAL_MARINE_ANALYSIS_VARIATIONAL", "00:20:00",
         "4:mpiprocs=64:ompthreads=1:ncpus=64:mem=500GB", "vscatter:exclhost"),
        ("jgdas_marine_analchkpt", "JGLOBAL_MARINE_ANALYSIS_CHECKPOINT", "00:10:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
        ("jgdas_marine_analfinal", "JGLOBAL_MARINE_ANALYSIS_FINALIZE", "00:10:00",
         "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared"),
    ]:
        write_ecf(
            f"gdas/analysis/marine/{task}.ecf",
            f"{task.replace('jgdas_', 'gdas_')}_%CYC%", wall, sel, plc,
            "ufsda", f"${{HOMEgfs}}/jobs/{jscript}",
        )

    # analysis/snow
    write_ecf(
        "gdas/analysis/snow/jgdas_atmos_analsnow.ecf",
        "gdas_atmos_analsnow_%CYC%", "00:10:00",
        "2:mpiprocs=64:ompthreads=2:ncpus=128", "vscatter:shared",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_SNOW_ANALYSIS",
    )

    # forecast
    write_ecf(
        "gdas/forecast/jgdas_fcst.ecf",
        "gdas_fcst_%CYC%", "00:40:00",
        "4:mpiprocs=128:ompthreads=1:ncpus=128", "vscatter:exclhost",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_FORECAST",
        exports=["export FCST_SEGMENT='0'"],
    )
    write_ecf(
        "gdas/forecast/jgdas_fcst_fsm.ecf",
        "gdas_fcst_fsm_%CYC%", "00:40:00",
        "1:ncpus=1:ompthreads=1:mem=20GB", "vscatter:shared",
        None, "${HOMEgfs}/jobs/JGLOBAL_FSM",
        exports=["export RJN='%RJN%'"],
        direct_modules=["module load intel/${intel_ver}", "module load craype/${craype_ver}"],
    )

    # product/atmos
    write_master_ecf(
        "gdas/product/atmos/product/jgdas_atmos_product_master.ecf",
        "gdas_atmos_product_%CYC%_f%FHR%", "00:10:00",
        "1:mpiprocs=24:ompthreads=1:ncpus=24", "vscatter:exclhost",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_PRODUCTS",
        exports=['export WGF="%WGF%"', 'export FHR_LIST="%FHR_LIST%"',
                 'export FORECAST_HOUR="${FHR_LIST}"',
                 'export COMPONENT=${WGF}'],
    )
    write_ecf(
        "gdas/product/atmos/jgdas_atmos_analprod.ecf",
        "gdas_atmos_analprod_%CYC%", "00:10:00",
        "1:mpiprocs=24:ompthreads=1:ncpus=24", "vscatter:exclhost",
        "run", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_PRODUCTS",
        exports=["export FORECAST_HOUR='-1'", "export FHR_LIST='-1'"],
    )

    # product/wave
    write_master_ecf(
        "gdas/product/wave/gridded/jgdas_wave_post_gridded_master.ecf",
        "gdas_wave_post_gridded_%CYC%_f%FHR%", "00:15:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=20GB", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_POST_GRIDDED",
        exports=['export WGF="%WGF%"', 'export FHR="%FHR%"',
                 'export FHR_LIST="%FHR_LIST%"',
                 'export FORECAST_HOUR="${FHR_LIST}"'],
    )
    write_ecf(
        "gdas/product/wave/jgdas_wave_postpnt.ecf",
        "gdas_wave_postpnt_%CYC%", "00:15:00",
        "1:mpiprocs=40:ompthreads=1:ncpus=40", "vscatter:shared",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_WAVE_POST_PNT",
    )

    # verf
    write_ecf(
        "gdas/verf/atmos/jgdas_verfozn.ecf",
        "gdas_verfozn_%CYC%", "00:10:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=1G", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGDAS_ATMOS_VERFOZN",
    )
    write_ecf(
        "gdas/verf/atmos/jgdas_verfrad.ecf",
        "gdas_verfrad_%CYC%", "00:30:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=10G", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGDAS_ATMOS_VERFRAD",
    )
    write_ecf(
        "gdas/verf/atmos/jgdas_vminmon.ecf",
        "gdas_vminmon_%CYC%", "00:05:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=1:mem=1G", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ATMOS_VMINMON",
    )
    write_ecf(
        "gdas/verf/atmos/jgdas_fit2obs.ecf",
        "gdas_fit2obs_%CYC%", "00:20:00",
        "1:mpiprocs=1:ompthreads=1:ncpus=28:mem=6GB", "vscatter:shared",
        "run", "${HOMEgfs}/jobs/JGDAS_FIT2OBS",
    )


# ── EnKFGDAS tasks ──────────────────────────────────────────

def gen_enkfgdas_scripts():
    """Generate all enkfgdas .ecf scripts."""

    # analysis/create
    write_ecf(
        "enkfgdas/analysis/create/jenkfgdas_atmos_ens_observer.ecf",
        "enkfgdas_atmos_ens_observer_%CYC%", "00:15:00",
        "2:mpiprocs=50:ompthreads=2:ncpus=100", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_SELECT_OBS",
    )
    write_ecf(
        "enkfgdas/analysis/create/jenkfgdas_atmos_diag_ens.ecf",
        "enkfgdas_atmos_diag_ens_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=48GB", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_DIAG",
    )
    write_ecf(
        "enkfgdas/analysis/create/jenkfgdas_atmos_ens_update.ecf",
        "enkfgdas_atmos_ens_update_%CYC%", "00:30:00",
        "4:mpiprocs=9:ompthreads=14:ncpus=126", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_UPDATE",
    )
    write_ecf(
        "enkfgdas/analysis/create/jenkfgdas_change_res_ens.ecf",
        "enkfgdas_change_res_ens_%CYC%", "00:10:00",
        "3:mpiprocs=1:ompthreads=128:ncpus=128:mem=200GB", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGDAS_ATMOS_CHGRES_FORENKF",
    )
    write_ecf(
        "enkfgdas/analysis/create/jenkfgdas_atmos_ens_anal_sfc_gcycle.ecf",
        "enkfgdas_atmos_ens_anal_sfc_gcycle_%CYC%", "00:30:00",
        "1:mpiprocs=64:ompthreads=1:ncpus=64", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_SFC_GCYCLE",
    )
    write_ecf(
        "enkfgdas/analysis/create/jenkfgdas_atmos_ens_anal_sfc_regrid.ecf",
        "enkfgdas_atmos_ens_anal_sfc_regrid_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_SFCANL_REGRID",
    )
    write_ecf(
        "enkfgdas/analysis/create/jenkfgdas_snow_anal_ens.ecf",
        "enkfgdas_snow_anal_ens_%CYC%", "00:30:00",
        "2:mpiprocs=64:ompthreads=2:ncpus=128", "vscatter:shared",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_SNOWENS_ANALYSIS",
    )

    # analysis/recenter
    write_master_ecf(
        "enkfgdas/analysis/recenter/jenkfgdas_atmos_ens_recenter_master.ecf",
        "enkfgdas_atmos_ens_recenter_%CYC%_%FHRGRP%", "00:15:00",
        "1:mpiprocs=32:ompthreads=4:ncpus=128", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_ECEN",
        exports=['export WGF="%WGF%"', 'export FHRGRP="%FHRGRP%"',
                 'export FHRLST="%FHRLST%"',
                 'export FHMIN_ECEN="${FHRLST}"',
                 'export FHMAX_ECEN="${FHRLST}"',
                 'export FHOUT_ECEN="${FHRLST}"',
                 'export COMPONENT=${WGF}'],
    )
    write_ecf(
        "enkfgdas/analysis/recenter/jenkfgdas_marine_ens_recenter.ecf",
        "enkfgdas_marine_ens_recenter_%CYC%", "00:30:00",
        "4:mpiprocs=32:ompthreads=1:ncpus=32:mem=500GB", "vscatter:exclhost",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_MARINE_ANALYSIS_ECEN",
    )

    # forecast
    write_master_ecf(
        "enkfgdas/forecast/jenkfgdas_fcst_master.ecf",
        "enkfgdas_fcst_%CYC%_mem%ENSMEM%", "00:20:00",
        "2:mpiprocs=128:ompthreads=1:ncpus=128", "vscatter:exclhost",
        "ufswm", "${HOMEgfs}/jobs/JGLOBAL_FORECAST",
        exports=['export WGF="%WGF%"', 'export ENSMEM="%ENSMEM%"',
                 'export MEMDIR="%MEMDIR%"'],
    )

    # ensstat
    write_master_ecf(
        "enkfgdas/ensstat/jenkfgdas_ens_post_master.ecf",
        "enkfgdas_ens_post%FHRGRP%_%CYC%", "00:20:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=128GB", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGDAS_ENKF_POST",
        exports=['export WGF="%WGF%"', 'export FHRGRP="%FHRGRP%"',
                 'export FHRLST="%FHRLST%"',
                 'export FHMIN_EPOS="%FHR%"',
                 'export FHMAX_EPOS="%FHR%"',
                 'export FHOUT_EPOS="%FHR%"'],
    )


# ── EnKFGFS tasks ───────────────────────────────────────────

def gen_enkfgfs_scripts():
    """Generate all enkfgfs .ecf scripts (analysis only, no efcs/epos)."""

    write_ecf(
        "enkfgfs/analysis/jenkfgfs_atmos_ens_observer.ecf",
        "enkfgfs_atmos_ens_observer_%CYC%", "00:15:00",
        "2:mpiprocs=50:ompthreads=2:ncpus=100", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_SELECT_OBS",
    )
    write_ecf(
        "enkfgfs/analysis/jenkfgfs_atmos_diag_ens.ecf",
        "enkfgfs_atmos_diag_ens_%CYC%", "00:10:00",
        "1:mpiprocs=128:ompthreads=1:ncpus=128:mem=48GB", "vscatter:shared",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_DIAG",
    )
    write_ecf(
        "enkfgfs/analysis/jenkfgfs_atmos_ens_update.ecf",
        "enkfgfs_atmos_ens_update_%CYC%", "00:30:00",
        "4:mpiprocs=9:ompthreads=14:ncpus=126", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_UPDATE",
    )
    write_ecf(
        "enkfgfs/analysis/jenkfgfs_snow_anal_ens.ecf",
        "enkfgfs_snow_anal_ens_%CYC%", "00:30:00",
        "2:mpiprocs=64:ompthreads=2:ncpus=128", "vscatter:shared",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_SNOWENS_ANALYSIS",
    )
    write_ecf(
        "enkfgfs/analysis/jenkfgfs_marine_ens_recenter.ecf",
        "enkfgfs_marine_ens_recenter_%CYC%", "00:30:00",
        "4:mpiprocs=32:ompthreads=1:ncpus=32:mem=500GB", "vscatter:exclhost",
        "ufsda", "${HOMEgfs}/jobs/JGLOBAL_MARINE_ANALYSIS_ECEN",
    )
    write_ecf(
        "enkfgfs/analysis/jenkfgfs_atmos_ens_anal_sfc_gcycle.ecf",
        "enkfgfs_atmos_ens_anal_sfc_gcycle_%CYC%", "00:30:00",
        "1:mpiprocs=64:ompthreads=1:ncpus=64", "vscatter:exclhost",
        "gsi", "${HOMEgfs}/jobs/JGLOBAL_ENKF_SFC_GCYCLE",
    )


# ── Main ────────────────────────────────────────────────────

def main():
    gen_gfs_scripts()
    gen_gdas_scripts()
    gen_enkfgdas_scripts()
    gen_enkfgfs_scripts()

    # Count generated files
    count = sum(1 for _ in SCRIPT_DIR.rglob("*.ecf"))
    print(f"Generated {count} .ecf files under {SCRIPT_DIR}")


if __name__ == "__main__":
    main()
