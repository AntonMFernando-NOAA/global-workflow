from ecflow.ecflow_suite import EcFlowSuite


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
