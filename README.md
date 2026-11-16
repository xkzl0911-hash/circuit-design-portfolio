# 김의연 회로설계 포트폴리오

디지털 논리회로, 증폭기, 메모리, CMOS 이미지 센서 설계 프로젝트입니다.

## Digital · Analog · Memory

| 프로젝트 | 설계 내용 | 보고서 |
|---|---|---|
| Advanced FSM Design | 현재·과거 상태를 기억하는 FSM과 Basys3 보드 구현 | [PDF](reports/Digital/Advanced%20FSM%20Design.pdf) · [본문](reports/Digital/Advanced%20FSM%20Design.txt) |
| CMOS Logic Design Comparison | LBD·FCD·PLD 방식의 논리회로와 전력·지연·면적 비교 | [PDF](reports/Digital/CMOS%20Logic%20Design%20Comparison.pdf) · [본문](reports/Digital/CMOS%20Logic%20Design%20Comparison.txt) |
| FSM Chip Design | 입력 처리·상태 메모리·출력 회로·I/O 패드를 포함한 칩 설계 | [PDF](reports/Digital/FSM%20Chip%20Design.pdf) · [본문](reports/Digital/FSM%20Chip%20Design.txt) |
| Single-Stage Amplifier Design | MOS 소신호 해석과 단일단 증폭기 설계 | [PDF](reports/Analog/Single-Stage%20Amplifier%20Design.pdf) · [본문](reports/Analog/Single-Stage%20Amplifier%20Design.txt) |
| Multistage and Differential Amplifier Design | 다단 증폭기와 차동 증폭기의 바이어스·이득·입출력 범위 분석 | [PDF](reports/Analog/Multistage%20and%20Differential%20Amplifier%20Design.pdf) · [본문](reports/Analog/Multistage%20and%20Differential%20Amplifier%20Design.txt) |
| Two-Stage Op-Amp Design | 주파수 보상과 반전 증폭기·저역통과필터 응용 | [PDF](reports/Analog/Two-Stage%20Op-Amp%20Design.pdf) · [본문](reports/Analog/Two-Stage%20Op-Amp%20Design.txt) |
| 6T and 7T SRAM Design | SRAM 셀·주변회로 설계와 전력·지연·면적 비교 | [PDF](reports/Memory/6T%20and%207T%20SRAM%20Design.pdf) · [본문](reports/Memory/6T%20and%207T%20SRAM%20Design.txt) |
| 1K DRAM Architecture | 1024bit DRAM의 8×8·8×4 셀 배열 구성 비교 | [PDF](reports/Memory/1K%20DRAM%20Architecture.pdf) · [본문](reports/Memory/1K%20DRAM%20Architecture.txt) |

## CMOS Image Sensor

4×4 픽셀의 출력을 두 채널의 5bit 파이프라인 ADC로 변환하고, 80bit SRAM에 저장한 뒤 5bit 출력 레지스터로 읽는 회로입니다.

- **구성:** 16개 픽셀, 3bit+2bit ADC, 80bit SRAM, 5bit 출력 레지스터
- **기능 검증:** TT·27°C에서 LOW/HIGH 두 프레임, 총 32개 입력 코드 확인
- **레이아웃:** 724×687µm, 초기 대비 면적 43.68% 감소, LVS 일치
- **추가 검증:** 패드·밀도 DRC 항목, PVT·PEX·노이즈·미스매치

[회로와 시뮬레이션](reports/CIS/4x4%20CMOS%20Image%20Sensor.md) · [Word 보고서](reports/CIS/4x4%20CMOS%20Image%20Sensor.docx)

## SRAM-CIM Accelerator

8T SRAM 기반 연산과 온칩 학습 회로의 설계안입니다. 고정소수점 연산, 가중치 갱신, 단계적 비트 읽기를 다룹니다.

[프로젝트 개요](reports/CIM/SRAM-CIM%20Accelerator.md) · [설계기획서 PDF](reports/CIM/SRAM-CIM%20Accelerator%20Proposal.pdf)

## 설계 도구

Cadence Virtuoso · Spectre · LTspice · Verilog · Python

공동 과제의 참여자와 기여도는 각 보고서에 기재했습니다.
