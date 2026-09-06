# -*- coding: utf-8 -*-
"""
marlin_serial.py — Marlin 펌웨어(BIGTREETECH SKR mini E3) USB 시리얼 통신 모듈

FEEG_ESD_eSCOPE 의 하위 모듈로, 다음 기능을 담당한다.
  * 사용 가능한 시리얼 포트 검색
  * USB 시리얼 연결 / 해제 (기본 115200 baud, Marlin 기본값)
  * 백그라운드 수신 스레드 : 보드가 보내는 모든 UART 메시지를 큐에 적재
  * G-code 송신 (조그 이동, 홈, 임의 명령)

GUI 와의 결합을 피하기 위해 이 모듈은 tkinter 를 전혀 알지 못한다.
수신된 문자열은 rx_queue 에, 송신 에코는 tx 콜백(옵션)으로 전달된다.
"""

import threading
import queue
import time

import serial
import serial.tools.list_ports

# SKR mini E3 (Marlin) 에서 흔히 쓰는 보레이트 목록
BAUD_RATES = [115200, 250000, 57600, 38400, 19200, 9600]
DEFAULT_BAUD = 115200


def list_serial_ports():
    """현재 PC 에 연결된 시리얼 포트 이름 목록을 돌려준다. (예: COM3, /dev/ttyACM0)"""
    return [p.device for p in serial.tools.list_ports.comports()]


class MarlinSerial:
    """Marlin 보드와의 시리얼 연결 하나를 관리하는 클래스."""

    def __init__(self):
        self._ser = None                 # serial.Serial 인스턴스
        self._rx_thread = None           # 수신 스레드
        self._running = False            # 수신 스레드 동작 플래그
        self.rx_queue = queue.Queue()    # 수신 라인 큐 (GUI 가 폴링)

    # ------------------------------------------------------------------ 연결
    @property
    def is_connected(self):
        return self._ser is not None and self._ser.is_open

    def connect(self, port, baud=DEFAULT_BAUD):
        """지정한 포트/보레이트로 연결하고 수신 스레드를 시작한다."""
        self.disconnect()
        self._ser = serial.Serial(port=port, baudrate=baud, timeout=0.1)
        # 보드에 따라 DTR 토글로 리셋되며 부팅 메시지가 올라온다.
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()
        self.rx_queue.put(("info", f"[연결됨] {port} @ {baud} baud"))

    def disconnect(self):
        """수신 스레드를 멈추고 포트를 닫는다. 연결이 없으면 아무것도 하지 않는다."""
        self._running = False
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=1.0)
            self._rx_thread = None
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None
                self.rx_queue.put(("info", "[연결 해제됨]"))

    # ------------------------------------------------------------------ 수신
    def _rx_loop(self):
        """백그라운드 스레드: 보드가 보내는 모든 라인을 rx_queue 에 넣는다."""
        buf = b""
        while self._running:
            try:
                data = self._ser.read(256)
            except (serial.SerialException, OSError):
                # 케이블 분리 등으로 포트가 사라진 경우
                self.rx_queue.put(("error", "[오류] 시리얼 포트가 끊어졌습니다."))
                self._running = False
                break
            if data:
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").rstrip("\r")
                    if text:
                        self.rx_queue.put(("rx", text))
            else:
                time.sleep(0.01)

    # ------------------------------------------------------------------ 송신
    def send_gcode(self, gcode):
        """G-code 한 줄을 전송한다. 송신 내용도 큐에 에코로 넣어 콘솔에 보이게 한다."""
        if not self.is_connected:
            self.rx_queue.put(("error", "[오류] 보드가 연결되어 있지 않습니다."))
            return False
        line = gcode.strip()
        if not line:
            return False
        try:
            self._ser.write((line + "\n").encode("ascii", errors="replace"))
        except (serial.SerialException, OSError):
            self.rx_queue.put(("error", "[오류] 전송 실패 — 연결을 확인하세요."))
            return False
        self.rx_queue.put(("tx", line))
        return True

    # ------------------------------------------------------- 모터 제어 명령
    def jog(self, axis, distance_mm, feedrate_mm_min=1200):
        """
        지정 축(axis: 'X'|'Y'|'Z')을 distance_mm 만큼 상대 이동시킨다.

        Marlin 은 G91(상대 좌표) → G0 이동 → G90(절대 좌표 복귀) 순서로 보내는
        것이 안전하다. 기본 이송 속도는 1200 mm/min (= 20 mm/s).
        """
        axis = axis.upper()
        if axis not in ("X", "Y", "Z"):
            raise ValueError("axis 는 X, Y, Z 중 하나여야 합니다.")
        ok = self.send_gcode("G91")                                   # 상대 좌표 모드
        ok &= self.send_gcode(f"G0 {axis}{distance_mm:g} F{feedrate_mm_min:d}")
        ok &= self.send_gcode("G90")                                  # 절대 좌표 복귀
        return ok

    def home(self, axes=""):
        """홈 이동. axes 가 빈 문자열이면 전체(G28), 'X' 등이면 해당 축만."""
        cmd = "G28" if not axes else "G28 " + " ".join(a.upper() for a in axes)
        return self.send_gcode(cmd)

    def disable_steppers(self):
        """모든 스테퍼 모터 전원 해제(M84). 손으로 축을 움직일 때 사용."""
        return self.send_gcode("M84")

    def get_position(self):
        """현재 위치 보고 요청(M114). 결과는 수신 콘솔에 표시된다."""
        return self.send_gcode("M114")
