#!/usr/bin/env python3
"""Generate c96_s2sw.def for the C96 S2SW ecFlow test suite.

Modeled on gfs_prod.def but sized for C96C48mx500_S2SW_cyc_gfs:
  - 3 cycles: 12Z (cold start, gdas only), 18Z, 00Z
  - GFS cycles: 18Z, 00Z (SDATE_GFS = 2021122018)
  - FHMAX_GFS = 120 (hourly to 120, 3-hourly after that)
  - FHMAX_GDAS = 9
  - NENS = 2 (ensemble members)
  - S2SW: ocean + ice + wave, no aerosols
  - GSI-based DA (not JEDI atm)
  - JEDI ocean + snow DA

Resources are hardcoded for WCOSS2 at C96 resolution.
"""

import sys
from pathlib import Path


def indent(level):
    return "  " * level


def gfs_fhr_list(fhmax=120):
    """GFS forecast hours: 0-120 hourly, 123-384 every 3h (capped at fhmax)."""
    fhrs = list(range(0, min(fhmax, 120) + 1))
    fhr = 123
    while fhr <= fhmax:
        fhrs.append(fhr)
        fhr += 3
    return fhrs


def gdas_fhr_list(fhmax=9):
    """GDAS forecast hours: 0-9 hourly."""
    return list(range(0, fhmax + 1))


def ocean_ice_fhr_list(fhmax=120):
    """Ocean/ice product hours: every 6h from 6 to fhmax."""
    return list(range(6, fhmax + 1, 6))


def wave_fhr_list(fhmax=120):
    """Wave post gridded hours: same schedule as atmos product."""
    return gfs_fhr_list(fhmax)


def write_fsm_events(f, lv, prefix, fhrs, component="atmos"):
    """Write FSM event lines for each forecast hour."""
    for fhr in fhrs:
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}event {100 + fhr} release_{prefix}_{component}_product_f{fstr}\n")


def write_wave_fsm_events(f, lv, prefix, fhrs):
    """Write FSM event lines for wave post gridded."""
    base = 900
    for fhr in fhrs:
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}event {base + fhr} release_{prefix}_wave_post_gridded_f{fstr}\n")


def write_ocean_fsm_events(f, lv, prefix, fhrs):
    """Write FSM event lines for ocean product."""
    base = 500
    for i, fhr in enumerate(fhrs):
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}event {base + i} release_{prefix}_ocean_product_f{fstr}\n")


def write_ice_fsm_events(f, lv, prefix, fhrs):
    """Write FSM event lines for ice product."""
    base = 700
    for i, fhr in enumerate(fhrs):
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}event {base + i} release_{prefix}_ice_product_f{fstr}\n")


def write_product_tasks(f, lv, run, fhrs, fsm_task):
    """Write per-forecast-hour product tasks triggered by FSM events."""
    for fhr in fhrs:
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}task j{run}_atmos_product_f{fstr}\n")
        f.write(f"{indent(lv+1)}edit FHR '{fstr}'\n")
        f.write(f"{indent(lv+1)}edit FHR_LIST '{fhr}'\n")
        f.write(f"{indent(lv+1)}trigger ../../../forecast/{fsm_task}:release_{run}_atmos_product_f{fstr}\n")


def write_wave_gridded_tasks(f, lv, run, fhrs, fsm_task):
    """Write per-forecast-hour wave post gridded tasks."""
    for fhr in fhrs:
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}task j{run}_wave_post_gridded_f{fstr}\n")
        f.write(f"{indent(lv+1)}edit FHR '{fstr}'\n")
        f.write(f"{indent(lv+1)}trigger ../../../forecast/{fsm_task}:release_{run}_wave_post_gridded_f{fstr}\n")


def write_ocean_tasks(f, lv, run, fhrs, fsm_task):
    """Write per-forecast-hour ocean product tasks.

    Ocean tasks sit at product/ocean/ (2 levels below the run family),
    so the relative path to forecast/ is ../../forecast/.
    """
    for fhr in fhrs:
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}task j{run}_ocean_product_f{fstr}\n")
        f.write(f"{indent(lv+1)}edit FHR '{fstr}'\n")
        f.write(f"{indent(lv+1)}trigger ../../forecast/{fsm_task}:release_{run}_ocean_product_f{fstr}\n")


def write_ice_tasks(f, lv, run, fhrs, fsm_task):
    """Write per-forecast-hour ice product tasks.

    Ice tasks sit at product/ice/ (2 levels below the run family),
    so the relative path to forecast/ is ../../forecast/.
    """
    for fhr in fhrs:
        fstr = f"{fhr:03d}"
        f.write(f"{indent(lv)}task j{run}_ice_product_f{fstr}\n")
        f.write(f"{indent(lv+1)}edit FHR '{fstr}'\n")
        f.write(f"{indent(lv+1)}trigger ../../forecast/{fsm_task}:release_{run}_ice_product_f{fstr}\n")


# ── GFS family ──────────────────────────────────────────────
def write_gfs_family(f, lv, cyc, prev_cyc):
    """Write the GFS family for a cycle that runs GFS."""
    gfs_fhrs = gfs_fhr_list(120)
    ocn_fhrs = ocean_ice_fhr_list(120)
    ice_fhrs = ocean_ice_fhr_list(120)
    wav_fhrs = wave_fhr_list(120)

    f.write(f"{indent(lv)}family gfs\n")
    f.write(f"{indent(lv+1)}edit RUN 'gfs'\n")

    # prep
    f.write(f"{indent(lv+1)}family prep\n")
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")
    f.write(f"{indent(lv+3)}task jgfs_atmos_emcsfc_sfc_prep\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+2)}family marine\n")
    f.write(f"{indent(lv+3)}edit WGF 'marine'\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_obs_bufr_dump\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_obs_dump\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    # init
    f.write(f"{indent(lv+1)}family init\n")
    f.write(f"{indent(lv+2)}family wave\n")
    f.write(f"{indent(lv+3)}edit WGF 'wave'\n")
    f.write(f"{indent(lv+3)}task jgfs_wave_init\n")
    f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgfs_atmos_emcsfc_sfc_prep == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    # analysis
    f.write(f"{indent(lv+1)}family analysis\n")
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")
    f.write(f"{indent(lv+3)}task jgfs_atmos_anal\n")
    f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgfs_atmos_emcsfc_sfc_prep == complete and ../../../../{prev_cyc}/enkfgdas/ensstat == complete and ../../../../{prev_cyc}/gdas/forecast == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_atmos_anal_sfc_gcycle\n")
    f.write(f"{indent(lv+4)}trigger jgfs_atmos_anal == complete and ../snow/jgfs_atmos_analsnow == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_atmos_anal_calc\n")
    f.write(f"{indent(lv+4)}trigger jgfs_atmos_anal_sfc_gcycle == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_atmos_analupp\n")
    f.write(f"{indent(lv+4)}trigger jgfs_atmos_anal_calc == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    f.write(f"{indent(lv+2)}family marine\n")
    f.write(f"{indent(lv+3)}edit WGF 'marine'\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_bmat_init\n")
    f.write(f"{indent(lv+4)}trigger ../../prep/marine/jgfs_marine_obs_dump == complete and ../../../../{prev_cyc}/enkfgdas/forecast == complete and ../../../../{prev_cyc}/gdas/forecast == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_bmat\n")
    f.write(f"{indent(lv+4)}trigger jgfs_marine_bmat_init == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_anal_init\n")
    f.write(f"{indent(lv+4)}trigger jgfs_marine_bmat == complete and ../../prep/marine/jgfs_marine_obs_dump == complete and ../../prep/marine/jgfs_marine_obs_bufr_dump == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_analvar\n")
    f.write(f"{indent(lv+4)}trigger jgfs_marine_anal_init == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_analchkpt\n")
    f.write(f"{indent(lv+4)}trigger jgfs_marine_analvar == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_marine_analfinal\n")
    f.write(f"{indent(lv+4)}trigger jgfs_marine_analchkpt == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    f.write(f"{indent(lv+2)}family snow\n")
    f.write(f"{indent(lv+3)}edit WGF 'snow'\n")
    f.write(f"{indent(lv+3)}task jgfs_atmos_analsnow\n")
    f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgfs_atmos_emcsfc_sfc_prep == complete and ../../../../{prev_cyc}/gdas/forecast/jgdas_fcst == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    # forecast
    f.write(f"{indent(lv+1)}family forecast\n")

    # FSM
    f.write(f"{indent(lv+2)}task jgfs_fcst_fsm\n")
    f.write(f"{indent(lv+3)}edit RJN 'forecast'\n")
    f.write(f"{indent(lv+3)}trigger jgfs_fcst == active or jgfs_fcst == complete\n")
    write_fsm_events(f, lv+3, "gfs", gfs_fhrs, "atmos")
    write_wave_fsm_events(f, lv+3, "gfs", wav_fhrs)
    write_ocean_fsm_events(f, lv+3, "gfs", ocn_fhrs)
    write_ice_fsm_events(f, lv+3, "gfs", ice_fhrs)

    # forecast task — carries the release_gfs_fcst_manager event for jgfs_fcst_manager
    f.write(f"{indent(lv+2)}task jgfs_fcst\n")
    f.write(f"{indent(lv+3)}event 1500 release_gfs_fcst_manager\n")
    f.write(f"{indent(lv+3)}trigger ../analysis/atmos/jgfs_atmos_analupp == complete and ../init == complete and ../analysis/marine == complete\n")

    # forecast manager
    f.write(f"{indent(lv+2)}task jgfs_fcst_manager\n")
    f.write(f"{indent(lv+3)}trigger jgfs_fcst:release_gfs_fcst_manager\n")

    f.write(f"{indent(lv+1)}endfamily\n")

    # product
    f.write(f"{indent(lv+1)}family product\n")

    # atmos product
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")
    f.write(f"{indent(lv+3)}family product\n")
    write_product_tasks(f, lv+4, "gfs", gfs_fhrs, "jgfs_fcst_fsm")
    f.write(f"{indent(lv+3)}endfamily\n")
    f.write(f"{indent(lv+3)}task jgfs_atmos_analprod\n")
    f.write(f"{indent(lv+4)}trigger ../../analysis/atmos/jgfs_atmos_analupp == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    # ocean product
    f.write(f"{indent(lv+2)}family ocean\n")
    f.write(f"{indent(lv+3)}edit WGF 'ocean'\n")
    write_ocean_tasks(f, lv+3, "gfs", ocn_fhrs, "jgfs_fcst_fsm")
    f.write(f"{indent(lv+2)}endfamily\n")

    # ice product
    f.write(f"{indent(lv+2)}family ice\n")
    f.write(f"{indent(lv+3)}edit WGF 'ice'\n")
    write_ice_tasks(f, lv+3, "gfs", ice_fhrs, "jgfs_fcst_fsm")
    f.write(f"{indent(lv+2)}endfamily\n")

    # wave product
    f.write(f"{indent(lv+2)}family wave\n")
    f.write(f"{indent(lv+3)}edit WGF 'wave'\n")
    f.write(f"{indent(lv+3)}family gridded\n")
    write_wave_gridded_tasks(f, lv+4, "gfs", wav_fhrs, "jgfs_fcst_fsm")
    f.write(f"{indent(lv+3)}endfamily\n")
    f.write(f"{indent(lv+3)}family station\n")
    f.write(f"{indent(lv+4)}task jgfs_wave_postpnt\n")
    f.write(f"{indent(lv+5)}trigger ../../../forecast/jgfs_fcst == complete\n")
    f.write(f"{indent(lv+4)}task jgfs_wave_postbndpnt\n")
    f.write(f"{indent(lv+5)}trigger ../../../forecast/jgfs_fcst == complete\n")
    f.write(f"{indent(lv+4)}task jgfs_wave_postbndpntbll\n")
    f.write(f"{indent(lv+5)}trigger jgfs_wave_postbndpnt == complete\n")
    f.write(f"{indent(lv+3)}endfamily\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    f.write(f"{indent(lv+1)}endfamily\n")

    # verf
    f.write(f"{indent(lv+1)}family verf\n")
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")
    f.write(f"{indent(lv+3)}task jgfs_tracker\n")
    f.write(f"{indent(lv+4)}trigger ../../product/atmos/product/jgfs_atmos_product_f072 == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_genesis\n")
    f.write(f"{indent(lv+4)}trigger ../../product/atmos/product/jgfs_atmos_product_f120 == complete\n")
    f.write(f"{indent(lv+3)}task jgfs_vminmon\n")
    f.write(f"{indent(lv+4)}trigger ../../analysis/atmos == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    f.write(f"{indent(lv)}endfamily\n")


# ── GDAS family ─────────────────────────────────────────────
def write_gdas_family(f, lv, cyc, prev_cyc, is_cold_start=False):
    """Write the GDAS family for a cycle."""
    gdas_fhrs = gdas_fhr_list(9)
    wav_fhrs = gdas_fhr_list(9)

    f.write(f"{indent(lv)}family gdas\n")
    f.write(f"{indent(lv+1)}edit RUN 'gdas'\n")

    # prep
    f.write(f"{indent(lv+1)}family prep\n")
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")
    f.write(f"{indent(lv+3)}task jgdas_atmos_emcsfc_sfc_prep\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+2)}family marine\n")
    f.write(f"{indent(lv+3)}edit WGF 'marine'\n")
    f.write(f"{indent(lv+3)}task jgdas_marine_obs_bufr_dump\n")
    f.write(f"{indent(lv+3)}task jgdas_marine_obs_dump\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    # init
    f.write(f"{indent(lv+1)}family init\n")
    f.write(f"{indent(lv+2)}family wave\n")
    f.write(f"{indent(lv+3)}edit WGF 'wave'\n")
    f.write(f"{indent(lv+3)}task jgdas_wave_init\n")
    f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    # analysis
    f.write(f"{indent(lv+1)}family analysis\n")
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")

    if is_cold_start:
        f.write(f"{indent(lv+3)}task jgdas_atmos_anal\n")
        f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete\n")
    else:
        f.write(f"{indent(lv+3)}task jgdas_atmos_anal\n")
        f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete and ../../../../{prev_cyc}/enkfgdas/ensstat == complete and ../../../../{prev_cyc}/gdas/forecast == complete\n")

    f.write(f"{indent(lv+3)}task jgdas_atmos_analdiag\n")
    f.write(f"{indent(lv+4)}trigger jgdas_atmos_anal == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_atmos_anal_sfc_regrid\n")
    f.write(f"{indent(lv+4)}trigger ../../../enkfgdas/analysis/create/jenkfgdas_atmos_ens_update == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_atmos_anal_sfc_gcycle\n")
    f.write(f"{indent(lv+4)}trigger jgdas_atmos_anal == complete and ../snow/jgdas_atmos_analsnow == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_atmos_anal_calc\n")
    f.write(f"{indent(lv+4)}trigger jgdas_atmos_anal_sfc_regrid == complete and jgdas_atmos_anal_sfc_gcycle == complete and ../../../enkfgdas/analysis/create/jenkfgdas_change_res_ens == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_atmos_analupp\n")
    f.write(f"{indent(lv+4)}trigger jgdas_atmos_anal_calc == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    f.write(f"{indent(lv+2)}family marine\n")
    f.write(f"{indent(lv+3)}edit WGF 'marine'\n")
    if is_cold_start:
        f.write(f"{indent(lv+3)}task jgdas_marine_bmat_init\n")
        f.write(f"{indent(lv+4)}trigger ../../prep/marine/jgdas_marine_obs_dump == complete\n")
    else:
        f.write(f"{indent(lv+3)}task jgdas_marine_bmat_init\n")
        f.write(f"{indent(lv+4)}trigger ../../prep/marine/jgdas_marine_obs_dump == complete and ../../../../{prev_cyc}/enkfgdas/forecast == complete and ../../../../{prev_cyc}/gdas/forecast == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_marine_bmat\n")
    f.write(f"{indent(lv+4)}trigger jgdas_marine_bmat_init == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_marine_anal_init\n")
    f.write(f"{indent(lv+4)}trigger jgdas_marine_bmat == complete and ../../prep/marine/jgdas_marine_obs_dump == complete and ../../prep/marine/jgdas_marine_obs_bufr_dump == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_marine_analvar\n")
    f.write(f"{indent(lv+4)}trigger jgdas_marine_anal_init == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_marine_analchkpt\n")
    f.write(f"{indent(lv+4)}trigger jgdas_marine_analvar == complete and ../../../enkfgdas/analysis/recenter/jenkfgdas_marine_ens_recenter == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_marine_analfinal\n")
    f.write(f"{indent(lv+4)}trigger jgdas_marine_analchkpt == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    f.write(f"{indent(lv+2)}family snow\n")
    f.write(f"{indent(lv+3)}edit WGF 'snow'\n")
    if is_cold_start:
        f.write(f"{indent(lv+3)}task jgdas_atmos_analsnow\n")
        f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete\n")
    else:
        f.write(f"{indent(lv+3)}task jgdas_atmos_analsnow\n")
        f.write(f"{indent(lv+4)}trigger ../../prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete and ../../../../{prev_cyc}/gdas/forecast/jgdas_fcst == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    # forecast
    f.write(f"{indent(lv+1)}family forecast\n")

    # FSM
    f.write(f"{indent(lv+2)}task jgdas_fcst_fsm\n")
    f.write(f"{indent(lv+3)}edit RJN 'forecast'\n")
    f.write(f"{indent(lv+3)}trigger jgdas_fcst == active or jgdas_fcst == complete\n")
    write_fsm_events(f, lv+3, "gdas", gdas_fhrs, "atmos")
    write_wave_fsm_events(f, lv+3, "gdas", wav_fhrs)

    # forecast task
    f.write(f"{indent(lv+2)}task jgdas_fcst\n")
    f.write(f"{indent(lv+3)}trigger ../analysis/atmos/jgdas_atmos_analupp == complete and ../init == complete and ../analysis/marine == complete\n")

    f.write(f"{indent(lv+1)}endfamily\n")

    # product
    f.write(f"{indent(lv+1)}family product\n")

    # atmos product
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")
    f.write(f"{indent(lv+3)}family product\n")
    write_product_tasks(f, lv+4, "gdas", gdas_fhrs, "jgdas_fcst_fsm")
    f.write(f"{indent(lv+3)}endfamily\n")
    f.write(f"{indent(lv+3)}task jgdas_atmos_analprod\n")
    f.write(f"{indent(lv+4)}trigger ../../analysis/atmos/jgdas_atmos_analupp == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    # wave product
    f.write(f"{indent(lv+2)}family wave\n")
    f.write(f"{indent(lv+3)}edit WGF 'wave'\n")
    f.write(f"{indent(lv+3)}family gridded\n")
    write_wave_gridded_tasks(f, lv+4, "gdas", wav_fhrs, "jgdas_fcst_fsm")
    f.write(f"{indent(lv+3)}endfamily\n")
    f.write(f"{indent(lv+3)}task jgdas_wave_postpnt\n")
    f.write(f"{indent(lv+4)}trigger ../../forecast/jgdas_fcst == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    f.write(f"{indent(lv+1)}endfamily\n")

    # verf (gdas-specific)
    f.write(f"{indent(lv+1)}family verf\n")
    f.write(f"{indent(lv+2)}family atmos\n")
    f.write(f"{indent(lv+3)}edit WGF 'atmos'\n")
    f.write(f"{indent(lv+3)}task jgdas_verfozn\n")
    f.write(f"{indent(lv+4)}trigger ../../analysis/atmos/jgdas_atmos_analdiag == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_verfrad\n")
    f.write(f"{indent(lv+4)}trigger ../../analysis/atmos/jgdas_atmos_analdiag == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_vminmon\n")
    f.write(f"{indent(lv+4)}trigger ../../analysis/atmos == complete\n")
    f.write(f"{indent(lv+3)}task jgdas_fit2obs\n")
    f.write(f"{indent(lv+4)}trigger ../../analysis/atmos == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    f.write(f"{indent(lv)}endfamily\n")


# ── EnKFGDAS family ─────────────────────────────────────────
def write_enkfgdas_family(f, lv, cyc, prev_cyc, nens=2, is_cold_start=False):
    """Write the enkfgdas family."""
    f.write(f"{indent(lv)}family enkfgdas\n")
    f.write(f"{indent(lv+1)}edit RUN 'enkfgdas'\n")
    f.write(f"{indent(lv+1)}edit WGF 'enkf'\n")
    f.write(f"{indent(lv+1)}edit ECF_FILES '%PACKAGEHOME%/ecf/scripts'\n")

    # analysis
    f.write(f"{indent(lv+1)}family analysis\n")

    # create
    f.write(f"{indent(lv+2)}family create\n")

    if is_cold_start:
        f.write(f"{indent(lv+3)}task jenkfgdas_atmos_ens_observer\n")
        f.write(f"{indent(lv+4)}trigger ../../../gdas/prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete\n")
        f.write(f"{indent(lv+3)}task jenkfgdas_snow_anal_ens\n")
        f.write(f"{indent(lv+4)}trigger ../../../gdas/prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete\n")
    else:
        f.write(f"{indent(lv+3)}task jenkfgdas_atmos_ens_observer\n")
        f.write(f"{indent(lv+4)}trigger ../../../gdas/prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete and ../../../../{prev_cyc}/enkfgdas/ensstat == complete\n")
        f.write(f"{indent(lv+3)}task jenkfgdas_snow_anal_ens\n")
        f.write(f"{indent(lv+4)}trigger ../../../gdas/prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete and ../../../../{prev_cyc}/enkfgdas/ensstat == complete\n")

    f.write(f"{indent(lv+3)}task jenkfgdas_atmos_diag_ens\n")
    f.write(f"{indent(lv+4)}trigger jenkfgdas_atmos_ens_observer == complete\n")
    f.write(f"{indent(lv+3)}task jenkfgdas_atmos_ens_update\n")
    f.write(f"{indent(lv+4)}trigger jenkfgdas_atmos_diag_ens == complete\n")
    f.write(f"{indent(lv+3)}task jenkfgdas_change_res_ens\n")
    f.write(f"{indent(lv+4)}trigger ../../../gdas/forecast/jgdas_fcst == complete and ../../forecast/jenkfgdas_fcst_mem001 == complete\n")
    f.write(f"{indent(lv+3)}task jenkfgdas_atmos_ens_anal_sfc_regrid\n")
    f.write(f"{indent(lv+4)}trigger jenkfgdas_atmos_ens_update == complete\n")
    f.write(f"{indent(lv+3)}task jenkfgdas_atmos_ens_anal_sfc_gcycle\n")
    f.write(f"{indent(lv+4)}trigger jenkfgdas_snow_anal_ens == complete and ../../../gdas/analysis/atmos/jgdas_atmos_anal_calc == complete\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    # recenter
    f.write(f"{indent(lv+2)}family recenter\n")
    f.write(f"{indent(lv+3)}task jenkfgdas_marine_ens_recenter\n")
    f.write(f"{indent(lv+4)}trigger ../../../gdas/analysis/marine/jgdas_marine_bmat_init == complete\n")
    for fhrgrp in range(3):
        fhrlst = (fhrgrp + 1) * 3
        f.write(f"{indent(lv+3)}task jenkfgdas_atmos_ens_recenter{fhrgrp:03d}\n")
        f.write(f"{indent(lv+4)}trigger ../create/jenkfgdas_atmos_ens_update == complete and ../../../gdas/analysis/atmos/jgdas_atmos_anal_calc == complete\n")
        f.write(f"{indent(lv+4)}edit FHRGRP '{fhrgrp:03d}'\n")
        f.write(f"{indent(lv+4)}edit FHRLST '{fhrlst:03d}'\n")
    f.write(f"{indent(lv+2)}endfamily\n")

    f.write(f"{indent(lv+1)}endfamily\n")

    # forecast
    recenter_triggers = " and ".join(
        f"analysis/recenter/jenkfgdas_atmos_ens_recenter{i:03d} == complete" for i in range(3)
    )
    f.write(f"{indent(lv+1)}family forecast\n")
    f.write(f"{indent(lv+2)}trigger {recenter_triggers} and analysis/create/jenkfgdas_atmos_ens_anal_sfc_gcycle == complete and analysis/recenter/jenkfgdas_marine_ens_recenter == complete and analysis/create/jenkfgdas_atmos_ens_anal_sfc_regrid == complete\n")
    for mem in range(1, nens + 1):
        f.write(f"{indent(lv+2)}task jenkfgdas_fcst_mem{mem:03d}\n")
        f.write(f"{indent(lv+3)}edit ENSMEM '{mem:03d}'\n")
        f.write(f"{indent(lv+3)}edit MEMDIR 'mem{mem:03d}'\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    # ensstat
    f.write(f"{indent(lv+1)}family ensstat\n")
    f.write(f"{indent(lv+2)}trigger forecast == complete\n")
    # GDAS FHMAX=9: epos for fhr 3-9
    for i, fhr in enumerate(range(3, 10)):
        f.write(f"{indent(lv+2)}task jenkfgdas_ens_post{i:03d}\n")
        f.write(f"{indent(lv+3)}edit FHRGRP '{i:03d}'\n")
        f.write(f"{indent(lv+3)}edit FHR '{fhr:03d}'\n")
        f.write(f"{indent(lv+3)}edit FHRLST 'f{fhr:03d}'\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    f.write(f"{indent(lv)}endfamily\n")


# ── EnKFGFS family (no efcs/epos/echgres — just analysis) ──
def write_enkfgfs_family(f, lv, cyc, prev_cyc, nens=2):
    """Write the enkfgfs family.

    enkfgfs sits at CYC/enkfgfs/, so cross-references to gdas use
    ../../gdas/ (analysis→enkfgfs→CYC, then down to gdas).
    """
    f.write(f"{indent(lv)}family enkfgfs\n")
    f.write(f"{indent(lv+1)}edit RUN 'enkfgfs'\n")
    f.write(f"{indent(lv+1)}edit WGF 'enkf'\n")

    f.write(f"{indent(lv+1)}family analysis\n")
    f.write(f"{indent(lv+2)}task jenkfgfs_atmos_ens_observer\n")
    f.write(f"{indent(lv+3)}trigger ../../gdas/prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete and ../../../{prev_cyc}/enkfgdas/ensstat == complete\n")
    f.write(f"{indent(lv+2)}task jenkfgfs_snow_anal_ens\n")
    f.write(f"{indent(lv+3)}trigger ../../gdas/prep/atmos/jgdas_atmos_emcsfc_sfc_prep == complete and ../../../{prev_cyc}/enkfgdas/ensstat == complete\n")
    f.write(f"{indent(lv+2)}task jenkfgfs_atmos_diag_ens\n")
    f.write(f"{indent(lv+3)}trigger jenkfgfs_atmos_ens_observer == complete\n")
    f.write(f"{indent(lv+2)}task jenkfgfs_atmos_ens_update\n")
    f.write(f"{indent(lv+3)}trigger jenkfgfs_atmos_diag_ens == complete\n")
    f.write(f"{indent(lv+2)}task jenkfgfs_marine_ens_recenter\n")
    f.write(f"{indent(lv+3)}trigger ../../gdas/analysis/marine/jgdas_marine_bmat_init == complete\n")
    f.write(f"{indent(lv+2)}task jenkfgfs_atmos_ens_anal_sfc_gcycle\n")
    f.write(f"{indent(lv+3)}trigger jenkfgfs_snow_anal_ens == complete and ../../gdas/analysis/atmos/jgdas_atmos_anal_calc == complete\n")
    f.write(f"{indent(lv+1)}endfamily\n")

    f.write(f"{indent(lv)}endfamily\n")


# ── Main ────────────────────────────────────────────────────
def main():
    outpath = Path(__file__).parent / "c96_s2sw.def"

    # Cycle layout: 12Z (cold), 18Z, 00Z
    # GFS starts at 18Z. enkfgfs only on GFS cycles.
    cycles = [
        {"cyc": "12", "prev_cyc": None, "has_gfs": False, "is_cold_start": True},
        {"cyc": "18", "prev_cyc": "12", "has_gfs": True, "is_cold_start": False},
        {"cyc": "00", "prev_cyc": "18", "has_gfs": True, "is_cold_start": False},
    ]

    with open(outpath, "w") as f:
        f.write("# c96_s2sw.def — C96 S2SW ecFlow test suite\n")
        f.write("# Generated by gen_c96_s2sw_def.py\n")
        f.write("# Modeled on C96C48mx500_S2SW_cyc_gfs Rocoto test (issue #4927)\n")
        f.write("#\n")
        f.write("# Cycles: 12Z (cold start, gdas only), 18Z, 00Z\n")
        f.write("# GFS FHMAX: 120h, GDAS FHMAX: 9h, NENS: 2\n")
        f.write("# S2SW: atmosphere + ocean + ice + wave (no aerosols)\n")
        f.write("# DA: GSI atm, JEDI ocean + snow, GSI soil\n")
        f.write("\n")

        f.write("suite c96_s2sw\n")

        # Suite-level edits
        f.write("  edit PACKAGEHOME '/lfs/h3/emc/eib/noscrub/%EMC_USER%/gfs/para/packages/gfs.%gfs_ver%'\n")
        f.write("  edit gfs_ver 'v17.0'\n")
        f.write("  edit NET 'gfs'\n")
        f.write("  edit PROJ 'GFS'\n")
        f.write("  edit PROJENVIR 'DEV'\n")
        f.write("  edit MACHINE_SITE 'development'\n")
        f.write("  edit ENVIR 'prod'\n")
        f.write("  edit QUEUE 'devmax'\n")
        f.write("  edit QUEUE_ARCH 'dev_transfer'\n")
        f.write("  edit OUTPUTDIR '/lfs/h3/emc/eib/noscrub/ptmp/%EMC_USER%/ecflow_c96/para/output/prod/today'\n")
        f.write("  edit EXPDIR '/lfs/h3/emc/eib/noscrub/%EMC_USER%/gfs/para/packages/gfs.%gfs_ver%/parm/config/gfs'\n")

        for cycle in cycles:
            cyc = cycle["cyc"]
            prev_cyc = cycle["prev_cyc"]
            has_gfs = cycle["has_gfs"]
            is_cold = cycle["is_cold_start"]

            f.write(f"\n  family {cyc}\n")
            f.write(f"    edit CYC '{cyc}'\n")
            f.write(f"    edit ECF_FILES '%PACKAGEHOME%/ecf/scripts'\n")

            if has_gfs:
                write_gfs_family(f, 4, cyc, prev_cyc)

            write_gdas_family(f, 4, cyc, prev_cyc, is_cold_start=is_cold)
            write_enkfgdas_family(f, 4, cyc, prev_cyc, nens=2, is_cold_start=is_cold)

            if has_gfs:
                write_enkfgfs_family(f, 4, cyc, prev_cyc, nens=2)

            f.write(f"  endfamily\n")

        f.write("endsuite\n")

    print(f"Generated: {outpath}")
    print(f"  Lines: {sum(1 for _ in open(outpath))}")


if __name__ == "__main__":
    main()
