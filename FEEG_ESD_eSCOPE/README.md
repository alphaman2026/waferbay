# FEEG_ESD_eSCOPE

BIGTREETECH SKR mini E3 (Marlin 펌웨어) 제어 + Analog Discovery 2 파형 표시 PC 프로그램.

## 기능
- USB Serial 로 SKR mini E3(Marlin) 연결 (기본 115200 baud)
- UART 메시지 콘솔 (송신/수신 컬러 표시, 수동 G-code 입력)
- X / Y / Z 스테퍼 모터 조그 제어 (0.1 / 1 / 10 mm, 기본 1 mm)
- Analog Discovery 2 자동 감지 및 연결 상태 표시등
- CH1 전압 파형 실시간 표시 (X축: 시간, Y축: 전압)
- 하드웨어 없이 확인 가능한 데모 모드(합성 파형)

## 실행 방법
```bash
pip install -r requirements.txt
python FEEG_ESD_eSCOPE.py
```

Analog Discovery 2 를 사용하려면 Digilent **WaveForms**(SDK 포함)를 설치해야 합니다.
https://digilent.com/shop/software/digilent-waveforms/

## 문서
- 사용 설명서: [`../docs/user_manual.html`](../docs/user_manual.html)
- 코드 설명서: [`../docs/code_manual.html`](../docs/code_manual.html)
