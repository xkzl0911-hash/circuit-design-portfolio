"""Optuna worker and durable session records for the local live dashboard."""
import argparse,csv,json,math,queue,re,threading,time,traceback,uuid,shutil,platform,sys
from importlib.metadata import version,PackageNotFoundError
from datetime import datetime
from pathlib import Path
import optuna
from circuit_engine import Evaluator,DEFAULT_PARAMS,ROOT,Cancelled,InvalidDesign
from overnight_support import fully_passing,SleepGuard

BOUNDS={
 'W12_um':[5,100], 'W5_um':[5,100], 'W6_um':[5,100],
 'W7_um':[5,100], 'W8_um':[5,100], 'W9_um':[5,100], 'W10_um':[5,100],
 'Rz_ohm':[10,10000], 'Cc_pF':[2.01,20]
}
def atomic_json(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False,ensure_ascii=False),encoding='utf-8')
    temp.replace(path)

def sample(trial):
    values={key:trial.suggest_float(key,*limits,log=True) for key,limits in BOUNDS.items()}
    return {**{key[:-3]:value*1e-6 for key,value in values.items() if key.endswith('_um')},
            'W34':40e-6,'RZERO':values['Rz_ohm'],'CCOMP':values['Cc_pF']*1e-12}

def export_candidate(source,params,destination,feasible):
    text=source.read_text(encoding='ascii')
    for key,value in params.items():
        # Only concrete .param definitions match, not MOS W={...} references.
        text,n=re.subn(r'(?<![\w])'+key+r'=(\{[^}]*\}|[^\s]+)',key+'='+format(value,'.12g'),text)
        if n!=1: raise ValueError(f'Cannot export parameter {key}')
    text=text.replace('STARTING SIZES, NOT OPTIMIZED.','BEST CANDIDATE; '+('SCREENING TARGETS PASS.' if feasible else 'SOME TARGETS STILL FAIL.'))
    text+='\nTEXT 96 1240 Left 2 ;See best.json and trial logs for measured results and numerical assumptions.\n'
    destination.write_text(text,encoding='ascii')

class OptimizationRun:
    def __init__(self,trials=100,startup=20,seed=42,events=None,mode='fixed',prevent_sleep=True):
        if mode not in ('fixed','until_pass'):raise ValueError('Unknown run mode.')
        if mode=='fixed' and not 1<=int(trials)<=10000: raise ValueError('Trials must be 1..10000.')
        if not 1<=int(startup)<=10000:raise ValueError('Startup must be 1..10000.')
        if mode=='fixed' and int(startup)>int(trials):raise ValueError('Startup must be 1..trial count.')
        self.mode=mode;self.total=int(trials) if mode=='fixed' else None
        self.startup=int(startup);self.seed=int(seed);self.prevent_sleep=bool(prevent_sleep)
        self.completion_reason=None;self.success_trial=None
        self.events=events if events is not None else queue.Queue()
        self.stop=threading.Event();self.paused=threading.Event()
        self.folder=ROOT/'runs'/('opt_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:4])
        self.history=[];self.best=None;self.baseline=None;self.current_trial=0
        self.stage='Preparing';self.status='running';self.started=time.monotonic();self.complete_count=0
        self.targets=json.loads((ROOT/'targets.json').read_text(encoding='utf-8'))
        self.thread=None
        self.report=None;self.report_status='not_started';self.report_error=None
    def emit(self,kind,**data):
        self.events.put(dict(type=kind,**data))
    def checkpoint(self):
        if self.stop.is_set(): raise Cancelled('Stopped by user')
        while self.paused.is_set():
            if self.stop.wait(.15): raise Cancelled('Stopped by user')
    def stage_event(self,stage):
        self.checkpoint();self.stage=stage
        self.emit('stage',stage=stage,trial=self.current_trial,phase=self.phase)
    @property
    def phase(self):
        return 'STARTUP / exploration' if self.complete_count<self.startup else 'TPE / adaptive search'
    def state(self):
        total=len(self.history) if self.mode=='until_pass' and self.status=='completed' else self.total
        return dict(schema=2,folder=str(self.folder),total=total,startup=self.startup,seed=self.seed,
            mode=self.mode,requested_trials=self.total,completion_reason=self.completion_reason,
            success_trial=self.success_trial,prevent_sleep=self.prevent_sleep,
            current_trial=self.current_trial,stage=self.stage,status=self.status,phase=self.phase,
            elapsed_s=time.monotonic()-self.started,history=self.history,best=self.best,baseline=self.baseline,
            targets=self.targets,search_bounds=BOUNDS,completed_simulations=self.complete_count,
            report=self.report,report_status=self.report_status,report_error=self.report_error)
    def save(self):
        atomic_json(self.folder/'session.json',self.state())
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True,name='LTspice-optimizer')
        self.thread.start()
    def run(self):
        self.folder.mkdir(parents=True,exist_ok=False)
        atomic_json(self.folder/'targets.json',self.targets)
        # Snapshot the actual code and dependency versions before the run.
        snapshot=self.folder/'source_snapshot';snapshot.mkdir()
        for name in ('optimizer.py','overnight_support.py','live_dashboard.py','circuit_engine.py','measure_baseline.py','build_schematic.py','targets.json','report_profile.json','report_generator.py','two_stage_cmos_3v3_pdk.asc'):
            source=ROOT/name
            if source.is_file(): shutil.copy2(source,snapshot/name)
        packages={}
        for name in ('optuna','numpy','matplotlib','reportlab'):
            try: packages[name]=version(name)
            except PackageNotFoundError: packages[name]='not installed'
        atomic_json(self.folder/'environment.json',dict(python=sys.version,platform=platform.platform(),packages=packages))
        self.emit('started',folder=str(self.folder),total=self.total,startup=self.startup)
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        storage=None;guard=SleepGuard(self.prevent_sleep)
        try:
            if not guard.acquire():self.emit('error',message='Automatic sleep prevention failed; check Windows power settings.')
            engine=Evaluator(self.targets,self.stage_event,self.checkpoint)
            storage=optuna.storages.RDBStorage(url='sqlite:///'+str(self.folder/'study.sqlite3'))
            study=optuna.create_study(direction='minimize',
                sampler=optuna.samplers.TPESampler(seed=self.seed,n_startup_trials=self.startup),
                storage=storage,study_name='opamp')
            # Trial 1 is an actual baseline simulation, never synthetic chart data.
            study.enqueue_trial({**{key+'_um':DEFAULT_PARAMS[key]*1e6 for key in ('W12','W5','W6','W7','W8','W9','W10')},
                                 'Rz_ohm':DEFAULT_PARAMS['RZERO'],'Cc_pF':DEFAULT_PARAMS['CCOMP']*1e12})
            index=0
            while self.total is None or index<self.total:
                self.checkpoint();self.current_trial=index+1
                trial=study.ask();params=sample(trial);phase=self.phase
                self.emit('trial_started',trial=index+1,phase=phase,params=params)
                try:
                    result=engine.evaluate(params,self.folder/'trials'/f'{index+1:04d}')
                    result.update(trial=index+1,phase=phase,status='measured')
                    trial.set_user_attr('feasible',result['feasible'])
                    trial.set_user_attr('constraints',[row['violation'] for row in result['checks']])
                    study.tell(trial,result['score']);self.complete_count+=1
                    if self.baseline is None: self.baseline=result
                    if self.best is None or result['score']<self.best['score']:
                        self.best=result
                        atomic_json(self.folder/'best.json',result)
                        export_candidate(ROOT/'two_stage_cmos_3v3_pdk.asc',result['params'],self.folder/'best_candidate.asc',result['feasible'])
                except Cancelled:
                    study.tell(trial,state=optuna.trial.TrialState.PRUNED)
                    raise
                except Exception as error:
                    study.tell(trial,state=optuna.trial.TrialState.FAIL)
                    result=dict(trial=index+1,phase=phase,status='simulation_error',error=str(error),params=params,feasible=False)
                    (self.folder/f'error_{index+1:04d}.txt').write_text(traceback.format_exc(),encoding='utf-8')
                self.history.append(result)
                with (self.folder/'trials.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(result,allow_nan=False)+'\n')
                self.save()
                self.emit('result',result=result,state=self.state())
                if self.mode=='until_pass' and fully_passing(result):
                    self.success_trial=result['trial'];self.completion_reason='targets_met'
                    atomic_json(self.folder/'success.json',result)
                    export_candidate(ROOT/'two_stage_cmos_3v3_pdk.asc',result['params'],self.folder/'successful_candidate.asc',True)
                    break
                index+=1
            if self.completion_reason is None:self.completion_reason='trial_limit'
            self.status='completed';self.stage='Finished'
        except Cancelled:
            self.status='stopped';self.completion_reason='user_stop';self.stage='Stopped; recorded results kept'
        except Exception as error:
            self.status='error';self.completion_reason='error';self.stage=str(error)
            (self.folder/'fatal_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            self.emit('error',message=str(error))
        finally:
            if storage is not None:
                storage.remove_session()
                storage.engine.dispose()
            self.save()
            measured=[r for r in self.history if r['status']=='measured']
            with (self.folder/'trials.csv').open('w',newline='',encoding='utf-8-sig') as stream:
                writer=csv.writer(stream)
                writer.writerow(['trial','score_lower_better','all_screening_targets_pass','fom_dB_Hz_per_mW','power_mW','gain_dB','unity_Hz','PM_deg','f3dB_Hz','SR_rise_V_us','SR_fall_V_us'])
                for r in measured:
                    m=r['metrics'];writer.writerow([r['trial'],r['score'],r['feasible'],r['fom'],m['power_mw'],m['low_frequency_gain_db'],m['f_unity_hz'],m['phase_margin_unity_feedback_estimate_deg'],m['f_3db_open_loop_hz'],m['slew_rate_rise_v_per_us'],m['slew_rate_fall_v_per_us']])
            if self.status=='completed' and (self.mode=='until_pass' or len(self.history)==self.total):
                self.stage='Generating PDF report';self.report_status='generating';self.save()
                self.emit('report_started',folder=str(self.folder))
                try:
                    from report_generator import generate_report
                    self.report=generate_report(self.folder/'session.json')
                    self.report_status='ready';self.stage='Finished; PDF report saved'
                    self.emit('report_ready',report=self.report)
                except Exception as report_error:
                    self.report_status='failed';self.report_error=str(report_error)
                    self.stage='Simulation finished; report generation failed'
                    (self.folder/'report_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
                    self.emit('error',message='Report generation failed: '+str(report_error))
                self.save()
            guard.release()
            self.emit('finished',state=self.state())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials',type=int,default=100);parser.add_argument('--startup',type=int,default=20)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--mode',choices=('fixed','until_pass'),default='fixed')
    parser.add_argument('--allow-sleep',action='store_true',help='Do not request Windows system wakefulness.')
    args=parser.parse_args()
    run=OptimizationRun(args.trials,args.startup if args.mode=='until_pass' else min(args.startup,args.trials),
                        args.seed,mode=args.mode,prevent_sleep=not args.allow_sleep);run.start()
    while run.thread.is_alive() or not run.events.empty():
        try:
            event=run.events.get(timeout=.2)
            if event['type'] in ('stage','finished','error'): print(json.dumps(event if event['type']!='finished' else dict(type='finished',folder=str(run.folder),status=run.status),ensure_ascii=False),flush=True)
        except queue.Empty: pass
    print(str(run.folder))
    if run.status=='error': raise SystemExit(1)

if __name__=='__main__': main()
