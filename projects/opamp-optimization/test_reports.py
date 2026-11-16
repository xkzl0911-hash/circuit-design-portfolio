"""Regression tests for automatic report lifecycle and report numbering."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import report_generator as rg
from optimizer import OptimizationRun,ROOT

def state_fixture(folder):
    return dict(status='completed',folder=str(folder),total=1,current_trial=1,startup=1,seed=42,elapsed_s=1,
        targets={},history=[dict(trial=1,status='simulation_error',error='test fixture',feasible=False)],
        best=None,baseline=None)

class ReportTests(unittest.TestCase):
    def test_rejects_partial_run_and_inconsistent_feasibility(self):
        s=state_fixture(ROOT);s['status']='stopped'
        with self.assertRaises(ValueError): rg.analyze(s)
        s=state_fixture(ROOT);s['total']=2
        with self.assertRaises(ValueError): rg.analyze(s)
        s=state_fixture(ROOT)
        s['history']=[dict(trial=1,status='measured',score=1.,feasible=True,checks=[dict(status='fail')])]
        with self.assertRaises(ValueError): rg.analyze(s)
    def test_no_measurements_does_not_invent_best_result(self):
        a=rg.analyze(state_fixture(ROOT))
        self.assertIsNone(a['best']);self.assertEqual(len(a['passing']),0);self.assertEqual(len(a['errors']),1)
    def test_signature_ignores_report_metadata_but_not_results(self):
        s=state_fixture(ROOT);t=copy.deepcopy(s);t.update(report_status='ready',stage='Finished')
        self.assertEqual(rg.run_signature(s),rg.run_signature(t))
        t['history'][0]['error']='different result'
        self.assertNotEqual(rg.run_signature(s),rg.run_signature(t))
    def test_numbering_duplicate_and_project_boundary(self):
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='_report_test_') as temp:
            temp=Path(temp);profile=dict(circuit_id='fixture',title='fixture',report_directory=str((temp/'reports').relative_to(ROOT)))
            def fake_pdf(path,*args): Path(path).write_bytes(b'%PDF-test-fixture')
            with patch.object(rg,'charts',return_value={}),patch.object(rg,'build_pdf',side_effect=fake_pdf):
                run=temp/'run1';run.mkdir();session=run/'session.json';rg.write_json(session,state_fixture(run))
                first=rg.generate_report(session,profile);again=rg.generate_report(session,profile)
                self.assertEqual(first['ordinal'],1);self.assertEqual(again['pdf'],first['pdf']);self.assertTrue(again['existing'])
                s=rg.read_json(session);s['report_status']='ready';rg.write_json(session,s)
                self.assertEqual(rg.generate_report(session,profile)['ordinal'],1)
                run2=temp/'run2';run2.mkdir();rg.write_json(run2/'session.json',state_fixture(run2))
                second=rg.generate_report(run2/'session.json',profile)
                self.assertEqual(second['ordinal'],2);self.assertNotEqual(first['pdf'],second['pdf'])
            self.assertFalse((temp/'reports'/'.report_generation.lock').exists())
        with self.assertRaises(ValueError): rg.inside(ROOT.parent/'outside.pdf')
    def worker_fixture(self,folder):
        run=OptimizationRun(1,1,42);run.folder=folder
        return run
    def test_worker_auto_reports_completed_run_and_preserves_failure(self):
        class FakeEvaluator:
            def __init__(self,*args,**kwargs): pass
            def evaluate(self,params,folder):
                metrics=dict(power_mw=1.,low_frequency_gain_db=65.,f_unity_hz=2e6,
                    phase_margin_unity_feedback_estimate_deg=70.,f_3db_open_loop_hz=2e4,
                    slew_rate_rise_v_per_us=20.,slew_rate_fall_v_per_us=20.)
                return dict(params=params,metrics=metrics,elapsed_s=1.,folder=str(folder),score=.5,
                    feasible=True,fom=1e8,checks=[dict(name='Power',violation=-1,status='pass')])
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='_report_hook_') as temp:
            temp=Path(temp)
            with patch('optimizer.Evaluator',FakeEvaluator),patch.object(rg,'generate_report',return_value=dict(pdf='test.pdf',folder='test',ordinal=1)) as mocked:
                run=self.worker_fixture(temp/'completed');run.run()
                mocked.assert_called_once();self.assertEqual(run.status,'completed');self.assertEqual(run.report_status,'ready')
                self.assertTrue((run.folder/'source_snapshot'/'optimizer.py').is_file())
                self.assertTrue((run.folder/'environment.json').is_file())
            with patch('optimizer.Evaluator',FakeEvaluator),patch.object(rg,'generate_report',side_effect=RuntimeError('expected test failure')):
                run=self.worker_fixture(temp/'report_failure');run.run()
                self.assertEqual(run.status,'completed');self.assertEqual(run.report_status,'failed')
                self.assertTrue((run.folder/'session.json').is_file());self.assertTrue((run.folder/'report_error.txt').is_file())
            with patch('optimizer.Evaluator',FakeEvaluator),patch.object(rg,'generate_report') as mocked:
                run=self.worker_fixture(temp/'stopped');run.stop.set();run.run()
                mocked.assert_not_called();self.assertEqual(run.status,'stopped')

if __name__=='__main__': unittest.main(verbosity=2)
