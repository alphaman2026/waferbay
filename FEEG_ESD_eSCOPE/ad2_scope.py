# -*- coding: utf-8 -*-
"""
ad2_scope.py — Analog Discovery 2 (Digilent) 오실로스코프 모듈

FEEG_ESD_eSCOPE 의 하위 모듈로, 다음 기능을 담당한다.
  * WaveForms SDK(dwf 라이브러리) 로드 — Windows / Linux / macOS 자동 판별
  * Analog Discovery 2 장치 감지(핫플러그 폴링용 enum) 및 연결/해제
  * Scope(AnalogIn) 단발 획득을 반복 실행하는 백그라운드 스레드
  * 획득한 전압 배열 + 샘플 주기를 큐로 GUI 에 전달

WaveForms SDK 가 설치되어 있지 않은 PC 에서도 프로그램 자체는 실행되도록,
SDK 로드 실패 시 sdk_available = False 로만 표시한다.
데모 모드(하드웨어 없이 합성 파형 표시)도 제공한다.
"""

import ctypes
import math
import queue
import random
import sys
import threading
import time

# ---------------------------------------------------------------- SDK 로드
_dwf = None
_sdk_error = None

def _load_dwf():
    """플랫폼별 dwf 공유 라이브러리를 로드한다. 실패하면 None."""
    global _dwf, _sdk_error
    if _dwf is not None:
        return _dwf
    try:
        if sys.platform.startswith("win"):
            _dwf = ctypes.cdll.dwf                       # dwf.dll (WaveForms 설치 시 PATH 등록)
        elif sys.platform == "darwin":
            _dwf = ctypes.cdll.LoadLibrary(
                "/Library/Frameworks/dwf.framework/dwf")
        else:
            _dwf = ctypes.cdll.LoadLibrary("libdwf.so")  # Linux (Adept Runtime + WaveForms)
    except OSError as e:
        _sdk_error = str(e)
        _dwf = None
    return _dwf


def sdk_available():
    """WaveForms SDK 사용 가능 여부."""
    return _load_dwf() is not None


def device_count():
    """PC 에 연결된 Digilent 장치 수. SDK 가 없으면 0."""
    dwf = _load_dwf()
    if dwf is None:
        return 0
    n = ctypes.c_int(0)
    # enumfilterAll = 0
    dwf.FDwfEnum(ctypes.c_int(0), ctypes.byref(n))
    return n.value


class AD2Scope:
    """
    Analog Discovery 2 의 아날로그 입력(CH1)을 오실로스코프처럼 반복 획득한다.

    사용 순서:
        scope = AD2Scope()
        scope.open()                      # 장치 열기 (또는 demo=True)
        scope.start(sample_rate, n_samples, ch_range)
        ...  data_queue 에서 (t_step, ndarray) 소비 ...
        scope.stop()
        scope.close()
    """

    def __init__(self):
        self._hdwf = ctypes.c_int(0)       # 장치 핸들
        self._running = False
        self._thread = None
        self._demo = False
        self.data_queue = queue.Queue(maxsize=4)   # (샘플주기[s], [전압 리스트]) 튜플
        self.is_open = False

    # ------------------------------------------------------------------ 장치
    def open(self, demo=False):
        """첫 번째 Digilent 장치를 연다. demo=True 면 하드웨어 없이 합성 파형."""
        self._demo = demo
        if demo:
            self.is_open = True
            return True
        dwf = _load_dwf()
        if dwf is None:
            raise RuntimeError("WaveForms SDK(dwf)를 찾을 수 없습니다: %s" % _sdk_error)
        dwf.FDwfDeviceOpen(ctypes.c_int(-1), ctypes.byref(self._hdwf))
        if self._hdwf.value == 0:   # hdwfNone
            err = ctypes.create_string_buffer(512)
            dwf.FDwfGetLastErrorMsg(err)
            raise RuntimeError("장치 열기 실패: " +
                               err.value.decode("utf-8", errors="replace"))
        self.is_open = True
        return True

    def close(self):
        """획득을 멈추고 장치를 닫는다."""
        self.stop()
        if self.is_open and not self._demo:
            dwf = _load_dwf()
            if dwf is not None:
                dwf.FDwfDeviceClose(self._hdwf)
            self._hdwf = ctypes.c_int(0)
        self.is_open = False

    # ------------------------------------------------------------------ 획득
    def start(self, sample_rate=1e6, n_samples=4096, ch_range=5.0):
        """
        반복 획득 스레드를 시작한다.
          sample_rate : 샘플링 주파수 [Hz]
          n_samples   : 1회 획득 샘플 수 (AD2 버퍼 최대 8192)
          ch_range    : 채널 전압 범위 [V] (피크-피크 기준 ±ch_range/2 가 아님,
                        SDK 의 range 는 풀스케일 폭. 5.0 → 약 ±2.5V, 50.0 → ±25V)
        """
        if not self.is_open:
            raise RuntimeError("장치가 열려 있지 않습니다.")
        self.stop()
        self._running = True
        self._thread = threading.Thread(
            target=self._acq_loop, args=(float(sample_rate), int(n_samples), float(ch_range)),
            daemon=True)
        self._thread.start()

    def stop(self):
        """획득 스레드를 정지한다."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _acq_loop(self, sample_rate, n_samples, ch_range):
        if self._demo:
            self._demo_loop(sample_rate, n_samples)
            return

        dwf = _load_dwf()
        hdwf = self._hdwf
        # --- AnalogIn(스코프) 설정 : CH1(index 0), 단발(acqmodeSingle) 획득 반복 ---
        dwf.FDwfAnalogInFrequencySet(hdwf, ctypes.c_double(sample_rate))
        dwf.FDwfAnalogInBufferSizeSet(hdwf, ctypes.c_int(n_samples))
        dwf.FDwfAnalogInChannelEnableSet(hdwf, ctypes.c_int(0), ctypes.c_int(1))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, ctypes.c_int(0), ctypes.c_double(ch_range))
        time.sleep(0.1)   # 아날로그 프론트엔드 안정화 대기

        buf = (ctypes.c_double * n_samples)()
        sts = ctypes.c_byte(0)
        DwfStateDone = 2

        while self._running:
            # 단발 획득 시작 (reconfigure=False, start=True)
            dwf.FDwfAnalogInConfigure(hdwf, ctypes.c_int(0), ctypes.c_int(1))
            # 완료 대기
            while self._running:
                dwf.FDwfAnalogInStatus(hdwf, ctypes.c_int(1), ctypes.byref(sts))
                if sts.value == DwfStateDone:
                    break
                time.sleep(0.001)
            if not self._running:
                break
            dwf.FDwfAnalogInStatusData(hdwf, ctypes.c_int(0), buf, ctypes.c_int(n_samples))
            self._push(1.0 / sample_rate, list(buf))
            time.sleep(0.03)   # 화면 갱신 주기 제한 (약 20~30 fps)

    def _demo_loop(self, sample_rate, n_samples):
        """데모 모드: 1 kHz 사인파 + 잡음을 합성해서 전달한다."""
        phase = 0.0
        while self._running:
            dt = 1.0 / sample_rate
            data = [
                2.0 * math.sin(2 * math.pi * 1000.0 * (phase + i * dt))
                + random.gauss(0, 0.05)
                for i in range(n_samples)
            ]
            phase += n_samples * dt
            self._push(dt, data)
            time.sleep(0.05)

    def _push(self, dt, data):
        """가장 오래된 프레임을 버리고 최신 프레임을 큐에 넣는다."""
        try:
            self.data_queue.put_nowait((dt, data))
        except queue.Full:
            try:
                self.data_queue.get_nowait()
                self.data_queue.put_nowait((dt, data))
            except queue.Empty:
                pass
