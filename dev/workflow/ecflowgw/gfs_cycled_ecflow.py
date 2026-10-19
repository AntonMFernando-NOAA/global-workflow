#!/usr/bin/env python3

"""
Cycled GFS ecFlow suite generator.

Builds one ecFlow suite for a cycled experiment.  The suite holds one
family per cycle hour that every cycle of that hour reuses, and, inside
it, a family per run (``gdas``, ``enkfgdas``, ``gfs``, ``enkfgfs``).  Each
family is named after the ``PDYCYC`` (``YYYYMMDDHH``) of its first cycle::

    suite {pslot}
      family 2021122012                      # first cycle, reduced tasks
        task cycle_begin
        family gdas
          ...
        endfamily
      endfamily
      family 2021122018                      # reused by every 18Z cycle
        task cycle_begin
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
It has a family of its own, named after its own ``PDYCYC``.

The family name is fixed to the first cycle it runs; the date advances
inside the family through the ``PDY`` variable, which ``cycle_begin``
updates each pass.

The ``cycle_begin`` task of a family starts a cycle.  It runs once the
previous cycle has started its forecast.  It hands the date (``PDY``) and
the log directory (``LOGDIR``) of the next cycle to the next cycle family
(named by the ``NEXT_FAMILY`` variable) and requeues that family, whose
run families wait for its own ``cycle_begin``.  See
``dev/ecflow/scripts/cycle_begin.ecf``.

Dependencies between runs and cycles are written in the task triggers as
``ref()`` placeholders, which this class turns into absolute ecFlow paths.
A dependency on a task that does not run in the cycle is dropped.  When
the cycles that share a family resolve a dependency differently, the paths
are combined with conditions on the ``PDY`` of the family.  The tasks
without an ecFlow definition are skipped and listed in the suite header.
"""

import os
from datetime import datetime, timedelta
from logging import getLogger
from typing import Dict, List, Optional, Tuple

from applications.applications import AppConfig
from ecflowgw.ecflow_tasks import REF_PATTERN
from ecflowgw.forecast_only_ecflow import _TASK_FAMILY, ForecastOnlyEcFlowSuite
from ecflowgw.gfs_cycled_ecflow_tasks import GFSCycledEcFlowTasks
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

# Grouping key of the first cycle, which runs the reduced set of tasks.
HALF_KEY = 'half'

# Task that starts a cycle.
CYCLE_BEGIN = 'cycle_begin'


class GFSCycledEcFlowSuite(ForecastOnlyEcFlowSuite):
    """ecFlow suite generator for cycled GFS workflows."""

    def __init__(self, app_config: AppConfig, ecflow_config: Dict) -> None:
        super().__init__(app_config, ecflow_config)

        self._sdate = self._base['SDATE']
        self._assim_freq = to_timedelta(f"{self._base['assim_freq']}H")
        self._runs = [run for run in RUN_ORDER if run in app_config.task_names]
        self._cycles = self._get_cycles()
        self._families = self._group_cycles()
        self._planned: Dict[Tuple[datetime, str], List[str]] = {}
        self._skipped: Dict[str, List[str]] = {}

    def _create_tasks(self, run: str):
        return GFSCycledEcFlowTasks(self._app_config, run)

    def _select_run(self, run: str) -> None:
        super()._select_run(run)
        # Ensemble members belong to the enkf runs, not to the suite.
        self._nmem = 0

    def _family_of(self, task_name: str, cycle_str: str = None) -> str:
        """Return the run-level family of a task in a cycle.

        ``init`` exists only in the first cycle.  Later cycles run
        ``waveinit`` as part of the analysis chain, and ``metp`` is a
        verification (``stats``) task.
        """
        if task_name == 'metp':
            return 'stats'
        if task_name == 'waveinit':
            cycle_str = cycle_str or self._cycle_str
            first = cycle_str == self._sdate.strftime('%Y%m%d%H')
            return 'init' if first else 'analysis'
        return _TASK_FAMILY.get(task_name)

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
        for name, cycles in self._families.items():
            body += self._emit_cycle_family(name, cycles)

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
        """Return the ecFlow task dicts of the selected run for a cycle.

        The triggers are resolved for every cycle that shares the family
        of *cycle_str*.
        """
        cycle = datetime.strptime(cycle_str, '%Y%m%d%H')
        family = self._family_name(cycle)

        task_dicts = [self._tasks.get_ecflow_task(name)
                      for name in self._planned_tasks(cycle, self._run)]
        for task in task_dicts:
            if task.get('trigger'):
                task['trigger'] = self._resolve_trigger(
                    task['trigger'], self._families[family])
        return task_dicts

    def _resolve_trigger(self, trigger: str, cycles: List[datetime]) -> str:
        """Resolve the references of *trigger* for the selected run.

        References to other runs or cycles become absolute ecFlow paths.
        Dependencies on tasks that do not run in their cycle are dropped.

        Parameters
        ----------
        trigger : str
            Trigger with ``ref()`` placeholders.
        cycles : List[datetime]
            Cycles that share the family of the task.
        """
        family = self._family_name(cycles[0])
        parts = []
        for part in trigger.split(' and '):
            resolved = self._combine_by_cycle(
                family, {cycle: self._resolve_part(part.strip(), cycle)
                         for cycle in cycles})
            if resolved:
                parts.append(resolved)
        return ' and '.join(parts)

    def _resolve_part(self, part: str, cycle: datetime) -> Optional[str]:
        """Resolve one ``task state`` part of a trigger for *cycle*.

        Returns None when the dependency is dropped.
        """
        token, _, state = part.partition(' ')
        match = REF_PATTERN.fullmatch(token)
        if match:
            run = match.group(1) or self._run
            target_cycle = cycle + timedelta(hours=int(match.group(2)))
            target = match.group(3)
        elif token.startswith('/'):
            return part
        else:
            run, target_cycle, target = self._run, cycle, token

        task = target.split('/')[0]
        if task not in self._planned_tasks(target_cycle, run):
            return None
        if match or '/' in target:
            token = self._task_path(target_cycle, run, task, target)
        return f'{token} {state}'

    def _task_path(self, cycle: datetime, run: str, task: str,
                   target: str = None) -> str:
        """Return the absolute ecFlow path of *target* (default *task*)."""
        path = [f'/{self.pslot}/{self._family_name(cycle)}', run,
                self._family_of(task, cycle.strftime('%Y%m%d%H')),
                target or task]
        return '/'.join(name for name in path if name)

    def _combine_by_cycle(self, family: str,
                          exprs: Dict[datetime, Optional[str]]) -> str:
        """Combine the expressions that each cycle of a family resolved to.

        A family runs several cycles with the same definition, so an
        expression that differs between them is guarded by the ``PDY`` the
        family holds in that cycle.

        Parameters
        ----------
        family : str
            Cycle family.
        exprs : Dict[datetime, Optional[str]]
            Expression of each cycle; None when the cycle has no condition.

        Returns
        -------
        str
            The expression, or an empty string when no cycle has a condition.
        """
        groups: Dict[Optional[str], List[datetime]] = {}
        for cycle, expr in exprs.items():
            groups.setdefault(expr, []).append(cycle)
        if len(groups) == 1:
            return next(iter(groups)) or ''

        clauses = []
        for expr, cycles in groups.items():
            guards = [f'/{self.pslot}/{family}:PDY == {cycle.strftime("%Y%m%d")}'
                      for cycle in cycles]
            guard = guards[0] if len(guards) == 1 else f'({" or ".join(guards)})'
            clauses.append(guard if expr is None else f'({expr} and {guard})')
        return f'({" or ".join(clauses)})'

    # -- Cycle families ------------------------------------------------

    def _group_key(self, cycle: datetime) -> str:
        """Return the key of the family that runs *cycle*.

        Cycles of the same hour share a family, except the first cycle,
        which runs a reduced set of tasks in a family of its own.
        """
        if cycle == self._sdate and any(
                run in HALF_CYCLE_TASKS for run in self._cycles[cycle]):
            return HALF_KEY
        return cycle.strftime('%H')

    def _family_name(self, cycle: datetime) -> str:
        """Return the name of the family that runs *cycle*.

        The name is the ``PDYCYC`` of the first cycle the family runs.
        """
        return self._family_names[self._group_key(cycle)]

    def _group_cycles(self) -> Dict[str, List[datetime]]:
        """Group the cycles by the family that runs them.

        Builds ``self._family_names`` (``group key`` -> family name) and
        returns the cycles of each family, keyed by the family name and in
        time order.

        Raises
        ------
        ValueError
            If the cycles of one hour do not run the same runs, because
            they could not share a family.
        """
        groups: Dict[str, List[datetime]] = {}
        for cycle in self._cycles:
            groups.setdefault(self._group_key(cycle), []).append(cycle)

        for key, cycles in groups.items():
            if len({tuple(self._cycles[cycle]) for cycle in cycles}) > 1:
                raise ValueError(
                    f"The cycles at {key}Z do not all run the same runs, so "
                    "they cannot share a cycle family.  Start the gfs cycles "
                    "at the first full cycle, or use an interval_gfs that "
                    "divides 24 hours.")

        self._family_names = {key: cycles[0].strftime('%Y%m%d%H')
                              for key, cycles in groups.items()}
        return {self._family_names[key]: cycles
                for key, cycles in groups.items()}

    def _next_family(self, cycles: List[datetime]) -> Optional[str]:
        """Return the name of the family that runs the cycle after *cycles*.

        None when the next cycle hour has no family (a short run that does
        not reach it); such a family is always the last one.
        """
        next_key = (cycles[0] + self._assim_freq).strftime('%H')
        return self._family_names.get(next_key)

    def _cycle_node(self, cycle_str: str) -> str:
        return self._family_name(datetime.strptime(cycle_str, '%Y%m%d%H'))

    def _run_family_attributes(self, indent: int) -> List[str]:
        # The run waits for cycle_begin, which requeues it
        cycle_path = self._run_path.rsplit('/', 1)[0]
        return [f"{' ' * indent}trigger {cycle_path}/{CYCLE_BEGIN} == complete"]

    def _emit_cycle_family(self, name: str, cycles: List[datetime]) -> List[str]:
        """Emit the family shared by *cycles*.

        The variables hold the values of the first cycle; ``cycle_begin``
        sets them for the next cycle.
        """
        first = cycles[0]
        first_str = first.strftime('%Y%m%d%H')

        lines = [f'  family {name}',
                 f"    edit PDY '{first.strftime('%Y%m%d')}'",
                 f"    edit CYC '{first.strftime('%H')}'",
                 f"    edit RUNS '{' '.join(self._cycles[first])}'"]
        next_family = self._next_family(cycles)
        if next_family:
            lines.append(f"    edit NEXT_FAMILY '{next_family}'")
        lines.append(self._log_dir_edit(first_str, indent=4))
        lines.append('')
        for cycle in cycles[1:]:
            self._log_dirs.add(self._log_dir(cycle.strftime('%Y%m%d%H')))

        lines += self._emit_cycle_begin(name, cycles)
        lines.append('')
        for run in self._cycles[first]:
            self._select_run(run)
            self._ecf_prefix = run
            lines += self._emit_run_family(first_str, indent=4)
            lines.append('')
        lines.append('  endfamily')
        lines.append('')
        return lines

    def _emit_cycle_begin(self, family: str, cycles: List[datetime]) -> List[str]:
        """Emit the ``cycle_begin`` task of a cycle family.

        The task starts once the previous cycle has started its gdas
        forecast and, when the gfs ran two cycles ago, once that gfs
        forecast is no longer running.  The first cycle has no trigger.
        """
        self._select_run(RUN_ORDER[0])
        self._ecf_prefix = ''
        resources = self._tasks.get_resource('cleanup')
        self._copy_maps.setdefault('', (RUN_ORDER[0], {}))[1][
            (CYCLE_BEGIN, CYCLE_BEGIN, None)] = resources

        trigger = self._combine_by_cycle(
            family, {cycle: self._begin_condition(cycle) for cycle in cycles})
        lines = [f'    task {CYCLE_BEGIN}',
                 f"      edit TASK '{CYCLE_BEGIN}'",
                 f"      edit LOG_NAME '{CYCLE_BEGIN}'"]
        lines += self._ecf_files_edit(CYCLE_BEGIN, '      ')
        lines += self._resource_edits(resources, '      ')
        if trigger:
            lines.append(f'      trigger {trigger}')
        return lines

    def _begin_condition(self, cycle: datetime) -> Optional[str]:
        """Return the trigger of ``cycle_begin`` in *cycle*, or None."""
        previous = cycle - self._assim_freq
        if previous not in self._cycles:
            return None

        forecast = self._task_path(previous, 'gdas', 'fcst')
        condition = f'({forecast} == active or {forecast} == complete)'

        two_ago = cycle - 2 * self._assim_freq
        if 'gfs' in self._cycles.get(two_ago, []):
            gfs_forecast = self._task_path(two_ago, 'gfs', 'fcst')
            condition += f' and {gfs_forecast} != active'
        return condition

    def _suite_variables(self, indent: int = 2) -> List[str]:
        """Emit the suite variables and those ``cycle_begin`` needs."""
        sp = ' ' * indent
        first_str = self._sdate.strftime('%Y%m%d%H')
        lines = super()._suite_variables(indent)
        lines.append(f'{sp}')
        lines.append(f'{sp}# Cycling, used by cycle_begin')
        lines.append(f"{sp}edit EDATE      '{self._base['EDATE'].strftime('%Y%m%d%H')}'")
        lines.append(f"{sp}edit ASSIM_FREQ '{int(self._assim_freq.total_seconds() // 3600)}'")
        lines.append(f"{sp}edit LOGROOT    '{os.path.dirname(self._log_dir(first_str))}'")
        return lines
