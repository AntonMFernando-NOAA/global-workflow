#!/usr/bin/env python3

"""
Unified forecast-only ecFlow suite generator.

Handles both single-member (GFS) and ensemble (GEFS, SFS) workflows.
When ``NMEM_ENS == 0``, all tasks are emitted linearly.  When
``NMEM_ENS > 0``, tasks marked with ``ensemble_task: True`` are wrapped
in a ``family fcst_ens`` with per-member sub-families.

The ``.def`` hierarchy for ensemble runs::

    suite {pslot}
      family {run}
        family {cycle}
          task stage_ic
          task fcst                          # control (mem000)
          family fcst_ens                    # per-member segmented forecasts
            family mem001
              family fcst_ens
                task seg0
                task seg1
              endfamily
            endfamily
            family mem002 ...
          endfamily
          family atmos_prod                  # per-member products
            family mem000
              task f000 ...
            endfamily
            family mem001 ...
          endfamily
          task atmos_ensstat                 # aggregation
          task arch_vrfy
          task cleanup
        endfamily
      endfamily
    endsuite

For non-ensemble runs, the ``family fcst_ens`` layer is absent and
tasks appear directly under the cycle family.
"""

import os
from logging import getLogger
from pathlib import Path
from typing import Dict, List, Set

from ecflow.ecflow_suite import EcFlowSuite
from ecflow.ecflow_tasks_factory import ecflow_tasks_factory
from applications.applications import AppConfig
from rocoto.tasks import Tasks
from wxflow import timedelta_to_HMS

logger = getLogger(__name__.split('.')[-1])

# Sentinel trigger -> product family name that must complete per member
_SENTINEL_MAP = {
    '__ALL_MEMBER_ATMOS_PROD__': 'atmos_prod',
    '__ALL_MEMBER_WAVEPOSTGRIDDED__': 'wavepostgridded',
}


class ForecastOnlyEcFlowSuite(EcFlowSuite):
    """
    ecFlow suite generator for forecast-only workflows (GFS, GEFS, SFS).

    A single class replaces the per-NET suite generators.  The factory
    registers it for every ``{net}_forecast-only`` key.
    """

    def __init__(self, app_config: AppConfig, ecflow_config: Dict) -> None:
        super().__init__(app_config, ecflow_config)

        self._run = list(app_config.task_names.keys())[0]
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

        # Fetch all task dicts
        all_tasks: List[Dict] = []
        for task_name in self._task_names:
            all_tasks.append(self._tasks.get_ecflow_task(task_name))

        # Classify into pre-ensemble, ensemble, post-ensemble.
        # For non-ensemble runs (nmem == 0) everything lands in
        # pre_ensemble and the other two stay empty.
        pre_ensemble, ensemble_tasks, post_ensemble = \
            self._classify_tasks(all_tasks)

        lines: List[str] = []
        lines.append(f'# Auto-generated ecFlow suite definition for {suite_name}')
        lines.append(f'# Mode: {self._app_config.mode}  NET: {self._base["NET"]}')
        if self._nmem > 0:
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
        self._cycle_path = f'/{suite_name}/{self._run}/{cycle_str}'
        lines.append(f'{" " * indent}family {cycle_str}')
        indent = 6
        lines.append(f'{" " * indent}edit PDY \'{sdate.strftime("%Y%m%d")}\'')
        lines.append(f'{" " * indent}edit CYC \'{sdate.strftime("%H")}\'')
        lines.append('')

        # ── Pre-ensemble tasks ────────────────────────────────────────
        for td in pre_ensemble:
            lines += self._emit_task(td, indent)
            lines.append('')

        # ── Ensemble tasks (only when nmem > 0) ──────────────────────
        if ensemble_tasks:
            # Separate forecast tasks from per-member product/simple tasks.
            fcst_ens_tasks = [td for td in ensemble_tasks
                              if td['task_name'] == 'fcst_ens']
            member_tasks = [td for td in ensemble_tasks
                            if td['task_name'] != 'fcst_ens']

            # Emit family fcst_ens with segmented forecasts per member.
            if fcst_ens_tasks:
                lines += self._emit_fcst_ens_family(
                    fcst_ens_tasks[0], indent)
                lines.append('')

            # Emit per-member product/simple task families at cycle level.
            for td in member_tasks:
                lines += self._emit_per_member_task(td, indent)
                lines.append('')

        # ── Post-ensemble tasks ───────────────────────────────────────
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
            lines += self._emit_task(td, indent)
            lines.append('')

        # Close cycle, run, suite
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

    # ── Task classification ───────────────────────────────────────────

    @staticmethod
    def _classify_tasks(all_tasks: List[Dict]):
        """Split tasks into pre-ensemble, ensemble, and post-ensemble.

        For non-ensemble runs, every task lands in pre_ensemble.
        """
        pre: List[Dict] = []
        ens: List[Dict] = []
        post: List[Dict] = []
        seen_ensemble = False

        for td in all_tasks:
            if td.get('ensemble_task', False):
                seen_ensemble = True
                ens.append(td)
            elif seen_ensemble:
                post.append(td)
            else:
                pre.append(td)

        return pre, ens, post

    # ── Ensemble emission ────────────────────────────────────────────

    def _emit_fcst_ens_family(self, fcst_td: Dict,
                              indent: int) -> List[str]:
        """Emit ``family fcst_ens`` with per-member segmented forecasts.

        Only the forecast task lives here — products are emitted
        separately at the cycle level via ``_emit_per_member_task``.
        """
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)
        msp = ' ' * (indent + 4)

        lines = []
        lines.append(f'{sp}family fcst_ens')
        lines.append(f'{fsp}# {self._nmem + 1} members '
                     f'(mem000=control + {self._nmem} perturbed)')

        # Family-level trigger from the task dict (stage_ic, waveinit, etc.)
        trigger = fcst_td.get('trigger', '')
        if trigger:
            lines.append(f'{fsp}trigger {trigger}')
        lines.append('')

        for mem in range(0, self._nmem + 1):
            mem_str = f'{mem:03d}'
            mem_name = f'mem{mem_str}'

            # mem000 control forecast is emitted as top-level 'fcst';
            # skip it inside fcst_ens.
            if mem == 0:
                continue

            td_copy = dict(fcst_td)
            # Remove trigger from individual members — it's on the family.
            td_copy['trigger'] = None

            lines.append(f'{fsp}family {mem_name}')
            lines.append(f"{msp}edit ENSMEM '{mem_str}'")
            lines.append(f"{msp}edit MEMDIR '{mem_name}'")
            lines.append('')

            # Emit segmented forecast sub-tasks inside the member family.
            lines += self._emit_task(td_copy, indent + 4)
            lines.append('')

            lines.append(f'{fsp}endfamily')
            lines.append('')

        lines.append(f'{sp}endfamily')
        return lines

    def _emit_per_member_task(self, td: Dict, indent: int) -> List[str]:
        """Emit a per-member task as a family with member sub-families.

        Produces at the cycle level::

            family atmos_prod
              family mem000
                edit ENSMEM / MEMDIR
                task f000 ...           # fhr children directly
              endfamily
              family mem001 ...
            endfamily

        For product tasks, forecast-hour children are emitted directly
        inside each member family (no extra wrapper family).
        """
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)
        msp = ' ' * (indent + 4)
        tsp = ' ' * (indent + 6)

        task_name = td['task_name']
        is_product = td.get('product_task', False)
        lines = []
        lines.append(f'{sp}family {task_name}')

        if is_product:
            lines.append(f"{fsp}edit TASK '{task_name}'")

        lines.append('')

        for mem in range(0, self._nmem + 1):
            mem_str = f'{mem:03d}'
            mem_name = f'mem{mem_str}'

            td_copy = dict(td)
            trigger = td_copy.get('trigger', '')
            if trigger:
                td_copy['trigger'] = self._rewrite_member_trigger(
                    trigger, mem)

            lines.append(f'{fsp}family {mem_name}')
            lines.append(f"{msp}edit ENSMEM '{mem_str}'")
            lines.append(f"{msp}edit MEMDIR '{mem_name}'")

            rewritten_trigger = td_copy.get('trigger')
            if rewritten_trigger:
                lines.append(f'{msp}trigger {rewritten_trigger}')
            lines.append('')

            if is_product:
                # Emit fhr group children directly inside the member
                # family without an extra product wrapper.
                lines += self._emit_product_children(td_copy, indent + 4)
            else:
                # Simple per-member task.
                self._copy_map[task_name] = task_name
                lines.append(f'{msp}task {task_name}')
                lines.append(f"{tsp}edit TASK '{task_name}'")
                lines += self._resource_edits(
                    td_copy['resources'], tsp)
            lines.append('')

            lines.append(f'{fsp}endfamily')
            lines.append('')

        lines.append(f'{sp}endfamily')
        return lines

    def _emit_product_children(self, task_dict: Dict,
                               indent: int) -> List[str]:
        """Emit forecast-hour group children for a product task.

        Produces the grouped fhr tasks directly (no wrapping family),
        for use inside a per-member family.
        """
        sp = ' ' * indent
        tsp = ' ' * (indent + 2)

        task_name = task_dict['task_name']
        res = task_dict['resources']
        fhrs = task_dict['forecast_hours']
        config_name = task_dict['config']

        max_tasks = self._configs.get(config_name, {}).get('MAX_TASKS', 25)
        ngroups = min(max_tasks, len(fhrs))
        groups = self._group_fhrs(fhrs, ngroups)
        base_walltime = res.get('walltime', '00:15:00')

        lines = []
        lines += self._resource_edits(res, sp, skip_walltime=True)
        lines.append(f"{sp}# {len(fhrs)} forecast hours in {ngroups} groups")
        lines.append('')

        for grp in groups:
            if len(grp) == 1:
                label = f'f{grp[0]:03d}'
            else:
                label = f'f{grp[0]:03d}_f{grp[-1]:03d}'

            self._copy_map[label] = task_name
            fhr_list_str = ','.join(str(f) for f in grp)
            grp_walltime = Tasks.multiply_HMS(base_walltime, len(grp))

            lines.append(f'{sp}task {label}')
            lines.append(f"{tsp}edit FHR_LIST '{fhr_list_str}'")
            lines.append(f"{tsp}edit WALLTIME '{grp_walltime}'")
            lines.append('')

        return lines

    def _rewrite_member_trigger(self, trigger: str, mem: int) -> str:
        """Adjust trigger paths for member context.

        Uses absolute paths from the suite root since ecFlow does not
        reliably support multi-level ``../../`` relative references.
        """
        cycle_path = self._cycle_path

        parts = trigger.split(' and ')
        rewritten = []
        for part in parts:
            part = part.strip()
            node_name = part.split(' ')[0]

            if node_name == 'fcst':
                if mem == 0:
                    rewritten.append(part.replace(
                        'fcst', f'{cycle_path}/fcst'))
                else:
                    rewritten.append(part.replace(
                        'fcst',
                        f'{cycle_path}/fcst_ens/mem{mem:03d}/fcst_ens'))
            else:
                rewritten.append(part)

        return ' and '.join(rewritten)

    # ── Sentinel / post-ensemble trigger resolution ───────────────────

    def _resolve_sentinel(self, sentinel: str) -> str:
        """Resolve a sentinel to per-member trigger expressions.

        Products are at cycle level: ``{cycle_path}/{task_name}/memNNN``.
        """
        family_name = _SENTINEL_MAP.get(sentinel)
        if not family_name:
            return sentinel

        cycle_path = self._cycle_path
        parts = []
        for mem in range(0, self._nmem + 1):
            parts.append(
                f'{cycle_path}/{family_name}/mem{mem:03d} == complete')
        return ' and '.join(parts)

    @staticmethod
    def _rewrite_post_ensemble_trigger(trigger: str,
                                       ens_task_names: Set[str]) -> str:
        """Rewrite triggers for post-ensemble tasks.

        Per-member product families (``atmos_prod``, ``ocean_prod``, etc.)
        are now cycle-level siblings, so ``atmos_prod == complete``
        correctly triggers when all members inside the family finish.
        ``fcst_ens == complete`` triggers when all member forecasts finish.
        No rewriting needed — ecFlow family completion handles it.
        """
        return trigger

    # ── Task rendering ────────────────────────────────────────────────

    def _emit_task(self, task_dict: Dict, indent: int) -> List[str]:
        """Dispatch to the appropriate emitter."""
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

        task_name = task_dict['task_name']
        res = task_dict['resources']
        trigger = task_dict.get('trigger')

        self._copy_map[task_name] = task_name

        lines = [f'{sp}task {task_name}',
                 f"{tsp}edit TASK '{task_name}'"]
        lines += self._resource_edits(res, tsp)
        if trigger:
            lines.append(f'{tsp}trigger {trigger}')

        return lines

    def _emit_segmented_task(self, task_dict: Dict,
                             indent: int) -> List[str]:
        """Emit a forecast task with sequential segment sub-tasks."""
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)
        tsp = ' ' * (indent + 4)

        task_name = task_dict['task_name']
        res = task_dict['resources']
        trigger = task_dict.get('trigger')
        num_segments = task_dict.get('num_segments', 1)

        lines = [f'{sp}family {task_name}',
                 f"{fsp}edit TASK '{task_name}'"]
        if trigger:
            lines.append(f'{fsp}trigger {trigger}')
        lines += self._resource_edits(res, fsp)
        lines.append('')

        for seg in range(num_segments):
            seg_name = f'seg{seg}'
            # Use task-prefixed key to avoid copy map collisions
            # between control (fcst) and ensemble (fcst_ens) segments.
            copy_key = f'{task_name}_seg{seg}'
            self._copy_map[copy_key] = task_name
            lines.append(f'{fsp}task {seg_name}')
            lines.append(f"{tsp}edit FCST_SEGMENT '{seg}'")
            if seg > 0:
                lines.append(f'{tsp}trigger seg{seg - 1} == complete')
            lines.append('')

        lines.append(f'{sp}endfamily')
        return lines

    def _emit_product_family(self, task_dict: Dict,
                             indent: int) -> List[str]:
        """Emit a product task as grouped forecast-hour children."""
        sp = ' ' * indent
        fsp = ' ' * (indent + 2)
        tsp = ' ' * (indent + 4)

        task_name = task_dict['task_name']
        res = task_dict['resources']
        trigger = task_dict.get('trigger')
        fhrs = task_dict['forecast_hours']
        config_name = task_dict['config']

        max_tasks = self._configs.get(config_name, {}).get('MAX_TASKS', 25)
        ngroups = min(max_tasks, len(fhrs))
        groups = self._group_fhrs(fhrs, ngroups)
        base_walltime = res.get('walltime', '00:15:00')

        lines = [f'{sp}family {task_name}',
                 f"{fsp}edit TASK '{task_name}'",
                 f"{fsp}# {len(fhrs)} forecast hours in {ngroups} groups"]
        if trigger:
            lines.append(f'{fsp}trigger {trigger}')
        lines += self._resource_edits(res, fsp, skip_walltime=True)
        lines.append('')

        for grp in groups:
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

    # ── Resource edits ────────────────────────────────────────────────

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
            logger.warning(
                f'Missing source .ecf (skipped): {", ".join(unique)}')

    # ── Suite-level variables ─────────────────────────────────────────

    def _suite_variables(self, indent: int = 2) -> List[str]:
        """Emit suite-level edit variables."""
        sp = ' ' * indent
        base = self._base
        lines = []

        rotdir = base.get('ROTDIR', os.path.join(
            str(base.get('COMROOT', '/tmp')), self.pslot))
        ecf_log_dir = os.path.join(rotdir, 'logs')

        ecf_host = os.environ.get(
            'ECF_HOST', os.environ.get('HOSTNAME', 'localhost'))
        ecf_port = os.environ.get('ECF_PORT', '3141')

        ecf_scripts_dir = os.path.join(self.expdir, 'ecf_scripts')
        ecf_include = os.environ.get(
            'ECF_INCLUDE',
            os.path.join(self.HOMEglobal, 'dev', 'ecflow', 'utils'))

        lines.append(f"{sp}# ecFlow server connection")
        lines.append(f"{sp}edit ECF_LOGHOST '{ecf_host}'")
        lines.append(f"{sp}edit ECF_PORT    '{ecf_port}'")
        lines.append(f"{sp}")
        lines.append(f"{sp}# File locations")
        lines.append(f"{sp}edit ECF_HOME    '{ecf_log_dir}'")
        lines.append(f"{sp}edit ECF_INCLUDE '{ecf_include}'")
        lines.append(f"{sp}edit ECF_FILES   '{ecf_scripts_dir}'")
        lines.append(
            f"{sp}edit ECF_JOBOUT  '{ecf_log_dir}/%TASK%.%ECF_TRYNO%'")
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
        lines.append(
            f"{sp}edit APP      '{self._options.get('app', 'ATM')}'")
        account = base.get('ACCOUNT', '')
        if not account or account == 'UNDEFINED':
            account = os.environ.get('HPC_ACCOUNT', 'fv3-cpu')
        lines.append(f"{sp}edit ACCOUNT  '{account}'")
        lines.append(
            f"{sp}edit QUEUE    '{base.get('PARTITION_BATCH', 'batch')}'")
        lines.append(f"{sp}edit PSLOT    '{self.pslot}'")
        lines.append(f"{sp}edit CASE     '{base['CASE']}'")
        lines.append(
            f"{sp}edit FHMAX_GFS '{base.get('FHMAX_GFS', 120)}'")
        if self._nmem > 0:
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
