from ecflowgw.ecflow_suite import EcFlowSuite
from ecflowgw.forecast_only_ecflow import ForecastOnlyEcFlowSuite


class TestEcFlowSuite:

    '''
    EcFlowSuite tests
    '''

    def test_memory_to_mb(self):
        assert EcFlowSuite._memory_to_mb('96GB') == 96 * 1024
        assert EcFlowSuite._memory_to_mb('10G') == 10 * 1024
        assert EcFlowSuite._memory_to_mb('4096M') == 4096
        assert EcFlowSuite._memory_to_mb('2TB') == 2 * 1024 * 1024
        assert EcFlowSuite._memory_to_mb('512') == 512

    def test_memory_to_mb_ignores_options(self):
        assert EcFlowSuite._memory_to_mb('24GB:prepost=true') == 24 * 1024

    def test_memory_to_mb_unparsable(self):
        assert EcFlowSuite._memory_to_mb('lots') is None


class TestLogNames:

    '''
    Job log names of the ecFlow tasks
    '''

    def test_add_log_names(self):
        lines = ['family gefs',
                 '  family init',
                 '    task stage_ic',
                 '  endfamily',
                 '  family atmos_prod',
                 '    family mem001',
                 '      task f000_f006',
                 '        edit FHR_LIST \'0,6\'',
                 '    endfamily',
                 '  endfamily',
                 'endfamily']
        named = ForecastOnlyEcFlowSuite._add_log_names(lines)
        assert "      edit LOG_NAME 'gefs_stage_ic'" in named
        assert "        edit LOG_NAME 'gefs_atmos_prod_mem001_f000_f006'" in named
        assert len(named) == len(lines) + 2
