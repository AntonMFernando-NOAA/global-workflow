#!/usr/bin/env python3

"""
Cycled GFS ecFlow task definitions.

Adds the data assimilation and ensemble tasks to ``GFSEcFlowTasks`` and
gives the forecast, archive and cleanup tasks their cycled dependencies.
Mirrors the cycled part of ``rocoto/gfs_tasks.py``.

A trigger lists every task a task may wait for.  The cycled suite drops
the entries for tasks that do not run in the cycle, so one list covers
the first (half) cycle, the later cycles and the different options.  The
Rocoto data dependencies on external files are not translated.

The tasks without a script in ``dev/ecflow/scripts`` run the Rocoto job
card of the same task (``card``).
"""

from logging import getLogger
from typing import Dict, List

import numpy as np

from applications.applications import AppConfig
from ecflowgw.ecflow_tasks import ref
from ecflowgw.gfs_ecflow_tasks import GFSEcFlowTasks

logger = getLogger(__name__.split('.')[-1])


class GFSCycledEcFlowTasks(GFSEcFlowTasks):
    """Per-task ecFlow definitions for cycled GFS workflows."""

    def __init__(self, app_config: AppConfig, run: str) -> None:
        super().__init__(app_config, run)
        # Rocoto names the deterministic run of an ensemble run
        self._det_run = run.replace('enkf', '')
        self._igdas = int(self._base['interval_gdas'].total_seconds() // 3600)

    # ── Helpers ───────────────────────────────────────────────────────

    def _card_task(self, task_name: str, *, card: str, jjob: str,
                   deps: List[str] = (), resource_name: str = None,
                   envars: Dict[str, str] = None) -> Dict:
        """Build a task that runs a Rocoto job card.

        Parameters
        ----------
        deps : list of str
            Tasks that must be complete; see the module docstring.
        """
        trigger = ' and '.join(f'{dep} == complete' for dep in deps) or None
        return self._simple_task(task_name, jjob=jjob, card=card,
                                 trigger=trigger,
                                 resource_name=resource_name, envars=envars)

    @staticmethod
    def _extend_trigger(task: Dict, deps: List[str]) -> Dict:
        """Add *deps* to the trigger of *task*."""
        parts = [task['trigger']] if task['trigger'] else []
        parts += [f'{dep} == complete' for dep in deps]
        task['trigger'] = ' and '.join(parts) or None
        return task

    # ── Tasks of the forecast-only suite with cycled dependencies ─────

    def waveinit(self):
        task = super().waveinit()
        return self._extend_trigger(task, ['prep'])

    def fcst(self):
        deps = ['stage_ic', 'waveinit', 'sfcanl_gcycle', 'marineanlfinal',
                'snowanl', 'aeroanlfinal']
        if self.options['do_gsisoilda'] and self.run == 'gdas':
            deps.append('sfcanl_regrid')

        task = self._simple_task(
            'fcst', jjob='JGLOBAL_FCST',
            trigger=' and '.join(f'{dep} == complete' for dep in deps))
        if self.run == 'gfs':
            task['num_segments'] = max(len(self.options['fcst_segments']) - 1, 1)
        return task

    def arch_vrfy(self):
        task = super().arch_vrfy()
        return self._extend_trigger(task, ['atmanlprod', 'fit2obs'])

    def arch_tars(self):
        task = super().arch_tars()
        return self._extend_trigger(
            task, ['atmanlprod', 'fit2obs', 'verfozn', 'verfrad', 'vminmon',
                   'anlstat', 'tracker', 'genesis', 'atmos_prod',
                   'wavepostgridded', 'wavepostpnt', 'wavepostbndpnt',
                   'wavepostbndpntbll', 'ocean_prod', 'ice_prod'])

    def cleanup(self):
        if self.run in ('enkfgdas', 'enkfgfs'):
            deps = ['epos', 'echgres', 'earc_vrfy', 'earc_tars']
        else:
            deps = ['atmos_prod', 'atmanlprod', 'fit2obs', 'verfozn',
                    'verfrad', 'vminmon', 'anlstat', 'tracker', 'genesis',
                    'wavepostpnt', 'wavepostbndpnt', 'wavepostbndpntbll',
                    'ocean_prod', 'ice_prod', 'arch_vrfy', 'arch_tars']
        # The gdas history is still needed by the next gfs forecast
        if self.run in ('gdas', 'enkfgdas'):
            deps.insert(0, ref('fcst', 'gfs', self._igdas))
        return self._simple_task(
            'cleanup', jjob='JGLOBAL_CLEANUP',
            trigger=' and '.join(f'{dep} == complete' for dep in deps))

    # ── Analysis ──────────────────────────────────────────────────────

    def prep_sfc(self):
        return self._card_task('prep_sfc', card='prep_sfc',
                               jjob='JGLOBAL_ATMOS_PREP_SFC')

    def prep(self):
        deps = [ref('atmos_prod', 'gdas', -self._igdas), 'prep_sfc']
        return self._card_task('prep', card='prep',
                               jjob='JOBSPROC_GLOBAL_PREP', deps=deps)

    def anal(self):
        deps = ['prep']
        if self.options['do_hybvar']:
            deps.append(ref('epos', 'enkfgdas', -self._igdas))
        return self._card_task('anal', card='anal', jjob='JGLOBAL_ATMOS_ANAL',
                               deps=deps)

    def analcalc(self):
        if self.options['do_jediatmvar'] and not self.options['do_jediatmens']:
            deps = ['atmanlfinal']
        else:
            deps = ['anal']
        deps.append('sfcanl_gcycle')
        if self.options['do_gsisoilda'] and self.run == 'gdas':
            deps.append('sfcanl_regrid')
        if self.options['do_hybvar'] and self.run == 'gdas':
            deps.append(ref('echgres', 'enkfgdas', -self._igdas))
        return self._card_task('analcalc', card='analcalc',
                               jjob='JGLOBAL_ATMOS_ANAL_CALC', deps=deps)

    def analdiag(self):
        return self._card_task('analdiag', card='analdiag',
                               jjob='JGLOBAL_ATMOS_ANAL_DIAG', deps=['anal'])

    def sfcanl_gcycle(self):
        deps = ['atmanlfinal' if self.options['do_jediatmvar'] else 'anal']
        if self.options['do_jedisnowda']:
            deps.append('snowanl')
        if (self.options['do_gsisoilda'] and self.run == 'gdas'
                and not self.options['do_gsiliau']):
            deps.append('sfcanl_regrid')
        return self._card_task('sfcanl_gcycle', card='sfcanl_gcycle',
                               jjob='JGLOBAL_ATMOS_ANAL_SFC_GCYCLE', deps=deps)

    def sfcanl_regrid(self):
        return self._card_task('sfcanl_regrid', card='sfcanl_regrid',
                               jjob='JGLOBAL_ATMOS_ANAL_SFC_REGRID',
                               deps=[ref('eupd', 'enkfgdas')])

    def snowanl(self):
        return self._card_task('snowanl', card='snowanl',
                               jjob='JGLOBAL_SNOW_ANAL', deps=['prep'])

    def atmanlupp(self):
        return self._card_task('atmanlupp', card='upp',
                               jjob='JGLOBAL_ATMOS_UPP', resource_name='upp',
                               deps=['analcalc'],
                               envars={'UPP_RUN': 'analysis', 'FHR3': '000'})

    def atmanlprod(self):
        return self._card_task('atmanlprod', card='atmos_products',
                               jjob='JGLOBAL_ATMOS_PRODUCTS',
                               resource_name='atmos_products',
                               deps=['atmanlupp'], envars={'FHR_LIST': '-1'})

    # ── Marine analysis ───────────────────────────────────────────────

    def prepoceanobs(self):
        return self._card_task('prepoceanobs', card='prepoceanobs',
                               jjob='JGLOBAL_PREP_OCEAN_OBS',
                               deps=[ref('fcst', 'gdas', -self._igdas)])

    def marinebmatinit(self):
        deps = [ref('fcst', 'gdas', -self._igdas)]
        if self.options['do_hybvar_ocn']:
            deps.append(ref('efcs', 'enkfgdas', -self._igdas))
        return self._card_task('marinebmatinit', card='marinebmatinit',
                               jjob='JGLOBAL_MARINE_BMAT_INIT', deps=deps)

    def marinebmat(self):
        return self._card_task('marinebmat', card='marinebmat',
                               jjob='JGLOBAL_MARINE_BMAT',
                               deps=['marinebmatinit'])

    def marineanlinit(self):
        deps = ['prepoceanobs', 'marinebmat',
                ref('fcst', 'gdas', -self._igdas)]
        return self._card_task('marineanlinit', card='marineanlinit',
                               jjob='JGLOBAL_MARINE_ANAL_INIT', deps=deps)

    def marineanlvar(self):
        return self._card_task('marineanlvar', card='marineanlvar',
                               jjob='JGLOBAL_MARINE_ANAL_VAR',
                               deps=['marineanlinit'])

    def marineanlchkpt(self):
        return self._card_task('marineanlchkpt', card='marineanlchkpt',
                               jjob='JGLOBAL_MARINE_ANAL_CHKPT',
                               deps=['marineanlvar'])

    def marineanlfinal(self):
        deps = ['marineanlchkpt']
        if self._base.get('DOLETKF_OCN_INC', True):
            deps.append(ref('marineanlecen', 'enkfgdas'))
        return self._card_task('marineanlfinal', card='marineanlfinal',
                               jjob='JGLOBAL_MARINE_ANAL_FINAL', deps=deps)

    # ── Monitoring and verification ───────────────────────────────────

    def vminmon(self):
        return self._card_task('vminmon', card='vminmon',
                               jjob='JGLOBAL_ATMOS_VMINMON', deps=['anal'])

    def fit2obs(self):
        return self._card_task('fit2obs', card='fit2obs',
                               jjob='JGDAS_FIT2OBS', deps=['atmos_prod'])

    def verfozn(self):
        return self._card_task('verfozn', card='verfozn',
                               jjob='JGDAS_ATMOS_VERFOZN', deps=['analdiag'])

    def verfrad(self):
        return self._card_task('verfrad', card='verfrad',
                               jjob='JGDAS_ATMOS_VERFRAD', deps=['analdiag'])

    def anlstat(self):
        deps = ['atmanlfinal' if self.options['do_jediatmvar'] else 'analdiag',
                'marineanlfinal', 'snowanl', 'aeroanlfinal']
        return self._card_task('anlstat', card='anlstat',
                               jjob='JGLOBAL_ANALYSIS_STATS', deps=deps)

    # ── Ensemble ──────────────────────────────────────────────────────

    def eobs(self):
        deps = [ref('prep', self._det_run),
                ref('epos', 'enkfgdas', -self._igdas)]
        return self._card_task('eobs', card='eobs',
                               jjob='JGLOBAL_ATMOS_ENS_OBSERVER', deps=deps)

    def ediag(self):
        return self._card_task('ediag', card='ediag',
                               jjob='JGLOBAL_ATMOS_ENS_DIAG', deps=['eobs'])

    def eupd(self):
        return self._card_task('eupd', card='eupd',
                               jjob='JGLOBAL_ATMOS_ENS_UPDATE', deps=['ediag'])

    def ecen(self):
        if self._base.get('DOIAU_ENKF', False):
            fhrs = self._base.get('IAUFHRS', '[6]')
            necengrp = self._configs['ecen']['NECENGRP']
            ngrps = necengrp if len(fhrs) > necengrp else len(fhrs)
            fhrs = [f'{int(fhr):03d}' for fhr in fhrs]
            groups = [group.tolist() for group in np.array_split(fhrs, ngrps)]
            children = {f'grp{grp:03d}': {'FHRGRP': f'{grp:03d}',
                                          'FHRLST': '_'.join(fhrs_in_grp)}
                        for grp, fhrs_in_grp in enumerate(groups)}
        else:
            children = {'grp000': {'FHRGRP': '000', 'FHRLST': 'f006'}}

        deps = [ref('analcalc', self._det_run), 'eupd']
        return self._group_task(
            'ecen', jjob='JGLOBAL_ATMOS_ENS_RECENTER', card='ecen',
            children=children,
            trigger=' and '.join(f'{dep} == complete' for dep in deps))

    def echgres(self):
        deps = [ref('fcst', self._det_run), ref('efcs/mem001')]
        return self._card_task('echgres', card='echgres',
                               jjob='JENKFGDAS_ATMOS_ENS_CHANGE_RES',
                               deps=deps)

    def marineanlecen(self):
        if self._base.get('DOLETKF_OCN_INC', True):
            deps = ['marineanlletkf', ref('marineanlchkpt', self._det_run)]
        else:
            deps = [ref('marinebmatinit', self._det_run)]
        return self._card_task('marineanlecen', card='marineanlecen',
                               jjob='JGLOBAL_MARINE_ENS_RECENTER', deps=deps)

    def esnowanl(self):
        deps = [ref('epos', 'enkfgdas', -self._igdas),
                ref('prep', self._det_run)]
        return self._card_task('esnowanl', card='esnowanl',
                               jjob='JGLOBAL_SNOW_ENS_ANAL', deps=deps)

    def esfc_gcycle(self):
        det_run = self._det_run
        if self.options['do_jediatmens']:
            deps = ['atmensanlfinal']
        elif self.options['do_enkfonly_atm']:
            deps = ['eupd']
        elif self.options['do_jediatmvar']:
            deps = [ref('atmanlfinal', det_run)]
        else:
            deps = [ref('anal', det_run)]
        if self.options['do_jedisnowda']:
            deps.append('esnowanl')
        if (self.options['do_gsisoilda'] and self.run == 'gdas'
                and not self.options['do_gsiliau']):
            deps.append(ref('esfc_regrid', 'gdas'))
        return self._card_task('esfc_gcycle', card='esfc_gcycle',
                               jjob='JGLOBAL_ATMOS_ENS_ANAL_SFC_GCYCLE',
                               deps=deps)

    def esfc_regrid(self):
        return self._card_task('esfc_regrid', card='esfc_regrid',
                               jjob='JGLOBAL_ATMOS_ENS_ANAL_SFC_REGRID',
                               deps=['eupd'])

    def efcs(self):
        deps = ['ecen', 'esfc_gcycle', 'esfc_regrid', 'stage_ic']
        if self.options['do_hybvar_ocn']:
            deps.append('marineanlecen')
        children = {f'mem{mem:03d}': {'ENSMEM': f'{mem:03d}',
                                      'MEMDIR': f'mem{mem:03d}'}
                    for mem in range(1, self.nmem + 1)}
        return self._group_task(
            'efcs', jjob='JGLOBAL_FCST', children=children, script='fcst',
            trigger=' and '.join(f'{dep} == complete' for dep in deps))

    def epos(self):
        epos = self._configs['epos']
        fhmax = epos['FHMAX_ENKF']
        fhout = epos['FHOUT_ENKF']
        if self.run == 'enkfgfs':
            fhmax = epos['FHMAX_ENKF_GFS']
            fhout = epos['FHOUT_ENKF_GFS']
        fhrs = [f'f{fhr:03d}'
                for fhr in range(epos['FHMIN_ENKF'], fhmax + fhout, fhout)]
        ngrps = min(epos['NEPOSGRP'], len(fhrs))
        groups = [group.tolist() for group in np.array_split(fhrs, ngrps)]
        children = {f'grp{grp:03d}': {'FHRGRP': f'{grp:03d}',
                                      'FHRLST': '_'.join(fhrs_in_grp)}
                    for grp, fhrs_in_grp in enumerate(groups)}
        return self._group_task('epos', jjob='JENKFGDAS_ENS_POST',
                                card='epos', children=children,
                                trigger='efcs == complete')

    def earc_vrfy(self):
        if self.run == 'enkfgdas':
            deps = ['epos']
            if not self.options['do_jediatmvar']:
                deps.append('echgres')
        else:
            deps = ['esfc_gcycle']
        return self._card_task('earc_vrfy', card='earc_vrfy',
                               jjob='JGLOBAL_ENKF_ARCHIVE_VRFY', deps=deps)

    def earc_tars(self):
        if self.run == 'enkfgdas':
            deps = ['epos', 'echgres', 'marineanlletkf']
        else:
            deps = ['esfc_gcycle', 'ecen', 'marineanlecen',
                    ref('marineanlfinal', 'gfs'), 'marineanlletkf']
        # Integer division is floor division, but this needs ceiling division
        n_groups = -(self.nmem // -self._configs['earc_groups']['NMEM_EARCGRP'])
        children = {f'grp{grp:02d}': {'ENSGRP': f'{grp:02d}'}
                    for grp in range(0, n_groups + 1)}
        return self._group_task(
            'earc_tars', jjob='JGLOBAL_ENKF_ARCHIVE_TARS', card='earc_tars',
            resource_name='arch_tars', children=children,
            trigger=' and '.join(f'{dep} == complete' for dep in deps))
