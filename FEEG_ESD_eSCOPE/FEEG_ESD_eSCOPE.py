# -*- coding: utf-8 -*-
"""
FEEG_ESD_eSCOPE — 메인 프로그램

BIGTREETECH SKR mini E3 (Marlin 펌웨어) 제어 + Analog Discovery 2 파형 표시 PC 프로그램.

구성:
  * 왼쪽  : Marlin USB 시리얼 연결, X/Y/Z 스테퍼 모터 조그(1mm 단위), UART 콘솔
  * 오른쪽: Analog Discovery 2 연결 상태 표시, 전압 파형(시간축-전압축) 디스플레이

실행:  python FEEG_ESD_eSCOPE.py
필요 패키지: pyserial, matplotlib  (requirements.txt 참고)
AD2 사용 시: Digilent WaveForms(SDK 포함) 설치 필요. 없으면 데모 모드 사용 가능.
"""

import queue
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import marlin_serial
import ad2_scope

APP_NAME = "FEEG_ESD_eSCOPE"
APP_VERSION = "1.0.0"

# 파형 표시 설정 선택지
SAMPLE_RATES = ["1000", "10000", "100000", "1000000", "10000000"]   # Hz
SAMPLE_COUNTS = ["512", "1024", "2048", "4096", "8192"]
CH_RANGES = ["5", "50"]        # V (AD2 는 저/고 감쇠 2단)


class App(tk.Tk):
    """FEEG_ESD_eSCOPE 메인 윈도우."""

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1280x760")
        self.minsize(1100, 640)

        self.marlin = marlin_serial.MarlinSerial()
        self.scope = ad2_scope.AD2Scope()
        self._scope_running = False

        self._build_ui()

        # 주기 작업 등록
        self.after(100, self._poll_marlin_rx)      # UART 수신 콘솔 갱신
        self.after(50, self._poll_scope_data)      # 파형 갱신
        self.after(500, self._poll_ad2_presence)   # AD2 연결 감지
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================== UI
    def _build_ui(self):
        root = ttk.Frame(self, padding=6)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 6))
        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_marlin_conn(left)
        self._build_jog(left)
        self._build_test_params(left)
        self._build_console(left)
        self._build_ad2_panel(right)

    # ------------------------------------------------- Marlin 연결 패널
    def _build_marlin_conn(self, parent):
        f = ttk.LabelFrame(parent, text=" SKR mini E3 (Marlin) — USB Serial 연결 ", padding=6)
        f.pack(fill="x", pady=(0, 6))

        ttk.Label(f, text="포트:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(f, textvariable=self.port_var, width=14,
                                       state="readonly")
        self.port_combo.grid(row=0, column=1, padx=3)
        ttk.Button(f, text="새로고침", width=8,
                   command=self._refresh_ports).grid(row=0, column=2, padx=3)

        ttk.Label(f, text="Baud:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.baud_var = tk.StringVar(value=str(marlin_serial.DEFAULT_BAUD))
        ttk.Combobox(f, textvariable=self.baud_var, width=14, state="readonly",
                     values=[str(b) for b in marlin_serial.BAUD_RATES]
                     ).grid(row=1, column=1, padx=3, pady=(4, 0))

        self.connect_btn = ttk.Button(f, text="연결", width=8,
                                      command=self._toggle_marlin)
        self.connect_btn.grid(row=1, column=2, padx=3, pady=(4, 0))

        self.marlin_status = ttk.Label(f, text="● 연결 안 됨", foreground="red")
        self.marlin_status.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        self._refresh_ports()

    def _refresh_ports(self):
        ports = marlin_serial.list_serial_ports()
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _toggle_marlin(self):
        if self.marlin.is_connected:
            self.marlin.disconnect()
            self.connect_btn.config(text="연결")
            self.marlin_status.config(text="● 연결 안 됨", foreground="red")
            return
        port = self.port_var.get()
        if not port:
            messagebox.showwarning(APP_NAME, "시리얼 포트를 선택하세요.")
            return
        try:
            self.marlin.connect(port, int(self.baud_var.get()))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"연결 실패:\n{e}")
            return
        self.connect_btn.config(text="해제")
        self.marlin_status.config(text=f"● 연결됨 ({port})", foreground="green")

    # ------------------------------------------------- 조그(모터 제어) 패널
    def _build_jog(self, parent):
        f = ttk.LabelFrame(parent, text=" 스테퍼 모터 제어 (X / Y / Z) ", padding=6)
        f.pack(fill="x", pady=(0, 6))

        # 이동 거리 입력 (mm 단위) — X/Y 축과 Z 축을 좌우로 나란히 배치
        sf = ttk.Frame(f)
        sf.pack(fill="x")
        ttk.Label(sf, text="X/Y 이동 거리:").grid(row=0, column=0, sticky="e")
        self.xy_step_var = tk.StringVar(value="1")          # 기본 1mm
        ttk.Entry(sf, textvariable=self.xy_step_var, width=6,
                  justify="right").grid(row=0, column=1, padx=(4, 2))
        ttk.Label(sf, text="mm").grid(row=0, column=2, sticky="w", padx=(0, 14))
        ttk.Label(sf, text="Z 이동 거리:").grid(row=0, column=3, sticky="e")
        self.z_step_var = tk.StringVar(value="1")           # 기본 1mm
        ttk.Entry(sf, textvariable=self.z_step_var, width=6,
                  justify="right").grid(row=0, column=4, padx=(4, 2))
        ttk.Label(sf, text="mm (최대 10)").grid(row=0, column=5, sticky="w")

        # 조그 버튼 패드
        pad = ttk.Frame(f)
        pad.pack(pady=6)

        def jbtn(text, r, c, axis, sign):
            b = ttk.Button(pad, text=text, width=6,
                           command=lambda: self._jog(axis, sign))
            b.grid(row=r, column=c, padx=2, pady=2)
            return b

        jbtn("Y +", 0, 1, "Y", +1)
        jbtn("X −", 1, 0, "X", -1)
        jbtn("X +", 1, 2, "X", +1)
        jbtn("Y −", 2, 1, "Y", -1)
        jbtn("Z +", 0, 4, "Z", +1)
        jbtn("Z −", 2, 4, "Z", -1)
        ttk.Label(pad, text=" ").grid(row=0, column=3, padx=6)   # X/Y 와 Z 사이 간격

        # 홈 / 보조 버튼
        hf = ttk.Frame(f)
        hf.pack(fill="x", pady=(4, 0))
        ttk.Button(hf, text="전체 홈 (G28)", width=12,
                   command=lambda: self.marlin.home()).pack(side="left", padx=2)
        ttk.Button(hf, text="XY 홈", width=8,
                   command=lambda: self.marlin.home("XY")).pack(side="left", padx=2)
        ttk.Button(hf, text="Z 홈", width=8,
                   command=lambda: self.marlin.home("Z")).pack(side="left", padx=2)
        hf2 = ttk.Frame(f)
        hf2.pack(fill="x", pady=(4, 0))
        ttk.Button(hf2, text="모터 해제 (M84)", width=14,
                   command=self.marlin.disable_steppers).pack(side="left", padx=2)
        ttk.Button(hf2, text="위치 확인 (M114)", width=14,
                   command=self.marlin.get_position).pack(side="left", padx=2)

    # Z축은 노즐/베드 충돌 위험이 있어 한 번에 최대 10mm 로 제한한다.
    Z_STEP_MAX_MM = 10.0

    def _jog(self, axis, sign):
        is_z = (axis == "Z")
        var = self.z_step_var if is_z else self.xy_step_var
        name = "Z 이동 거리" if is_z else "X/Y 이동 거리"
        try:
            step = float(var.get().strip())
        except ValueError:
            messagebox.showwarning(APP_NAME, f"{name}는 숫자로 입력하세요. (mm 단위)")
            return
        if step <= 0:
            messagebox.showwarning(APP_NAME, f"{name}는 0 보다 큰 값이어야 합니다.")
            return
        if is_z and step > self.Z_STEP_MAX_MM:
            messagebox.showwarning(
                APP_NAME,
                f"Z 이동 거리는 최대 {self.Z_STEP_MAX_MM:g} mm 까지만 입력할 수 있습니다.\n"
                f"(입력값: {step:g} mm)")
            return
        self.marlin.jog(axis, sign * step)

    # --------------------------------------- 테스트 설정 (Test Parameters)
    def _build_test_params(self, parent):
        f = ttk.LabelFrame(parent, text=" 테스트 설정 (Test Parameters) ", padding=6)
        f.pack(fill="x", pady=(0, 6))

        self.xscope_var = tk.StringVar(value="10")
        self.yscope_var = tk.StringVar(value="10")
        self.xtest_var = tk.StringVar(value="1")
        self.ytest_var = tk.StringVar(value="1")
        self.speed_var = tk.StringVar(value="5")
        self.test_params = None      # [설정 적용] 성공 시 dict 로 저장

        def row(r, name1, var1, name2, var2):
            ttk.Label(f, text=name1 + ":").grid(row=r, column=0, sticky="e")
            ttk.Entry(f, textvariable=var1, width=7,
                      justify="right").grid(row=r, column=1, padx=(2, 0))
            ttk.Label(f, text="mm").grid(row=r, column=2, sticky="w", padx=(2, 10))
            ttk.Label(f, text=name2 + ":").grid(row=r, column=3, sticky="e")
            ttk.Entry(f, textvariable=var2, width=7,
                      justify="right").grid(row=r, column=4, padx=(2, 0))
            ttk.Label(f, text="mm").grid(row=r, column=5, sticky="w", padx=(2, 0))

        row(0, "X_scope", self.xscope_var, "Y_scope", self.yscope_var)
        self.scope_warn = ttk.Label(f, text="", foreground="red")
        self.scope_warn.grid(row=1, column=0, columnspan=6, sticky="w")

        row(2, "X_test_distance", self.xtest_var, "Y_test_distance", self.ytest_var)
        self.dist_warn = ttk.Label(f, text="", foreground="red")
        self.dist_warn.grid(row=3, column=0, columnspan=6, sticky="w")

        ttk.Label(f, text="Search Speed:").grid(row=4, column=0, sticky="e", pady=(2, 0))
        ttk.Entry(f, textvariable=self.speed_var, width=7,
                  justify="right").grid(row=4, column=1, padx=(2, 0), pady=(2, 0))
        ttk.Label(f, text="(최대 12)").grid(row=4, column=2, columnspan=2,
                                            sticky="w", padx=(2, 0), pady=(2, 0))
        ttk.Button(f, text="설정 적용", width=9,
                   command=self._apply_test_params).grid(row=4, column=4,
                                                         columnspan=2, pady=(2, 0))
        self.speed_warn = ttk.Label(f, text="", foreground="red")
        self.speed_warn.grid(row=5, column=0, columnspan=6, sticky="w")

        # 입력이 바뀔 때마다 실시간으로 불일치/범위 초과 경고를 표시
        for var in (self.xscope_var, self.yscope_var, self.xtest_var,
                    self.ytest_var, self.speed_var):
            var.trace_add("write", lambda *_: self._update_param_warnings())

    @staticmethod
    def _pair_differs(var1, var2):
        """두 입력이 모두 숫자로 해석될 때만 값 비교. 다르면 True."""
        try:
            return float(var1.get()) != float(var2.get())
        except ValueError:
            return False

    def _update_param_warnings(self):
        self.scope_warn.config(
            text="X_scope 와 Y_scope 값이 서로 틀립니다!"
            if self._pair_differs(self.xscope_var, self.yscope_var) else "")
        self.dist_warn.config(
            text="X_test_distance 와 Y_test_distance 값이 서로 틀립니다!"
            if self._pair_differs(self.xtest_var, self.ytest_var) else "")
        warn = ""
        try:
            if float(self.speed_var.get()) > 12:
                warn = "Search Speed 는 최대 12 까지만 입력할 수 있습니다!"
        except ValueError:
            pass
        self.speed_warn.config(text=warn)

    def _apply_test_params(self):
        """모든 테스트 설정 값을 검증하고, 통과하면 저장 + 콘솔에 기록한다."""
        try:
            xs = float(self.xscope_var.get().strip())
            ys = float(self.yscope_var.get().strip())
            xd = float(self.xtest_var.get().strip())
            yd = float(self.ytest_var.get().strip())
            sp = float(self.speed_var.get().strip())
        except ValueError:
            messagebox.showerror(APP_NAME, "테스트 설정 값은 모두 숫자로 입력하세요.")
            return
        if xs != ys:
            messagebox.showerror(
                APP_NAME, "X_scope 와 Y_scope 값이 서로 틀립니다.\n"
                          f"(X_scope={xs:g} mm, Y_scope={ys:g} mm)")
            return
        if xd != yd:
            messagebox.showerror(
                APP_NAME, "X_test_distance 와 Y_test_distance 값이 서로 틀립니다.\n"
                          f"(X_test_distance={xd:g} mm, Y_test_distance={yd:g} mm)")
            return
        if sp <= 0:
            messagebox.showerror(APP_NAME, "Search Speed 는 0 보다 커야 합니다.")
            return
        if sp > 12:
            messagebox.showerror(APP_NAME,
                                 f"Search Speed 는 최대 12 까지만 입력할 수 있습니다.\n"
                                 f"(입력값: {sp:g})")
            return
        self.test_params = {"x_scope": xs, "y_scope": ys,
                            "x_test_distance": xd, "y_test_distance": yd,
                            "search_speed": sp}
        self._append_console(
            "action",
            f"[설정] X/Y_scope={xs:g} mm, X/Y_test_distance={xd:g} mm, "
            f"Search Speed={sp:g} 적용됨")

    # ------------------------------- 메시지 콘솔 (UART / Command) 패널
    def _build_console(self, parent):
        f = ttk.LabelFrame(parent, text=" 메시지 콘솔 (UART / Command) ", padding=6)
        f.pack(fill="both", expand=True)

        self.console = scrolledtext.ScrolledText(
            f, width=48, height=14, state="disabled", font=("Consolas", 9))
        self.console.pack(fill="both", expand=True)
        self.console.tag_config("rx", foreground="#006400")     # 수신: 녹색
        self.console.tag_config("tx", foreground="#00008B")     # 송신: 파랑
        self.console.tag_config("error", foreground="#B00000")  # 오류: 빨강
        self.console.tag_config("info", foreground="#555555")   # 정보: 회색
        self.console.tag_config("action", foreground="#7B1FA2",  # PC 제어 행위: 보라 굵게
                                font=("Consolas", 9, "bold"))

        ef = ttk.Frame(f)
        ef.pack(fill="x", pady=(4, 0))
        self.cmd_var = tk.StringVar()
        entry = ttk.Entry(ef, textvariable=self.cmd_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda e: self._send_manual())
        ttk.Button(ef, text="전송", width=6,
                   command=self._send_manual).pack(side="left", padx=(4, 0))
        ttk.Button(ef, text="지우기", width=6,
                   command=self._clear_console).pack(side="left", padx=(4, 0))

    def _send_manual(self):
        cmd = self.cmd_var.get().strip()
        if cmd:
            self.marlin.send_gcode(cmd)
            self.cmd_var.set("")

    def _clear_console(self):
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

    def _append_console(self, kind, text):
        prefix = {"tx": ">> ", "rx": "<< "}.get(kind, "")
        self.console.config(state="normal")
        self.console.insert("end", prefix + text + "\n", kind)
        # 콘솔이 무한정 커지지 않도록 2000줄 초과분은 잘라낸다.
        if float(self.console.index("end-1c").split(".")[0]) > 2000:
            self.console.delete("1.0", "200.0")
        self.console.see("end")
        self.console.config(state="disabled")

    def _poll_marlin_rx(self):
        """100ms 마다 수신 큐를 비워 콘솔에 표시한다."""
        try:
            while True:
                kind, text = self.marlin.rx_queue.get_nowait()
                self._append_console(kind, text)
                if kind == "error" and not self.marlin.is_connected:
                    self.connect_btn.config(text="연결")
                    self.marlin_status.config(text="● 연결 안 됨", foreground="red")
        except queue.Empty:
            pass
        self.after(100, self._poll_marlin_rx)

    # ------------------------------------------------- AD2 패널 (파형 표시)
    def _build_ad2_panel(self, parent):
        top = ttk.LabelFrame(parent, text=" Analog Discovery 2 — 오실로스코프 ", padding=6)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # 연결 상태 표시등
        self.ad2_lamp = tk.Canvas(top, width=16, height=16, highlightthickness=0)
        self.ad2_lamp.grid(row=0, column=0)
        self._lamp_id = self.ad2_lamp.create_oval(2, 2, 14, 14, fill="red")
        self.ad2_status = ttk.Label(top, text="AD2 연결 안 됨")
        self.ad2_status.grid(row=0, column=1, sticky="w", padx=(4, 12))

        self.demo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="데모 모드(합성 파형)",
                        variable=self.demo_var).grid(row=0, column=2, padx=4)

        ttk.Label(top, text="샘플레이트[Hz]:").grid(row=1, column=0, columnspan=2,
                                                   sticky="e", pady=(6, 0))
        self.rate_var = tk.StringVar(value="1000000")
        ttk.Combobox(top, textvariable=self.rate_var, values=SAMPLE_RATES,
                     width=10, state="readonly").grid(row=1, column=2, pady=(6, 0))
        ttk.Label(top, text="샘플 수:").grid(row=1, column=3, sticky="e", padx=(10, 2),
                                             pady=(6, 0))
        self.nsamp_var = tk.StringVar(value="4096")
        ttk.Combobox(top, textvariable=self.nsamp_var, values=SAMPLE_COUNTS,
                     width=7, state="readonly").grid(row=1, column=4, pady=(6, 0))
        ttk.Label(top, text="범위[V]:").grid(row=1, column=5, sticky="e", padx=(10, 2),
                                             pady=(6, 0))
        self.range_var = tk.StringVar(value="5")
        ttk.Combobox(top, textvariable=self.range_var, values=CH_RANGES,
                     width=5, state="readonly").grid(row=1, column=6, pady=(6, 0))

        self.scope_btn = ttk.Button(top, text="측정 시작", width=10,
                                    command=self._toggle_scope)
        self.scope_btn.grid(row=1, column=7, padx=(12, 0), pady=(6, 0))

        # matplotlib 파형 캔버스 (X축: 시간, Y축: 전압)
        self.fig = Figure(figsize=(7, 4.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Time [ms]")
        self.ax.set_ylabel("Voltage [V]")
        self.ax.grid(True, alpha=0.4)
        self.line, = self.ax.plot([], [], lw=0.9, color="#c8a200")
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")

    def _poll_ad2_presence(self):
        """0.5초마다 AD2 장치 존재 여부를 확인하여 상태등을 갱신한다."""
        if self.scope.is_open:
            # 이미 열려 있으면(측정 중 포함) 연결됨으로 유지
            self._set_lamp(True, "AD2 연결됨 (사용 중)"
                           if not self.demo_var.get() else "데모 모드 동작 중")
        elif not ad2_scope.sdk_available():
            self._set_lamp(False, "WaveForms SDK 미설치 — 데모 모드만 사용 가능")
        elif ad2_scope.device_count() > 0:
            self._set_lamp(True, "AD2 연결됨")
        else:
            self._set_lamp(False, "AD2 연결 안 됨")
        self.after(2000 if not self.scope.is_open else 500, self._poll_ad2_presence)

    def _set_lamp(self, on, text):
        self.ad2_lamp.itemconfig(self._lamp_id, fill="#00b000" if on else "red")
        self.ad2_status.config(text=text)

    def _toggle_scope(self):
        if self._scope_running:
            self.scope.stop()
            self.scope.close()
            self._scope_running = False
            self.scope_btn.config(text="측정 시작")
            return
        demo = self.demo_var.get()
        if not demo and not ad2_scope.sdk_available():
            messagebox.showwarning(
                APP_NAME,
                "WaveForms SDK 가 설치되어 있지 않습니다.\n"
                "Digilent WaveForms 를 설치하거나 데모 모드를 사용하세요.")
            return
        if not demo and ad2_scope.device_count() == 0:
            messagebox.showwarning(APP_NAME, "Analog Discovery 2 가 감지되지 않습니다.")
            return
        try:
            self.scope.open(demo=demo)
            self.scope.start(sample_rate=float(self.rate_var.get()),
                             n_samples=int(self.nsamp_var.get()),
                             ch_range=float(self.range_var.get()))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"측정 시작 실패:\n{e}")
            self.scope.close()
            return
        self._scope_running = True
        self.scope_btn.config(text="측정 정지")

    def _poll_scope_data(self):
        """50ms 마다 파형 큐를 확인해 최신 프레임을 그린다."""
        frame = None
        try:
            while True:                      # 최신 프레임만 남긴다
                frame = self.scope.data_queue.get_nowait()
        except queue.Empty:
            pass
        if frame is not None:
            dt, volts = frame
            n = len(volts)
            t_ms = [i * dt * 1e3 for i in range(n)]     # X축: 시간[ms]
            self.line.set_data(t_ms, volts)
            self.ax.set_xlim(0, t_ms[-1] if n > 1 else 1)
            rng = float(self.range_var.get())
            self.ax.set_ylim(-rng / 2 * 1.1, rng / 2 * 1.1)   # Y축: 전압[V]
            self.canvas.draw_idle()
        self.after(50, self._poll_scope_data)

    # ================================================================== 종료
    def _on_close(self):
        try:
            self.scope.stop()
            self.scope.close()
            self.marlin.disconnect()
        finally:
            self.destroy()


def _selftest():
    """--selftest: 데모 파형이 그려지는지 확인하고 종료 코드로 결과를 알린다.

    배포용 EXE 가 실제로 뜨고 그래프까지 그려지는지 CI(빌드 서버)에서
    자동 검증하는 용도. 성공 시 0, 실패 시 1 로 종료한다.
    """
    app = App()
    app.demo_var.set(True)
    app._toggle_scope()
    result = {"ok": False}

    def check():
        result["ok"] = len(app.line.get_xdata()) > 0
        app._on_close()

    app.after(3000, check)
    app.mainloop()
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    App().mainloop()
