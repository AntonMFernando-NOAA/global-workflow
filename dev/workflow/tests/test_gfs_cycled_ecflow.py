from datetime import datetime, timedelta

from ecflow.ecflow_tasks import ref
from ecflow.gfs_cycled_ecflow import GFSCycledEcFlowSuite

FIRST = datetime(2021, 12, 20, 12)
SECOND = datetime(2021, 12, 20, 18)
THIRD = datetime(2021, 12, 21, 0)


def _make_suite(interval_gfs_hours=6):
    """Build a suite object without running the full app configuration."""
    task_names = {'gfs': ['prep', 'fcst', 'atmos_prod'],
                  'enkfgfs': ['eobs', 'cleanup'],
                  'gdas': ['prep', 'stage_ic', 'fcst', 'waveinit', 'atmos_prod', 'arch_vrfy'],
                  'enkfgdas': ['stage_ic', 'eobs', 'efcs', 'epos']}
    suite = object.__new__(GFSCycledEcFlowSuite)
    suite._base = {'EDATE': THIRD,
                   'SDATE_GFS': SECOND,
                   'interval_gfs': timedelta(hours=interval_gfs_hours)}
    suite._app_config = type('AppConfig', (), {'task_names': task_names})()
    suite._sdate = FIRST
    suite._assim_freq = timedelta(hours=6)
    suite._runs = [run for run in ('gdas', 'enkfgdas', 'gfs', 'enkfgfs') if run in task_names]
    suite._cycles = suite._get_cycles()
    suite._planned = {}
    suite._skipped = {}
    suite._run = 'gdas'
    suite.pslot = 'exp'
    return suite


class TestGFSCycledEcFlowSuite:

    '''
    GFSCycledEcFlowSuite tests

    Only the cycle and trigger logic is tested; the full suite needs an experiment.
    '''

    def test_get_cycles(self):
        suite = _make_suite()

        assert list(suite._cycles) == [FIRST, SECOND, THIRD]
        assert suite._cycles[FIRST] == ['gdas', 'enkfgdas']
        assert suite._cycles[SECOND] == ['gdas', 'enkfgdas', 'gfs', 'enkfgfs']
        assert suite._cycles[THIRD] == ['gdas', 'enkfgdas', 'gfs', 'enkfgfs']

    def test_get_cycles_gfs_every_other_cycle(self):
        suite = _make_suite(interval_gfs_hours=12)

        assert suite._cycles[SECOND] == ['gdas', 'enkfgdas', 'gfs', 'enkfgfs']
        assert suite._cycles[THIRD] == ['gdas', 'enkfgdas']

    def test_planned_tasks_first_cycle(self):
        suite = _make_suite()

        assert suite._planned_tasks(FIRST, 'gdas') == ['stage_ic', 'fcst', 'waveinit', 'atmos_prod']
        assert suite._planned_tasks(FIRST, 'enkfgdas') == ['stage_ic', 'efcs', 'epos']

    def test_planned_tasks_later_cycle(self):
        suite = _make_suite()

        assert suite._planned_tasks(SECOND, 'gdas') == ['prep', 'fcst', 'waveinit', 'atmos_prod', 'arch_vrfy']
        assert suite._planned_tasks(SECOND, 'enkfgdas') == ['eobs', 'efcs', 'epos']

    def test_planned_tasks_run_not_in_cycle(self):
        suite = _make_suite()

        assert suite._planned_tasks(FIRST, 'gfs') == []

    def test_planned_tasks_enkfgfs_has_no_stage_ic(self):
        suite = _make_suite()
        suite._app_config.task_names['enkfgfs'].append('stage_ic')

        assert 'stage_ic' not in suite._planned_tasks(SECOND, 'enkfgfs')

    def test_resolve_trigger_drops_tasks_missing_in_the_cycle(self):
        suite = _make_suite()

        trigger = 'stage_ic == complete and waveinit == complete and prep == complete'

        assert suite._resolve_trigger(trigger, FIRST) == 'stage_ic == complete and waveinit == complete'
        assert suite._resolve_trigger(trigger, SECOND) == 'waveinit == complete and prep == complete'

    def test_resolve_trigger_previous_cycle(self):
        suite = _make_suite()

        trigger = f"prep == complete and {ref('atmos_prod', 'gdas', -6)} == complete"
        resolved = suite._resolve_trigger(trigger, SECOND)

        assert resolved == 'prep == complete and /exp/2021122012/gdas/products/atmos_prod == complete'

    def test_resolve_trigger_missing_cycle(self):
        suite = _make_suite()

        trigger = f"{ref('atmos_prod', 'gdas', -6)} == complete"

        assert suite._resolve_trigger(trigger, FIRST) == ''

    def test_resolve_trigger_other_run_and_child(self):
        suite = _make_suite()

        trigger = f"{ref('fcst', 'gdas')} == complete and {ref('efcs/mem001', 'enkfgdas')} == complete"
        resolved = suite._resolve_trigger(trigger, SECOND)

        assert resolved == ('/exp/2021122018/gdas/fcst == complete and '
                            '/exp/2021122018/enkfgdas/efcs/mem001 == complete')

    def test_waveinit_family_only_init_in_first_cycle(self):
        suite = _make_suite()

        assert suite._family_of('waveinit', '2021122012') == 'init'
        assert suite._family_of('waveinit', '2021122018') == 'analysis'
        assert suite._family_of('waveinit', '2021122100') == 'analysis'

    def test_metp_family_is_stats(self):
        suite = _make_suite()

        assert suite._family_of('metp', '2021122018') == 'stats'

    def test_resolve_trigger_waveinit_path_follows_cycle(self):
        suite = _make_suite()

        trigger = f"{ref('waveinit', 'gdas', -6)} == complete"

        assert suite._resolve_trigger(trigger, SECOND) == '/exp/2021122012/gdas/init/waveinit == complete'
        assert suite._resolve_trigger(trigger, THIRD) == '/exp/2021122018/gdas/analysis/waveinit == complete'
