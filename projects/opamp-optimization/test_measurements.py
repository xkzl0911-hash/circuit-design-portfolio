import copy,struct,tempfile,unittest
from pathlib import Path
import numpy as np
from circuit_engine import contiguous_range,slew_value,assess,ROOT
from measure_baseline import read_raw
from optimizer import export_candidate

class MeasurementTests(unittest.TestCase):
    def test_range_does_not_bridge_a_failed_interval(self):
        self.assertEqual(contiguous_range([0,1,2,3,4],[1,1,0,1,1],1),[0.,1.])
        self.assertIsNone(contiguous_range([0,1,2],[1,0,1],1))
    def test_known_rising_and_falling_slew(self):
        t=np.linspace(0,1e-6,1001)
        self.assertAlmostEqual(slew_value(t,t*1e6,.2,.8,0,1e-6),1.,places=8)
        self.assertAlmostEqual(slew_value(t,1-t*1e6,.2,.8,0,1e-6,False),1.,places=8)
        self.assertIsNone(slew_value(t,t*0,.2,.8,0,1e-6))
    def test_binary_formats_do_not_mix_float_double_complex(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            for flags,fmt,values,expected in [
                ('real','<df',(1.,2.),(1.,2.)),
                ('real double','<dd',(1.,2.),(1.,2.)),
                ('complex','<dddd',(1.,0.,2.,3.),(1+0j,2+3j))]:
                p=Path(d)/'test.raw'
                h=f'Title: test\nFlags: {flags}\nNo. Variables: 2\nNo. Points: 1\nVariables:\n\t0\tx\tvoltage\n\t1\ty\tvoltage\nBinary:\n'
                p.write_bytes(h.encode('utf-16le')+struct.pack(fmt,*values))
                raw=read_raw(p);self.assertEqual((raw['x'][0],raw['y'][0]),expected)
    def test_strict_gain_and_margin_and_missing_sr_do_not_pass(self):
        import json
        targets=json.loads((ROOT/'targets.json').read_text(encoding='utf-8'))
        m=dict(power_mw=1,low_frequency_gain_db=61,f_unity_hz=2e6,
               phase_margin_unity_feedback_estimate_deg=61,f_3db_open_loop_hz=10001,
               slew_rate_rise_v_per_us=11,slew_rate_fall_v_per_us=11,
               dc_voltages_v={'vout':1.65},icmr_v=[.5,2.5],ocmr_v=[.5,2.5],
               saturation_headroom_v={f'M{i}':.1 for i in range(1,11)},
               all_falling_unity_crossings=[{}],slew_settled=True)
        self.assertTrue(assess(m,targets)['feasible'])
        self.assertLess(assess(m,targets)['score'],1)
        for key,value in [('low_frequency_gain_db',60),('phase_margin_unity_feedback_estimate_deg',60),('slew_rate_rise_v_per_us',None),('ocmr_v',None)]:
            x=copy.deepcopy(m);x[key]=value
            self.assertFalse(assess(x,targets)['feasible'],key)
            self.assertGreaterEqual(assess(x,targets)['score'],1)
    def test_candidate_export_updates_values_and_keeps_wiring(self):
        source=ROOT/'two_stage_cmos_3v3_pdk.asc'
        before=source.read_text(encoding='ascii')
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            p=Path(d)/'candidate.asc'
            export_candidate(source,{'W12':55e-6,'W34':39e-6},p,False)
            after=p.read_text(encoding='ascii')
            self.assertIn('W12=5.5e-05',after)
            self.assertIn('W34=3.9e-05',after)
            self.assertEqual([x for x in before.splitlines() if x.startswith('WIRE ')],[x for x in after.splitlines() if x.startswith('WIRE ')])

if __name__=='__main__': unittest.main(verbosity=2)
