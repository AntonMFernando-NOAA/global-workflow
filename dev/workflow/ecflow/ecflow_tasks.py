#!/usr/bin/env python3

"""
Base class for ecFlow task definitions.

Extends ``rocoto.tasks.Tasks`` to reuse the resource extraction,
forecast hour grouping, and system configuration infrastructure.
Subclasses (e.g. ``GFSEcFlowTasks``) provide per-task methods that
return ecFlow task dictionaries instead of Rocoto XML strings.

Each task method returns a dict (or list of dicts for product tasks)
with keys consumed by the suite generator::

    {
        'task_name':    str,        # logical task name
        'jjob':         str,        # J-Job basename under dev/jobs/
        'resources':    dict,       # from get_resource()
        'step':         str,        # config.resources step name
        'trigger':      str | None, # ecFlow trigger expression
        'product_task': bool,       # True → emit as family with fhr children
        'tarball_task': bool,       # True → emit as family with one child per tarball type
        'service_task': bool,       # True → service partition
        'component':    str | None, # 'atmos', 'ocean', 'ice', 'wave'
        'config':       str | None, # config step name (for product tasks)
        'forecast_hours': list | None,  # forecast hours (for product tasks)
        'card':         str | None, # Rocoto job card run when no .ecf script exists
        'envars':       dict,       # variables exported to the task
        'group_task':   bool,       # True → family with one child per entry of 'children'
        'children':     dict,       # {child name: {variable: value}} (tarball and group tasks)
    }

A trigger may name a task of another run or cycle with ``ref()``.  The
cycled suite resolves those references and drops every dependency on a
task that does not run in the cycle.
"""

import re
from logging import getLogger
from typing import Dict, List, Optional

from applications.applications import AppConfig
from rocoto.tasks import Tasks

logger = getLogger(__name__.split('.')[-1])

REF_PATTERN = re.compile(r'\[(\w*)@(-?\d+)\](\S+)')


def ref(task: str, run: str = '', offset_hours: int = 0) -> str:
    """Return a placeholder for a task of another run or cycle.

    Parameters
    ----------
    task : str
        Task name, or ``family/child`` for a child of a group task.
    run : str, optional
        Run of the task; the current run when empty.
    offset_hours : int, optional
        Cycle offset in hours relative to the current cycle.
    """
    return f'[{run}@{offset_hours}]{task}'


class EcFlowTasks(Tasks):
    """
    Base class for ecFlow task definitions.

    Inherits ``Tasks.__init__`` which sets up configs, options, base,
    system settings, and environment variables.  The Rocoto-specific
    envars (XML strings) are unused on the ecFlow side but harmless.

    Subclasses override individual task methods to return ecFlow task
    dicts.
    """

    def __init__(self, app_config: AppConfig, run: str) -> None:
        super().__init__(app_config, run)
        self._task_names = app_config.task_names[run]

    def get_ecflow_task(self, task_name: str) -> Dict:
        """
        Dispatch to the task method for *task_name* and return its
        ecFlow task dict.

        Mirrors ``Tasks.get_task()`` but returns a dict instead of
        Rocoto XML.
        """
        try:
            return getattr(self, task_name)()
        except AttributeError:
            raise AttributeError(
                f'"{task_name}" is not a valid ecFlow task.\n'
                f'Valid tasks are:\n'
                f'{", ".join(Tasks.VALID_TASKS)}')

    # ── Helpers for subclasses ────────────────────────────────────────

    def _has_task(self, name: str) -> bool:
        """Return True if *name* is in the active task list."""
        return name in self._task_names

    def _simple_task(self, task_name: str, *,
                     jjob: str,
                     trigger: Optional[str] = None,
                     resource_name: Optional[str] = None,
                     service: bool = False,
                     card: Optional[str] = None,
                     envars: Optional[Dict[str, str]] = None) -> Dict:
        """
        Build a standard (non-product) ecFlow task dict.

        Parameters
        ----------
        task_name : str
            Logical task name.
        jjob : str
            J-Job script basename under dev/jobs/.
        trigger : str, optional
            ecFlow trigger expression.
        resource_name : str, optional
            Config step name for ``get_resource()``.  Defaults to
            *task_name*.
        service : bool
            Whether this task runs on the service partition.
        card : str, optional
            Basename of a Rocoto job card under ``dev/job_cards/rocoto``.
            Tasks without a script in ``dev/ecflow/scripts`` are run
            through this card.
        envars : dict, optional
            Variables the task needs; the suite emits them as ecFlow
            variables and the generated script exports them.
        """
        resources = self.get_resource(resource_name or task_name)
        step = resource_name or task_name
        return {
            'task_name': task_name,
            'jjob': jjob,
            'resources': resources,
            'step': step,
            'trigger': trigger,
            'product_task': False,
            'tarball_task': False,
            'service_task': service,
            'component': None,
            'config': None,
            'forecast_hours': None,
            'card': card,
            'envars': envars or {},
        }

    def _group_task(self, task_name: str, *,
                    jjob: str,
                    children: Dict[str, Dict[str, str]],
                    trigger: Optional[str] = None,
                    resource_name: Optional[str] = None,
                    card: Optional[str] = None,
                    script: Optional[str] = None) -> Dict:
        """
        Build a group ecFlow task dict (emitted as a family with one child
        task per group), like a Rocoto metatask over a variable.

        Parameters
        ----------
        task_name : str
            Logical task name (becomes the family name).
        jjob : str
            J-Job script basename.
        children : dict
            ``{child name: {variable: value}}``; each child sets its own
            variables.
        trigger : str, optional
            ecFlow trigger expression, applied on the family.
        resource_name : str, optional
            Config step name for ``get_resource()``.  Defaults to
            *task_name*.
        card : str, optional
            Rocoto job card used when no script exists for the task.
        script : str, optional
            Name of the existing ``.ecf`` script the children run.
            Defaults to *task_name*.
        """
        task = self._simple_task(task_name, jjob=jjob, trigger=trigger,
                                 resource_name=resource_name, card=card)
        task['group_task'] = True
        task['children'] = children
        task['script'] = script or task_name
        return task

    def _product_task(self, task_name: str, *,
                      jjob: str,
                      config: str,
                      component: str,
                      trigger: Optional[str] = None,
                      resource_name: Optional[str] = None) -> Dict:
        """
        Build a product ecFlow task dict (emitted as a family of
        per-forecast-hour-group children).

        Parameters
        ----------
        task_name : str
            Logical task name.
        jjob : str
            J-Job script basename.
        config : str
            Config step name for resource + forecast hour lookup.
        component : str
            Component name ('atmos', 'ocean', 'ice', 'wave').
        trigger : str, optional
            ecFlow trigger expression.
        resource_name : str, optional
            Config step name for ``get_resource()``.  Defaults to
            *config*.
        """
        resources = self.get_resource(resource_name or config)
        step = resource_name or config
        fhrs = self._get_forecast_hours(self.run, self._configs[config], component)

        # Ocean/ice do not produce output at fhr 0
        if component in ('ocean', 'ice') and 0 in fhrs:
            fhrs.remove(0)

        return {
            'task_name': task_name,
            'jjob': jjob,
            'resources': resources,
            'step': step,
            'trigger': trigger,
            'product_task': True,
            'tarball_task': False,
            'service_task': False,
            'component': component,
            'config': config,
            'forecast_hours': fhrs,
        }

    def _tarball_task(self, task_name: str, *,
                      jjob: str,
                      tarball_types: List[str],
                      trigger: Optional[str] = None,
                      resource_name: Optional[str] = None) -> Dict:
        """
        Build a tarball ecFlow task dict (emitted as a family with one
        ``arch_tar_{tarball_type}`` child per tarball type, like the
        Rocoto ``arch_tars`` metatask).

        Parameters
        ----------
        task_name : str
            Logical task name (becomes the family name).
        jjob : str
            J-Job script basename.
        tarball_types : list of str
            Tarball types; each child sets ``TARBALL_TYPE`` to one of them.
        trigger : str, optional
            ecFlow trigger expression, applied on the family.
        resource_name : str, optional
            Config step name for ``get_resource()``.  Defaults to
            *task_name*.
        """
        resources = self.get_resource(resource_name or task_name)
        step = resource_name or task_name
        return {
            'task_name': task_name,
            'jjob': jjob,
            'resources': resources,
            'step': step,
            'trigger': trigger,
            'product_task': False,
            'tarball_task': True,
            'service_task': False,
            'component': None,
            'config': None,
            'forecast_hours': None,
            'children': {f'arch_tar_{t}': t for t in tarball_types},
        }

    def _get_tarball_types(self) -> List[str]:
        """
        Determine the list of tarball types for the arch_tars task.

        Mirrors rocoto/gfs_tasks.py arch_tars() logic.
        """
        if self.run == 'gfs':
            tarball_types = ['gfsa']

            if self._configs['arch_tars'].get('ARCH_GAUSSIAN', True):
                tarball_types.extend(['gfs_flux', 'gfs_netcdfb', 'gfs_pgrb2b'])
                if self.app_config.mode == 'cycled':
                    tarball_types.append('gfs_netcdfa')

            if self.options['do_wave']:
                tarball_types.append('gfswave')

            if self.options['do_aero_fcst']:
                tarball_types.append('chem')

            if self.options['do_ocean']:
                tarball_types.extend(['ocean_6hravg', 'ocean_native'])
                if self.options.get('do_jediocnvar', False) and self.app_config.mode == 'cycled':
                    tarball_types.append('gfsocean_analysis')

            if self.options['do_ice']:
                tarball_types.extend(['ice_6hravg', 'ice_native'])

            if self.options['do_bufrsnd']:
                tarball_types.append('gfs_downstream')

            if self.app_config.mode == 'cycled':
                tarball_types.append('gfs_restarta')

        elif self.run == 'gdas':
            tarball_types = ['gdas']

            if self.options['do_ice']:
                tarball_types.append('gdasice')

            if self.options['do_ocean']:
                tarball_types.append('gdasocean')
                if self.options['do_jediocnvar'] and self.app_config.mode == 'cycled':
                    tarball_types.append('gdasocean_analysis')

            if self.options['do_wave']:
                tarball_types.append('gdaswave')

            if self.app_config.mode == 'cycled':
                tarball_types.append('gdas_restarta')
                tarball_types.append('gdas_restartb')
                if self.options['do_ice']:
                    tarball_types.append('gdasice_restart')
                if self.options['do_ocean']:
                    tarball_types.append('gdasocean_restart')
                if self.options['do_wave']:
                    tarball_types.append('gdaswave_restart')
        else:
            tarball_types = [self.run]

        return tarball_types
