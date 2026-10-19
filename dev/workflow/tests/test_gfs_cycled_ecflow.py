from datetime import datetime, timedelta

import pytest

from ecflowgw.ecflow_tasks import ref
from ecflowgw.gfs_cycled_ecflow import GFSCycledEcFlowSuite

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
    suite._families = suite._group_cycles()
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

        assert suite._resolve_trigger(trigger, [FIRST]) == 'stage_ic == complete and waveinit == complete'
        assert suite._resolve_trigger(trigger, [SECOND]) == 'waveinit == complete and prep == complete'

    def test_resolve_trigger_previous_cycle(self):
        suite = _make_suite()

        trigger = f"prep == complete and {ref('atmos_prod', 'gdas', -6)} == complete"
        resolved = suite._resolve_trigger(trigger, [SECOND])

        assert resolved == 'prep == complete and /exp/2021122012/gdas/products/atmos_prod == complete'

    def test_resolve_trigger_missing_cycle(self):
        suite = _make_suite()

        trigger = f"{ref('atmos_prod', 'gdas', -6)} == complete"

        assert suite._resolve_trigger(trigger, [FIRST]) == ''

    def test_resolve_trigger_other_run_and_child(self):
        suite = _make_suite()

        trigger = f"{ref('fcst', 'gdas')} == complete and {ref('efcs/mem001', 'enkfgdas')} == complete"
        resolved = suite._resolve_trigger(trigger, [SECOND])

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

        assert suite._resolve_trigger(trigger, [SECOND]) == '/exp/2021122012/gdas/init/waveinit == complete'
        assert suite._resolve_trigger(trigger, [THIRD]) == '/exp/2021122018/gdas/analysis/waveinit == complete'

    def test_family_names(self):
        suite = _make_suite()

        assert [suite._family_name(cycle) for cycle in suite._cycles] == ['2021122012', '2021122018', '2021122100']

    def test_cycles_of_one_hour_share_a_family(self):
        suite = _make_suite()
        suite._base['EDATE'] = datetime(2021, 12, 22, 0)
        suite._cycles = suite._get_cycles()
        suite._families = suite._group_cycles()

        assert list(suite._families) == ['2021122012', '2021122018', '2021122100',
                                         '2021122106', '2021122112']
        assert suite._families['2021122018'] == [SECOND, datetime(2021, 12, 21, 18)]
        assert suite._families['2021122100'] == [THIRD, datetime(2021, 12, 22, 0)]

    def test_cycles_of_one_hour_with_different_runs(self):
        suite = _make_suite(interval_gfs_hours=24)
        suite._base['SDATE_GFS'] = datetime(2021, 12, 21, 18)
        suite._base['EDATE'] = datetime(2021, 12, 22, 18)
        suite._cycles = suite._get_cycles()

        with pytest.raises(ValueError):
            suite._group_cycles()

    def test_begin_condition(self):
        suite = _make_suite()

        assert suite._begin_condition(FIRST) is None
        assert suite._begin_condition(SECOND) == ('(/exp/2021122012/gdas/fcst == active or '
                                                  '/exp/2021122012/gdas/fcst == complete)')
        assert suite._begin_condition(THIRD) == ('(/exp/2021122018/gdas/fcst == active or '
                                                 '/exp/2021122018/gdas/fcst == complete)')

    def test_begin_condition_waits_for_gfs_of_two_cycles_ago(self):
        suite = _make_suite()
        suite._base['EDATE'] = datetime(2021, 12, 21, 6)
        suite._cycles = suite._get_cycles()
        suite._families = suite._group_cycles()

        assert suite._begin_condition(datetime(2021, 12, 21, 6)).endswith('and /exp/2021122018/gfs/fcst != active')

    def test_combine_by_cycle_same_expression(self):
        suite = _make_suite()

        assert suite._combine_by_cycle('2021122018', {SECOND: 'a == complete', THIRD: 'a == complete'}) == 'a == complete'
        assert suite._combine_by_cycle('2021122018', {SECOND: None, THIRD: None}) == ''

    def test_combine_by_cycle_guards_with_pdy(self):
        suite = _make_suite()

        combined = suite._combine_by_cycle('2021122018', {SECOND: '/exp/2021122012/x == complete',
                                                          THIRD: '/exp/2021122012/x == complete',
                                                          datetime(2021, 12, 22, 0): None})

        assert combined == ('((/exp/2021122012/x == complete and '
                            '(/exp/2021122018:PDY == 20211220 or /exp/2021122018:PDY == 20211221)) or '
                            '/exp/2021122018:PDY == 20211222)')

    def test_next_family(self):
        suite = _make_suite()
        suite._base['EDATE'] = datetime(2021, 12, 22, 0)
        suite._cycles = suite._get_cycles()
        suite._families = suite._group_cycles()

        # half (12Z) -> first 18Z family; 18Z -> first 00Z family
        assert suite._next_family([FIRST]) == '2021122018'
        assert suite._next_family([SECOND, datetime(2021, 12, 21, 18)]) == '2021122100'
        # a full run loops the hour families; 06Z -> the regular 12Z family
        assert suite._next_family([datetime(2021, 12, 21, 6)]) == '2021122112'

    def test_next_family_none_on_last(self):
        suite = _make_suite()

        # The run ends at 00Z, so the 06Z family does not exist
        assert suite._next_family([THIRD]) is None
