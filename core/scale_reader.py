"""
称重秤串口读取模块

通过串口（RS-232 / USB转串口）实时读取真实称重秤数据
兼容：Python 3.8+ / Windows 7+
"""
import re
import os
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

    def restart(self):
        """重新连接串口"""
        self.stop()
        time.sleep(0.3)
        self.start()

    def _run_loop(self):
        """主循环 — 直接从真实串口读取数据"""
        self._run_real()

    # ─── 真实串口模式 ──────────────────────────────────────
    def _run_real(self):
        """从真实串口读取称重数据"""
        port = self.config.get("scale_port", "COM1")
        baudrate = self.config.get("scale_baudrate", 9600)
        bytesize = self.config.get("scale_bytesize", 8)
        parity = self.config.get("scale_parity", "N")
        stopbits = self.config.get("scale_stopbits", 1)

        try:
            import serial

            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=1
            )
            self.status_changed.emit(True, "已连接电子秤 %s (%d bps)" % (port, baudrate))

            buffer = b""
            while self._running:
                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    buffer += data

                    # 支持 STX(0x02)/ETX(0x03)、\r\n、\n、\r 分帧
                    while len(buffer) > 0:
                        packet = None
                        # 优先查找 STX ... ETX 完整报文
                        if b"\x02" in buffer and b"\x03" in buffer:
                            start_idx = buffer.find(b"\x02")
                            end_idx = buffer.find(b"\x03", start_idx)
                            if end_idx != -1:
                                packet = buffer[start_idx:end_idx + 1]
                                buffer = buffer[end_idx + 1:]
                        
                        # 换行符分帧
                        if packet is None:
                            for sep in [b"\r\n", b"\n", b"\r"]:
                                if sep in buffer:
                                    packet, buffer = buffer.split(sep, 1)
                                    break

                        if packet is not None:
                            weight, raw_info = self._parse_weight(packet)
                            if weight is not None:
                                self.weight_updated.emit(weight)
                                self._check_stability(weight)
                                if raw_info:
                                    self.status_changed.emit(True, "已连接 %s | 原始报文: %s" % (port, raw_info))
                        else:
                            # 缓冲区过长且无法切帧时，清空早期字节防死锁
                            if len(buffer) > 256:
                                buffer = buffer[-64:]
                            break
                else:
                    time.sleep(0.05)

        except ImportError:
            msg = "未安装 pyserial 库，请运行: pip install pyserial"
            self.error_occurred.emit(msg)
            self.status_changed.emit(False, msg)
        except Exception as e:
            err_str = str(e)
            if "FileNotFoundError" in err_str or "could not open port" in err_str:
                msg = "串口 %s 未找到/不可用，请在【系统设置】中切换为可用端口 (如 COM1)" % port
            elif "PermissionError" in err_str or "Access is denied" in err_str:
                msg = "串口 %s 被其他程序占用 (如公司原有POS系统)，请使用 VSPE 进行端口分流" % port
            else:
                msg = "串口 %s 连接失败: %s" % (port, err_str)

            self.error_occurred.emit(msg)
            self.status_changed.emit(False, msg)

    def _parse_weight(self, raw):
        """
        解析 DIBAL ACS-G315 电子计价秤及通用电子秤的串口数据。
        返回 tuple: (weight_kg: float, raw_str: str)
        """
        # 记录调试日志
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
            ascii_str = ""

        try:
            # 过滤打印可见 ASCII 字符
            cleaned = bytearray()
            for b in raw:
                if 0x20 <= b <= 0x7E:
                    cleaned.append(b)

            text = cleaned.decode("ascii", errors="ignore").strip()
            if not text:
                return None, ascii_str

            # 协议 1: DIBAL 标准 STX 帧 (如: 02 30 30 30 33 35 30 ... -> STX 000350 ...)
            # 格式: 状态(1字节) + 5位/6位重量克数
            if len(text) >= 5 and text.isdigit():
                # 纯数字，代表克数，如 000350 -> 350g -> 0.35kg
                g_val = float(text[:6]) if len(text) >= 6 else float(text)
                kg_val = round(g_val / 1000.0, 3)
                return kg_val, text

            # 协议 2: 标准逗号分隔 / 带单位报文 (如 "ST,GS,+00.350kg", "WN0.350kg", "+ 0.350")
            match = re.search(r'([+-]?\s*\d{1,5}\.\d{1,4})\s*(kg|g|jin|斤)?', text, re.IGNORECASE)
            if match:
                val_str = match.group(1).replace(" ", "")
                unit_str = (match.group(2) or "").lower()
                val = float(val_str)

                # 单位换算
                if unit_str in ("g", "克"):
                    kg_val = val / 1000.0
                elif unit_str in ("jin", "斤"):
                    kg_val = val / 2.0
                elif abs(val) > 20:  # 默认无单位且大于20认为是克数
                    kg_val = val / 1000.0
                else:
                    kg_val = val

                return round(abs(kg_val), 3), text

            # 协议 3: 提取第一个正浮点数
            m2 = re.search(r'\d+\.\d+', text)
            if m2:
                val = float(m2.group(0))
                return round(val, 3), text

        except Exception:
            pass

        return None, ascii_str

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
