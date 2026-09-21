"""
Factory for creating ecFlow suite generators.

This module provides a factory that creates appropriate ecFlow suites
for different types of workflows (GFS, GEFS, SFS, GCAFS).

The ``gfs_forecast-only`` key maps to ``C48ATMEcFlowSuite``, the
concrete subclass of the generic ``GFSForecastOnlyEcFlowSuite`` base.
Additional GFS forecast-only cases register their own subclasses here.
"""
from wxflow import Factory
from ecflow.c48_atm_ecflow_suite import C48ATMEcFlowSuite

# Create a factory for ecFlow suite objects
ecflow_suite_factory = Factory('ecFlowSuite')

# Register ecFlow suites for different workflow types
# ecflow_suite_factory.register('gfs_cycled', GFSCycledEcFlowSuite)
ecflow_suite_factory.register('gfs_forecast-only', C48ATMEcFlowSuite)
# ecflow_suite_factory.register('gefs_forecast-only', GEFSEcFlowSuite)
# ecflow_suite_factory.register('sfs_forecast-only', SFSEcFlowSuite)
# ecflow_suite_factory.register('gcafs_cycled', GCAFSCycledEcFlowSuite)
# ecflow_suite_factory.register('gcafs_forecast-only', GCAFSForecastOnlyEcFlowSuite)
