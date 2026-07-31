"""
称重秤串口读取模块

通过串口（RS-232 / USB转串口）实时读取真实称重秤数据
支持主动发送查询指令 (ENQ / W\\r) 与 连续主动上报 两种模式
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
                timeout=0.5
            )
            self.status_changed.emit(True, "已打开 %s (%d bps) | 正在监听电子秤..." % (port, baudrate))

            buffer = b""
            last_query_time = 0
            query_cmds = [b"\x05", b"W\r\n", b"Q\r\n", b"S\r\n"]  # 常见电子秤查询指令
            cmd_idx = 0

            while self._running:
                now = time.time()
                # 每 0.5 秒如果没收到新数据，主动向秤发送一次查询请求指令 (应对问答式电子秤)
                if now - last_query_time > 0.5:
                    try:
                        self._serial.write(query_cmds[cmd_idx])
                        cmd_idx = (cmd_idx + 1) % len(query_cmds)
                    except Exception:
                        pass
                    last_query_time = now

                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    buffer += data

                    # 尝试按多种方式切帧
                    while len(buffer) > 0:
                        packet = None
                        # 1. 优先查找 STX(0x02) ... ETX(0x03) 完整帧
                        if b"\x02" in buffer and b"\x03" in buffer:
                            start_idx = buffer.find(b"\x02")
                            end_idx = buffer.find(b"\x03", start_idx)
                            if end_idx != -1:
                                packet = buffer[start_idx:end_idx + 1]
                                buffer = buffer[end_idx + 1:]

                        # 2. 换行符切帧
                        if packet is None:
                            for sep in [b"\r\n", b"\n", b"\r"]:
                                if sep in buffer:
                                    packet, buffer = buffer.split(sep, 1)
                                    break

                        # 3. 如果收到固定长度报文（如 8~16 字节）
                        if packet is None and len(buffer) >= 12:
                            packet = buffer[:12]
                            buffer = buffer[12:]

                        if packet is not None:
                            weight, raw_info = self._parse_weight(packet)
                            if weight is not None:
                                self.weight_updated.emit(weight)
                                self._check_stability(weight)
                                self.status_changed.emit(True, "已连接 %s | 读数: %.3fkg | 报文: %s" % (port, weight, raw_info))
                            elif raw_info:
                                self.status_changed.emit(True, "已连接 %s | 收到数据但未解析: %s" % (port, raw_info))
                        else:
                            # 缓冲区防止死锁溢出
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
        解析电子秤数据。
        返回 tuple: (weight_kg: float or None, raw_display_str: str)
        """
        # 记录本地调试日志
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
            # 清理控制字符
            cleaned = bytearray()
            for b in raw:
                if 0x20 <= b <= 0x7E:
                    cleaned.append(b)

            text = cleaned.decode("ascii", errors="ignore").strip()
            if not text:
                return None, raw.hex(' ')

            # 匹配 1: 标准带单位或正负号数 ("ST,GS,+ 00.350kg", "00.700", "wn000.350kg")
            match = re.search(r'([+-]?\s*\d{1,5}\.\d{1,4})\s*(kg|g|jin|斤)?', text, re.IGNORECASE)
            if match:
                val_str = match.group(1).replace(" ", "")
                unit_str = (match.group(2) or "").lower()
                val = float(val_str)

                if unit_str in ("g", "克"):
                    kg_val = val / 1000.0
                elif unit_str in ("jin", "斤"):
                    kg_val = val / 2.0
                elif abs(val) > 30:  # 默认无单位且数值较大概率为克数
                    kg_val = val / 1000.0
                else:
                    kg_val = val

                return round(abs(kg_val), 3), text

            # 匹配 2: 纯数字格式 (如 DIBAL STX 报文 "000350" -> 350g)
            digits = re.sub(r'\D', '', text)
            if len(digits) >= 4:
                g_val = float(digits[:6]) if len(digits) >= 6 else float(digits)
                kg_val = round(g_val / 1000.0, 3)
                if kg_val < 50:  # 过滤异常大数
                    return kg_val, text

        except Exception:
            pass

        return None, raw.hex(' ')

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
