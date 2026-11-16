# 김의연 회로설계 포트폴리오

디지털·아날로그·메모리 회로 과제와 CMOS 이미지 센서(CIS), SRAM-CIM 기반 AI 가속기 설계 작업을 모았습니다. 원본 보고서와 회로 그림, 검색 가능한 본문을 아래에서 열람할 수 있습니다.

## 주요 설계 작업

| 프로젝트 | 설계 내용 | 확인된 결과와 범위 |
|---|---|---|
| 4×4 CMOS 이미지 센서 | 16개 픽셀, odd/even 5bit 3+2 파이프라인 ADC, 80bit SRAM, Q4~Q0 출력 DFF, 물리 바이어스·PLL·타이밍 회로 | LOW/HIGH 두 프레임으로 32개 입력 코드에 대해 native Spectre TT27 nominal·엄격 수치 설정 검증 통과 |
| CIS 물리 구현 | KIM_SS2 CIS5 칩의 계층 레이아웃과 면적 압축 | 최종 724×687µm, 초기 920×960µm 대비 면적 43.68% 감소. native schematic LVS CORRECT, ERC·antenna 0 |
| SRAM-CIM / AI 가속기 | SRAM 저장 셀, MAC, 고정소수점 골든모델, 트랜지스터 수준 학습·holdout 검증 | 단계별 연구 진행 자료. 아래 설계기획서는 계획 문서이며 전체 과제 완료 또는 성능 확정을 의미하지 않음 |

CIS의 기능 검증은 TT 조건의 결과입니다. PVT·노이즈·미스매치·PEX·EMIR은 미완료이며, 물리 구현에는 패드·밀도 DRC 잔여 항목이 있어 전체 sign-off 완료로 주장하지 않습니다. 원본 보고서는 작성 시점의 설계 상태를 기록합니다.

## CIS 회로설계 보고서

- [LOW/HIGH 보고서 본문과 회로 그림](reports/CIS5/KIM_SS2_%ED%9A%8C%EB%A1%9C%EC%84%A4%EA%B3%84_%EB%B3%B4%EA%B3%A0%EC%84%9C_LOW_HIGH.md)
- [원본 Word 보고서 다운로드](reports/CIS5/KIM_SS2_%ED%9A%8C%EB%A1%9C%EC%84%A4%EA%B3%84_%EB%B3%B4%EA%B3%A0%EC%84%9C_LOW_HIGH.docx)

## 디지털·아날로그·메모리 과제

공동 과제의 참여자 이름은 각 원본 표기를 따릅니다. 이름에 '복사본'이 있는 자료도 사용자가 제공한 별도 파일 그대로 보존했습니다.

| 분야 | 원본 PDF | 검색용 본문 |
|---|---|---|
| 디지털회로 | [디지털_1차과제_김의연전솔빈](reports/%EB%94%94%EC%A7%80%ED%84%B8%ED%9A%8C%EB%A1%9C/%EB%94%94%EC%A7%80%ED%84%B8_1%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0%EC%A0%84%EC%86%94%EB%B9%88.pdf) | [텍스트](reports/%EB%94%94%EC%A7%80%ED%84%B8%ED%9A%8C%EB%A1%9C/%EB%94%94%EC%A7%80%ED%84%B8_1%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0%EC%A0%84%EC%86%94%EB%B9%88_text.txt) |
| 디지털회로 | [디지털_2차과제_김의연_전솔빈](reports/%EB%94%94%EC%A7%80%ED%84%B8%ED%9A%8C%EB%A1%9C/%EB%94%94%EC%A7%80%ED%84%B8_2%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%A0%84%EC%86%94%EB%B9%88.pdf) | [텍스트](reports/%EB%94%94%EC%A7%80%ED%84%B8%ED%9A%8C%EB%A1%9C/%EB%94%94%EC%A7%80%ED%84%B8_2%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%A0%84%EC%86%94%EB%B9%88_text.txt) |
| 디지털회로 | [디지털_3차과제_김의연_전솔빈](reports/%EB%94%94%EC%A7%80%ED%84%B8%ED%9A%8C%EB%A1%9C/%EB%94%94%EC%A7%80%ED%84%B8_3%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%A0%84%EC%86%94%EB%B9%88.pdf) | [텍스트](reports/%EB%94%94%EC%A7%80%ED%84%B8%ED%9A%8C%EB%A1%9C/%EB%94%94%EC%A7%80%ED%84%B8_3%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%A0%84%EC%86%94%EB%B9%88_text.txt) |
| 아날로그 | [아날로그_HW1_김의연_오연재 - 복사본](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW1_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC%20-%20%EB%B3%B5%EC%82%AC%EB%B3%B8.pdf) | [텍스트](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW1_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC%20-%20%EB%B3%B5%EC%82%AC%EB%B3%B8_text.txt) |
| 아날로그 | [아날로그_HW1_김의연_오연재](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW1_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC.pdf) | [텍스트](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW1_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC_text.txt) |
| 아날로그 | [아날로그_HW2_김의연_오연재 - 복사본](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW2_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC%20-%20%EB%B3%B5%EC%82%AC%EB%B3%B8.pdf) | [텍스트](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW2_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC%20-%20%EB%B3%B5%EC%82%AC%EB%B3%B8_text.txt) |
| 아날로그 | [아날로그_HW2_김의연_오연재](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW2_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC.pdf) | [텍스트](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW2_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC_text.txt) |
| 아날로그 | [아날로그_HW3_김의연_오연재 - 복사본](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW3_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC%20-%20%EB%B3%B5%EC%82%AC%EB%B3%B8.pdf) | [텍스트](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW3_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC%20-%20%EB%B3%B5%EC%82%AC%EB%B3%B8_text.txt) |
| 아날로그 | [아날로그_HW3_김의연_오연재](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW3_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC.pdf) | [텍스트](reports/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8/%EC%95%84%EB%82%A0%EB%A1%9C%EA%B7%B8_HW3_%EA%B9%80%EC%9D%98%EC%97%B0_%EC%98%A4%EC%97%B0%EC%9E%AC_text.txt) |
| 메모리 | [메모리_1차과제_김의연오연재](reports/%EB%A9%94%EB%AA%A8%EB%A6%AC/%EB%A9%94%EB%AA%A8%EB%A6%AC_1%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0%EC%98%A4%EC%97%B0%EC%9E%AC.pdf) | [텍스트](reports/%EB%A9%94%EB%AA%A8%EB%A6%AC/%EB%A9%94%EB%AA%A8%EB%A6%AC_1%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0%EC%98%A4%EC%97%B0%EC%9E%AC_text.txt) |
| 메모리 | [메모리_2차과제_김의연오연재](reports/%EB%A9%94%EB%AA%A8%EB%A6%AC/%EB%A9%94%EB%AA%A8%EB%A6%AC_2%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0%EC%98%A4%EC%97%B0%EC%9E%AC.pdf) | [텍스트](reports/%EB%A9%94%EB%AA%A8%EB%A6%AC/%EB%A9%94%EB%AA%A8%EB%A6%AC_2%EC%B0%A8%EA%B3%BC%EC%A0%9C_%EA%B9%80%EC%9D%98%EC%97%B0%EC%98%A4%EC%97%B0%EC%9E%AC_text.txt) |

## AI 가속기 연구

- [AI-CIM 논문연구 설계기획서](reports/AI/AI_CIM_%EB%85%BC%EB%AC%B8%EC%97%B0%EA%B5%AC_%EC%84%A4%EA%B3%84%EA%B8%B0%ED%9A%8D%EC%84%9C.pdf)
- [설계기획서 텍스트](reports/AI/AI_CIM_%EB%85%BC%EB%AC%B8%EC%97%B0%EA%B5%AC_%EC%84%A4%EA%B3%84%EA%B8%B0%ED%9A%8D%EC%84%9C_text.txt)

## 도구와 자료 안내

Cadence Virtuoso·Spectre, LTspice, Python, SKILL, Git을 활용했습니다. 이 저장소는 공개 열람용 보고서와 소개 자료를 담습니다. 공정 PDK 원본·접속 설정·서버 로그·전체 시뮬레이션 원시 데이터는 공개 자료에 포함하지 않았습니다.

PDF는 원본 그대로이며, 자동 추출 텍스트는 수식·그림·읽기 순서를 완전히 재현하지 못할 수 있습니다. 정확한 도표와 회로는 원본 PDF 또는 Word 보고서를 기준으로 확인해 주세요.

자료 정리: 2026-11-16. 별도의 재배포 라이선스를 부여하지 않습니다.
