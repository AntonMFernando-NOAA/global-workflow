#!/usr/bin/env python3

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
