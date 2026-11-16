"""Reusable, offline PDF report generation from completed optimization sessions."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone,timedelta
import csv,hashlib,html,json,math,os,re,shutil,sys,time
import numpy as np

ROOT=Path(__file__).resolve().parent
KST=timezone(timedelta(hours=9))
VERSION='1.0'
LABELS={'Power':'소비전력','DC gain':'DC 이득','Unity gain':'Unity gain 주파수',
 'Phase margin':'위상여유','-3dB BW':'-3 dB 대역폭','SR rise':'상승 SR','SR fall':'하강 SR',
 'DC balance':'출력 DC 오차','ICMR':'입력 공통모드 범위','OCMR':'출력 전압 범위',
 'MOS saturation':'최소 포화 여유','Single unity crossing':'Unity 교차 개수','Step settles':'과도 응답 정착'}
UNITS={'mW':'mW','dB':'dB','Hz':'Hz','deg':'deg','V/us':'V/us','V error':'V',
 'V':'V','V headroom':'V','count':'개','bool':''}

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    temp.replace(path)

def inside(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT): raise ValueError('All source and output paths must remain within the circuit project.')
    return path

def load_profile():
    path=ROOT/'report_profile.json'
    return read_json(path) if path.exists() else dict(circuit_id=ROOT.name,title=ROOT.name,report_directory='결과보고서',parameter_units={},parameter_labels={})

def analyze(state):
    history=state.get('history',[])
    measured=[r for r in history if r.get('status')=='measured']
    errors=[r for r in history if r.get('status')=='simulation_error']
    if state.get('status')!='completed':raise ValueError('A completed run is required.')
    total=int(state.get('total',len(history)))
    if state.get('status')!='completed' or len(history)!=total:
        raise ValueError('A completed run with every scheduled trial recorded is required.')
    if state.get('mode')=='until_pass':
        from overnight_support import fully_passing
        if (state.get('completion_reason')!='targets_met' or not history
            or not fully_passing(history[-1]) or state.get('success_trial')!=history[-1]['trial']):
            raise ValueError('Continuous-mode completion requires a recorded fully passing final trial.')
    nums=[r.get('trial') for r in history]
    if len(set(nums))!=len(nums): raise ValueError('Duplicate trial numbers.')
    if nums!=list(range(1,total+1)): raise ValueError('Trial records must be complete and ordered.')
    for r in measured:
        if not math.isfinite(r['score']): raise ValueError('Non-finite score.')
        if bool(r['feasible']) != all(c['status']=='pass' for c in r['checks']):
            raise ValueError('Feasibility flag disagrees with measured checks.')
    baseline=measured[0] if measured else None
    best=min(measured,key=lambda r:r['score']) if measured else None
    improvements=[];best_score=math.inf
    for r in measured:
        if r['score']<best_score:
            improvements.append(r);best_score=r['score']
    milestones=[]
    cuts=sorted(set([min(total,n) for n in (20,40,60,80,100)]+[total]))
    for cutoff in cuts:
        candidates=[r for r in measured if r['trial']<=cutoff]
        row=min(candidates,key=lambda r:r['score']) if candidates else None
        milestones.append(dict(trial=cutoff,measured=len(candidates),best=row))
    passing=[r for r in measured if r['feasible']]
    return dict(total=total,history=history,measured=measured,errors=errors,baseline=baseline,best=best,
        improvements=improvements,milestones=milestones,passing=passing,
        error_counts=Counter(r.get('error','Unknown error') for r in errors),
        failed_checks=[c for c in best['checks'] if c['status']=='fail'] if best else [])

def fmt(value,unit=''):
    if value is None: return '미측정'
    if isinstance(value,(list,tuple)): return ' ~ '.join(f'{v:.3g}' for v in value)
    if isinstance(value,bool): return '예' if value else '아니오'
    if not isinstance(value,(int,float)): return str(value)
    if not math.isfinite(value): return '유효값 없음'
    if unit=='Hz':
        if abs(value)>=1e6: return f'{value/1e6:,.3g} MHz'
        if abs(value)>=1e3: return f'{value/1e3:,.3g} kHz'
        return f'{value:,.3g} Hz'
    if unit=='V error': return f'{value*1e3:.4g} mV'
    return f'{value:,.4g}'+(' '+UNITS.get(unit,unit) if unit else '')

def target_text(check):
    name=check['name'];value=check['target'];unit=check.get('unit','')
    if name in ('ICMR','OCMR'): return fmt(value,'')+' V 포함'
    if name=='Power': return '<= '+fmt(value,unit)
    if name=='DC balance': return '<= '+fmt(value,unit)
    if name in ('DC gain','Unity gain','Phase margin'): return '> '+fmt(value,unit)
    if name=='Step settles': return '정착'
    if name=='Single unity crossing': return '= 1'
    return '>= '+fmt(value,unit)

def path_for_trial(run,result,filename):
    # Resolve relative to the verified source session, never trust absolute paths in JSON.
    return run/'trials'/f'{int(result["trial"]):04d}'/filename

def charts(folder,run,a,state):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,
        'axes.labelsize':9,'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False,
        'savefig.facecolor':'white','figure.facecolor':'white'})
    assets=folder/'figures';assets.mkdir(exist_ok=True)
    out={}
    def save(fig,name):
        path=assets/(name+'.png');fig.savefig(path,dpi=180,bbox_inches='tight');plt.close(fig);out[name]=path
    measured=a['measured'];best=a['best'];base=a['baseline']
    fig,(ax,ax2)=plt.subplots(2,1,figsize=(7.2,3.7),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    if measured:
        x=np.array([r['trial'] for r in measured]);scores=np.array([r['score'] for r in measured])
        ax.scatter(x,scores,s=12,color='#94a3b8',label='Measured trials')
        ax.plot(x,np.minimum.accumulate(scores),lw=1.8,color='#1d4ed8',label='Best so far')
        ax.set_yscale('symlog',linthresh=1);ax.axhline(1,color='#0f766e',ls='--',lw=.8,label='Feasible score boundary')
        transition=next((r['trial'] for r in a['history'] if str(r.get('phase','')).startswith('TPE')),None)
        if transition is not None:
            ax.axvline(transition,color='#b45309',ls=':',lw=1)
            ax.text(transition,.98,'TPE starts',transform=ax.get_xaxis_transform(),va='top',fontsize=7)
        allx=[r['trial'] for r in a['history']]
        ax2.step(allx,np.cumsum([r.get('status')=='measured' for r in a['history']]),where='post',label='Measured',color='#0f766e')
        ax2.step(allx,np.cumsum([r.get('status')=='simulation_error' for r in a['history']]),where='post',label='Excluded / failed',color='#b91c1c')
        ax.legend(fontsize=7,loc='upper right');ax2.legend(fontsize=7,loc='upper left')
    else: ax.text(.5,.5,'No successfully measured trials',transform=ax.transAxes,ha='center')
    ax.set_ylabel('Score (lower is better)');ax.set_title('Optimization history and evaluation outcomes',loc='left')
    ax2.set_ylabel('Count');ax2.set_xlabel('Trial');ax2.set_xlim(.5,max(1.5,a['total']+.5))
    for axis in (ax,ax2): axis.grid(alpha=.18)
    fig.tight_layout();save(fig,'learning_history')
    if not best: return out
    fields=[('Gain','low_frequency_gain_db',60,False),('UGF','f_unity_hz',1e6,False),
            ('PM','phase_margin_unity_feedback_estimate_deg',60,False),('BW','f_3db_open_loop_hz',10000,False),
            ('SR rise','slew_rate_rise_v_per_us',10,False),('Power','power_mw',10,True)]
    # Derive targets from the session instead of the current project configuration.
    target_keys=['gain_min_db_exclusive','f_unity_min_hz_exclusive','pm_min_deg_exclusive',None,'sr_min_v_per_us','power_max_mw']
    targets=state.get('targets',{})
    fields=[(label,key,(targets.get(target_keys[i],target) if i!=3 else targets.get('input_frequency_hz',1000)*targets.get('f3db_multiplier_of_fin',10)),inv)
            for i,(label,key,target,inv) in enumerate(fields)]
    fig,ax=plt.subplots(figsize=(7.2,2.5));y=np.arange(len(fields))
    for r,offset,color,label in ((base,-.17,'#cbd5e1','Initial balanced candidate'),(best,.17,'#0f766e','Best candidate')):
        vals=[]
        for _,key,target,inverse in fields:
            v=r['metrics'].get(key);vals.append((target/v if inverse else v/target) if v and v>0 else 0)
        ax.barh(y+offset,np.minimum(vals,3),height=.30,color=color,label=label)
        if label=='Best candidate':
            for i,v in enumerate(vals): ax.text(min(v,3)+.05,i+offset,f'{v:.2g}x',va='center',fontsize=8)
    ax.axvline(1,color='#b91c1c',ls='--',lw=.9);ax.set_yticks(y,[x[0] for x in fields]);ax.invert_yaxis()
    ax.set_xlim(0,3.8);ax.set_xlabel('Target ratio; higher is better; bars capped at 3x')
    ax.legend(fontsize=7,loc='lower right');ax.grid(axis='x',alpha=.18);fig.tight_layout();save(fig,'target_comparison')
    fig,axs=plt.subplots(2,2,figsize=(7.2,3.5))
    specs=[('f_3db_open_loop_hz','Bandwidth (kHz)',1e-3,targets.get('input_frequency_hz',1000)*targets.get('f3db_multiplier_of_fin',10)*1e-3),
           ('phase_margin_unity_feedback_estimate_deg','Phase margin (deg)',1,targets.get('pm_min_deg_exclusive',60)),
           ('slew_rate_rise_v_per_us','SR rise (V/us)',1,targets.get('sr_min_v_per_us',10)),
           ('power_mw','Power (mW)',1,targets.get('power_max_mw',10))]
    for ax,(key,label,scale,target) in zip(axs.flat,specs):
        values=[(r['trial'],r['metrics'].get(key)) for r in measured]
        values=[(x,v) for x,v in values if v is not None and math.isfinite(v)]
        if values: ax.scatter([x for x,v in values],[v*scale for x,v in values],s=11,color='#64748b',alpha=.7)
        v=best['metrics'].get(key)
        if v is not None: ax.scatter(best['trial'],v*scale,marker='*',s=90,color='#b45309',zorder=3)
        ax.axhline(target,color='#b91c1c',ls='--',lw=.8);ax.set_ylabel(label);ax.set_xlabel('Trial');ax.grid(alpha=.18)
    fig.tight_layout();save(fig,'metric_evolution')
    fig,ax=plt.subplots(figsize=(7.2,2.7));other=ax.twinx()
    available=False
    for record,color,label in ((base,'#94a3b8','Initial'),(best,'#1d4ed8','Best')):
        p=path_for_trial(run,record,'bode.csv')
        if not p.is_file(): continue
        c=np.loadtxt(p,delimiter=',',skiprows=1);available=True
        ax.semilogx(c[:,0],c[:,1],color=color,lw=1.3,label=label+' gain')
        if record is best: other.semilogx(c[:,0],c[:,2],color='#0f766e',lw=1.2,label='Best phase')
    if available:
        ax.axhline(0,color='#94a3b8',lw=.7);other.axhline(-180,color='#b91c1c',ls=':',lw=.8)
        ax.set_xlabel('Frequency (Hz)');ax.set_ylabel('Gain (dB)');other.set_ylabel('Phase (deg)')
        h,l=ax.get_legend_handles_labels();h2,l2=other.get_legend_handles_labels();ax.legend(h+h2,l+l2,fontsize=7,loc='lower left')
        ax.grid(alpha=.18);fig.tight_layout();save(fig,'frequency_response')
    else: plt.close(fig)
    p=path_for_trial(run,best,'slew.csv')
    if p.is_file():
        c=np.loadtxt(p,delimiter=',',skiprows=1)
        fig,ax=plt.subplots(figsize=(7.2,2.45));ax.plot(c[:,0]*1e6,c[:,1],ls='--',lw=1,color='#94a3b8',label='Input')
        ax.plot(c[:,0]*1e6,c[:,2],lw=1.3,color='#1d4ed8',label='Output')
        ax.set_xlabel('Time (us)');ax.set_ylabel('Voltage (V)');ax.set_title('Unity-follower large-signal step response',loc='left')
        ax.legend(fontsize=7);ax.grid(alpha=.18);fig.tight_layout();save(fig,'slew_response')
    return out

def paper_content(state,a,profile,number):
    best=a['best'];base=a['baseline'];t=state.get('targets',{})
    elapsed=float(state.get('elapsed_s',0))
    title=f'{profile["circuit_id"]}_{number}차 보고서'
    conclusion=(f'총 {a["total"]}회 중 {len(a["measured"])}회가 정상 측정되었고, {len(a["errors"])}회는 제외 또는 실패하였다. '
        f'설정한 모든 수치 검사를 통과한 후보는 {len(a["passing"])}개였다.')
    if best:
        conclusion+=f' 최선 후보는 {best["trial"]}번째 시행이며, 종합 점수는 {base["score"]:.4g}에서 {best["score"]:.4g}로 변하였다.'
        fails=', '.join(LABELS.get(c['name'],c['name']) for c in a['failed_checks'])
        conclusion+=(' 최선 후보의 미달 항목은 '+fails+'이다.') if fails else ' 최선 후보는 현재 측정 조건의 모든 수치 검사를 통과하였다.'
    else: conclusion+=' 정상 측정 후보가 없어 성능 개선을 평가할 수 없다.'
    return title,conclusion

def build_pdf(path,folder,run,state,a,profile,ordinal,figs):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    regular=Path(profile.get('font_path','C:/Windows/Fonts/malgun.ttf'))
    bold=regular.with_name('malgunbd.ttf')
    if not regular.is_file(): raise FileNotFoundError('A Korean TrueType font is required; set font_path in report_profile.json.')
    if 'ReportKR' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('ReportKR',str(regular)))
        pdfmetrics.registerFont(TTFont('ReportKRB',str(bold if bold.exists() else regular)))
        pdfmetrics.registerFontFamily('ReportKR',normal='ReportKR',bold='ReportKRB',italic='ReportKR',boldItalic='ReportKRB')
    style=ParagraphStyle('body',fontName='ReportKR',fontSize=9.4,leading=14.6,spaceAfter=7,wordWrap='CJK',textColor=colors.black)
    head=ParagraphStyle('head',parent=style,fontName='ReportKRB',fontSize=13,leading=18,spaceBefore=4,spaceAfter=10,keepWithNext=True)
    small=ParagraphStyle('small',parent=style,fontSize=8,leading=11.5,spaceAfter=5)
    cell=ParagraphStyle('cell',parent=style,fontSize=8.2,leading=11,spaceAfter=0)
    title_style=ParagraphStyle('title',parent=head,fontSize=21,leading=29,spaceAfter=8)
    doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=17*mm,bottomMargin=17*mm,
        title=f'{profile["circuit_id"]} {ordinal}차 최적화 보고서',author='Local circuit optimization system')
    story=[];title,abstract=paper_content(state,a,profile,ordinal)
    def p(text,sty=style):
        return Paragraph(html.escape(str(text)).replace('\n','<br/>'),sty)
    def para(text,sty=style): story.append(p(text,sty))
    def h(text): story.append(p(text,head))
    def table(headers,rows,widths=None):
        rows=[[p(v,cell) for v in row] for row in rows]
        data=[[p(v,ParagraphStyle('headercell',parent=cell,fontName='ReportKRB')) for v in headers]]+rows
        tab=Table(data,colWidths=[doc.width*v for v in widths] if widths else None,repeatRows=1,hAlign='LEFT')
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8edf2')),
            ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#d9d9d9')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafc')])]))
        story.append(tab);story.append(Spacer(1,7))
    def figure(key,caption,height_mm):
        if key not in figs:
            para('그림 데이터가 보관되어 있지 않아 해당 그림은 생성하지 않았다.',small);return
        im=Image(str(figs[key]),width=doc.width,height=height_mm*mm,kind='proportional')
        story.append(KeepTogether([im,Spacer(1,4),p(caption,small),Spacer(1,5)]))
    def page(): story.append(PageBreak())
    best=a['best'];base=a['baseline'];t=state.get('targets',{})
    para(title,title_style);para(profile.get('title',profile['circuit_id']),head)
    para(f'실행 기록 {run.name}\n보고서 생성 {datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")}',small)
    h('초록');para(abstract)
    para(f'탐색 소요 시간은 {state.get("elapsed_s",0)/60:.2f}분이다. 정상 측정은 시뮬레이션의 완료를 뜻하며 목표 통과와 구분한다. '
         '본 보고서는 저장된 시행 기록에 대한 실험 보고서이며, 조건을 만족하는 회로의 존재 또는 부재를 증명하지 않는다.')
    h('1 연구 목적과 실험 조건')
    para('지정한 회로의 소자 크기와 보상 소자를 자동 탐색하고, 성능 변화와 미달 원인을 재현 가능한 형태로 기록한다. '
         '비교 기준은 탐색의 첫 정상 측정 후보이며, 현재 최선 후보는 저장된 평가 점수가 가장 낮은 후보이다.')
    conditions=[['공정과 모델',profile.get('process','세션 기록 참조')],
        ['전원과 코너',f'{t.get("supply_v","미기록")} V / {profile.get("model_corner","미기록")} / {profile.get("temperature_c","미기록")} C'],
        ['채널 길이와 부하',f'L = {t.get("length_m",0)*1e6:g} um / CL = {t.get("load_capacitance_f",0)*1e12:g} pF'],
        ['입력 공통모드와 목표 출력 DC',f'{t.get("input_common_mode_v","미기록")} V / {t.get("desired_output_dc_v","미기록")} V'],
        ['입력 주파수와 보상 구성',f'{t.get("input_frequency_hz","미기록")} Hz / {profile.get("compensation_mode","기록 참조")}'],
        ['시행과 난수 시드',f'{a["total"]}회 / seed {state.get("seed","미기록")}'],
        ['실행 모드와 종료 이유',('조건 충족까지 지속 / 전체 수치 검사 통과' if state.get('mode')=='until_pass' else '횟수 지정 / 지정 시행 완료')]]
    table(['항목','설정'],conditions,[.36,.64])
    para('현재 코너의 회로 수준 시뮬레이션 결과를 다룬다. 실측, 레이아웃 기생 추출, 공정 코너 전체 및 mismatch 검증 결과로 확대 해석하지 않는다.',small)
    page();h('2 최적화와 측정 방법')
    para(f'Optuna의 TPE 기반 탐색을 사용하였다. 초기 탐색 설정은 {state.get("startup","미기록")}개 정상 완료 시행이다. '
         '시뮬레이션 실패와 정상 측정되었지만 목표를 만족하지 못한 시행을 구분한다. '
         '확률적 탐색이므로 시행 횟수의 종료가 전역 최적해 도달을 의미하지 않는다.')
    bounds=state.get('search_bounds',{})
    table(['탐색 변수','하한','상한'],[[k,str(v[0]),str(v[1])] for k,v in bounds.items()] or [['미기록','-','-']],[.56,.22,.22])
    para('현 회로에서는 W1과 W2를 같게 유지하고 W3과 W4는 매 시행의 DC 균형 계산으로 결정한다. '
         'M7의 W7은 병렬 소자 각각의 폭이며 병렬 배수는 2이다. L과 CL은 세션의 고정 조건을 사용한다.')
    protocols=[
        ['AC','Vout / (VIN2 - VIN1). 저주파 이득, 첫 하강 unity 교차, 위상 및 상대 -3 dB 대역폭 측정.'],
        ['위상여유','단위 이득 음의 피드백을 가정한 180 deg + unity 교차 위상. 복수 교차 여부도 검사.'],
        ['SR','단위 이득 버퍼의 1 V와 2 V 사이 스텝 응답에서 20%와 80% 사이 평균 기울기.'],
        ['ICMR과 OCMR','50 mV 간격의 DC servo 검사. 국소 DC 이득 >= 1000, servo 오차 <= 1 mV, 입력 차전압 <= 10 mV.'],
        ['DC 균형과 포화','출력 DC 오차 <= 1 mV 및 모델의 abs(Vds) - abs(Vdsat) >= 0 검사. Vdsat는 로그 반올림값.']]
    table(['측정','정의와 수치 기준'],protocols,[.21,.79])
    para('평가 점수는 목표 미달 후보에서 1 + 각 양의 위반값 제곱합을 사용한다. 모든 수치 검사를 통과하면 '
         '1 / (1 + FoM / 10^8)을 사용한다. 점수는 낮을수록 좋으며 FoM은 높을수록 좋다. '
         'FoM은 과제 표기대로 이득 dB와 unity 주파수 Hz의 곱을 전력 mW로 나눈 값이다. '
         '포화 여유 등 일부 위반값은 동일한 상대 척도로 정규화되어 있지 않으므로 가중치 개선 여지가 있다.',small)
    page();h('3 탐색 과정과 개선 이력')
    figure('learning_history','그림 1 전체 시행의 점수와 누적 측정 결과. 파란 선은 각 시점까지의 최선 점수이다. 오류 시행은 성능 점으로 대체하지 않았다.',92)
    rows=[]
    for snap in a['milestones']:
        r=snap['best'];m=r['metrics'] if r else {}
        rows.append([str(snap['trial']),str(snap['measured']),str(r['trial']) if r else '-',fmt(r['score']) if r else '-',fmt(m.get('f_3db_open_loop_hz'),'Hz'),fmt(m.get('phase_margin_unity_feedback_estimate_deg'),'deg')])
    table(['누적 시행','정상 측정','최선 시행','최선 점수','대역폭','위상여유'],rows,[.14,.14,.14,.17,.21,.20])
    para(f'최선 점수가 갱신된 횟수는 초기 기준 후보를 포함해 {len(a["improvements"])}회이다. '
         '점수 개선과 FoM 증가는 같은 의미가 아니다. 제약 위반이 줄어들면 FoM이 감소하더라도 더 좋은 후보로 선택될 수 있다.')
    figure('metric_evolution','그림 2 각 정상 측정 시행의 주요 성능. 별은 최종 최선 후보이고 점선은 목표 경계이다.',73)
    page();h('4 초기 후보와 최선 후보의 성능 비교')
    if best:
        before={c['name']:c for c in base['checks']}
        rows=[]
        for c in best['checks']:
            rows.append([LABELS.get(c['name'],c['name']),fmt(before.get(c['name'],{}).get('value'),c.get('unit','')),fmt(c['value'],c.get('unit','')),target_text(c),'통과' if c['status']=='pass' else '미달'])
        table(['항목','초기 후보','최선 후보','목표 또는 검사 기준','판정'],rows,[.21,.19,.19,.31,.10])
        figure('target_comparison','그림 3 목표 대비 성능 비율. 전력은 목표값을 측정값으로 나누어 큰 값이 유리하도록 표시했다. 막대 길이는 3배에서 제한하고 실제 비율을 숫자로 표기했다.',66)
        para(f'초기 FoM은 {base.get("fom",0):.6g}, 최선 후보 FoM은 {best.get("fom",0):.6g} dB Hz/mW이다. '
             '모든 목표의 통과 여부는 개별 판정과 함께 해석해야 한다.',small)
    else: para('정상 측정 후보가 없어 초기 및 최선 성능 비교표를 작성하지 않았다.')
    page();h('5 주파수 응답과 과도 응답')
    figure('frequency_response','그림 4 저장된 AC 파형에서 읽은 초기 후보와 최선 후보의 이득 및 최선 후보의 위상.',65)
    figure('slew_response','그림 5 최선 후보의 실제 LTspice 스텝 응답. 작은 신호 정현파 시험과 구분되는 큰 신호 SR 시험이다.',64)
    para('초기 후보와 최선 후보 모두 현재 설정된 보상 구성을 사용한다. 보상 전 또는 Cc 단독 조건의 별도 시뮬레이션이 없는 경우, '
         '이 비교를 보상 전후 실험으로 표시하지 않는다. 작은 신호 정현파와 손계산 결과도 별도로 산출하지 않았다면 본 보고서의 측정값으로 대체하지 않는다.')
    if best:
        para('입력 공통모드 범위와 출력 전압 범위는 DC servo 및 국소 이득 기준으로 구한 표본 구간이다. '
             '연속 전압 전체 또는 모든 출력 부하에서의 동작을 보장하는 결과가 아니며, 경계 분해능은 50 mV이다.',small)
    page();h('6 소자 값과 동작점 변화')
    if best:
        rows=[];units=profile.get('parameter_units',{});labels=profile.get('parameter_labels',{})
        for key,v in best['params'].items():
            unit=units.get(key,'');scale=1e6 if unit=='um' else (1e12 if unit=='pF' else 1)
            first=base['params'].get(key)
            change=(v/first-1)*100 if first else None
            rows.append([labels.get(key,key),fmt(first*scale if first is not None else None),fmt(v*scale),unit,fmt(change)+'%' if change is not None else '-'])
        table(['변수','초기','최선','단위','변화율'],rows,[.28,.19,.19,.13,.21])
        para('W3과 W4는 독립 난수 변수가 아니라 DC 균형을 위해 계산된 값이다. W7은 소자 한 개의 폭이며 총 유효 폭은 2 x W7이다. '
             '위 크기값은 해당 실행의 후보값이며 모든 조건을 통과한 경우에만 수치 검사 통과 후보로 해석한다.',small)
        a0=base['metrics'].get('saturation_headroom_v',{});a1=best['metrics'].get('saturation_headroom_v',{})
        if a1:
            table(['MOS','초기 포화 여유 V','최선 포화 여유 V','최선 판정'],
                [[name,fmt(a0.get(name)),fmt(v),'통과' if v>=0 else '미달'] for name,v in sorted(a1.items(),key=lambda kv:int(re.sub(r'\D','',kv[0]) or 0))],
                [.17,.28,.28,.27])
            para('포화 여유는 abs(Vds) - abs(Vdsat)이다. 음수인 소자는 모델의 해당 포화 경계 검사에 미달한다. '
                 '이 표는 수치 동작점 검사이며 실제 제조 편차에 대한 여유 검증을 대신하지 않는다.',small)
    else: para('최선 후보가 없어 소자 값 및 포화 여유 비교를 작성하지 않았다.')
    page();h('7 결과 해석과 후속 실험')
    para(abstract)
    if best:
        for c in a['failed_checks']:
            para(f'{LABELS.get(c["name"],c["name"])}: 측정값 {fmt(c["value"],c.get("unit",""))}, 기준 {target_text(c)}. '
                 '현재 최선 후보에서도 이 조건을 만족하지 못했다.')
        if a['failed_checks']:
            para('이 결과만으로 주어진 회로와 공정에서 조건 충족이 불가능하다고 결론내릴 수 없다. '
                 '탐색 범위, 변수 표현, 평가 함수 및 시행 예산이 제한되어 있기 때문이다. '
                 '포화와 DC 균형을 우선하는 제약 처리, 이전 결과를 활용하는 후속 탐색, 모델 유효 범위를 지키는 병렬 배수 검토가 후속 실험 후보이다.')
        else:
            para('모든 수치 검사 통과는 현재 코너와 테스트벤치에 한정된다. 후속으로 동일 조건 재실행, 다른 시뮬레이터와 동작점 대조, '
                 '공정 코너와 mismatch 검증을 수행한 뒤 설계를 확정해야 한다.')
    if a['error_counts']:
        h('7 1 제외 및 실패 원인')
        table(['기록된 원인','횟수'],[[error,str(count)] for error,count in a['error_counts'].most_common()],[.88,.12])
    h('7 2 재현성과 자료 구성')
    repro=[['실행 데이터','session.json, best.json, trials.jsonl 및 trials.csv'],
           ['파형과 그래프','figures 폴더 및 source_data 폴더의 선택 후보 파형'],
           ['소자 값','best_candidate.asc가 있는 경우 보고서 폴더에 함께 보관'],
           ['생성 근거','report_manifest.json의 원본 경로, SHA256 해시, 생성 버전과 시각'],
           ['실행 코드','run의 source_snapshot이 있으면 실행 시점 코드. 없으면 생성 시점 코드로 명시']]
    table(['자료','설명'],repro,[.25,.75])
    para('참고 자료: Optuna TPESampler 공식 문서, '
         'https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html '
         '및 각 시행의 LTspice 로그. 공정 모델 파일 자체는 보고서에 복제하지 않는다.',small)
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('ReportKR',7.5);canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(18*mm,10*mm,title);canvas.drawRightString(A4[0]-18*mm,10*mm,str(doc.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)

def run_signature(state):
    payload={k:state.get(k) for k in ('history','targets','total','seed','startup')}
    if 'mode' in state:
        payload.update({k:state.get(k) for k in ('mode','requested_trials','completion_reason','success_trial')})
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()

def find_existing_report(session_path,profile=None):
    session_path=inside(session_path);profile=profile or load_profile()
    signature=run_signature(read_json(session_path))
    out=inside(ROOT/profile.get('report_directory','결과보고서'))
    if not out.exists(): return None
    for path in out.glob('*/report_manifest.json'):
        try:
            m=read_json(path)
            if m.get('status')=='ready' and m.get('session_path')==str(session_path) and m.get('run_signature')==signature and m.get('circuit_id')==profile.get('circuit_id'):
                pdf=path.parent/m['pdf_name']
                if pdf.is_file(): return dict(pdf=str(pdf),folder=str(path.parent),ordinal=m['ordinal'],existing=True)
        except (OSError,ValueError,KeyError): continue
    return None

def generate_report(session_path,profile=None):
    session_path=inside(session_path);state=read_json(session_path);a=analyze(state)
    profile=profile or load_profile();circuit_id=profile.get('circuit_id',ROOT.name)
    if not re.fullmatch(r'[A-Za-z0-9_-]+',circuit_id): raise ValueError('circuit_id must use letters, numbers, underscores or hyphens.')
    report_root=inside(ROOT/profile.get('report_directory','결과보고서'));report_root.mkdir(parents=True,exist_ok=True)
    lock=report_root/'.report_generation.lock';fd=None
    for _ in range(300):
        try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);break
        except FileExistsError: time.sleep(.1)
    if fd is None: raise RuntimeError('Report generation is busy; retry after the existing report finishes.')
    os.close(fd)
    try:
        existing=find_existing_report(session_path,profile)
        if existing: return existing
        regex=re.compile(re.escape(circuit_id)+r'_(\d+)차 보고서$')
        numbers=[int(m[1]) for p in report_root.iterdir() if p.is_dir() and (m:=regex.fullmatch(p.name))]
        ordinal=max(numbers,default=0)+1;title=f'{circuit_id}_{ordinal}차 보고서'
        folder=report_root/title;folder.mkdir(exist_ok=False);run=session_path.parent
        manifest=dict(schema=1,status='generating',ordinal=ordinal,circuit_id=circuit_id,run_signature=run_signature(state),pdf_name=title+'.pdf',session_path=str(session_path),
            generated_at=datetime.now(KST).isoformat(),generator_version=VERSION,source_session_sha256=hashlib.sha256(session_path.read_bytes()).hexdigest())
        write_json(folder/'report_manifest.json',manifest)
        try:
            assets=charts(folder,run,a,state)
            build_pdf(folder/manifest['pdf_name'],folder,run,state,a,profile,ordinal,assets)
            data=folder/'source_data';data.mkdir()
            for name in ('session.json','best.json','trials.jsonl','trials.csv','targets.json','environment.json'):
                p=run/name
                if p.is_file(): shutil.copy2(p,data/name)
            for label,record in [('initial',a['baseline']),('best',a['best'])]:
                if not record: continue
                for name in ('bode.csv','slew.csv','icmr.csv','ocmr.csv','ac.log'):
                    p=path_for_trial(run,record,name)
                    if p.is_file(): shutil.copy2(p,data/(label+'_'+name))
            candidate=run/'best_candidate.asc'
            if candidate.is_file(): shutil.copy2(candidate,folder/'best_candidate.asc')
            source=run/'source_snapshot';destination=folder/'source_snapshot'
            if source.is_dir():
                shutil.copytree(source,destination)
                manifest['code_snapshot_kind']='at_run_start'
            else:
                destination.mkdir()
                for name in ('optimizer.py','circuit_engine.py','measure_baseline.py','build_schematic.py','report_profile.json','report_generator.py','targets.json'):
                    p=ROOT/name
                    if p.is_file(): shutil.copy2(p,destination/name)
                manifest['code_snapshot_kind']='at_report_generation_not_verified_run_version'
            title,abstract=paper_content(state,a,profile,ordinal)
            lines=['# '+title,'',profile.get('title',''),'',abstract,'','## 실행 요약',
                f'- 완료 시행: {a["total"]}',f'- 정상 측정: {len(a["measured"])}',f'- 제외 또는 실패: {len(a["errors"])}',f'- 전체 수치 검사 통과: {len(a["passing"])}','',
                '전체 설명과 표는 같은 폴더의 PDF에, 원본 데이터는 source_data에 보관되어 있습니다.',
                '','## 그림']+[f'![{key}](figures/{path.name})' for key,path in assets.items()]
            (folder/(title+'.md')).write_text('\n'.join(lines),encoding='utf-8')
            manifest.update(status='ready',completed_trials=a['total'],measured_trials=len(a['measured']),
                passing_trials=len(a['passing']),best_trial=a['best']['trial'] if a['best'] else None,
                source_files_sha256={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in data.iterdir() if p.is_file()})
            write_json(folder/'report_manifest.json',manifest)
            return dict(pdf=str(folder/manifest['pdf_name']),folder=str(folder),ordinal=ordinal,existing=False)
        except Exception as error:
            manifest.update(status='failed',error=str(error));write_json(folder/'report_manifest.json',manifest)
            raise
    finally:
        lock.unlink(missing_ok=True)

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path);parser.add_argument('--latest',action='store_true');parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    path=args.session
    if path is None:
        paths=sorted((ROOT/'runs').glob('opt_*/session.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        path=next((p for p in paths if read_json(p).get('status')=='completed'),None)
        if path is None: raise SystemExit('No completed optimization session found.')
    if path.is_dir(): path=path/'session.json'
    result=generate_report(path)
    print(json.dumps(result,ensure_ascii=False))
    if args.open: os.startfile(result['pdf'])

if __name__=='__main__': main()
