#!/usr/bin/env python3

"""
Cycled GFS ecFlow suite generator.

Builds one ecFlow suite for a cycled experiment.  The suite holds a
family per cycle and, inside it, a family per run (``gdas``,
``enkfgdas``, ``gfs``, ``enkfgfs``)::

    suite {pslot}
      family {cycle}
        family gdas
          ...
        endfamily
        family enkfgdas
          ...
        endfamily
        family gfs                           # only on gfs cycles
          ...
        endfamily
      endfamily
    endsuite

The run families reuse the emitters of ``ForecastOnlyEcFlowSuite``.

The first cycle only initializes the system (the "gdas_half" cycle of the
Rocoto workflow): ``gdas`` and ``enkfgdas`` run a reduced set of tasks.

Dependencies between runs and cycles are written in the task triggers as
``ref()`` placeholders, which this class turns into absolute ecFlow paths.
A dependency on a task that does not run in the cycle is dropped.  The
tasks without an ecFlow definition are skipped and listed in the suite
header.
"""

import os
from datetime import datetime, timedelta
from logging import getLogger
from typing import Dict, List, Tuple

from applications.applications import AppConfig
from ecflow.ecflow_tasks import REF_PATTERN
from ecflow.forecast_only_ecflow import _TASK_FAMILY, ForecastOnlyEcFlowSuite
from ecflow.gfs_cycled_ecflow_tasks import GFSCycledEcFlowTasks
from wxflow import to_timedelta, timedelta_to_HMS

logger = getLogger(__name__.split('.')[-1])

# Runs of a cycle, in emission order.
RUN_ORDER = ('gdas', 'enkfgdas', 'gfs', 'enkfgfs')

# Tasks of the first cycle.
HALF_CYCLE_TASKS = {
    'gdas': ('stage_ic', 'waveinit', 'fcst', 'atmos_prod', 'cleanup'),
    'enkfgdas': ('stage_ic', 'echgres', 'efcs', 'epos', 'cleanup'),
}

# The Rocoto workflow defines no cycle for this task.
NEVER_RUN = (('enkfgfs', 'stage_ic'),)


class GFSCycledEcFlowSuite(ForecastOnlyEcFlowSuite):
    """ecFlow suite generator for cycled GFS workflows."""

    def __init__(self, app_config: AppConfig, ecflow_config: Dict) -> None:
        super().__init__(app_config, ecflow_config)

        self._sdate = self._base['SDATE']
        self._assim_freq = to_timedelta(f"{self._base['assim_freq']}H")
        self._runs = [run for run in RUN_ORDER if run in app_config.task_names]
        self._cycles = self._get_cycles()
        self._planned: Dict[Tuple[datetime, str], List[str]] = {}
        self._skipped: Dict[str, List[str]] = {}

    def _create_tasks(self, run: str):
        return GFSCycledEcFlowTasks(self._app_config, run)

    def _select_run(self, run: str) -> None:
        super()._select_run(run)
        # Ensemble members belong to the enkf runs, not to the suite.
        self._nmem = 0

    # ── Public interface ──────────────────────────────────────────────

    def get_cycledefs(self) -> str:
        """Human-readable cycle summary."""
        edate = self._base['EDATE']
        return (f"Cycles: {self._sdate.strftime('%Y%m%d%H')} - "
                f"{edate.strftime('%Y%m%d%H')} every "
                f"{timedelta_to_HMS(self._assim_freq)} "
                f"(gfs from {self._base['SDATE_GFS'].strftime('%Y%m%d%H')} "
                f"every {timedelta_to_HMS(self._base['interval_gfs'])})")

    def write(self, def_file: str = None) -> str:
        """Generate the ecFlow ``.def`` file and ecf_scripts directory."""
        if def_file is None:
            def_file = os.path.join(self.expdir, f'{self.pslot}.def')

        self._prepare_write()
        self._skipped = {}

        body: List[str] = []
        for cycle, runs in self._cycles.items():
            cycle_str = cycle.strftime('%Y%m%d%H')
            body.append(f'  family {cycle_str}')
            body.append(f"    edit PDY '{cycle.strftime('%Y%m%d')}'")
            body.append(f"    edit CYC '{cycle.strftime('%H')}'")
            body.append('')
            for run in runs:
                self._select_run(run)
                self._ecf_prefix = run
                body += self._emit_run_family(cycle_str, indent=4)
                body.append('')
            body.append('  endfamily')
            body.append('')

        # The suite variables describe the first run
        self._select_run(self._runs[0])

        lines: List[str] = []
        lines.append(f'# Auto-generated ecFlow suite definition for {self.pslot}')
        lines.append(f'# Mode: {self._app_config.mode}  NET: {self._base["NET"]}')
        lines.append(f'# {self.get_cycledefs()}')
        if self._skipped:
            lines.append('# Not yet defined in ecFlow (skipped):')
            for run, names in self._skipped.items():
                lines.append(f'#   {run}: {", ".join(names)}')
        lines.append('')
        lines.append(f'suite {self.pslot}')
        lines += self._suite_variables(indent=2)
        lines.append('')
        lines += body
        lines.append('endsuite')
        lines.append('')

        return self._finish_write(def_file, lines)

    # ── Cycles and tasks ──────────────────────────────────────────────

    def _get_cycles(self) -> Dict[datetime, List[str]]:
        """Map each cycle to the runs that execute in it.

        Returns
        -------
        Dict[datetime, List[str]]
            Cycles in time order with their runs, in ``RUN_ORDER``.
        """
        edate = self._base['EDATE']
        interval_gfs = self._base['interval_gfs']

        cycles: Dict[datetime, List[str]] = {}
        for run in self._runs:
            if run.endswith('gdas'):
                start, step = self._sdate, self._assim_freq
            elif interval_gfs > to_timedelta('0H'):
                start, step = self._base['SDATE_GFS'], interval_gfs
            else:
                continue
            cycle = start
            while cycle <= edate:
                cycles.setdefault(cycle, []).append(run)
                cycle += step

        return {cycle: sorted(runs, key=RUN_ORDER.index)
                for cycle, runs in sorted(cycles.items())}

    def _planned_tasks(self, cycle: datetime, run: str) -> List[str]:
        """Return the tasks of *run* that execute in *cycle*.

        The list is empty when the run does not execute in the cycle.
        """
        if run not in self._cycles.get(cycle, []):
            return []

        key = (cycle, run)
        if key not in self._planned:
            first_cycle = cycle == self._sdate
            names, skipped = [], []
            for name in self._app_config.task_names[run]:
                if run in HALF_CYCLE_TASKS:
                    if first_cycle and name not in HALF_CYCLE_TASKS[run]:
                        continue
                    if not first_cycle and name == 'stage_ic':
                        continue
                if (run, name) in NEVER_RUN:
                    continue
                if not callable(getattr(GFSCycledEcFlowTasks, name, None)):
                    skipped.append(name)
                    continue
                names.append(name)
            self._planned[key] = names
            if skipped and not (first_cycle and run in HALF_CYCLE_TASKS):
                self._skipped[run] = skipped
        return self._planned[key]

    def _get_task_dicts(self, cycle_str: str) -> List[Dict]:
        """Return the ecFlow task dicts of the selected run for a cycle."""
        cycle = datetime.strptime(cycle_str, '%Y%m%d%H')

        task_dicts = [self._tasks.get_ecflow_task(name)
                      for name in self._planned_tasks(cycle, self._run)]
        for task in task_dicts:
            if task.get('trigger'):
                task['trigger'] = self._resolve_trigger(task['trigger'], cycle)
        return task_dicts

    def _resolve_trigger(self, trigger: str, cycle: datetime) -> str:
        """Resolve the references of *trigger* for the selected run.

        References to other runs or cycles become absolute ecFlow paths.
        Dependencies on tasks that do not run in their cycle are dropped.
        """
        parts = []
        for part in trigger.split(' and '):
            token, _, state = part.strip().partition(' ')
            match = REF_PATTERN.fullmatch(token)
            if match:
                run = match.group(1) or self._run
                target_cycle = cycle + timedelta(hours=int(match.group(2)))
                target = match.group(3)
            elif token.startswith('/'):
                parts.append(part.strip())
                continue
            else:
                run, target_cycle, target = self._run, cycle, token

            task = target.split('/')[0]
            if task not in self._planned_tasks(target_cycle, run):
                continue
            if match or '/' in target:
                path = [f'/{self.pslot}/{target_cycle.strftime("%Y%m%d%H")}',
                        run, _TASK_FAMILY.get(task), target]
                token = '/'.join(name for name in path if name)
            parts.append(f'{token} {state}')
        return ' and '.join(parts)
