#!/usr/bin/env python3
"""Print the settings of a GFSv17 ecflow realtime config file as section.key=value lines.

Usage: gfsv17_ecflow_rt_config.py CONFIG_FILE HOMEGLOBAL
"""
import os
import sys

home = sys.argv[2]
sys.path.insert(0, os.path.join(home, 'sorc', 'wxflow', 'src'))

from wxflow import AttrDict, parse_j2yaml  # noqa: E402

cfg = parse_j2yaml(path=sys.argv[1], data=AttrDict(HOMEglobal=home))
for section in ('experiment', 'ecflow'):
    for key, value in (cfg.get(section) or {}).items():
        if value is not None:
            print(f"{section}.{key}={value}")
