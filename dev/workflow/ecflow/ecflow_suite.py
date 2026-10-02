#!/usr/bin/env python3

import os
from pathlib import Path
from typing import Dict
from applications.applications import AppConfig
from workflow_suite import WorkflowSuite
from abc import ABC
from logging import getLogger

logger = getLogger(__name__.split('.')[-1])


class EcFlowSuite(WorkflowSuite, ABC):

    def __init__(self, app_config: AppConfig, ecflow_config: Dict) -> None:

        super().__init__(app_config, ecflow_config)

    @staticmethod
    def index_ecf_sources(src_dir: Path) -> Dict[str, str]:
        """Map each source ``.ecf`` name to its path under ``src_dir``.

        The repo ``dev/ecflow/scripts`` tree is nested by category (for
        example ``product/atmos/atmos_prod.ecf``), so scripts are located by
        name instead of by a fixed path.

        Parameters
        ----------
        src_dir : Path
            Root of the repo ``.ecf`` source tree.

        Returns
        -------
        Dict[str, str]
            ``{name: relative path without the .ecf suffix}``.

        Raises
        ------
        ValueError
            If two source scripts share the same name.
        """
        index: Dict[str, str] = {}
        for src in sorted(Path(src_dir).rglob('*.ecf')):
            name = src.stem
            if name in index:
                raise ValueError(f'Duplicate .ecf source name "{name}" under {src_dir}')
            index[name] = src.relative_to(src_dir).with_suffix('').as_posix()
        return index

    def _sbatch_header(self, resources: Dict, task_name: str) -> str:
        """Generate ``#SBATCH`` directive lines for a task.

        Parameters
        ----------
        resources : dict
            Resource dict from ``get_resource()``.
        task_name : str
            Used for the ``--job-name``.

        Returns
        -------
        str
            Multi-line string of ``#SBATCH`` directives (no shebang).
        """
        run = self._run
        cyc = self._base['SDATE_GFS'].strftime('%H')
        account = resources.get('account', '')
        if not account or account == 'UNDEFINED':
            account = os.environ.get('HPC_ACCOUNT', 'fv3-cpu')

        lines = [
            f"#SBATCH --job-name={run}_{task_name}_{cyc}",
            f"#SBATCH --account={account}",
            f"#SBATCH --partition={resources['partition']}",
            f"#SBATCH --time={resources['walltime']}",
            f"#SBATCH --nodes={resources['nodes']}",
            f"#SBATCH --ntasks-per-node={resources['ppn']}",
            f"#SBATCH --cpus-per-task={resources['threads']}",
            "#SBATCH --output=%ECF_JOBOUT%",
        ]
        if resources.get('native'):
            lines.append(f"#SBATCH {resources['native']}")
        return '\n'.join(lines)

    @staticmethod
    def _insert_sbatch(content: str, sbatch: str) -> str:
        """Return script *content* with *sbatch* inserted after the shebang."""
        shebang = '#!/bin/bash\n'
        if content.startswith(shebang):
            content = content[len(shebang):]
        return shebang + sbatch + '\n' + content
