"""Run-control regression tests. Evaluations/reports are mocked; no LTspice calls."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import optimizer as op
import report_generator as reports
from overnight_support import fully_passing

class FakeEvaluator:
    outcomes=[]
    def __init__(self,*args):self.index=0;self.checkpoint=args[2]
    def evaluate(self,params,folder):
        outcome=type(self).outcomes[self.index];self.index+=1
        if isinstance(outcome,Exception):raise outcome
        metrics=dict(power_mw=1.,low_frequency_gain_db=65.,f_unity_hz=2e6,
            phase_margin_unity_feedback_estimate_deg=70.,f_3db_open_loop_hz=2e4,
            slew_rate_rise_v_per_us=20.,slew_rate_fall_v_per_us=20.)
        return dict(params=params,metrics=metrics,elapsed_s=.01,folder=str(folder),
            score=.5 if outcome else 2.,feasible=outcome,fom=1e8,
            checks=[dict(name='test condition',violation=-1 if outcome else 1,status='pass' if outcome else 'fail')])

class Modes(unittest.TestCase):
    def execute(self,folder,mode,outcomes,trials=1,report_error=False):
        FakeEvaluator.outcomes=outcomes
        worker=op.OptimizationRun(trials,1,42,mode=mode,prevent_sleep=False);worker.folder=folder
        with patch.object(op,'Evaluator',FakeEvaluator),patch.object(reports,'generate_report',
            side_effect=RuntimeError('fixture report error') if report_error else None,
            return_value={'pdf':'fixture.pdf'}) as report:
            worker.run()
        return worker,report
    def test_fixed_does_not_stop_at_first_pass(self):
        with tempfile.TemporaryDirectory(dir=op.ROOT,prefix='_mode_test_') as tmp:
            worker,report=self.execute(Path(tmp)/'fixed','fixed',[True,False,True],trials=3)
            self.assertEqual(len(worker.history),3);self.assertEqual(worker.completion_reason,'trial_limit')
            self.assertEqual(worker.state()['total'],3);report.assert_called_once()
    def test_continuous_ignores_count_stops_only_on_full_pass(self):
        with tempfile.TemporaryDirectory(dir=op.ROOT,prefix='_mode_test_') as tmp:
            worker,report=self.execute(Path(tmp)/'continuous','until_pass',[False,False,True,True])
            self.assertEqual(len(worker.history),3);self.assertIsNone(worker.total)
            self.assertEqual(worker.completion_reason,'targets_met');self.assertEqual(worker.success_trial,3)
            self.assertEqual(worker.state()['total'],3);self.assertIsNone(worker.state()['requested_trials'])
            self.assertTrue((worker.folder/'success.json').is_file())
            self.assertTrue((worker.folder/'successful_candidate.asc').is_file())
            reports.analyze(worker.state());report.assert_called_once()
    def test_simulation_error_does_not_end_continuous_search(self):
        with tempfile.TemporaryDirectory(dir=op.ROOT,prefix='_mode_test_') as tmp:
            worker,_=self.execute(Path(tmp)/'error_then_pass','until_pass',[RuntimeError('fixture failure'),True])
            self.assertEqual(worker.status,'completed');self.assertEqual(len(worker.history),2)
            self.assertEqual(worker.history[0]['status'],'simulation_error')
    def test_user_stop_preserves_history_skips_report(self):
        with tempfile.TemporaryDirectory(dir=op.ROOT,prefix='_mode_test_') as tmp:
            worker,report=self.execute(Path(tmp)/'stopped','until_pass',[False,op.Cancelled('fixture stop')])
            self.assertEqual(worker.status,'stopped');self.assertEqual(len(worker.history),1)
            self.assertEqual(worker.completion_reason,'user_stop');report.assert_not_called()
            self.assertTrue((worker.folder/'session.json').is_file())
            with self.assertRaises(ValueError):reports.analyze(worker.state())
    def test_report_error_keeps_success_and_results(self):
        with tempfile.TemporaryDirectory(dir=op.ROOT,prefix='_mode_test_') as tmp:
            worker,_=self.execute(Path(tmp)/'report_failure','until_pass',[True],report_error=True)
            self.assertEqual(worker.status,'completed');self.assertEqual(worker.report_status,'failed')
            self.assertTrue((worker.folder/'success.json').is_file())
            self.assertTrue((worker.folder/'report_error.txt').is_file())
    def test_completion_needs_real_passing_checks(self):
        self.assertFalse(fully_passing(dict(status='measured',feasible=True,checks=[])))
        self.assertFalse(fully_passing(dict(status='measured',feasible=True,checks=[dict(status='fail')])))
        self.assertFalse(fully_passing(dict(status='simulation_error',feasible=True,checks=[dict(status='pass')])))
    def test_indefinite_state_and_startup_are_independent_of_count(self):
        worker=op.OptimizationRun(1,20,mode='until_pass',prevent_sleep=False)
        self.assertIsNone(worker.state()['total']);self.assertEqual(worker.startup,20)
        with self.assertRaises(ValueError):op.OptimizationRun(1,20,mode='fixed')
        with self.assertRaises(ValueError):op.OptimizationRun(mode='typo')
    def test_report_rejects_false_continuous_completion(self):
        state=dict(status='completed',total=1,mode='until_pass',completion_reason='targets_met',success_trial=1,
            history=[dict(trial=1,status='simulation_error')])
        with self.assertRaises(ValueError):reports.analyze(state)

if __name__=='__main__':unittest.main(verbosity=2)
