"""Native live dashboard for real LTspice/Optuna trials."""
import argparse,json,math,os,queue,sys,time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from optimizer import OptimizationRun,ROOT

BG='#eef2f7';PANEL='#ffffff';INK='#162538';MUTED='#64748b'
BLUE='#2563eb';TEAL='#0d9488';RED='#dc5461';AMBER='#e6a23c';LINE='#e2e8f0'

def number(value,unit=''):
    if value is None: return '--'
    if isinstance(value,list): return f'{value[0]:.2f} ~ {value[1]:.2f}'
    if isinstance(value,bool): return 'YES' if value else 'NO'
    if unit=='Hz':
        return f'{value/1e6:.2f}M' if abs(value)>=1e6 else (f'{value/1e3:.2f}k' if abs(value)>=1e3 else f'{value:.0f}')
    if unit=='V error': return f'{value*1e3:.3f}m'
    if isinstance(value,(int,float)): return f'{value:.3g}'
    return str(value)

class Dashboard:
    def __init__(self,root,args):
        self.root=root;self.args=args;self.run=None;self.state=None;self.events=queue.Queue()
        self.latest_params={};self.started_at=None;self.last_draw=0;self.pending_draw=False
        self.progress_running=False
        root.title('LTspice Live Optimization | 2-stage PMOS OP-AMP')
        root.configure(bg=BG)
        sw,sh=root.winfo_screenwidth(),root.winfo_screenheight()
        root.geometry(f'{min(1450,sw-100)}x{min(850,sh-160)}+20+20')
        root.minsize(1080,720)
        style=ttk.Style();style.theme_use('clam')
        style.configure('.',font=('Malgun Gothic',9))
        style.configure('TFrame',background=BG)
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',padding=(14,7))
        style.configure('Treeview',rowheight=24,background=PANEL,fieldbackground=PANEL,borderwidth=0,font=('Malgun Gothic',9))
        style.configure('Treeview.Heading',background='#f1f5f9',foreground=MUTED,font=('Malgun Gothic',9,'bold'))
        style.configure('TProgressbar',background=TEAL,troughcolor=LINE,borderwidth=0)
        style.configure('TButton',padding=(12,7))
        self._layout()
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(120,self.poll)
        if args.session: self.load(Path(args.session))
        else: self.load_latest(silent=True)
        if args.autostart: root.after(700,self.start)
    def label(self,parent,text,**kw):
        return tk.Label(parent,text=text,bg=kw.pop('bg',parent.cget('bg')),fg=kw.pop('fg',INK),font=kw.pop('font',('Malgun Gothic',10)),**kw)
    def _layout(self):
        head=tk.Frame(self.root,bg=INK,height=79);head.pack(fill='x');head.pack_propagate(False)
        self.label(head,'OP-AMP  /  LIVE OPTIMIZATION',bg=INK,fg='white',font=('Segoe UI',20,'bold')).pack(side='left',padx=24)
        self.label(head,'3.3 V   |   L = 1 um   |   CL = 10 pF   |   TT, 25 C',bg=INK,fg='#b7c8de',font=('Segoe UI',10)).pack(side='right',padx=24)
        modes=tk.Frame(self.root,bg=BG);modes.pack(fill='x',padx=20,pady=(8,0))
        self.label(modes,'실행 모드').pack(side='left')
        self.mode=tk.StringVar(value='조건 충족까지 지속' if self.args.mode=='until_pass' else '횟수 지정')
        self.mode_input=ttk.Combobox(modes,textvariable=self.mode,values=('횟수 지정','조건 충족까지 지속'),state='readonly',width=22)
        self.mode_input.pack(side='left',padx=8);self.mode_input.bind('<<ComboboxSelected>>',lambda event:self.update_mode())
        self.prevent_sleep=tk.BooleanVar(value=True)
        self.sleep_input=ttk.Checkbutton(modes,text='실행 중 자동 절전 방지',variable=self.prevent_sleep)
        self.sleep_input.pack(side='left',padx=10)
        self.label(modes,'지속 모드: 전체 수치 검사 통과 시 자동 종료',fg=MUTED,font=('Malgun Gothic',9)).pack(side='left',padx=8)
        controls=tk.Frame(self.root,bg=BG);controls.pack(fill='x',padx=20,pady=(12,8))
        self.label(controls,'시행 횟수').pack(side='left')
        self.trials=tk.StringVar(value=str(self.args.trials))
        self.trials_input=ttk.Spinbox(controls,from_=1,to=10000,width=6,textvariable=self.trials);self.trials_input.pack(side='left',padx=(7,14))
        self.label(controls,'초기 탐색').pack(side='left')
        self.startup=tk.StringVar(value=str(self.args.startup))
        self.startup_input=ttk.Spinbox(controls,from_=1,to=10000,width=5,textvariable=self.startup);self.startup_input.pack(side='left',padx=7)
        self.start_button=ttk.Button(controls,text='▶  시작',command=self.start);self.start_button.pack(side='left',padx=(14,5))
        self.pause_button=ttk.Button(controls,text='일시정지',command=self.pause,state='disabled');self.pause_button.pack(side='left',padx=5)
        self.stop_button=ttk.Button(controls,text='중지',command=self.stop,state='disabled');self.stop_button.pack(side='left',padx=5)
        ttk.Button(controls,text='최근 기록',command=self.load_latest).pack(side='right',padx=5)
        ttk.Button(controls,text='결과 폴더',command=self.open_folder).pack(side='right',padx=5)
        ttk.Button(controls,text='보고서 열기',command=self.open_report).pack(side='right',padx=5)
        self.cards={}
        row=tk.Frame(self.root,bg=BG);row.pack(fill='x',padx=16,pady=(0,10))
        for key,title,accent in [('trial','진행 시행',BLUE),('score','현재 최선 점수 ↓',TEAL),('feasible','전체 기준 통과',TEAL),('fom','최선 회로 FoM ↑',BLUE)]:
            box=tk.Frame(row,bg=PANEL,highlightbackground=LINE,highlightthickness=1);box.pack(side='left',expand=True,fill='both',padx=4)
            self.label(box,title,fg=MUTED,font=('Malgun Gothic',9)).pack(anchor='w',padx=15,pady=(9,1))
            v=self.label(box,'--',fg=accent,font=('Segoe UI',21,'bold'));v.pack(anchor='w',padx=15,pady=(0,7));self.cards[key]=v
        body=tk.Frame(self.root,bg=BG);body.pack(fill='both',expand=True,padx=20)
        right=tk.Frame(body,bg=PANEL,width=410);right.pack(side='right',fill='y',padx=(12,0));right.pack_propagate(False)
        plots=tk.Frame(body,bg=PANEL);plots.pack(side='left',fill='both',expand=True)
        self.figure=Figure(figsize=(9,4.8),dpi=100,facecolor=PANEL)
        self.axes=self.figure.subplots(2,2)
        self.phase_axis=self.axes[1,1].twinx()
        self.figure.subplots_adjust(left=.08,right=.90,top=.94,bottom=.09,wspace=.38,hspace=.43)
        self.canvas=FigureCanvasTkAgg(self.figure,master=plots)
        self.canvas.get_tk_widget().pack(fill='both',expand=True)
        notebook=ttk.Notebook(right);notebook.pack(fill='both',expand=True)
        metrics=tk.Frame(notebook,bg=PANEL);sizes=tk.Frame(notebook,bg=PANEL);logs=tk.Frame(notebook,bg=PANEL)
        notebook.add(metrics,text='목표 / 성능');notebook.add(sizes,text='소자 값');notebook.add(logs,text='실행 기록')
        self.label(metrics,'기준 회로 vs 현재 최선 회로',font=('Malgun Gothic',11,'bold')).pack(anchor='w',padx=12,pady=(12,4))
        self.label(metrics,'초기 회로는 DC 균형 조정 후 측정',fg=MUTED,font=('Malgun Gothic',8)).pack(anchor='w',padx=12,pady=(0,9))
        cols=('metric','base','best','target','state')
        self.metrics_tree=ttk.Treeview(metrics,columns=cols,show='headings',height=13)
        for col,title,width in [('metric','항목',113),('base','초기',68),('best','최선',68),('target','기준',68),('state','판정',48)]:
            self.metrics_tree.heading(col,text=title);self.metrics_tree.column(col,width=width,minwidth=40,anchor='w' if col=='metric' else 'center',stretch=True)
        self.metrics_tree.pack(fill='x',padx=8)
        self.metrics_tree.tag_configure('pass',foreground=TEAL);self.metrics_tree.tag_configure('fail',foreground=RED)
        self.detail=self.label(metrics,'아직 측정하지 않았습니다.',justify='left',anchor='nw',wraplength=340,fg=MUTED,font=('Malgun Gothic',9))
        self.detail.pack(fill='both',expand=True,padx=13,pady=14)
        self.label(metrics,'※ 수치 기준은 targets.json에 저장됩니다.\n범위는 50 mV 간격의 DC 검사입니다.\nPM은 단위 이득 피드백 기준입니다.',justify='left',fg=MUTED,font=('Malgun Gothic',8)).pack(anchor='w',padx=13,pady=(0,14))
        self.label(sizes,'현재 시행 / 최선 시행',font=('Malgun Gothic',11,'bold')).pack(anchor='w',padx=12,pady=12)
        self.sizes_tree=ttk.Treeview(sizes,columns=('name','current','best'),show='headings',height=12)
        for col,title,width in [('name','변수',113),('current','현재',105),('best','최선',105)]:
            self.sizes_tree.heading(col,text=title);self.sizes_tree.column(col,width=width,anchor='center')
        self.sizes_tree.pack(fill='x',padx=10)
        self.label(sizes,'W1=W2, W3=W4  |  L=1 um\nW3/W4는 매 시행 DC 균형으로 계산합니다.\nM7은 소자 2개 병렬: 총 폭 = 2 × W7.\n각 소자 폭 탐색 범위: 5~100 um.',justify='left',wraplength=330,fg=MUTED,font=('Malgun Gothic',9)).pack(anchor='w',padx=14,pady=15)
        self.log_text=tk.Text(logs,bg=PANEL,fg=MUTED,font=('Consolas',9),wrap='word',relief='flat',state='disabled')
        self.log_text.pack(fill='both',expand=True,padx=10,pady=10)
        foot=tk.Frame(self.root,bg=BG);foot.pack(side='bottom',fill='x',padx=22,pady=(10,12),before=body)
        self.stage_label=self.label(foot,'준비됨 · 실제 LTspice 결과만 표시합니다.',anchor='w',fg=MUTED,font=('Malgun Gothic',9));self.stage_label.pack(fill='x')
        self.progress=ttk.Progressbar(foot,mode='determinate');self.progress.pack(fill='x',pady=6)
        self.status_label=self.label(foot,'시뮬레이션 정상 실행과 목표 통과를 구분합니다.',anchor='w',fg=MUTED,font=('Malgun Gothic',8));self.status_label.pack(fill='x')
        self.update_mode()
        self.draw()
    def log(self,text):
        self.log_text.configure(state='normal');self.log_text.insert('end',time.strftime('%H:%M:%S')+'  '+text+'\n')
        if int(self.log_text.index('end-1c').split('.')[0])>1500:self.log_text.delete('1.0','301.0')
        self.log_text.see('end');self.log_text.configure(state='disabled')
    def update_mode(self):
        active=bool(self.run and self.run.thread and self.run.thread.is_alive())
        self.trials_input.configure(state='disabled' if active or self.mode.get()=='조건 충족까지 지속' else 'normal')
    def start(self):
        if self.run and self.run.thread and self.run.thread.is_alive(): return
        try:
            mode='until_pass' if self.mode.get()=='조건 충족까지 지속' else 'fixed'
            trials=int(self.trials.get()) if mode=='fixed' else 100;startup=int(self.startup.get())
            self.run=OptimizationRun(trials,startup,self.args.seed,self.events,mode=mode,prevent_sleep=self.prevent_sleep.get())
        except Exception as e: messagebox.showerror('설정 확인',str(e));return
        self.state=None;self.latest_params={};self.started_at=time.monotonic()
        self.start_button.configure(state='disabled');self.pause_button.configure(state='normal',text='일시정지');self.stop_button.configure(state='normal')
        self.trials_input.configure(state='disabled');self.startup_input.configure(state='disabled')
        self.mode_input.configure(state='disabled');self.sleep_input.configure(state='disabled')
        self.run.start();self.log(f'새 실행: '+('조건 충족까지 지속' if mode=='until_pass' else f'{trials}회')+f', 초기 탐색 {startup}회')
        self.draw()
    def pause(self):
        if not self.run: return
        if self.run.paused.is_set():
            self.run.paused.clear();self.pause_button.configure(text='일시정지');self.log('계속 진행')
        else:
            self.run.paused.set();self.pause_button.configure(text='계속 진행');self.stage_label.configure(text='일시정지 요청 · 현재 LTspice 해석 후 대기');self.log('일시정지 요청')
    def stop(self):
        if self.run:
            self.run.stop.set();self.run.paused.clear();self.stage_label.configure(text='중지 요청 · 현재 해석이 끝나면 기록을 보존하고 중지');self.log('중지 요청')
    def close(self):
        if self.run and self.run.thread and self.run.thread.is_alive():
            self.run.stop.set();self.run.paused.clear()
            self.stage_label.configure(text='현재 해석 종료와 기록 저장을 기다린 뒤 창을 닫습니다.')
            self.root.after(300,self.close_when_stopped)
        else: self.root.destroy()
    def close_when_stopped(self):
        if self.run.thread.is_alive(): self.root.after(300,self.close_when_stopped)
        else: self.root.destroy()
    def open_folder(self):
        folder=Path(self.state['folder']) if self.state else ROOT
        os.startfile(folder)
    def open_report(self):
        if not self.state:
            messagebox.showinfo('보고서','완료된 실행 기록을 먼저 선택해 주세요.');return
        try:
            from report_generator import find_existing_report
            result=find_existing_report(Path(self.state['folder'])/'session.json')
            if result: os.startfile(result['pdf'])
            else: messagebox.showinfo('보고서','완료된 새 실행은 PDF가 자동 생성됩니다. 이전 실행은 Generate_Report.bat로 생성할 수 있습니다.')
        except Exception as error: messagebox.showerror('보고서 열기',str(error))
    def load(self,path):
        if path.is_dir(): path=path/'session.json'
        try:
            self.state=json.loads(path.read_text(encoding='utf-8'));self.state['status']='saved record'
            self.log('저장된 실제 기록: '+str(path.parent));self.draw()
        except Exception as e: messagebox.showerror('기록 읽기',str(e))
    def load_latest(self,silent=False):
        if self.run and self.run.thread and self.run.thread.is_alive():
            if not silent: messagebox.showinfo('진행 중','실행을 마친 뒤 기록을 불러올 수 있습니다.')
            return
        paths=sorted((ROOT/'runs').glob('opt_*/session.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        if paths: self.load(paths[0])
        elif not silent: messagebox.showinfo('실행 기록','아직 저장된 최적화 기록이 없습니다.')
    def poll(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event['type']
                if kind=='stage':
                    trial=event['trial'];self.cards['trial'].configure(text=f'{trial} / '+('∞' if self.run.mode=='until_pass' else str(self.run.total)))
                    self.stage_label.configure(text=f'Trial {trial} · {event["phase"]} · {event["stage"]}')
                    self.log(f'#{trial} {event["stage"]}')
                elif kind=='trial_started':
                    self.latest_params=event['params'];self.update_sizes()
                elif kind in ('result','finished'):
                    self.state=event['state'];self.pending_draw=True
                    if kind=='result':
                        r=event['result'];self.log(f'#{r["trial"]} '+(f'score {r["score"]:.4g} | '+('PASS' if r['feasible'] else '조건 미달') if r['status']=='measured' else '실행 오류: '+r['error']))
                    else:
                        self.start_button.configure(state='normal');self.pause_button.configure(state='disabled');self.stop_button.configure(state='disabled')
                        self.startup_input.configure(state='normal');self.mode_input.configure(state='readonly');self.sleep_input.configure(state='normal');self.update_mode()
                        report_state=self.state.get('report_status','not_started')
                        suffix='PDF 보고서까지 저장했습니다.' if report_state=='ready' else ('보고서 생성 실패 · 실행 기록을 확인하세요.' if report_state=='failed' else '실행 기록을 저장했습니다.')
                        outcome='전체 조건 충족 · 자동 종료' if self.state.get('completion_reason')=='targets_met' else self.state['status']
                        self.stage_label.configure(text=outcome+' · '+suffix)
                        self.log('실행 종료: '+self.state['status'])
                elif kind=='report_started':
                    self.stage_label.configure(text='탐색 종료 · PDF 보고서를 생성하고 있습니다.')
                    self.log('PDF 보고서 생성 시작')
                elif kind=='report_ready':
                    self.log('보고서 저장: '+event['report']['pdf'])
                elif kind=='error': self.log('오류: '+event['message'])
                elif kind=='started': self.log('결과 폴더: '+event['folder'])
        except queue.Empty: pass
        if self.pending_draw and time.monotonic()-self.last_draw>.6:
            self.draw();self.pending_draw=False;self.last_draw=time.monotonic()
        self.root.after(150,self.poll)
    def update_sizes(self):
        self.sizes_tree.delete(*self.sizes_tree.get_children())
        best=(self.state or {}).get('best') or {}
        for key,label in [('W12','W1=W2 (um)'),('W34','W3=W4 (um)'),('W5','W5 (um)'),('W6','W6 (um)'),('W7','W7 each (um)'),('W8','W8 (um)'),('W9','W9 (um)'),('W10','W10 (um)'),('RZERO','Rz (ohm)'),('CCOMP','Cc (pF)')]:
            factor=1e6 if key.startswith('W') else (1e12 if key=='CCOMP' else 1)
            a=self.latest_params.get(key);b=best.get('params',{}).get(key)
            self.sizes_tree.insert('','end',values=(label,number(a*factor if a is not None else None),number(b*factor if b is not None else None)))
    def draw(self):
        state=self.state or {};history=state.get('history',[])
        results=[r for r in history if r['status']=='measured'];best=state.get('best');baseline=state.get('baseline')
        good=sum(bool(r['feasible']) for r in results);errors=sum(r['status']=='simulation_error' for r in history)
        continuous=state.get('mode')=='until_pass'
        total=state.get('total')
        self.cards['trial'].configure(text=f'{len(history)} / '+('∞' if continuous else str(total if total is not None else self.trials.get())))
        self.cards['score'].configure(text=number(best['score']) if best else '--')
        self.cards['feasible'].configure(text=f'{good} / {len(results)}')
        self.cards['fom'].configure(text=f'{best["fom"]/1e6:.1f} M' if best else '--')
        moving=continuous and state.get('status')=='running'
        if moving and not self.progress_running:
            self.progress.configure(mode='indeterminate');self.progress.start(40);self.progress_running=True
        elif not moving:
            if self.progress_running:self.progress.stop();self.progress_running=False
            self.progress.configure(mode='determinate',maximum=max(1,total or len(history) or 100),value=len(history))
        elapsed=state.get('elapsed_s',0);remaining=(elapsed/len(history)*(total-len(history))) if history and total and state.get('status')=='running' and not continuous else 0
        self.status_label.configure(text=f'측정 완료 {len(results)}  ·  실행 오류 {errors}  ·  전체 기준 통과 {good}  |  경과 {elapsed:.0f}s'+(f'  ·  예상 잔여 {remaining:.0f}s' if remaining else '')+'  |  FoM: gain(dB) × unity(Hz) / P(mW)')
        for ax in self.axes.flat: ax.clear()
        self.phase_axis.clear()
        self.phase_axis.yaxis.tick_right()
        self.phase_axis.yaxis.set_label_position('right')
        ax=self.axes[0,0];ax.set_title('Optimization history  /  lower score is better',loc='left',fontsize=10,fontweight='bold')
        ax.set_xlabel('Trial');ax.set_ylabel('Constraint score');ax.set_yscale('symlog',linthresh=1)
        ax.axhspan(0,1,color=TEAL,alpha=.08);ax.axhline(1,color=TEAL,ls='--',lw=.8)
        if results:
            x=[r['trial'] for r in results];y=[r['score'] for r in results]
            ax.scatter(x,y,c=[TEAL if r['feasible'] else '#94a3b8' for r in results],s=20,alpha=.65,label='Measured')
            ax.plot(x,np.minimum.accumulate(y),color=BLUE,lw=2,label='Best so far')
            ax.legend(fontsize=7,loc='upper right')
        else: ax.text(.5,.5,'Waiting for actual LTspice trials',transform=ax.transAxes,ha='center',color=MUTED,fontsize=10)
        ax=self.axes[0,1];ax.set_title('Baseline vs best  /  normalized to target',loc='left',fontsize=10,fontweight='bold')
        fields=[('Gain','low_frequency_gain_db',60,False),('UGF','f_unity_hz',1e6,False),('PM','phase_margin_unity_feedback_estimate_deg',60,False),('BW','f_3db_open_loop_hz',10000,False),('SR+','slew_rate_rise_v_per_us',10,False),('Power','power_mw',10,True)]
        y=np.arange(len(fields));ratios=[]
        for record,offset,color,label in [(baseline,-.17,'#cbd5e1','Baseline'),(best,.17,TEAL,'Best')]:
            values=[]
            for _,key,target,inverse in fields:
                value=record['metrics'].get(key) if record else None
                values.append((target/value if inverse else value/target) if value is not None and value>0 else 0)
            ax.barh(y+offset,np.minimum(values,2.5),height=.3,color=color,label=label)
            if label=='Best' and best:
                for yy,value in zip(y+offset,values): ax.text(min(value,2.5)+.04,yy,f'{value:.2g}x',va='center',fontsize=7,color=TEAL if value>=1 else RED)
        ax.set_yticks(y,[v[0] for v in fields]);ax.invert_yaxis();ax.axvline(1,color=RED,ls='--',lw=1)
        ax.set_xlim(0,3.2);ax.set_xlabel('1.0x = target; bars capped at 2.5x');ax.legend(fontsize=7,loc='lower right')
        ax=self.axes[1,0];ax.set_title('Gain / phase trade-off',loc='left',fontsize=10,fontweight='bold');ax.set_xlabel('DC gain (dB)');ax.set_ylabel('Phase margin (deg)')
        plotted=[r for r in results if r['metrics']['phase_margin_unity_feedback_estimate_deg'] is not None]
        ax.scatter([r['metrics']['low_frequency_gain_db'] for r in plotted],
                   [r['metrics']['phase_margin_unity_feedback_estimate_deg'] for r in plotted],
                   s=28,c=[TEAL if r['feasible'] else '#94a3b8' for r in plotted],alpha=.6)
        ax.axvline(60,color=RED,ls='--',lw=.8);ax.axhline(60,color=RED,ls='--',lw=.8)
        if best and best['metrics']['phase_margin_unity_feedback_estimate_deg'] is not None:
            ax.scatter(best['metrics']['low_frequency_gain_db'],best['metrics']['phase_margin_unity_feedback_estimate_deg'],marker='*',s=200,c=AMBER,edgecolors='white',zorder=5,label='Best candidate');ax.legend(fontsize=7)
        ax=self.axes[1,1];ax.set_title('Best candidate  /  frequency response',loc='left',fontsize=10,fontweight='bold')
        ax.set_xlabel('Frequency (Hz)');ax.set_ylabel('Gain (dB)',color=BLUE);self.phase_axis.set_ylabel('Phase (deg)',color=TEAL)
        if best:
            try:
                curve=np.loadtxt(Path(best['folder'])/'bode.csv',delimiter=',',skiprows=1)
                ax.semilogx(curve[:,0],curve[:,1],color=BLUE,lw=1.6)
                self.phase_axis.semilogx(curve[:,0],curve[:,2],color=TEAL,lw=1.2,alpha=.8)
                ax.axhline(0,color=LINE,lw=1);self.phase_axis.axhline(-180,color=RED,ls=':',lw=.8)
            except (OSError,ValueError): pass
        for ax in self.axes.flat:
            ax.set_facecolor(PANEL);ax.grid(alpha=.18,color='#94a3b8');ax.tick_params(labelsize=8)
            for spine in ax.spines.values(): spine.set_color(LINE)
        self.phase_axis.tick_params(labelsize=8)
        self.canvas.draw_idle()
        self.metrics_tree.delete(*self.metrics_tree.get_children())
        if best:
            old={r['name']:r for r in baseline['checks']} if baseline else {}
            for row in best['checks']:
                self.metrics_tree.insert('','end',values=(row['name']+({'Power':' (mW)','DC gain':' (dB)','Phase margin':' (deg)','SR rise':' (V/us)','SR fall':' (V/us)','ICMR':' (V)','OCMR':' (V)'}.get(row['name'],'')),number(old.get(row['name'],{}).get('value'),row['unit']),number(row['value'],row['unit']),number(row['target'],row['unit']),row['status'].upper()),tags=(row['status'],))
            fails=[r['name'] for r in best['checks'] if r['status']=='fail']
            text=('전체 수치 검사 통과' if not fails else '아직 미달: '+', '.join(fails))
            text+='\n\n최선 시행 #'+str(best['trial'])+'\n'+f'시행 소요 {best["elapsed_s"]:.1f}s'
            text+='\n\n점수는 작을수록 좋습니다.\n1 미만이면 모든 수치 검사 통과,\n1 이상이면 미달 항목이 있습니다.'
            text+='\n\nDC 균형 허용오차 1 mV,\n범위 검사 기준은 조정 가능합니다.'
            self.detail.configure(text=text)
        self.update_sizes()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials',type=int,default=100);parser.add_argument('--startup',type=int,default=20);parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--session',type=Path);parser.add_argument('--autostart',action='store_true')
    parser.add_argument('--mode',choices=('fixed','until_pass'),default='fixed')
    args=parser.parse_args();root=tk.Tk();Dashboard(root,args);root.mainloop()

if __name__=='__main__': main()
