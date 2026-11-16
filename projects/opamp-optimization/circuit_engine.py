"""Local LTspice evaluator. Every reported metric comes from a saved simulation."""
from pathlib import Path
import csv,json,math,re,subprocess,time
import numpy as np
from measure_baseline import read_raw,measure,DEFAULT_EXE,ROOT

DEFAULT_PARAMS=dict(W12=40e-6,W34=40e-6,W5=40e-6,W6=80e-6,W7=80e-6,W8=20e-6,W9=5e-6,W10=5e-6,RZERO=1000.,CCOMP=2.2e-12)

class Cancelled(Exception): pass
class InvalidDesign(Exception): pass

def device_table(log):
    devices={}; names=[]
    for line in log.splitlines():
        if line.startswith('Name:'):
            names=line.split()[1:]
            for name in names: devices[name]={}
        elif names and re.match(r'^(Id|Vgs|Vds|Vbs|Vth|Vdsat|Gm|Gds):',line):
            field,*values=line.split()
            for name,value in zip(names,values): devices[name][field.rstrip(':').lower()]=float(value)
    return devices

def contiguous_range(x,mask,anchor=1.5):
    """Return the sampled passing interval containing the anchor, never bridge gaps."""
    x=np.asarray(x);mask=np.asarray(mask,dtype=bool)
    i=int(np.argmin(abs(x-anchor)))
    if not mask[i]: return None
    a=b=i
    while a>0 and mask[a-1]: a-=1
    while b+1<len(x) and mask[b+1]: b+=1
    return [float(x[a]),float(x[b])]

def slew_value(t,y,low,high,start,end,rising=True):
    mask=(t>=start)&(t<=end);t=t[mask];y=y[mask]
    if len(t)<3: return None
    def first_cross(level,after=-math.inf):
        for i in range(1,len(t)):
            if t[i-1]<after: continue
            if (y[i-1]<level<=y[i]) if rising else (y[i-1]>level>=y[i]):
                return float(t[i-1]+(t[i]-t[i-1])*(level-y[i-1])/(y[i]-y[i-1]))
        return None
    first=first_cross(low if rising else high)
    last=first_cross(high if rising else low,first if first is not None else math.inf)
    return (high-low)/(last-first)*1e-6 if first is not None and last is not None and last>first else None

def assess(metrics,targets):
    """Constraint violations are normalized; <=0 means pass."""
    rows=[]
    def add(name,value,target,violation,unit):
        rows.append(dict(name=name,value=value,target=target,violation=float(violation),unit=unit,status='pass' if violation<=0 else 'fail'))
    def minimum(name,value,target,unit,strict=False):
        add(name,value,target,10. if value is None or not math.isfinite(value) else (target+(1e-8*target if strict else 0)-value)/target,unit)
    p=metrics['power_mw'];add('Power',p,targets['power_max_mw'],p/targets['power_max_mw']-1,'mW')
    minimum('DC gain',metrics['low_frequency_gain_db'],targets['gain_min_db_exclusive'],'dB',True)
    minimum('Unity gain',metrics['f_unity_hz'],targets['f_unity_min_hz_exclusive'],'Hz',True)
    minimum('Phase margin',metrics['phase_margin_unity_feedback_estimate_deg'],targets['pm_min_deg_exclusive'],'deg',True)
    minimum('-3dB BW',metrics['f_3db_open_loop_hz'],targets['input_frequency_hz']*targets['f3db_multiplier_of_fin'],'Hz')
    for key,label in [('slew_rate_rise_v_per_us','SR rise'),('slew_rate_fall_v_per_us','SR fall')]:
        minimum(label,metrics.get(key),targets['sr_min_v_per_us'],'V/us')
    tol=targets.get('dc_balance_tolerance_v',0.001)
    err=abs(metrics['dc_voltages_v']['vout']-targets['desired_output_dc_v'])
    add('DC balance',err,tol,err/tol-1,'V error')
    for key,label,interval in [('icmr_v','ICMR',targets['icmr_required_interval_v']),('ocmr_v','OCMR',targets['ocmr_required_interval_v'])]:
        value=metrics.get(key)
        violation=10. if value is None else max(value[0]-interval[0],interval[1]-value[1])
        add(label,value,interval,violation,'V')
    margins=metrics.get('saturation_headroom_v',{})
    worst=min(margins.values()) if len(margins)==10 else -1.
    add('MOS saturation',worst,0.,-worst,'V headroom')
    crossings=len(metrics.get('all_falling_unity_crossings',[]))
    add('Single unity crossing',crossings,1,0. if crossings==1 else 1.,'count')
    settled=metrics.get('slew_settled',False)
    add('Step settles',bool(settled),True,0. if settled else 1.,'bool')
    feasible=all(row['status']=='pass' for row in rows)
    fom=metrics['low_frequency_gain_db']*(metrics.get('f_unity_hz') or 0)/max(metrics['power_mw'],1e-9)
    penalty=sum(min(max(0,row['violation']),1e3)**2 for row in rows)
    score=1/(1+max(fom,0)/1e8) if feasible else 1+penalty
    return dict(checks=rows,feasible=feasible,score=float(score),fom=float(fom),
                score_description='Lower is better: feasible <1, unmet constraints >=1; FoM is higher-better.')

class Evaluator:
    def __init__(self,targets=None,progress=None,checkpoint=None,exe=DEFAULT_EXE):
        self.targets=targets or json.loads((ROOT/'targets.json').read_text(encoding='utf-8'))
        self.exe=Path(exe);self.progress=progress or (lambda value:None);self.checkpoint=checkpoint or (lambda:None)
        if not self.exe.is_file(): raise FileNotFoundError(self.exe)
        schematic=ROOT/'two_stage_cmos_3v3_pdk.asc'
        self.call('-netlist',schematic)
        self.template=schematic.with_suffix('.net').read_text(encoding='utf-8',errors='replace')
        self.template=re.sub(r'(?im)^\.(op|ac|backanno|end)\b[^\n]*','',self.template)
        self.template+='\n.options numdgt=15 plotwinsize=0\n'
    def call(self,*args):
        self.checkpoint()
        p=subprocess.run([str(self.exe),*map(str,args)],cwd=ROOT,capture_output=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=40)
        if p.returncode: raise RuntimeError(f'LTspice exit={p.returncode}: {p.stderr!r}')
    def text(self,params):
        text=self.template
        values=dict(params,VSUPPLY=self.targets['supply_v'],VCM=self.targets['input_common_mode_v'],
                    LCH=self.targets['length_m'],CLOAD=self.targets['load_capacitance_f'])
        for key,value in values.items():
            text,n=re.subn(r'(?<![\w])'+key+r'=(\{[^}]*\}|[^\s]+)',key+'='+format(value,'.12g'),text)
            if n!=1: raise ValueError(f'Expected one parameter definition for {key}, found {n}')
        return text
    def simulate(self,folder,name,text,commands):
        self.progress(name)
        deck=folder/(name+'.cir')
        if deck.exists(): raise RuntimeError(f'Refusing to reuse trial output: {deck}')
        deck.write_text(text+'\n'+commands+'\n.end\n',encoding='utf-8')
        self.call('-b',deck)
        log=deck.with_suffix('.log').read_text(encoding='utf-8',errors='replace')
        if 'Total elapsed time:' not in log or re.search(r'(?im)^\s*(error|fatal)\b',log):
            raise RuntimeError(f'{name} did not complete. See {deck.with_suffix(".log")}')
        return read_raw(deck.with_suffix('.raw')),log,deck
    def balance(self,folder,params):
        p=dict(params)
        p['W34']=min(100e-6,max(5e-6,p['W7']*2*p['W5']/(2*p['W6'])))
        residual=math.inf
        for i in range(7):
            raw,_,_=self.simulate(folder,f'balance_{i+1}',self.text(p),
                f'VCLAMP VOUT 0 {self.targets["desired_output_dc_v"]}\n.op')
            ip=abs(raw['id(m6)'][0]);inn=abs(raw['id(m7)'][0])
            if min(ip,inn)<1e-12: raise InvalidDesign('Bias branch is off during DC balance.')
            residual=abs(ip-inn)/ip
            if residual<1e-6: return p
            new=p['W34']*inn/ip
            if not 5e-6<=new<=100e-6:
                raise InvalidDesign('DC-balance W3=W4 falls outside the 5..100um model/search range.')
            p['W34']=new
        if residual>2e-4: raise InvalidDesign(f'DC-balance iteration did not converge ({residual:.3g}).')
        return p
    def evaluate(self,params,folder,auto_balance=True):
        started=time.monotonic();folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
        params=dict(params)
        for key,value in params.items():
            if key.startswith('W'):
                if not 5e-6-1e-15<=value<=100e-6+1e-15: raise InvalidDesign(f'{key} outside 5..100um')
                params[key]=min(100e-6,max(5e-6,value))
        if params['CCOMP']<=self.targets['cc_minimum_exclusive_f']: raise InvalidDesign('Cc must exceed 0.2*CL.')
        p=self.balance(folder,params) if auto_balance else dict(params)
        text=self.text(p)
        ac,log,deck=self.simulate(folder,'ac',text,'.options logopinfo\n.op\n.ac dec 100 0.01 1G')
        op=read_raw(deck.with_suffix('.op.raw'))
        metrics,curve=measure(ac,op)
        devices=device_table(log)
        metrics['saturation_headroom_v']={name:abs(d['vds'])-abs(d['vdsat']) for name,d in devices.items()}
        metrics['rz_one_over_gm7_reference_ohm']=1/devices['M7']['gm'] if devices.get('M7',{}).get('gm') else None
        metrics['measurement_notes']=[
            'TT, 25C, 3.3V, CL=10pF. VIN2=plus, VIN1=minus.',
            'PM is an estimate for unity negative feedback, not all closed-loop gains.',
            'SR is the 20%-80% average slope of a unity-follower 1V<->2V step.',
            'ICMR: output servo at 1.65V; small DC output perturbation estimates gain.',
            'OCMR: output servo sweep at input common-mode 1.65V; local DC gain >=60dB.',
            'Ranges are sampled in 0.05V steps. Servo error <=1mV, |input difference|<=10mV.',
            'DC balance tolerance=1mV is an engineering screening assumption; ideal target is zero.',
            'MOS saturation uses rounded Vdsat values from the model operating-point log.'
        ]
        with (folder/'bode.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['frequency_hz','gain_db','phase_deg']);w.writerows(curve)
        no_inputs=re.sub(r'(?im)^VIN_(MINUS|PLUS)\b[^\n]*','',text)
        follower=no_inputs+'\nRFOLLOW VIN1 VOUT 1u\nVIN_STEP VIN2 0 PULSE(1 2 1u 1n 1n 3u 6u)\n'
        tran,_,_=self.simulate(folder,'slew',follower,'.tran 0 8u 0 2n')
        t=np.asarray(tran['time']);out=np.asarray(tran['v(vout)'])
        metrics['slew_rate_rise_v_per_us']=slew_value(t,out,1.2,1.8,1e-6,3.8e-6,True)
        metrics['slew_rate_fall_v_per_us']=slew_value(t,out,1.2,1.8,4.001e-6,6.8e-6,False)
        def settled(start,end,target):
            v=out[(t>=start)&(t<=end)]
            return len(v)>0 and bool(np.max(abs(v-target))<0.02)
        metrics['slew_settled']=settled(3.5e-6,3.8e-6,2.) and settled(6.5e-6,6.8e-6,1.)
        with (folder/'slew.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['time_s','input_v','output_v']);w.writerows(zip(t,tran['v(vin2)'],out))
        # Numerical DC servos preserve either output DC or input common-mode.
        vcm=self.targets['input_common_mode_v'];vout=self.targets['desired_output_dc_v'];supply=self.targets['supply_v']
        ic=[]
        for tag,target in [('low',vout-.01),('high',vout+.01)]:
            servo=no_inputs+f'\nVCM_SWEEP VCM_CTRL 0 0\nBMIN VIN1 0 V=V(VCM_CTRL)-({target}-V(VOUT))/2\nBPLUS VIN2 0 V=V(VCM_CTRL)+({target}-V(VOUT))/2\n'
            raw,_,_=self.simulate(folder,'icmr_'+tag,servo,f'.dc VCM_SWEEP 0 {supply} 0.05')
            ic.append(raw)
        a,b=ic;common=np.asarray(a['v(vcm_ctrl)'])
        da=np.asarray(a['v(vin2)'])-np.asarray(a['v(vin1)'])
        db=np.asarray(b['v(vin2)'])-np.asarray(b['v(vin1)'])
        oa=np.asarray(a['v(vout)']);ob=np.asarray(b['v(vout)'])
        with np.errstate(divide='ignore',invalid='ignore'):
            gain=(ob-oa)/(db-da)
        mask=(gain>=1000)&(abs(oa-(vout-.01))<=.001)&(abs(ob-(vout+.01))<=.001)&(abs(da)<=.01)&(abs(db)<=.01)
        mask &= (np.asarray(a['v(vin1)'])>=0)&(np.asarray(b['v(vin2)'])<=supply)
        metrics['icmr_v']=contiguous_range(common,mask,1.5)
        np.savetxt(folder/'icmr.csv',np.column_stack([common,oa,ob,gain,mask]),delimiter=',',
                   header='common_mode_v,output_low_v,output_high_v,local_gain_linear,pass',comments='')
        servo=no_inputs+f'\nVTARGET TARGET 0 0\nBMIN VIN1 0 V={vcm}-(V(TARGET)-V(VOUT))/2\nBPLUS VIN2 0 V={vcm}+(V(TARGET)-V(VOUT))/2\n'
        raw,_,_=self.simulate(folder,'ocmr',servo,f'.dc VTARGET 0 {supply} 0.05')
        target=np.asarray(raw['v(target)']);out=np.asarray(raw['v(vout)'])
        diff=np.asarray(raw['v(vin2)'])-np.asarray(raw['v(vin1)'])
        with np.errstate(divide='ignore',invalid='ignore'):
            gain=np.gradient(out)/np.gradient(diff)
        mask=(gain>=1000)&(abs(out-target)<=.001)&(abs(diff)<=.01)
        metrics['ocmr_v']=contiguous_range(target,mask,1.5)
        np.savetxt(folder/'ocmr.csv',np.column_stack([target,out,diff,gain,mask]),delimiter=',',
                   header='target_v,output_v,input_difference_v,local_gain_linear,pass',comments='')
        assessment=assess(metrics,self.targets)
        result=dict(params=p,metrics=metrics,elapsed_s=time.monotonic()-started,folder=str(folder),**assessment)
        (folder/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        return result
