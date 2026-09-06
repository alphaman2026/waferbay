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

### Windows — 원클릭 실행
1. [python.org](https://www.python.org/downloads/) 에서 Python 3.9+ 설치 ("Add Python to PATH" 체크)
2. **`run_windows.bat` 더블클릭** — 필요한 패키지를 자동 설치하고 프로그램을 실행합니다.

### Windows — 단일 EXE 만들기 (Python 없는 PC 배포용)
**`build_exe.bat` 더블클릭** → `dist\FEEG_ESD_eSCOPE.exe` 가 생성됩니다.
이 EXE 파일 하나만 복사하면 Python 이 없는 PC 에서도 더블클릭으로 실행됩니다.

### Linux / macOS
```bash
./run_linux_mac.sh
```
Linux 에서 시리얼 포트 권한 오류가 나면: `sudo usermod -aG dialout $USER` 후 재로그인.

### 수동 실행
```bash
pip install -r requirements.txt
python FEEG_ESD_eSCOPE.py
```

Analog Discovery 2 를 사용하려면 Digilent **WaveForms**(SDK 포함)를 설치해야 합니다.
https://digilent.com/shop/software/digilent-waveforms/

## 문서
- 사용 설명서: [`../docs/user_manual.html`](../docs/user_manual.html)
- 코드 설명서: [`../docs/code_manual.html`](../docs/code_manual.html)
