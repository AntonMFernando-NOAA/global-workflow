#!/usr/bin/env python3

"""
C48_ATM ecFlow suite definition.

Subclass of ``GFSForecastOnlyEcFlowSuite`` that supplies the task
mappings, resource overrides, product-task definitions, and dependency
triggers specific to the C48 atmosphere-only (ATM) forecast case.

The dependency chain mirrors ``rocoto/gfs_tasks.py`` for forecast-only
mode with the ATM app::

    [fetch ->] stage_ic [-> waveinit/aerosol_init] -> fcst ->
        atmos_prod -> {tracker, genesis, genesis_fsu, metp, postsnd, ...} ->
        [ocean_prod, ice_prod, wave*] -> arch_vrfy -> cleanup
"""

from logging import getLogger
from typing import Optional

from ecflow.gfs_forecast_only_ecflow import GFSForecastOnlyEcFlowSuite

logger = getLogger(__name__.split('.')[-1])


class C48ATMEcFlowSuite(GFSForecastOnlyEcFlowSuite):
    """
    ecFlow suite generator for the C48_ATM forecast-only case.

    Populates the class-level task metadata and overrides
    ``_get_trigger()`` with the ATM-specific dependency chain.
    """

    # ── Task name -> J-Job script mapping ─────────────────────────────
    # Maps the logical task name (from get_task_names()) to the J-Job
    # basename under dev/jobs/.
    JJOB_MAP = {
        'fetch': 'JGLOBAL_FETCH',
        'stage_ic': 'JGLOBAL_STAGE_IC',
        'aerosol_init': 'JGLOBAL_AEROSOL_INIT',
        'waveinit': 'JGLOBAL_WAVE_INIT',
        'fcst': 'JGLOBAL_FCST',
        'atmupp': 'JGLOBAL_ATMOS_UPP',
        'goesupp': 'JGLOBAL_ATMOS_UPP',
        'atmos_prod': 'JGLOBAL_ATMOS_PRODUCTS',
        'ocean_prod': 'JGLOBAL_OCEANICE_PRODUCTS',
        'ice_prod': 'JGLOBAL_OCEANICE_PRODUCTS',
        'tracker': 'JGFS_ATMOS_CYCLONE_TRACKER',
        'genesis': 'JGFS_ATMOS_CYCLONE_GENESIS',
        'genesis_fsu': 'JGFS_ATMOS_CYCLONE_GENESIS_FSU',
        'metp': 'JGFS_ATMOS_VERIFICATION',
        'postsnd': 'JGFS_ATMOS_POSTSND',
        'gempak': 'JGFS_ATMOS_GEMPAK',
        'gempakmeta': 'JGFS_ATMOS_GEMPAK_META',
        'awips_20km_1p0deg': 'JGFS_ATMOS_AWIPS_20KM_1P0',
        'fbwind': 'JGFS_ATMOS_FBWIND',
        'wavepostgridded': 'JGLOBAL_WAVE_POST_GRIDDED',
        'wavepostpnt': 'JGLOBAL_WAVE_POST_PNT',
        'wavepostbndpnt': 'JGLOBAL_WAVE_POST_BNDPNT',
        'wavepostbndpntbll': 'JGLOBAL_WAVE_POST_BNDPNTBLL',
        'wavegempak': 'JGFS_WAVE_GEMPAK',
        'waveawipsbulls': 'JGFS_WAVE_AWIPS_BULLS',
        'waveawipsgridded': 'JGFS_WAVE_AWIPS_GRIDDED',
        'arch_tars': 'JGLOBAL_ARCHIVE_TARS',
        'globus_arch': 'JGLOBAL_GLOBUS_ARCHIVE',
        'arch_vrfy': 'JGLOBAL_ARCHIVE_VRFY',
        'cleanup': 'JGLOBAL_CLEANUP',
    }

    # Resource config name overrides for tasks where the config step
    # name differs from the logical task name.
    RESOURCE_STEP_MAP = {
        'atmupp': 'upp',
        'goesupp': 'upp',
        'atmos_prod': 'atmos_products',
        'ocean_prod': 'oceanice_products',
        'ice_prod': 'oceanice_products',
        'awips_20km_1p0deg': 'awips',
        'arch_vrfy': 'arch_vrfy',
        'arch_tars': 'arch_tars',
        'globus_arch': 'arch_tars',
    }

    # Tasks that run on the service partition.
    SERVICE_TASKS = {'arch_vrfy', 'stage_ic'}

    # Product tasks that process forecast hours in groups.
    PRODUCT_TASKS = {
        'atmos_prod': {'config': 'atmos_products', 'component': 'atmos'},
        'ocean_prod': {'config': 'oceanice_products', 'component': 'ocean'},
        'ice_prod': {'config': 'oceanice_products', 'component': 'ice'},
        'wavepostgridded': {'config': 'wavepostgridded', 'component': 'wave'},
    }

    # ── Trigger logic ─────────────────────────────────────────────────

    def _get_trigger(self, task_name: str) -> Optional[str]:
        """
        Return the ecFlow trigger expression for *task_name*.

        Mirrors the dependency logic from ``rocoto/gfs_tasks.py`` for
        forecast-only ATM mode.
        """
        tasks = self._task_names

        def has(name):
            return name in tasks

        if task_name == 'stage_ic':
            if has('fetch'):
                return 'fetch == complete'
            return None

        if task_name == 'aerosol_init':
            return None

        if task_name == 'waveinit':
            return None

        if task_name == 'fcst':
            deps = ['stage_ic == complete']
            if has('waveinit'):
                deps.append('waveinit == complete')
            if has('aerosol_init'):
                deps.append('aerosol_init == complete')
            return ' and '.join(deps)

        if task_name == 'atmupp':
            return 'fcst == complete'

        if task_name == 'goesupp':
            return 'fcst == complete'

        if task_name == 'atmos_prod':
            return 'fcst == complete'

        if task_name == 'ocean_prod':
            return 'fcst == complete'

        if task_name == 'ice_prod':
            return 'fcst == complete'

        if task_name in ('tracker', 'genesis', 'genesis_fsu', 'metp'):
            return 'atmos_prod == complete'

        if task_name == 'postsnd':
            return 'atmos_prod == complete'

        if task_name in ('gempak', 'gempakmeta'):
            return 'atmos_prod == complete'

        if task_name in ('awips_20km_1p0deg', 'fbwind'):
            return 'atmos_prod == complete'

        if task_name in ('wavepostgridded', 'wavepostpnt',
                         'wavepostbndpnt', 'wavepostbndpntbll'):
            return 'fcst == complete'

        if task_name in ('wavegempak',):
            return 'wavepostgridded == complete'

        if task_name in ('waveawipsbulls', 'waveawipsgridded'):
            return 'wavepostgridded == complete'

        if task_name in ('arch_tars', 'globus_arch'):
            return 'arch_vrfy == complete'

        if task_name == 'arch_vrfy':
            deps = ['atmos_prod == complete']
            if has('tracker'):
                deps.append('tracker == complete')
            if has('genesis'):
                deps.append('genesis == complete')
            if has('genesis_fsu'):
                deps.append('genesis_fsu == complete')
            if has('ocean_prod'):
                deps.append('ocean_prod == complete')
            if has('ice_prod'):
                deps.append('ice_prod == complete')
            if has('wavepostgridded'):
                deps.append('wavepostgridded == complete')
            if has('wavepostpnt'):
                deps.append('wavepostpnt == complete')
            if has('wavepostbndpnt'):
                deps.append('wavepostbndpnt == complete')
            if has('wavepostbndpntbll'):
                deps.append('wavepostbndpntbll == complete')
            return ' and '.join(deps)

        if task_name == 'cleanup':
            deps = ['arch_vrfy == complete']
            if has('arch_tars'):
                deps.append('arch_tars == complete')
            if has('globus_arch'):
                deps.append('globus_arch == complete')
            return ' and '.join(deps)

        return None
