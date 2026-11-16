"""Run and measure the 3.3V PDK baseline; no optimization or target guessing."""
from pathlib import Path
import argparse, cmath, csv, json, math, re, struct, subprocess, time

ROOT = Path(__file__).resolve().parent
DEFAULT_EXE = Path.home()/'AppData/Local/Programs/ADI/LTspice/LTspice.exe'

def run_ltspice(exe, *args):
    result = subprocess.run([str(exe), *map(str,args)], cwd=ROOT,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
        capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'LTspice returned {result.returncode}: {result.stderr!r}')

def read_raw(path):
    """Read uncompressed LTspice real or complex binary point-major data."""
    b=path.read_bytes()
    marker='Binary:'.encode('utf-16le')
    k=b.index(marker)
    header=b[:k].decode('utf-16le')
    start=b.index(b'\n\x00',k)+2
    names=re.findall(r'^\s*\d+\s+(\S+)\s+\S+\s*$',header,re.M)
    n=len(names)
    count=int(re.search(r'No. Points:\s*(\d+)',header)[1])
    flags=re.search(r'Flags:\s*(.*)',header)[1].lower().split()
    if 'fastaccess' in flags:
        raise ValueError('Fast-access raw format is not supported; rerun without -FastAccess.')
    complex_data='complex' in flags
    fmt=('<'+'d'*(2*n)) if complex_data else ('<'+'d'*n if 'double' in flags else '<d'+'f'*(n-1))
    size=struct.calcsize(fmt)
    if len(b)-start != size*count:
        raise ValueError('Unexpected RAW data size; refusing to infer metrics.')
    data={name.lower():[] for name in names}
    for point in range(count):
        values=struct.unpack_from(fmt,b,start+point*size)
        if complex_data:
            values=[complex(values[j],values[j+1]) for j in range(0,len(values),2)]
        for name,value in zip(names,values):
            data[name.lower()].append(value)
    return data

def crossing(f,y,target):
    """Return all falling crossings using interpolation in log-frequency."""
    result=[]
    for i in range(1,len(f)):
        if y[i-1]>target>=y[i]:
            w=(target-y[i-1])/(y[i]-y[i-1])
            freq=math.exp(math.log(f[i-1])+w*math.log(f[i]/f[i-1]))
            result.append((freq,i,w))
    return result

def measure(ac,op):
    f=[x.real for x in ac['frequency']]
    gain=[out/(vp-vm) for out,vp,vm in zip(ac['v(vout)'],ac['v(vin2)'],ac['v(vin1)'])]
    if not all(math.isfinite(abs(g)) and abs(g)>0 for g in gain):
        raise ValueError('Non-finite or zero differential gain.')
    db=[20*math.log10(abs(g)) for g in gain]
    phase=[]
    for g in gain:
        value=math.degrees(cmath.phase(g))
        if phase:
            while value-phase[-1]>180: value-=360
            while value-phase[-1]<-180: value+=360
        phase.append(value)
    if abs(phase[0])>10:
        raise ValueError('Unexpected low-frequency polarity; check plus/minus input assignment.')
    unity=crossing(f,db,0)
    bw=crossing(f,db,db[0]-3)
    all_pm=[{'frequency_hz':fu,'phase_margin_deg':180+phase[i-1]+w*(phase[i]-phase[i-1])} for fu,i,w in unity]
    current=op['i(vdd)'][0]
    voltage=op['v(vdda)'][0]
    answer={
        'gain_reference_frequency_hz':f[0],
        'low_frequency_gain_db':db[0],
        'low_frequency_phase_deg':phase[0],
        'gain_change_first_decade_db':db[100]-db[0],
        'power_mw':-voltage*current*1e3,
        'supply_current_ua':-current*1e6,
        'f_unity_hz':unity[0][0] if unity else None,
        'phase_margin_unity_feedback_estimate_deg':all_pm[0]['phase_margin_deg'] if all_pm else None,
        'all_falling_unity_crossings':all_pm,
        'f_3db_open_loop_hz':bw[0][0] if bw else None,
        'dc_voltages_v':{k:op[f'v({k})'][0] for k in ('vdda','vbp','vbn','vx','vo1','vout')},
        'measurement_notes':[
            'Gain = V(out)/(V(VIN2)-V(VIN1)); VIN2 is plus, VIN1 is minus.',
            'Low-frequency gain is measured at 0.01Hz, not mathematically at zero frequency.',
            'Phase margin assumes unity negative feedback and the simulated 10pF load.',
            'Open-loop -3dB bandwidth is relative to the low-frequency gain.',
            'SR, ICMR and OCMR are not yet measured.',
            'All results are TT, 25C, 3.3V and VCM=VDD/2, using initial sizes.'
        ],
    }
    return answer, list(zip(f,db,phase))

def check_targets(metrics,targets):
    rules=[
        ('power_mw','power_max_mw',lambda x,t:x<=t),
        ('low_frequency_gain_db','gain_min_db_exclusive',lambda x,t:x>t),
        ('f_unity_hz','f_unity_min_hz_exclusive',lambda x,t:x>t),
        ('phase_margin_unity_feedback_estimate_deg','pm_min_deg_exclusive',lambda x,t:x>t),
    ]
    checks={}
    for metric,target,ok in rules:
        value=metrics[metric]
        checks[metric]={'value':value,'target':targets[target],
            'status':'not_measured' if value is None else ('pass' if ok(value,targets[target]) else 'fail')}
    fin=targets.get('input_frequency_hz')
    if fin is None:
        checks['f_3db_open_loop_hz']={'value':metrics['f_3db_open_loop_hz'],'status':'pending_input_frequency'}
    else:
        value=metrics['f_3db_open_loop_hz']
        checks['f_3db_open_loop_hz']={'value':value,'target':10*fin,
            'status':'not_measured' if value is None else ('pass' if value>=10*fin else 'fail')}
    for name in ('slew_rate_rise_v_per_us','slew_rate_fall_v_per_us','icmr_v','ocmr_v'):
        checks[name]={'status':'not_measured'}
    return checks

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ltspice',type=Path,default=DEFAULT_EXE)
    args=parser.parse_args()
    if not args.ltspice.is_file(): raise FileNotFoundError(args.ltspice)
    schematic=ROOT/'two_stage_cmos_3v3_pdk.asc'
    net=schematic.with_suffix('.net')
    # Remove stale netlists only after the generator succeeds; compare timestamps.
    started=time.time()
    run_ltspice(args.ltspice,'-netlist',schematic)
    if not net.is_file() or net.stat().st_mtime < started-2:
        raise RuntimeError('LTspice did not produce a fresh netlist.')
    work=ROOT/'measurements'; work.mkdir(exist_ok=True)
    deck=work/'baseline.cir'
    text=net.read_text(encoding='utf-8',errors='replace')
    text=re.sub(r'(?im)^\.end\s*$', '.options logopinfo plotwinsize=0\n'
        '.meas ac CHECK_GAIN_DB FIND db(V(vout)) AT=0.01\n'
        '.meas ac CHECK_FUN_HZ WHEN mag(V(vout))=1 FALL=1\n.end',text)
    deck.write_text(text,encoding='utf-8')
    for suffix in ('.raw','.op.raw','.log'):
        stale=deck.with_suffix(suffix)
        if stale.exists(): stale.unlink()
    run_ltspice(args.ltspice,'-b',deck)
    log=deck.with_suffix('.log').read_text(encoding='utf-8',errors='replace')
    if 'Total elapsed time:' not in log or re.search(r'(?im)^\s*(fatal|error)\b',log):
        raise RuntimeError('Simulation did not complete successfully; inspect measurements/baseline.log')
    ac=read_raw(deck.with_suffix('.raw'))
    op=read_raw(deck.with_suffix('.op.raw'))
    metrics,curve=measure(ac,op)
    # Independent LTspice .meas checks catch RAW parser or normalization mistakes.
    for name,key in [('check_gain_db','low_frequency_gain_db'),('check_fun_hz','f_unity_hz')]:
        line=re.search(rf'(?im)^{name}:.*$',log)
        if line is None: raise RuntimeError(f'Missing LTspice independent check: {name}')
        if name=='check_gain_db':
            # LTspice prints FIND results as complex dB/phase even when
            # db() was already evaluated. Undo only this display conversion.
            match=re.search(r'=\(([-+0-9.eE]+)dB,',line[0])
            if match is None: raise ValueError(f'Unexpected AC FIND format: {line[0]}')
            observed=10**(float(match[1])/20)
        else:
            match=re.search(r'\bAT\s+([-+0-9.eE]+)',line[0])
            if match is None: raise ValueError(f'Unexpected AC WHEN format: {line[0]}')
            observed=float(match[1])
        if metrics[key] is None or not math.isclose(observed,metrics[key],rel_tol=2e-3,abs_tol=1e-4):
            raise ValueError(f'Independent {name} disagrees: {observed}, {metrics[key]}')
    targets=json.loads((ROOT/'targets.json').read_text(encoding='utf-8'))
    metrics['target_checks']=check_targets(metrics,targets)
    devices={}
    names=[]
    for line in log.splitlines():
        if line.startswith('Name:'):
            names=line.split()[1:]
            for name in names: devices[name]={}
        elif names and re.match(r'^(Id|Vgs|Vds|Vbs|Vth|Vdsat|Gm|Gds):',line):
            field,*values=line.split()
            for name,value in zip(names,values):
                devices[name][field.rstrip(':').lower()]=float(value)
    if len(devices)!=10 or any('vdsat' not in d for d in devices.values()):
        raise ValueError('Incomplete MOS operating-point information.')
    for device in devices.values():
        device['saturation_headroom_v']=abs(device['vds'])-abs(device['vdsat'])
        device['nonzero_current_and_saturation_headroom']=abs(device['id'])>1e-9 and device['saturation_headroom_v']>=0
    metrics['mos_operating_points_rounded_by_ltspice_log']=devices
    metrics['model_saturation_headroom_screen_all_pass']=all(d['nonzero_current_and_saturation_headroom'] for d in devices.values())
    metrics['rz_one_over_gm7_reference_ohm']=1/devices['M7']['gm']
    metrics['output_midrail_error_v']=metrics['dc_voltages_v']['vout']-targets['supply_v']/2
    metrics['fom_gain_db_times_unity_hz_per_mw']=(metrics['low_frequency_gain_db']*metrics['f_unity_hz']/metrics['power_mw']) if metrics['f_unity_hz'] else None
    metrics['measurement_notes'].append('Device parameters are rounded in the LTspice log; saturation headroom is a screening check.')
    metrics['measurement_notes'].append('Output midrail error is measured; a zero-offset tolerance is not yet specified.')
    (work/'baseline_metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False),encoding='utf-8')
    with (work/'baseline_bode.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream);writer.writerow(['frequency_hz','gain_db','phase_deg']);writer.writerows(curve)
    print(json.dumps(metrics,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
