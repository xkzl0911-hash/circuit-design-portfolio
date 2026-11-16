from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--pdk', action='store_true')
args = parser.parse_args()

root = Path(__file__).resolve().parent
lines = ['Version 4', 'SHEET 1 1680 1240']
def wire(x1,y1,x2,y2): lines.append(f'WIRE {x1} {y1} {x2} {y2}')
def flag(x,y,name): lines.append(f'FLAG {x} {y} {name}')
def symbol(kind,x,y,rot,name,value,extra=None):
    lines.append(f'SYMBOL {kind} {x} {y} {rot}')
    lines.extend([f'SYMATTR InstName {name}',f'SYMATTR Value {value}'])
    if extra: lines.append(f'SYMATTR SpiceLine {extra}')

# Same source/drain orientation as the supplied drawing.
mos = [
 ('pmos',368,400,'M180','M1','PDEMO','W=40u L=1u'),
 ('pmos',720,400,'R180','M2','PDEMO','W=40u L=1u'),
 ('nmos',464,496,'M0','M3','NDEMO','W=40u L=1u'),
 ('nmos',624,496,'R0','M4','NDEMO','W=40u L=1u'),
 ('pmos',496,240,'M180','M5','PDEMO','W=40u L=1u'),
 ('pmos',1008,240,'M180','M6','PDEMO','W=80u L=1u'),
 ('nmos',1008,400,'R0','M7','NDEMO','W=160u L=1u'),
 ('pmos',208,240,'R180','M8','PDEMO','W=20u L=1u'),
 ('nmos',208,288,'M0','M9','NDEMO','W=2u L=1u'),
 ('nmos',208,512,'M0','M10','NDEMO','W=2u L=1u'),
]
segments = [
 (160,96,1056,96),(160,96,160,144),(544,96,544,144),(1056,96,1056,144),
 (208,160,1008,160),(256,160,256,368),(256,240,160,240),(160,240,160,288),
 (208,368,256,368),(160,384,160,512),
 (160,512,256,512),(256,512,256,592),(208,592,256,592),(160,608,160,640),
 (544,240,544,272),(416,272,672,272),(416,272,416,304),(672,272,672,304),
 (320,320,368,320),(720,320,768,320),
 (416,400,416,496),(672,400,672,496),
 (416,448,512,448),(512,448,512,576),(464,576,624,576),
 (416,592,416,640),(672,592,672,640),
 (672,448,864,448),(864,448,864,480),(864,480,1008,480),
 (864,448,864,352),(944,352,976,352),(1040,352,1280,352),
 (1056,240,1056,352),(1056,352,1056,400),(1056,496,1056,640),
 (1280,416,1280,640),(160,640,1280,640),
]
for s in segments: wire(*s)
for x,y,n in [(544,96,'VDDA'),(256,160,'Vbp'),(160,448,'Vbn'),(544,272,'Vx'),
              (320,320,'VIN1'),(768,320,'VIN2'),(672,448,'Vo1'),(1216,352,'VOUT'),(544,640,'0')]:
    # VOUT is on the continuous compensation/load wire.
    flag(x,y,n)
for m in mos:
    if not args.pdk:
        symbol(*m)
        continue
    kind,x,y,rot,name,_,_ = m
    width = {'M1':'W12','M2':'W12','M3':'W34','M4':'W34'}.get(name, 'W'+name[1:])
    multiplier = ' M=2' if name == 'M7' else ''
    symbol(kind+'4', x,y,rot,name, 'pch_33' if kind == 'pmos' else 'nch_33',
           f'W={{{width}}} L={{LCH}}'+multiplier)
    # Explicit well/substrate connections, separate from source.
    bx = x + (48 if rot in ('R0','M180') else -48)
    by = y + (48 if rot in ('R0','M0') else -48)
    dx = 32 if rot in ('R0','M180') else -32
    wire(bx,by,bx+dx,by)
    flag(bx+dx,by,'VDDA' if kind == 'pmos' else '0')
symbol('res',960,336,'R90','Rz','{RZERO}')
symbol('cap',1040,336,'R90','Cc','{CCOMP}')
symbol('cap',1264,352,'R0','CL','{CLOAD}' if args.pdk else '5p')

# Independent supplies and differential small-signal drive.
for x,name,node,value in [(160,'VDD','VDDA','{VSUPPLY}'),
                          (448,'VIN_MINUS','VIN1','DC {VCM} AC 0.5 180'),
                          (736,'VIN_PLUS','VIN2','DC {VCM} AC 0.5')]:
    wire(x,768,x,784)
    flag(x,768,node)
    wire(x,864,x,896)
    flag(x,896,'0')
    symbol('voltage',x,768,'R0',name,value)
texts = [
 (96,24,';Two-stage CMOS amplifier - reconstructed from supplied image'),
 (96,688,';DEMO VALUES: only CL=5p is specified in the reference image.'),
 (96,720,';3-terminal MOS symbols: bulk tied to source. Replace with PDK devices for IC verification.'),
 (96,960,'!.param VSUPPLY=3.3 VCM=1.2 RZERO=1k CCOMP=1p'),
 (96,1000,'!.model NDEMO NMOS (LEVEL=1 VTO=0.5 KP=100u LAMBDA=0.02)'),
 (96,1040,'!.model PDEMO PMOS (LEVEL=1 VTO=-0.5 KP=50u LAMBDA=0.02)'),
 (96,1080,'!.op'),
 (96,1120,'!.ac dec 100 0.01 1G'),
 (96,1160,';Plot V(vout)/(V(vin2)-V(vin1)) for differential open-loop gain.'),
]
if args.pdk:
    model_path = root/'models/1533IL11SK_Rev3p0.l'
    if not model_path.is_file(): raise FileNotFoundError(model_path)
    texts = [
        (96,24,';Two-stage CMOS amplifier - DB HiTek 3.3V / TT / L=1um'),
        (96,688,';STARTING SIZES, NOT OPTIMIZED. M7 uses two parallel devices; effective width = 2*W7.'),
        (96,720,';Bulk assumption: all PMOS wells to VDDA, all NMOS bodies to ground. CL=10p fixed.'),
        (96,960,'!.param VSUPPLY=3.3 VCM={VSUPPLY/2} LCH=1u RZERO=1k CCOMP=2.2p CLOAD=10p'),
        (96,1000,'!.param W12=40u W34=40u W5=40u W6=80u W7=80u W8=20u W9=5u W10=5u'),
        (96,1040,f'!.lib "{model_path.as_posix()}" tt_33'),
        (96,1080,'!.op'),
        (96,1120,'!.ac dec 100 0.01 1G'),
        (96,1160,'!.temp 25'),
        (96,1200,';Differential gain: V(vout)/(V(vin2)-V(vin1)). VIN2 is non-inverting; VIN1 is inverting.'),
    ]
for x,y,t in texts: lines.append(f'TEXT {x} {y} Left 2 {t}')
output = 'two_stage_cmos_3v3_pdk.asc' if args.pdk else 'two_stage_cmos.asc'
(root/output).write_text('\n'.join(lines)+'\n',encoding='ascii')
