# Optuna 기반 OP-Amp 스펙 최적화

[PDF](results/Optuna%20Op-Amp%20Optimization.pdf) · [Python 코드](optimizer.py) · [회로도](results/best_candidate.asc) · [측정 데이터](results/data/)

| 항목 | 내용 |
|---|---|
| 회로 | PMOS 입력 2단 OP-Amp, Rz·Cc 보상 |
| 조건 | 3.3 V, L=1 µm, CL=10 pF, TT·25°C |
| 탐색 | Optuna TPE, MOS 폭 7개와 Rz·Cc 조정 |
| DC 균형 | 각 후보에서 W3=W4를 별도 조정 |
| 평가 | 이득·UGF·위상여유·전력·대역폭·SR·ICMR·OCMR·포화 여유 |

## 100회 탐색 결과

정상 측정 82회, 제외·실패 18회. 전체 조건 통과 0개. 최선 후보는 94번째 시행.

| 측정 항목 | 최선 후보 |
|---|---:|
| DC 이득 | 78.59 dB |
| UGF | 44.96 MHz |
| 위상여유 추정값 | 73.05° |
| 소비전력 | 3.567 mW |
| SR 상승 / 하강 | 37.40 / 116.24 V/µs |
| −3 dB 대역폭 | 6.065 kHz (목표 10 kHz 미달) |
| 최소 MOS 포화 여유 | −0.027 V (미달) |

![탐색 이력](results/figures/learning_history.png)

![주파수 응답](results/figures/frequency_response.png)

보고서는 저장된 100회 실행 결과다. 코드는 이후 실행 제어 기능을 추가한 버전이다. 검증 범위는 TT·25°C이며 PVT·미스매치 검증은 수행하지 않았다.

## 실행

Windows, Python, LTspice가 필요하다. 공정 모델은 별도 준비한다.

- 모델 경로: `models/1533IL11SK_Rev3p0.l` 및 모델이 참조하는 파일. 경로가 다르면 `two_stage_cmos_3v3_pdk.asc`의 `.lib`를 수정한다.
- LTspice 경로: `measure_baseline.py`의 `DEFAULT_EXE`.
- 목표 스펙: [targets.json](targets.json).

```powershell
python -m pip install -r requirements.txt
python live_dashboard.py
```

명령줄에서 100회 실행:

```powershell
python optimizer.py --mode fixed --trials 100 --startup 20
```

LTspice를 호출하지 않는 코드 검사:

```powershell
python -m unittest -v test_measurements test_run_modes test_reports
```
