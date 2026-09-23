#!/usr/bin/env python3

"""
GEFS forecast-only ecFlow suite generator.

Extends the GFS pattern with ensemble member handling.  The ``.def``
hierarchy for a GEFS run looks like::

    suite {pslot}
      [suite-level edits]
      family gefs
        edit RUN 'gefs'
        family {cycle}
          edit PDY / CYC

          task stage_ic
          task waveinit
          task fcst                          # control (mem000)

          family ensemble                    # per-member forecasts + products
            family mem001
              edit ENSMEM '001'
              edit MEMDIR 'mem001'
              task efcs
              family atmos_prod
                task f000  ...
              endfamily
            endfamily
            family mem002
              ...
            endfamily
          endfamily

          task atmos_ensstat                 # aggregation
          task arch_vrfy
          task cleanup
        endfamily
      endfamily
    endsuite

Ensemble tasks are identified by ``task_dict['ensemble_task'] == True``.
The suite collects them, then emits member families inside a single
``family ensemble`` container.  Non-ensemble tasks are emitted in the
normal linear order.

Sentinel triggers (``__ALL_MEMBER_ATMOS_PROD__``, etc.) are resolved to
ecFlow trigger expressions of the form
``../ensemble/mem000/atmos_prod == complete and .../mem001/atmos_prod == complete``.
"""

import os
from logging import getLogger
from pathlib import Path
from typing import Dict, List

from ecflow.ecflow_suite import EcFlowSuite
from ecflow.ecflow_tasks_factory import ecflow_tasks_factory
from applications.applications import AppConfig
from rocoto.tasks import Tasks
from wxflow import timedelta_to_HMS

logger = getLogger(__name__.split('.')[-1])

# Sentinel trigger → product family name that must complete per member
_SENTINEL_MAP = {
    '__ALL_MEMBER_ATMOS_PROD__': 'atmos_prod',
    '__ALL_MEMBER_WAVEPOSTGRIDDED__': 'wavepostgridded',
}


class GEFSForecastOnlyEcFlowSuite(EcFlowSuite):
    """
    ecFlow suite generator for GEFS forecast-only workflows.

    Produces a ``.def`` file with per-member families for ensemble
    forecasts and product tasks, plus aggregation tasks that trigger
    on all members completing.
    """

    def __init__(self, app_config: AppConfig, ecflow_config: Dict) -> None:
        super().__init__(app_config, ecflow_config)

        self._run = list(app_config.task_names.keys())[0]  # 'gefs'
        self._task_names = app_config.task_names[self._run]
        self._options = app_config.run_options[self._run]
        self._configs = app_config.configs[self._run]
        self._nmem = int(self._base.get('NMEM_ENS', 0))

        self._tasks = ecflow_tasks_factory.create(
            self._base['NET'], app_config, self._run)

    # ── Public interface ──────────────────────────────────────────────

    def get_cycledefs(self):
        """Human-readable cycle summary."""
        sdate = self._base['SDATE_GFS']
        edate = self._base['EDATE']
        interval = self._base['interval_gfs']
        return (f"# Cycles: {sdate.strftime('%Y%m%d%H')} - "
                f"{edate.strftime('%Y%m%d%H')} every "
                f"{timedelta_to_HMS(interval)}")

    def write(self, def_file: str = None) -> str:
        """Generate the ecFlow ``.def`` file and ecf_scripts directory."""
        if def_file is None:
            def_file = os.path.join(self.expdir, f'{self.pslot}.def')

        suite_name = self.pslot

        self._ecf_scripts_dir = Path(self.expdir) / 'ecf_scripts'
        self._ecf_src_dir = Path(
            os.environ.get('ECF_FILES',
                           os.path.join(self.HOMEglobal, 'dev', 'ecflow',
                                        'scripts')))
        self._copy_map: Dict[str, str] = {}

        # Fetch all task dicts and classify them
        all_tasks: List[Dict] = []
        for task_name in self._task_names:
            task_dict = self._tasks.get_ecflow_task(task_name)
            all_tasks.append(task_dict)

        # Split into non-ensemble (linear) and ensemble (per-member)
        pre_ensemble: List[Dict] = []    # before ensemble block
        ensemble_tasks: List[Dict] = []  # per-member tasks
        post_ensemble: List[Dict] = []   # after ensemble block
        seen_ensemble = False

        for td in all_tasks:
            is_ens = td.get('ensemble_task', False)
            if is_ens:
                seen_ensemble = True
                ensemble_tasks.append(td)
            elif seen_ensemble:
                post_ensemble.append(td)
            else:
                pre_ensemble.append(td)

        lines: List[str] = []
        lines.append(f'# Auto-generated ecFlow suite definition for {suite_name}')
        lines.append(f'# Mode: {self._app_config.mode}  NET: {self._base["NET"]}')
        lines.append(f'# NMEM_ENS: {self._nmem}')
        lines.append(f'# {self.get_cycledefs()}')
        lines.append('')

        # ── Suite header ──────────────────────────────────────────────
        lines.append(f'suite {suite_name}')
        lines += self._suite_variables(indent=2)
        lines.append('')

        # ── RUN family ────────────────────────────────────────────────
        indent = 2
        lines.append(f'{" " * indent}family {self._run}')
        indent = 4
        lines.append(f'{" " * indent}edit RUN \'{self._run}\'')
        lines.append('')

        # ── Cycle family ──────────────────────────────────────────────
        sdate = self._base['SDATE_GFS']
        cycle_str = sdate.strftime('%Y%m%d%H')
        lines.append(f'{" " * indent}family {cycle_str}')
        indent = 6
        lines.append(f'{" " * indent}edit PDY \'{sdate.strftime("%Y%m%d")}\'')
        lines.append(f'{" " * indent}edit CYC \'{sdate.strftime("%H")}\'')
        lines.append('')

        # ── Pre-ensemble tasks (stage_ic, waveinit, control fcst) ─────
        for td in pre_ensemble:
            task_lines = self._emit_task(td, indent)
            lines += task_lines
            lines.append('')

        # ── Ensemble family (per-member forecasts + products) ─────────
        if ensemble_tasks:
            lines += self._emit_ensemble_family(ensemble_tasks, indent)
            lines.append('')

        # ── Post-ensemble tasks (ensstat, arch, cleanup) ──────────────
        # Collect ensemble task names for trigger rewriting.
        ens_task_names = {td['task_name'] for td in ensemble_tasks}

        for td in post_ensemble:
            trigger = td.get('trigger', '')
            if trigger:
                td = dict(td)
                if trigger in _SENTINEL_MAP:
                    td['trigger'] = self._resolve_sentinel(trigger)
                else:
                    td['trigger'] = self._rewrite_post_ensemble_trigger(
                        trigger, ens_task_names)
            task_lines = self._emit_task(td, indent)
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

        self._create_ecf_scripts()

        return def_file

    # ── Ensemble family emission ──────────────────────────────────────

    def _emit_ensemble_family(self, ensemble_tasks: List[Dict],
                              indent: int) -> List[str]:
        """Emit a ``family ensemble`` containing per-member sub-families.

        Each member family (mem000 .. memNNN) contains its own copy
        of every ensemble task — forecasts, product families, and
        per-member simple tasks.  The control member is mem000.
        """
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)
        msp = ' ' * (indent + 4)

        lines = []
        lines.append(f'{sp}family ensemble')
        lines.append(f'{fsp}# {self._nmem + 1} members (mem000=control + {self._nmem} perturbed)')
        lines.append('')

        for mem in range(0, self._nmem + 1):
            mem_str = f'{mem:03d}'
            mem_name = f'mem{mem_str}'

            lines.append(f'{fsp}family {mem_name}')
            lines.append(f"{msp}edit ENSMEM '{mem_str}'")
            lines.append(f"{msp}edit MEMDIR '{mem_name}'")
            lines.append('')

            for td in ensemble_tasks:
                task_name = td['task_name']

                # Control (mem000) forecast is emitted as the top-level
                # 'fcst' task, not inside ensemble.  efcs is for members
                # 1..N only.  But we also need mem000 products.
                if task_name == 'efcs' and mem == 0:
                    continue

                # Rewrite triggers for member context.
                # Inside a member family, 'fcst == complete' needs to
                # resolve correctly:
                # - For mem000: the control fcst lives at ../../fcst
                # - For mem001+: efcs lives at ./efcs
                td_copy = dict(td)
                trigger = td_copy.get('trigger', '')
                if trigger:
                    td_copy['trigger'] = self._rewrite_member_trigger(
                        trigger, mem, task_name)

                task_lines = self._emit_task(td_copy, indent + 4)
                lines += task_lines
                lines.append('')

            lines.append(f'{fsp}endfamily')
            lines.append('')

        lines.append(f'{sp}endfamily')

        return lines

    def _rewrite_member_trigger(self, trigger: str, mem: int,
                                task_name: str) -> str:
        """Adjust trigger expressions for member context.

        Tasks inside ``ensemble/memNNN/`` reference nodes outside their
        family via ``../../`` (two levels up: memNNN → ensemble → cycle).

        - ``fcst == complete`` → ``../../fcst == complete`` (mem000) or
          ``efcs == complete`` (memNNN, sibling within the member family).
        - Other pre-ensemble tasks (``stage_ic``, ``waveinit``, etc.)
          always need ``../../`` since they live at the cycle level.
        """
        # Collect names of pre-ensemble tasks (siblings of the ensemble
        # family, not siblings of member tasks inside it).
        pre_ensemble_names = set()
        for tn in self._task_names:
            td = self._tasks.get_ecflow_task(tn)
            if td.get('ensemble_task', False):
                break
            pre_ensemble_names.add(tn)

        parts = trigger.split(' and ')
        rewritten = []
        for part in parts:
            part = part.strip()
            # Extract the node name from "node == complete"
            node_name = part.split(' ')[0]

            if node_name == 'fcst':
                if mem == 0:
                    rewritten.append(part.replace('fcst', '../../fcst'))
                else:
                    rewritten.append(part.replace('fcst', 'efcs'))
            elif node_name in pre_ensemble_names:
                rewritten.append(part.replace(node_name, f'../../{node_name}'))
            else:
                rewritten.append(part)

        return ' and '.join(rewritten)

    # ── Sentinel trigger resolution ───────────────────────────────────

    def _resolve_sentinel(self, sentinel: str) -> str:
        """Resolve a sentinel trigger to a real ecFlow expression.

        ``__ALL_MEMBER_ATMOS_PROD__`` becomes::

            ensemble/mem000/atmos_prod == complete and
            ensemble/mem001/atmos_prod == complete and ...
        """
        family_name = _SENTINEL_MAP.get(sentinel)
        if not family_name:
            return sentinel

        parts = []
        for mem in range(0, self._nmem + 1):
            mem_name = f'mem{mem:03d}'
            parts.append(f'ensemble/{mem_name}/{family_name} == complete')
        return ' and '.join(parts)

    def _rewrite_post_ensemble_trigger(self, trigger: str,
                                       ens_task_names: set) -> str:
        """Prefix ensemble task references with ``ensemble == complete``.

        Post-ensemble tasks (like ``arch_vrfy``) may trigger on both
        ensemble tasks (``atmos_prod``, ``ocean_prod``) and non-ensemble
        siblings (``atmos_ensstat``, ``wave_stat_pnt``).

        Ensemble task references are replaced with a single
        ``ensemble == complete`` condition (ecFlow triggers on the
        entire family completing).  Non-ensemble references stay as-is.
        """
        parts = trigger.split(' and ')
        rewritten = []
        needs_ensemble = False

        for part in parts:
            part = part.strip()
            node_name = part.split(' ')[0]
            if node_name in ens_task_names:
                needs_ensemble = True
            else:
                rewritten.append(part)

        if needs_ensemble:
            rewritten.insert(0, 'ensemble == complete')

        return ' and '.join(rewritten)

    # ── Task rendering (reuses GFS patterns) ──────────────────────────

    def _emit_task(self, task_dict: Dict, indent: int) -> List[str]:
        """Dispatch to product family or simple task emitter."""
        if task_dict.get('product_task', False):
            return self._emit_product_family(task_dict, indent)
        num_segments = task_dict.get('num_segments', 1)
        if num_segments > 1:
            return self._emit_segmented_task(task_dict, indent)
        return self._emit_simple_task(task_dict, indent)

    def _emit_simple_task(self, task_dict: Dict, indent: int) -> List[str]:
        """Emit a single non-product task node."""
        sp = ' ' * indent
        tsp = ' ' * (indent + 2)
        lines = []

        task_name = task_dict['task_name']
        res = task_dict['resources']
        trigger = task_dict.get('trigger')

        self._copy_map[task_name] = task_name

        lines.append(f'{sp}task {task_name}')
        lines.append(f"{tsp}edit TASK '{task_name}'")

        lines += self._resource_edits(res, tsp)

        if trigger:
            lines.append(f'{tsp}trigger {trigger}')

        return lines

    def _emit_segmented_task(self, task_dict: Dict, indent: int) -> List[str]:
        """Emit a forecast task with segment sub-tasks.

        For GEFS segmented forecasts, each segment runs sequentially::

            family efcs
              task seg0
                edit FCST_SEGMENT '0'
              task seg1
                edit FCST_SEGMENT '1'
                trigger seg0 == complete
            endfamily
        """
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)
        tsp = ' ' * (indent + 4)
        lines = []

        task_name = task_dict['task_name']
        res = task_dict['resources']
        trigger = task_dict.get('trigger')
        num_segments = task_dict.get('num_segments', 1)

        self._copy_map[task_name] = task_name

        lines.append(f'{sp}family {task_name}')
        lines.append(f"{fsp}edit TASK '{task_name}'")

        if trigger:
            lines.append(f'{fsp}trigger {trigger}')

        lines += self._resource_edits(res, fsp)
        lines.append('')

        for seg in range(num_segments):
            seg_name = f'seg{seg}'
            self._copy_map[seg_name] = task_name

            lines.append(f'{fsp}task {seg_name}')
            lines.append(f"{tsp}edit FCST_SEGMENT '{seg}'")
            if seg > 0:
                lines.append(f'{tsp}trigger seg{seg - 1} == complete')
            lines.append('')

        lines.append(f'{sp}endfamily')

        return lines

    def _emit_product_family(self, task_dict: Dict, indent: int) -> List[str]:
        """Emit a product task as a family of per-forecast-hour-group children."""
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)
        tsp = ' ' * (indent + 4)
        lines = []

        task_name = task_dict['task_name']
        res = task_dict['resources']
        trigger = task_dict.get('trigger')
        fhrs = task_dict['forecast_hours']
        config_name = task_dict['config']

        max_tasks = self._configs.get(config_name, {}).get('MAX_TASKS', 25)
        ngroups = min(max_tasks, len(fhrs))
        groups = self._group_fhrs(fhrs, ngroups)

        base_walltime = res.get('walltime', '00:15:00')

        lines.append(f'{sp}family {task_name}')
        lines.append(f"{fsp}edit TASK '{task_name}'")
        lines.append(f"{fsp}# {len(fhrs)} forecast hours in {ngroups} groups")

        if trigger:
            lines.append(f'{fsp}trigger {trigger}')

        lines += self._resource_edits(res, fsp, skip_walltime=True)
        lines.append('')

        for i, grp in enumerate(groups):
            if len(grp) == 1:
                label = f'f{grp[0]:03d}'
            else:
                label = f'f{grp[0]:03d}_f{grp[-1]:03d}'

            self._copy_map[label] = task_name

            fhr_list_str = ','.join(str(f) for f in grp)
            grp_walltime = Tasks.multiply_HMS(base_walltime, len(grp))

            lines.append(f'{fsp}task {label}')
            lines.append(f"{tsp}edit FHR_LIST '{fhr_list_str}'")
            lines.append(f"{tsp}edit WALLTIME '{grp_walltime}'")
            lines.append('')

        lines.append(f'{sp}endfamily')

        return lines

    def _resource_edits(self, res: Dict, indent_str: str, *,
                        skip_walltime: bool = False) -> List[str]:
        """Emit per-task resource edit lines."""
        lines = []

        walltime = res.get('walltime', '00:30:00')
        nodes = res.get('nodes', 1)
        ppn = res.get('ppn', 1)
        threads = res.get('threads', 1)
        partition = res.get('partition')
        native = res.get('native', '')
        is_exclusive = native and '--exclusive' in str(native)

        if not skip_walltime:
            lines.append(f"{indent_str}edit WALLTIME '{walltime}'")
        if nodes > 1:
            lines.append(f"{indent_str}edit NODES '{nodes}'")
        if ppn > 1:
            lines.append(f"{indent_str}edit NTASKS '{ppn}'")
        if threads > 1:
            lines.append(f"{indent_str}edit CPUS_PER_TASK '{threads}'")
        if partition and partition != self._base.get('PARTITION_BATCH'):
            lines.append(f"{indent_str}edit QUEUE '{partition}'")
        if is_exclusive:
            lines.append(f"{indent_str}edit EXCLUSIVE 'YES'")

        return lines

    # ── ecf_scripts management ────────────────────────────────────────

    def _create_ecf_scripts(self) -> None:
        """Populate the ECF_FILES directory with .ecf copies."""
        scripts_dir = self._ecf_scripts_dir
        src_dir = self._ecf_src_dir

        if scripts_dir.exists():
            for f in scripts_dir.iterdir():
                if f.is_symlink() or f.is_file():
                    f.unlink()
        else:
            scripts_dir.mkdir(parents=True)

        import shutil
        skipped = []
        for dest_name, src_name in self._copy_map.items():
            dest = scripts_dir / f'{dest_name}.ecf'
            src = src_dir / f'{src_name}.ecf'
            if not src.is_file():
                skipped.append(f'{src_name}.ecf')
                continue
            shutil.copy2(str(src), str(dest))

        manifest = scripts_dir / 'ecf_scripts.manifest'
        with open(manifest, 'w') as fh:
            fh.write(f'# ECF_SRC_DIR={self._ecf_src_dir}\n')
            for dest_name, src_name in sorted(self._copy_map.items()):
                fh.write(f'{dest_name}\t{src_name}\n')

        copied = len(self._copy_map) - len(skipped)
        logger.info(f'Copied {copied} .ecf files to {scripts_dir}')
        if skipped:
            unique = sorted(set(skipped))
            logger.warning(f'Missing source .ecf (skipped): {", ".join(unique)}')

    # ── Suite-level variables ─────────────────────────────────────────

    def _suite_variables(self, indent: int = 2) -> List[str]:
        """Emit suite-level edit variables."""
        sp = ' ' * indent
        base = self._base
        lines = []

        rotdir = base.get('ROTDIR', os.path.join(str(base.get('COMROOT', '/tmp')),
                                                  self.pslot))
        ecf_log_dir = os.path.join(rotdir, 'logs')

        ecf_host = os.environ.get('ECF_HOST', os.environ.get('HOSTNAME', 'localhost'))
        ecf_port = os.environ.get('ECF_PORT', '3141')

        ecf_scripts_dir = os.path.join(self.expdir, 'ecf_scripts')
        ecf_include = os.environ.get('ECF_INCLUDE',
                                     os.path.join(self.HOMEglobal, 'dev', 'ecflow',
                                                  'utils'))

        lines.append(f"{sp}# ecFlow server connection")
        lines.append(f"{sp}edit ECF_LOGHOST '{ecf_host}'")
        lines.append(f"{sp}edit ECF_PORT    '{ecf_port}'")
        lines.append(f"{sp}")
        lines.append(f"{sp}# File locations")
        lines.append(f"{sp}edit ECF_HOME    '{ecf_log_dir}'")
        lines.append(f"{sp}edit ECF_INCLUDE '{ecf_include}'")
        lines.append(f"{sp}edit ECF_FILES   '{ecf_scripts_dir}'")
        lines.append(f"{sp}edit ECF_JOBOUT  '{ecf_log_dir}/%TASK%.%ECF_TRYNO%'")
        lines.append(f"{sp}")

        lines.append(f"{sp}# Slurm job submission commands")
        lines.append(f"{sp}edit ECF_JOB_CMD  'sbatch %ECF_JOB%'")
        lines.append(f"{sp}edit ECF_KILL_CMD 'scancel %ECF_RID%'")
        lines.append(f"{sp}edit ECF_STATUS_CMD 'squeue -j %ECF_RID%'")
        lines.append(f"{sp}")

        lines.append(f"{sp}# Experiment variables")
        lines.append(f"{sp}edit ENVIR    '{base.get('envir', 'test')}'")
        lines.append(f"{sp}edit NET      '{base['NET']}'")
        lines.append(f"{sp}edit RUN      '{self._run}'")
        lines.append(f"{sp}edit APP      '{self._options.get('app', 'S2SWA')}'")
        account = base.get('ACCOUNT', '')
        if not account or account == 'UNDEFINED':
            account = os.environ.get('HPC_ACCOUNT', 'fv3-cpu')
        lines.append(f"{sp}edit ACCOUNT  '{account}'")
        lines.append(f"{sp}edit QUEUE    '{base.get('PARTITION_BATCH', 'batch')}'")
        lines.append(f"{sp}edit PSLOT    '{self.pslot}'")
        lines.append(f"{sp}edit CASE     '{base['CASE']}'")
        lines.append(f"{sp}edit FHMAX_GFS '{base.get('FHMAX_GFS', 120)}'")
        lines.append(f"{sp}edit NMEM_ENS  '{self._nmem}'")
        lines.append(f"{sp}")

        sdate = base['SDATE_GFS']
        lines.append(f"{sp}edit PDY      '{sdate.strftime('%Y%m%d')}'")
        lines.append(f"{sp}edit CYC      '{sdate.strftime('%H')}'")
        lines.append(f"{sp}")

        lines.append(f"{sp}# Paths consumed by J-Jobs")
        lines.append(f"{sp}edit HOMEglobal '{self.HOMEglobal}'")
        lines.append(f"{sp}edit EXPDIR     '{self.expdir}'")
        lines.append(f"{sp}edit COMROOT    '{base['COMROOT']}'")
        dataroot = f"{base.get('STMP', '/tmp')}/RUNDIRS/{self.pslot}"
        lines.append(f"{sp}edit DATAROOT   '{dataroot}'")
        lines.append(f"{sp}")

        lines.append(f"{sp}# Slurm resource defaults (overridden per-task)")
        lines.append(f"{sp}edit WALLTIME '00:30:00'")
        lines.append(f"{sp}edit NODES    '1'")
        lines.append(f"{sp}edit NTASKS   '1'")
        lines.append(f"{sp}edit CPUS_PER_TASK '1'")
        lines.append(f"{sp}edit EXCLUSIVE 'NO'")

        return lines

    # ── Utility ───────────────────────────────────────────────────────

    @staticmethod
    def _group_fhrs(fhrs: List[int], ngroups: int) -> List[List[int]]:
        """Split forecast hours into *ngroups* roughly equal groups."""
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
