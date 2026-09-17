#!/usr/bin/env python3

"""
GFS forecast-only ecFlow suite generator.

Generates a complete ``.def`` file from the same ``AppConfig`` and task/resource
data that the Rocoto XML generator uses.  The output is self-contained: every
ecFlow edit variable (ECF_HOME, ACCOUNT, QUEUE, per-task WALLTIME, etc.) is
baked into the definition so that ``ecflow_client --load`` works with **no**
subsequent ``--alter`` overrides.

The dependency chain mirrors ``rocoto/gfs_tasks.py`` for forecast-only mode::

    [fetch →] stage_ic [→ waveinit/aerosol_init] → fcst →
        atmos_prod → {tracker, genesis, genesis_fsu, metp, postsnd, ...} →
        [ocean_prod, ice_prod, wave*] → arch_vrfy → cleanup
"""

import os
from logging import getLogger
from typing import Dict, List, Optional, Tuple

from ecflow.ecflow_suite import EcFlowSuite
from applications.applications import AppConfig
from rocoto.tasks_factory import tasks_factory
from wxflow import timedelta_to_HMS

logger = getLogger(__name__.split('.')[-1])

# ── Task name → J-Job script mapping ─────────────────────────────────────
# Maps the logical task name (from get_task_names()) to the J-Job basename
# under dev/jobs/.  Most follow the pattern JGLOBAL_<UPPER> or
# JGFS_ATMOS_<UPPER>.
_JJOB_MAP = {
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

# Resource config name for tasks where the config.resources step name
# differs from the task name used in get_task_names().
_RESOURCE_STEP_MAP = {
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

# Tasks classified as "service" by the Rocoto Tasks class — these run on
# the service partition rather than compute.
_SERVICE_TASKS = {'arch_vrfy', 'stage_ic'}


class GFSForecastOnlyEcFlowSuite(EcFlowSuite):
    """
    ecFlow suite generator for GFS forecast-only workflows.

    Produces a ``.def`` file that mirrors the Rocoto XML for the same
    ``AppConfig``.  All variables are baked into the definition so the
    bootstrap script can simply::

        ecflow_client --load=<path>.def
        ecflow_client --begin=<suite_name>

    Parameters
    ----------
    app_config : AppConfig
        Application configuration object containing GFS settings.
    ecflow_config : Dict
        Dictionary containing ecFlow-specific configuration
        (currently only ``verbosity``).
    """

    def __init__(self, app_config: AppConfig, ecflow_config: Dict) -> None:
        super().__init__(app_config, ecflow_config)

        self._run = list(app_config.task_names.keys())[0]  # 'gfs'
        self._task_names = app_config.task_names[self._run]
        self._options = app_config.run_options[self._run]
        self._configs = app_config.configs[self._run]

        # Create a Rocoto Tasks helper so we can reuse get_resource()
        self._tasks_helper = tasks_factory.create(
            app_config.net, app_config, self._run)

    # ── Public interface ──────────────────────────────────────────────

    def get_cycledefs(self):
        """Return a human-readable cycle summary (not used in .def output)."""
        sdate = self._base['SDATE_GFS']
        edate = self._base['EDATE']
        interval = self._base['interval_gfs']
        return (f"# Cycles: {sdate.strftime('%Y%m%d%H')} – "
                f"{edate.strftime('%Y%m%d%H')} every "
                f"{timedelta_to_HMS(interval)}")

    def write(self, def_file: str = None) -> str:
        """
        Generate the ecFlow ``.def`` file and write it to disk.

        Parameters
        ----------
        def_file : str, optional
            Output path.  Defaults to ``{EXPDIR}/{pslot}.def``.

        Returns
        -------
        str
            The path of the written ``.def`` file.
        """
        if def_file is None:
            def_file = os.path.join(self.expdir, f'{self.pslot}.def')

        suite_name = self.pslot

        lines: List[str] = []
        lines.append(f'# Auto-generated ecFlow suite definition for {suite_name}')
        lines.append(f'# Mode: {self._app_config.mode}  NET: {self._base["NET"]}')
        lines.append(f'# {self.get_cycledefs()}')
        lines.append('')

        # ── Suite header ──────────────────────────────────────────────
        lines.append(f'suite {suite_name}')
        lines += self._suite_variables(indent=2)
        lines.append('')

        # ── RUN family (e.g. "gfs") ──────────────────────────────────
        indent = 2
        lines.append(f'{" " * indent}family {self._run}')
        indent = 4
        lines.append(f'{" " * indent}edit RUN \'{self._run}\'')
        lines.append('')

        # Emit tasks in dependency order with triggers
        prev_task = None
        for task_name in self._task_names:
            task_lines, trigger_target = self._emit_task(
                task_name, indent)
            lines += task_lines
            lines.append('')

        indent = 2
        lines.append(f'{" " * indent}endfamily')
        lines.append('endsuite')
        lines.append('')

        def_content = '\n'.join(lines)

        os.makedirs(os.path.dirname(def_file), exist_ok=True)
        with open(def_file, 'w') as fh:
            fh.write(def_content)

        logger.info(f'ecFlow suite definition written to {def_file}')
        return def_file

    # ── Private helpers ───────────────────────────────────────────────

    def _suite_variables(self, indent: int = 2) -> List[str]:
        """Emit suite-level edit variables."""
        sp = ' ' * indent
        base = self._base
        lines = []

        # ecFlow server connection (placeholders — overwritten by
        # bootstrap or the ecflow_client environment)
        ecf_home = os.environ.get('ECF_HOME', '/tmp/ecflow')
        ecf_host = os.environ.get('ECF_HOST', os.environ.get('HOSTNAME', 'localhost'))
        ecf_port = os.environ.get('ECF_PORT', '3141')

        lines.append(f"{sp}# ecFlow server connection")
        lines.append(f"{sp}edit ECF_LOGHOST '{ecf_host}'")
        lines.append(f"{sp}edit ECF_PORT    '{ecf_port}'")
        lines.append(f"{sp}")
        lines.append(f"{sp}# File locations")
        lines.append(f"{sp}edit ECF_HOME    '{ecf_home}'")
        lines.append(f"{sp}edit ECF_INCLUDE '{ecf_home}/include'")
        lines.append(f"{sp}edit ECF_FILES   '{ecf_home}/scripts'")
        lines.append(f"{sp}edit ECF_JOBOUT  '{ecf_home}/output/%ECF_NAME%.%ECF_TRYNO%'")
        lines.append(f"{sp}")

        # Slurm job submission commands
        lines.append(f"{sp}# Slurm job submission commands")
        lines.append(f"{sp}edit ECF_JOB_CMD  'sbatch %ECF_JOB%'")
        lines.append(f"{sp}edit ECF_KILL_CMD 'scancel %ECF_RID%'")
        lines.append(f"{sp}edit ECF_STATUS_CMD 'squeue -j %ECF_RID%'")
        lines.append(f"{sp}")

        # Experiment identity
        lines.append(f"{sp}# Experiment variables")
        lines.append(f"{sp}edit ENVIR    '{base.get('envir', 'test')}'")
        lines.append(f"{sp}edit NET      '{base['NET']}'")
        lines.append(f"{sp}edit RUN      '{self._run}'")
        lines.append(f"{sp}edit APP      '{self._options.get('app', 'ATM')}'")
        lines.append(f"{sp}edit ACCOUNT  '{base['ACCOUNT']}'")
        lines.append(f"{sp}edit QUEUE    '{base.get('PARTITION_BATCH', 'batch')}'")
        lines.append(f"{sp}edit PSLOT    '{self.pslot}'")
        lines.append(f"{sp}edit CASE     '{base['CASE']}'")
        lines.append(f"{sp}edit FHMAX_GFS '{base.get('FHMAX_GFS', 120)}'")
        lines.append(f"{sp}")

        # Date/time (from SDATE_GFS)
        sdate = base['SDATE_GFS']
        lines.append(f"{sp}edit PDY      '{sdate.strftime('%Y%m%d')}'")
        lines.append(f"{sp}edit CYC      '{sdate.strftime('%H')}'")
        lines.append(f"{sp}")

        # Paths consumed by J-Jobs
        lines.append(f"{sp}# Paths consumed by J-Jobs")
        lines.append(f"{sp}edit HOMEglobal '{self.HOMEglobal}'")
        lines.append(f"{sp}edit EXPDIR     '{self.expdir}'")
        lines.append(f"{sp}edit COMROOT    '{base['COMROOT']}'")
        dataroot = f"{base.get('STMP', '/tmp')}/RUNDIRS/{self.pslot}"
        lines.append(f"{sp}edit DATAROOT   '{dataroot}'")
        lines.append(f"{sp}")

        # Slurm resource defaults (overridden per-task)
        lines.append(f"{sp}# Slurm resource defaults (overridden per-task)")
        lines.append(f"{sp}edit WALLTIME '00:30:00'")
        lines.append(f"{sp}edit NODES    '1'")
        lines.append(f"{sp}edit NTASKS   '1'")
        lines.append(f"{sp}edit CPUS_PER_TASK '1'")
        lines.append(f"{sp}edit EXCLUSIVE 'NO'")

        return lines

    def _get_resource_for_task(self, task_name: str) -> Dict:
        """
        Get the resource dict for a task using the same logic as Rocoto.

        Falls back to sensible defaults if config.resources does not
        define the task (e.g. a newly added task).
        """
        resource_step = _RESOURCE_STEP_MAP.get(task_name, task_name)
        try:
            return self._tasks_helper.get_resource(resource_step)
        except (KeyError, Exception) as e:
            logger.warning(f'Could not get resources for {task_name} '
                           f'(step={resource_step}): {e}. Using defaults.')
            return {
                'walltime': '00:30:00',
                'nodes': 1,
                'ntasks': 1,
                'ppn': 1,
                'threads': 1,
                'memory': None,
                'account': self._base['ACCOUNT'],
                'queue': self._base.get('PARTITION_BATCH', 'batch'),
                'partition': self._base.get('PARTITION_BATCH', 'batch'),
                'native': None,
            }

    def _get_trigger(self, task_name: str) -> Optional[str]:
        """
        Return the ecFlow trigger expression for *task_name*, or None.

        Mirrors the dependency logic from ``rocoto/gfs_tasks.py`` for
        forecast-only mode.
        """
        options = self._options
        tasks = self._task_names

        # Helper: is a task present in this workflow?
        def has(name):
            return name in tasks

        if task_name == 'stage_ic':
            if has('fetch'):
                return 'fetch == complete'
            return None

        if task_name == 'aerosol_init':
            return None  # no intra-cycle dep in forecast-only

        if task_name == 'waveinit':
            return None  # no intra-cycle dep

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

        # Wave post-processing depends on fcst
        if task_name in ('wavepostgridded', 'wavepostpnt',
                         'wavepostbndpnt', 'wavepostbndpntbll'):
            return 'fcst == complete'

        if task_name in ('wavegempak',):
            return 'wavepostgridded == complete'

        if task_name in ('waveawipsbulls', 'waveawipsgridded'):
            return 'wavepostgridded == complete'

        if task_name in ('arch_tars', 'globus_arch'):
            # arch_tars waits for all products + verification
            return 'arch_vrfy == complete'

        if task_name == 'arch_vrfy':
            # arch_vrfy depends on all product and verification tasks
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

    def _emit_task(self, task_name: str, indent: int
                   ) -> Tuple[List[str], str]:
        """
        Emit a single task block with edit variables and trigger.

        Returns (lines, task_name) where task_name can be used as a
        trigger target by downstream tasks.
        """
        sp = ' ' * indent
        lines = []

        res = self._get_resource_for_task(task_name)
        trigger = self._get_trigger(task_name)

        lines.append(f'{sp}task {task_name}')

        tsp = ' ' * (indent + 2)
        lines.append(f"{tsp}edit TASK '{task_name}'")

        # Per-task resource overrides
        walltime = res.get('walltime', '00:30:00')
        nodes = res.get('nodes', 1)
        ntasks = res.get('ntasks', 1)
        threads = res.get('threads', 1)
        partition = res.get('partition')
        native = res.get('native', '')
        is_exclusive = native and '--exclusive' in str(native)

        lines.append(f"{tsp}edit WALLTIME '{walltime}'")
        if nodes > 1:
            lines.append(f"{tsp}edit NODES '{nodes}'")
        if ntasks > 1:
            lines.append(f"{tsp}edit NTASKS '{ntasks}'")
        if threads > 1:
            lines.append(f"{tsp}edit CPUS_PER_TASK '{threads}'")
        if partition and partition != self._base.get('PARTITION_BATCH'):
            lines.append(f"{tsp}edit QUEUE '{partition}'")
        if is_exclusive:
            lines.append(f"{tsp}edit EXCLUSIVE 'YES'")

        # Trigger
        if trigger:
            lines.append(f'{tsp}trigger {trigger}')

        return lines, task_name
