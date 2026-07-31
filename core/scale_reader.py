"""
称重秤串口读取模块

支持两种模式：
  1. 真实模式 — 通过串口读取真实称重秤数据
  2. 模拟模式 — 生成模拟数据用于开发测试

兼容：Python 3.8+ / Windows 7+
"""
import re
import os
import random
import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal


class ScaleReader(QObject):
    """
    称重秤读取器，运行在后台线程中。
    通过 Qt 信号将重量数据传递给 UI。
    """

    # 信号：重量更新 (weight_kg: float)
    weight_updated = pyqtSignal(float)
    # 信号：连接状态变化 (connected: bool, message: str)
    status_changed = pyqtSignal(bool, str)
    # 信号：重量稳定（连续 N 次重量变化小于阈值）
    weight_stable = pyqtSignal(float)
    # 信号：错误信息
    error_occurred = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._running = False
        self._thread = None
        self._serial = None

        # 稳定检测
        self._last_weights = []
        self._stable_threshold = config.get("stable_threshold", 0.01)
        self._stable_count = config.get("stable_count", 5)

    def start(self):
        """启动称重读取"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止称重读取"""
        self._running = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _run_loop(self):
        """主循环"""
        if self.config.get("simulation_mode", True):
            self._run_simulation()
        else:
            self._run_real()

    # ─── 模拟模式 ──────────────────────────────────────
    def _run_simulation(self):
        """模拟称重数据，用于开发测试"""
        self.status_changed.emit(True, "模拟模式已启动")
        sim_weight = 0.0
        phase = "idle"  # idle -> rising -> stable -> falling -> idle
        phase_timer = 0

        while self._running:
            time.sleep(0.2)  # 5Hz 更新频率

            if phase == "idle":
                sim_weight = random.gauss(0.0, 0.002)
                sim_weight = max(0.0, sim_weight)
                phase_timer += 1
                if phase_timer > 30 and random.random() < 0.05:
                    phase = "rising"
                    phase_timer = 0
                    sim_weight = 0.0

            elif phase == "rising":
                target = random.uniform(0.3, 1.5)
                step = target / 10
                sim_weight += step + random.gauss(0, 0.005)
                sim_weight = max(0, sim_weight)
                phase_timer += 1
                if phase_timer > 10:
                    phase = "stable"
                    phase_timer = 0
                    sim_weight = round(random.uniform(0.3, 1.5), 3)

            elif phase == "stable":
                base = sim_weight
                sim_weight = base + random.gauss(0, 0.002)
                sim_weight = max(0, sim_weight)
                phase_timer += 1
                if phase_timer > 50:
                    phase = "falling"
                    phase_timer = 0

            elif phase == "falling":
                sim_weight *= 0.5
                phase_timer += 1
                if phase_timer > 5 or sim_weight < 0.01:
                    phase = "idle"
                    phase_timer = 0
                    sim_weight = 0.0

            self.weight_updated.emit(round(max(0, sim_weight), 3))
            self._check_stability(round(max(0, sim_weight), 3))

    # ─── 真实模式 ──────────────────────────────────────
    def _run_real(self):
        """从真实串口读取称重数据"""
        try:
            import serial
            port = self.config.get("scale_port", "COM3")
            baudrate = self.config.get("scale_baudrate", 9600)
            bytesize = self.config.get("scale_bytesize", 8)
            parity = self.config.get("scale_parity", "N")
            stopbits = self.config.get("scale_stopbits", 1)

            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=1
            )
            self.status_changed.emit(True, "已连接 %s (波特率 %d)" % (port, baudrate))

            buffer = b""
            while self._running:
                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    buffer += data

                    # 尝试按行解析
                    while b"\n" in buffer or b"\r" in buffer:
                        for sep in [b"\r\n", b"\n", b"\r"]:
                            if sep in buffer:
                                line, buffer = buffer.split(sep, 1)
                                weight = self._parse_weight(line)
                                if weight is not None:
                                    self.weight_updated.emit(weight)
                                    self._check_stability(weight)
                                break
                else:
                    time.sleep(0.05)

        except ImportError:
            self.error_occurred.emit("未安装 pyserial 库，请运行: pip install pyserial")
            self.status_changed.emit(False, "缺少 pyserial 库")
        except Exception as e:
            self.error_occurred.emit("串口连接失败: %s" % str(e))
            self.status_changed.emit(False, "连接失败: %s" % str(e))

    def _parse_weight(self, raw):
        """
        解析 DIBAL ACS-G315 电子计价秤的串口数据。

        DIBAL G 系列支持 40+ 种协议，常见格式包括：
        1. STX 帧格式:  STX + 状态 + 重量ASCII + ETX
        2. 逗号分隔:    "ST,GS,+ 001.250 kg"
        3. 状态+重量:   "S  +001.250 kg"
        4. 纯数字:      "+001.250" 或 "001.250"
        5. 带前缀:      "wn001.250kg"
        """
        # ── 记录原始数据（远程调试用）──
        try:
            log_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "raw_scale.log"
            )
            hex_str = raw.hex(' ') if hasattr(raw, 'hex') else ' '.join('%02x' % b for b in raw)
            ascii_str = raw.decode("ascii", errors="replace").strip()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[HEX] %s\n" % hex_str)
                f.write("[ASC] %s\n\n" % ascii_str)
        except Exception:
            pass

        try:
            # 去掉 STX(0x02) / ETX(0x03) 等控制字符
            cleaned = bytearray()
            for b in raw:
                if 0x20 <= b <= 0x7E:
                    cleaned.append(b)
                elif b in (0x2B, 0x2D):  # + -
                    cleaned.append(b)

            text = cleaned.decode("ascii", errors="ignore").strip()
            if not text:
                return None

            match = re.search(r'[+-]?\s*(\d{1,6}\.?\d{0,4})', text)
            if match:
                weight_str = match.group(1)
                weight = float(weight_str)
                if weight > 20:
                    weight = weight / 1000.0
                return round(weight, 3)

        except Exception:
            pass
        return None

    # ─── 稳定检测 ──────────────────────────────────────
    def _check_stability(self, weight):
        """检测重量是否稳定"""
        self._last_weights.append(weight)
        if len(self._last_weights) > self._stable_count:
            self._last_weights.pop(0)

        if len(self._last_weights) == self._stable_count and weight > 0.01:
            max_w = max(self._last_weights)
            min_w = min(self._last_weights)
            if (max_w - min_w) < self._stable_threshold:
                avg_weight = sum(self._last_weights) / len(self._last_weights)
                self.weight_stable.emit(round(avg_weight, 3))
