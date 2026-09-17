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
from rocoto.tasks import Tasks
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

# Product tasks that process forecast hours in groups.
_PRODUCT_TASKS = {
    'atmos_prod': {'config': 'atmos_products', 'component': 'atmos'},
    'ocean_prod': {'config': 'oceanice_products', 'component': 'ocean'},
    'ice_prod': {'config': 'oceanice_products', 'component': 'ice'},
    'wavepostgridded': {'config': 'wavepostgridded', 'component': 'wave'},
}


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

        # ── Cycle family (e.g. "2021032312") ─────────────────────────
        sdate = self._base['SDATE_GFS']
        cycle_str = sdate.strftime('%Y%m%d%H')
        lines.append(f'{" " * indent}family {cycle_str}')
        indent = 6
        lines.append(f'{" " * indent}edit PDY \'{sdate.strftime("%Y%m%d")}\'')
        lines.append(f'{" " * indent}edit CYC \'{sdate.strftime("%H")}\'')
        lines.append('')

        # Emit tasks with {RUN}_ prefix (Rocoto naming convention)
        for task_name in self._task_names:
            task_lines, trigger_target = self._emit_task(
                task_name, indent)
            lines += task_lines
            lines.append('')

        # Close cycle family
        indent = 4
        lines.append(f'{" " * indent}endfamily')

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
        # ECF_HOME holds runtime .job files; ECF_JOBOUT holds job stdout.
        # Both go under ROTDIR/logs/{YYYYMMDDHH}/ to match Rocoto's layout.
        sdate = base['SDATE_GFS']
        cycle_dir = sdate.strftime('%Y%m%d%H')
        rotdir = base.get('ROTDIR', os.path.join(str(base.get('COMROOT', '/tmp')),
                                                  self.pslot))
        ecf_log_dir = os.path.join(rotdir, 'logs', cycle_dir)

        ecf_host = os.environ.get('ECF_HOST', os.environ.get('HOSTNAME', 'localhost'))
        ecf_port = os.environ.get('ECF_PORT', '3141')

        # ECF_FILES and ECF_INCLUDE point to the .ecf source in the repo.
        ecf_files = os.environ.get('ECF_FILES',
                                   os.path.join(self.HOMEglobal, 'dev', 'ecf',
                                                'ursa', 'scripts'))
        ecf_include = os.environ.get('ECF_INCLUDE',
                                     os.path.join(self.HOMEglobal, 'dev', 'ecf',
                                                  'ursa', 'include'))

        lines.append(f"{sp}# ecFlow server connection")
        lines.append(f"{sp}edit ECF_LOGHOST '{ecf_host}'")
        lines.append(f"{sp}edit ECF_PORT    '{ecf_port}'")
        lines.append(f"{sp}")
        lines.append(f"{sp}# File locations")
        lines.append(f"{sp}edit ECF_HOME    '{ecf_log_dir}'")
        lines.append(f"{sp}edit ECF_INCLUDE '{ecf_include}'")
        lines.append(f"{sp}edit ECF_FILES   '{ecf_files}'")
        # Use %TASK% for flat output — ecFlow's %ECF_NAME% includes the
        # full node hierarchy which creates unwanted subdirectories.
        lines.append(f"{sp}edit ECF_JOBOUT  '{ecf_log_dir}/%TASK%.%ECF_TRYNO%'")
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
        account = base.get('ACCOUNT', '')
        if not account or account == 'UNDEFINED':
            account = os.environ.get('HPC_ACCOUNT', 'fv3-cpu')
        lines.append(f"{sp}edit ACCOUNT  '{account}'")
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

    def _get_forecast_hours(self, task_name: str) -> Optional[List[int]]:
        """
        Compute the list of forecast hours for a product task.

        Uses the same logic as ``Tasks._get_forecast_hours``: high-frequency
        output up to FHMAX_HF_GFS at FHOUT_HF_GFS intervals, then standard
        output at FHOUT_GFS intervals to FHMAX_GFS.

        Returns None for non-product tasks.
        """
        if task_name not in _PRODUCT_TASKS:
            return None

        prod_info = _PRODUCT_TASKS[task_name]
        config_name = prod_info['config']
        component = prod_info['component']

        if config_name not in self._configs:
            return None

        config = self._configs[config_name].copy()

        # Ocean/ice have no high-frequency output
        if component in ('ocean', 'ice'):
            config['FHMAX_HF_GFS'] = 0

        if component == 'ocean':
            config['FHOUT_HF_GFS'] = config.get('FHOUT_OCN_GFS', 6)
            config['FHOUT_GFS'] = config.get('FHOUT_OCN_GFS', 6)
        elif component == 'ice':
            config['FHOUT_HF_GFS'] = config.get('FHOUT_ICE_GFS', 6)
            config['FHOUT_GFS'] = config.get('FHOUT_ICE_GFS', 6)
        elif component == 'wave':
            config['FHMAX_HF_GFS'] = config.get('FHMAX_HF_WAV', 120)
            config['FHOUT_HF_GFS'] = config.get('FHOUT_HF_WAV', 1)
            config['FHOUT_GFS'] = config.get('FHOUT_WAV_GFS', 3)

        fhmin = config.get('FHMIN', 0)
        fhmax = config.get('FHMAX_GFS', 120)
        fhout = config.get('FHOUT_GFS', 3)
        fhout_hf = config.get('FHOUT_HF_GFS', 1)
        fhmax_hf = config.get('FHMAX_HF_GFS', 0)

        if fhmax_hf > 0 and fhout_hf > 0:
            fhrs_hf = list(range(fhmin, min(fhmax_hf, fhmax) + fhout_hf, fhout_hf))
            last_hf = fhrs_hf[-1]
            fhrs = fhrs_hf + list(range(last_hf + fhout, fhmax + fhout, fhout))
        else:
            fhrs = list(range(fhmin, fhmax + fhout, fhout))

        # Ocean/ice do not produce output at fhr 0
        if component in ('ocean', 'ice') and 0 in fhrs:
            fhrs.remove(0)

        return fhrs

    def _get_resource_for_task(self, task_name: str) -> Dict:
        """
        Extract task resources directly from the already-parsed AppConfig.

        Reads walltime, ntasks, threads, etc. from
        ``app_config.configs[run][config_name]`` which was populated by
        ``Configuration.parse_config`` during AppConfig initialization.
        No additional subprocess calls are made.
        """
        import math

        resource_step = _RESOURCE_STEP_MAP.get(task_name, task_name)
        base = self._base

        try:
            task_config = self._configs[resource_step]
        except KeyError:
            logger.warning(f'No config for {task_name} '
                           f'(step={resource_step}). Using defaults.')
            return {
                'walltime': '00:30:00',
                'nodes': 1,
                'ntasks': 1,
                'ppn': 1,
                'threads': 1,
                'memory': None,
                'partition': base.get('PARTITION_BATCH', 'batch'),
                'native': None,
            }

        walltime = task_config.get('walltime', '00:30:00')
        ntasks = int(task_config.get('ntasks', 1))
        ppn = int(task_config.get('tasks_per_node', 1))
        nodes = math.ceil(ntasks / max(ppn, 1))
        threads = int(task_config.get('threads_per_task', 1))
        memory = task_config.get('memory', None)
        is_exclusive = task_config.get('is_exclusive', False)

        # Determine partition based on task type
        service_task = task_name in _SERVICE_TASKS
        if service_task:
            partition = base.get('PARTITION_SERVICE',
                                 base.get('PARTITION_BATCH', 'batch'))
        else:
            partition = base.get('PARTITION_BATCH', 'batch')

        native = '--exclusive' if is_exclusive else '--export=NONE'

        return {
            'walltime': walltime,
            'nodes': nodes,
            'ntasks': ntasks,
            'ppn': ppn,
            'threads': threads,
            'memory': memory,
            'partition': partition,
            'native': native,
        }

    def _get_trigger(self, task_name: str) -> Optional[str]:
        """
        Return the ecFlow trigger expression for *task_name*, or None.

        Mirrors the dependency logic from ``rocoto/gfs_tasks.py`` for
        forecast-only mode.  Task references use the {RUN}_ prefix to
        match emitted node names.
        """
        tasks = self._task_names
        run = self._run

        def has(name):
            return name in tasks

        def ref(name):
            return f'{run}_{name}'

        if task_name == 'stage_ic':
            if has('fetch'):
                return f'{ref("fetch")} == complete'
            return None

        if task_name == 'aerosol_init':
            return None

        if task_name == 'waveinit':
            return None

        if task_name == 'fcst':
            deps = [f'{ref("stage_ic")} == complete']
            if has('waveinit'):
                deps.append(f'{ref("waveinit")} == complete')
            if has('aerosol_init'):
                deps.append(f'{ref("aerosol_init")} == complete')
            return ' and '.join(deps)

        if task_name == 'atmupp':
            return f'{ref("fcst")} == complete'

        if task_name == 'goesupp':
            return f'{ref("fcst")} == complete'

        if task_name == 'atmos_prod':
            return f'{ref("fcst")} == complete'

        if task_name == 'ocean_prod':
            return f'{ref("fcst")} == complete'

        if task_name == 'ice_prod':
            return f'{ref("fcst")} == complete'

        if task_name in ('tracker', 'genesis', 'genesis_fsu', 'metp'):
            return f'{ref("atmos_prod")} == complete'

        if task_name == 'postsnd':
            return f'{ref("atmos_prod")} == complete'

        if task_name in ('gempak', 'gempakmeta'):
            return f'{ref("atmos_prod")} == complete'

        if task_name in ('awips_20km_1p0deg', 'fbwind'):
            return f'{ref("atmos_prod")} == complete'

        if task_name in ('wavepostgridded', 'wavepostpnt',
                         'wavepostbndpnt', 'wavepostbndpntbll'):
            return f'{ref("fcst")} == complete'

        if task_name in ('wavegempak',):
            return f'{ref("wavepostgridded")} == complete'

        if task_name in ('waveawipsbulls', 'waveawipsgridded'):
            return f'{ref("wavepostgridded")} == complete'

        if task_name in ('arch_tars', 'globus_arch'):
            return f'{ref("arch_vrfy")} == complete'

        if task_name == 'arch_vrfy':
            deps = [f'{ref("atmos_prod")} == complete']
            if has('tracker'):
                deps.append(f'{ref("tracker")} == complete')
            if has('genesis'):
                deps.append(f'{ref("genesis")} == complete')
            if has('genesis_fsu'):
                deps.append(f'{ref("genesis_fsu")} == complete')
            if has('ocean_prod'):
                deps.append(f'{ref("ocean_prod")} == complete')
            if has('ice_prod'):
                deps.append(f'{ref("ice_prod")} == complete')
            if has('wavepostgridded'):
                deps.append(f'{ref("wavepostgridded")} == complete')
            if has('wavepostpnt'):
                deps.append(f'{ref("wavepostpnt")} == complete')
            if has('wavepostbndpnt'):
                deps.append(f'{ref("wavepostbndpnt")} == complete')
            if has('wavepostbndpntbll'):
                deps.append(f'{ref("wavepostbndpntbll")} == complete')
            return ' and '.join(deps)

        if task_name == 'cleanup':
            deps = [f'{ref("arch_vrfy")} == complete']
            if has('arch_tars'):
                deps.append(f'{ref("arch_tars")} == complete')
            if has('globus_arch'):
                deps.append(f'{ref("globus_arch")} == complete')
            return ' and '.join(deps)

        return None

    def _emit_task(self, task_name: str, indent: int
                   ) -> Tuple[List[str], str]:
        """
        Emit a task block (or a family of per-group subtasks for product jobs).

        Product tasks (atmos_prod, ocean_prod, etc.) are emitted as an
        ecFlow family containing one child task per forecast-hour group,
        each with its own FHR_LIST and scaled walltime.  Non-product
        tasks are emitted as a single task node.

        Returns (lines, task_name).
        """
        fhrs = self._get_forecast_hours(task_name)

        if fhrs is not None:
            return self._emit_product_family(task_name, fhrs, indent)

        return self._emit_simple_task(task_name, indent)

    def _emit_simple_task(self, task_name: str, indent: int
                          ) -> Tuple[List[str], str]:
        """Emit a single non-product task node with {RUN}_ prefix."""
        sp = ' ' * indent
        tsp = ' ' * (indent + 2)
        lines = []

        res = self._get_resource_for_task(task_name)
        trigger = self._get_trigger(task_name)

        node_name = f'{self._run}_{task_name}'
        lines.append(f'{sp}task {node_name}')
        lines.append(f"{tsp}edit TASK '{task_name}'")

        walltime = res.get('walltime', '00:30:00')
        nodes = res.get('nodes', 1)
        ntasks = res.get('ntasks', 1)
        ppn = res.get('ppn', ntasks)
        threads = res.get('threads', 1)
        partition = res.get('partition')
        native = res.get('native', '')
        is_exclusive = native and '--exclusive' in str(native)

        lines.append(f"{tsp}edit WALLTIME '{walltime}'")
        # NODES and NTASKS are always emitted for non-default values.
        # NTASKS maps to --ntasks-per-node in slurm_ursa.h (per-node count).
        if nodes > 1:
            lines.append(f"{tsp}edit NODES '{nodes}'")
        if ppn > 1:
            lines.append(f"{tsp}edit NTASKS '{ppn}'")
        if threads > 1:
            lines.append(f"{tsp}edit CPUS_PER_TASK '{threads}'")
        if partition and partition != self._base.get('PARTITION_BATCH'):
            lines.append(f"{tsp}edit QUEUE '{partition}'")
        if is_exclusive:
            lines.append(f"{tsp}edit EXCLUSIVE 'YES'")

        if trigger:
            lines.append(f'{tsp}trigger {trigger}')

        return lines, task_name

    def _emit_product_family(self, task_name: str, fhrs: List[int],
                             indent: int) -> Tuple[List[str], str]:
        """Emit a product task as a family of per-group subtasks.

        Each child task processes a subset of forecast hours.  The family
        completes when all children complete, giving ecFlow UI visibility
        into per-group progress.
        """
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)   # family-level indent
        tsp = ' ' * (indent + 4)   # task-level indent
        lines = []

        res = self._get_resource_for_task(task_name)
        trigger = self._get_trigger(task_name)

        prod_info = _PRODUCT_TASKS[task_name]
        max_tasks = self._configs.get(
            prod_info['config'], {}).get('MAX_TASKS', 25)
        ngroups = min(max_tasks, len(fhrs))
        groups = self._group_fhrs(fhrs, ngroups)

        base_walltime = res.get('walltime', '00:15:00')
        nodes = res.get('nodes', 1)
        ntasks = res.get('ntasks', 1)
        threads = res.get('threads', 1)
        partition = res.get('partition')
        native = res.get('native', '')
        is_exclusive = native and '--exclusive' in str(native)

        # Family wrapping all forecast-hour groups
        node_name = f'{self._run}_{task_name}'
        lines.append(f'{sp}family {node_name}')
        lines.append(f"{fsp}edit TASK '{task_name}'")
        lines.append(f"{fsp}# {len(fhrs)} forecast hours in {ngroups} groups")

        if trigger:
            lines.append(f'{fsp}trigger {trigger}')

        # Shared resource defaults at family level
        if ntasks > 1:
            lines.append(f"{fsp}edit NTASKS '{ntasks}'")
        if threads > 1:
            lines.append(f"{fsp}edit CPUS_PER_TASK '{threads}'")
        if partition and partition != self._base.get('PARTITION_BATCH'):
            lines.append(f"{fsp}edit QUEUE '{partition}'")
        if is_exclusive:
            lines.append(f"{fsp}edit EXCLUSIVE 'YES'")
        if nodes > 1:
            lines.append(f"{fsp}edit NODES '{nodes}'")

        lines.append('')

        # One child task per forecast-hour group
        for i, grp in enumerate(groups):
            if len(grp) == 1:
                label = f'f{grp[0]:03d}'
            else:
                label = f'f{grp[0]:03d}_f{grp[-1]:03d}'

            fhr_list_str = ','.join(str(f) for f in grp)
            grp_walltime = Tasks.multiply_HMS(base_walltime, len(grp))

            lines.append(f'{fsp}task {label}')
            lines.append(f"{tsp}edit FHR_LIST '{fhr_list_str}'")
            lines.append(f"{tsp}edit WALLTIME '{grp_walltime}'")
            lines.append('')

        lines.append(f'{sp}endfamily')

        return lines, task_name

    @staticmethod
    def _group_fhrs(fhrs: List[int], ngroups: int) -> List[List[int]]:
        """
        Split forecast hours into *ngroups* roughly equal groups.

        Simplified version of Tasks.get_job_groups() without
        forecast-segment breakpoint handling.
        """
        if ngroups >= len(fhrs):
            return [[f] for f in fhrs]

        groups: List[List[int]] = []
        base_size = len(fhrs) // ngroups
        remainder = len(fhrs) % ngroups
        idx = 0
        for i in range(ngroups):
            size = base_size + (1 if i < remainder else 0)
            groups.append(fhrs[idx:idx + size])
            idx += size
        return groups
