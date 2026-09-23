#!/usr/bin/env python3

"""
GEFS ecFlow task definitions.

Mirrors ``rocoto/gefs_tasks.py``: one method per task, each returning an
ecFlow task dictionary consumed by the suite generator.  Dependencies
are expressed as ecFlow trigger strings rather than Rocoto XML.

GEFS adds ensemble-specific concepts on top of the GFS task model:

- **fcst_ens** (ensemble forecast): one forecast per ensemble member, each
  potentially segmented.  Returns a dict with ``ensemble_task: True``.
- **Per-member product tasks**: ``atmos_prod``, ``ocean_prod``, ``ice_prod``,
  ``wavepostgridded`` run once per member (mem000 .. memNNN).  These
  return dicts with ``'ensemble_task': True`` so the suite generator
  wraps them in per-member families.
- **Ensemble aggregation tasks**: ``atmos_ensstat``, ``wave_stat`` run
  after all member products complete.
"""

from logging import getLogger
from typing import Dict, List, Optional

from applications.applications import AppConfig
from ecflow.ecflow_tasks import EcFlowTasks

logger = getLogger(__name__.split('.')[-1])


class GEFSEcFlowTasks(EcFlowTasks):
    """Per-task ecFlow definitions for GEFS workflows."""

    def __init__(self, app_config: AppConfig, run: str) -> None:
        super().__init__(app_config, run)
        self._nmem = self.nmem  # from Tasks base (NMEM_ENS)
        self._gefstype = getattr(app_config, 'gefstype', 'gefs-offline')

    # ── Helper: ensemble-aware product task ───────────────────────────

    def _ensemble_product_task(self, task_name: str, *,
                               jjob: str,
                               config: str,
                               component: str,
                               trigger: Optional[str] = None,
                               resource_name: Optional[str] = None) -> Dict:
        """
        Build a product task dict that also needs per-member iteration.

        The dict is identical to ``_product_task`` but adds
        ``ensemble_task: True`` so the suite generator wraps the
        product family inside a ``family memNNN`` for each member.
        """
        task_dict = self._product_task(
            task_name,
            jjob=jjob,
            config=config,
            component=component,
            trigger=trigger,
            resource_name=resource_name,
        )
        task_dict['ensemble_task'] = True
        task_dict['nmem'] = self._nmem
        return task_dict

    def _ensemble_simple_task(self, task_name: str, *,
                              jjob: str,
                              trigger: Optional[str] = None,
                              resource_name: Optional[str] = None,
                              service: bool = False) -> Dict:
        """
        Build a simple (non-product) task that runs per member.

        Adds ``ensemble_task: True`` so the suite wraps it in member
        families.
        """
        task_dict = self._simple_task(
            task_name,
            jjob=jjob,
            trigger=trigger,
            resource_name=resource_name,
            service=service,
        )
        task_dict['ensemble_task'] = True
        task_dict['nmem'] = self._nmem
        return task_dict

    # ── Simple tasks (run once, not per member) ───────────────────────

    def stage_ic(self):
        return self._simple_task(
            'stage_ic',
            jjob='JGLOBAL_STAGE_IC',
            service=True,
        )

    def gen_control_ic(self):
        return self._simple_task(
            'gen_control_ic',
            jjob='JGLOBAL_ATMOS_CHGRES_GEN_CONTROL',
            trigger='stage_ic == complete',
        )

    def waveinit(self):
        return self._simple_task(
            'waveinit',
            jjob='JGLOBAL_WAVE_INIT',
        )

    def prep_emissions(self):
        return self._simple_task(
            'prep_emissions',
            jjob='JGLOBAL_PREP_EMISSIONS',
        )

    def fcst(self):
        """Control forecast (mem000)."""
        deps = ['stage_ic == complete']
        if self._gefstype == 'gefs-real-time':
            deps = ['gen_control_ic == complete']
        if self._has_task('waveinit'):
            deps.append('waveinit == complete')
        if self._has_task('prep_emissions'):
            deps.append('prep_emissions == complete')
        trigger = ' and '.join(deps)

        task_dict = self._simple_task(
            'fcst',
            jjob='JGLOBAL_FCST',
            trigger=trigger,
        )
        # Mark as segmented so the suite can emit FCST_SEGMENT
        fcst_segments = self.options.get('fcst_segments', [0])
        if fcst_segments:
            num_segments = len(fcst_segments) - 1
        else:
            num_segments = 1
        task_dict['num_segments'] = max(num_segments, 1)
        return task_dict

    # ── Ensemble forecast (per member) ────────────────────────────────

    def fcst_ens(self):
        """Ensemble member forecasts (mem001..memNNN).

        Returns a dict with ``ensemble_task: True``.  The suite
        generator iterates members and emits a family per member,
        each containing a (potentially segmented) forecast task.
        """
        deps = ['stage_ic == complete']
        if self._has_task('waveinit'):
            deps.append('waveinit == complete')
        if self._has_task('prep_emissions'):
            deps.append('prep_emissions == complete')
        trigger = ' and '.join(deps)

        task_dict = self._simple_task(
            'fcst_ens',
            jjob='JGLOBAL_FCST',
            trigger=trigger,
            resource_name='efcs',
        )
        task_dict['ensemble_task'] = True
        task_dict['nmem'] = self._nmem
        # Segmented forecasts
        fcst_segments = self.options.get('fcst_segments', [0])
        if fcst_segments:
            num_segments = len(fcst_segments) - 1
        else:
            num_segments = 1
        task_dict['num_segments'] = max(num_segments, 1)
        return task_dict

    # ── Per-member product tasks ──────────────────────────────────────

    def atmos_prod(self):
        return self._ensemble_product_task(
            'atmos_prod',
            jjob='JGLOBAL_ATMOS_PRODUCTS',
            config='atmos_products',
            component='atmos',
            trigger='fcst == complete',
        )

    def ocean_prod(self):
        return self._ensemble_product_task(
            'ocean_prod',
            jjob='JGLOBAL_OCEANICE_PRODUCTS',
            config='oceanice_products',
            component='ocean',
            trigger='fcst == complete',
        )

    def ice_prod(self):
        return self._ensemble_product_task(
            'ice_prod',
            jjob='JGLOBAL_OCEANICE_PRODUCTS',
            config='oceanice_products',
            component='ice',
            trigger='fcst == complete',
        )

    def wavepostgridded(self):
        return self._ensemble_product_task(
            'wavepostgridded',
            jjob='JGLOBAL_WAVE_POST_GRIDDED',
            config='wavepostgridded',
            component='wave',
            trigger='fcst == complete',
        )

    # ── Per-member simple tasks ───────────────────────────────────────

    def postsnd(self):
        return self._ensemble_simple_task(
            'postsnd',
            jjob='JGFS_ATMOS_POST_SND',
            trigger='fcst == complete',
        )

    def gempak(self):
        return self._ensemble_simple_task(
            'gempak',
            jjob='JGFS_ATMOS_GEMPAK',
            trigger='atmos_prod == complete',
        )

    def extractvars(self):
        deps = []
        if self._has_task('atmos_prod'):
            deps.append('atmos_prod == complete')
        if self._has_task('ocean_prod'):
            deps.append('ocean_prod == complete')
        if self._has_task('ice_prod'):
            deps.append('ice_prod == complete')
        if self._has_task('wavepostgridded'):
            deps.append('wavepostgridded == complete')
        trigger = ' and '.join(deps) if deps else None

        return self._ensemble_simple_task(
            'extractvars',
            jjob='JGLOBAL_EXTRACTVARS',
            trigger=trigger,
        )

    # ── Ensemble aggregation tasks (run once, after all members) ──────

    def atmos_ensstat(self):
        """Ensemble mean/spread statistics.

        Triggers on *all* per-member atmos_prod families completing.
        The suite generator builds the trigger expression from the
        member family names.
        """
        task_dict = self._simple_task(
            'atmos_ensstat',
            jjob='JGLOBAL_ATMOS_ENSSTAT',
        )
        # The suite generator will build the actual trigger from
        # all member atmos_prod completions.  We store a sentinel.
        task_dict['trigger'] = '__ALL_MEMBER_ATMOS_PROD__'
        return task_dict

    def awips(self):
        return self._simple_task(
            'awips',
            jjob='JGFS_ATMOS_AWIPS_20KM_1P0',
            resource_name='awips',
            trigger='atmos_ensstat == complete',
        )

    def wave_stat(self):
        """Wave ensemble statistics.

        Triggers on all per-member wavepostgridded families completing.
        """
        task_dict = self._simple_task(
            'wave_stat',
            jjob='JGEFS_WAVE_STAT',
        )
        task_dict['trigger'] = '__ALL_MEMBER_WAVEPOSTGRIDDED__'
        return task_dict

    def wave_stat_pnt(self):
        return self._simple_task(
            'wave_stat_pnt',
            jjob='JGEFS_WAVE_STAT_PNT',
            trigger='wave_stat == complete',
        )

    # ── Archive and cleanup (run once) ────────────────────────────────

    def arch_vrfy(self):
        deps = ['atmos_prod == complete']
        if self._has_task('atmos_ensstat'):
            deps.append('atmos_ensstat == complete')
        if self._has_task('ocean_prod'):
            deps.append('ocean_prod == complete')
        if self._has_task('ice_prod'):
            deps.append('ice_prod == complete')
        if self._has_task('wavepostgridded'):
            deps.append('wavepostgridded == complete')
        if self._has_task('wave_stat_pnt'):
            deps.append('wave_stat_pnt == complete')
        if self._has_task('extractvars'):
            deps.append('extractvars == complete')
        trigger = ' and '.join(deps)

        return self._simple_task(
            'arch_vrfy',
            jjob='JGLOBAL_ARCHIVE_VRFY',
            trigger=trigger,
            service=True,
        )

    def arch_tars(self):
        return self._simple_task(
            'arch_tars',
            jjob='JGLOBAL_ARCHIVE_TARS',
            trigger='arch_vrfy == complete',
        )

    def globus_arch(self):
        return self._simple_task(
            'globus_arch',
            jjob='JGLOBAL_GLOBUS_ARCH',
            resource_name='arch_tars',
            trigger='arch_vrfy == complete',
        )

    def cleanup(self):
        deps = ['arch_vrfy == complete']
        if self._has_task('arch_tars'):
            deps.append('arch_tars == complete')
        if self._has_task('globus_arch'):
            deps.append('globus_arch == complete')
        trigger = ' and '.join(deps)

        return self._simple_task(
            'cleanup',
            jjob='JGLOBAL_CLEANUP',
            trigger=trigger,
        )
