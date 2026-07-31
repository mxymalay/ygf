"""
称重秤串口读取模块 — 含智能全端口/全波特率自适应扫描匹配
支持 RTS/DTR 硬件激活与 DIBAL/多品牌协议自动识别
PyQt5 + Python 3.8 兼容
"""
import re
import os
import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal
from config import save_config


class ScaleReader(QObject):
    """
    称重秤读取器，运行在后台线程中。
    具有全自动端口与波特率扫描重连功能。
    """

    weight_updated = pyqtSignal(float)
    status_changed = pyqtSignal(bool, str)
    weight_stable = pyqtSignal(float)
    error_occurred = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._running = False
        self._thread = None
        self._serial = None

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
        """主循环 — 智能匹配串口与波特率"""
        try:
            import serial
            import serial.tools.list_ports
        except ImportError:
            msg = "未安装 pyserial 库，请运行: pip install pyserial"
            self.error_occurred.emit(msg)
            self.status_changed.emit(False, msg)
            return

        baudrates = [9600, 4800, 2400, 19200, 38400, 115200]
        init_cmds = [b"\x05", b"\x0201\x03", b"W\r\n", b"\x0200\x03", b"Q\r\n"]

        # 先尝试配置中的首选端口与波特率
        pref_port = self.config.get("scale_port", "COM1")
        pref_baud = self.config.get("scale_baudrate", 9600)

        # 构建待测试候选清单
        com_list = [p.device for p in serial.tools.list_ports.comports()]
        if pref_port not in com_list and os.name == 'nt':
            com_list.insert(0, pref_port)

        if not com_list:
            com_list = ["COM1", "COM2", "COM3", "COM4"]

        # 候选尝试队列：首选优先，其次遍历所有 COM 与波特率
        candidates = [(pref_port, pref_baud)]
        for p in com_list:
            for b in baudrates:
                if (p, b) not in candidates:
                    candidates.append((p, b))

        cand_idx = 0
        current_port, current_baud = candidates[0]

        while self._running:
            # 尝试打开当前选定的 (port, baudrate)
            try:
                if self._serial:
                    try:
                        self._serial.close()
                    except Exception:
                        pass
                    self._serial = None

                self.status_changed.emit(
                    True, "正在检测 %s (%d bps) RTS/DTR 激活..." % (current_port, current_baud)
                )

                self._serial = serial.Serial(
                    port=current_port,
                    baudrate=current_baud,
                    bytesize=8,
                    parity='N',
                    stopbits=1,
                    timeout=0.2
                )

                # 拉高 RTS/DTR 供电
                try:
                    self._serial.dtr = True
                    self._serial.rts = True
                except Exception:
                    pass

                # 发送握手激活探针
                for cmd in init_cmds:
                    try:
                        self._serial.write(cmd)
                        time.sleep(0.05)
                    except Exception:
                        pass

                buffer = b""
                start_listen_t = time.time()
                last_query_t = 0
                got_valid_data = False

                # 监听 3 秒看是否有数据响应
                while self._running and (time.time() - start_listen_t < 3.0):
                    now = time.time()
                    if now - last_query_t > 0.3:
                        for cmd in init_cmds:
                            try:
                                self._serial.write(cmd)
                            except Exception:
                                pass
                        last_query_t = now

                    if self._serial.in_waiting > 0:
                        data = self._serial.read(self._serial.in_waiting)
                        buffer += data

                        # 切帧解析
                        while len(buffer) > 0:
                            packet = None
                            if b"\x02" in buffer and b"\x03" in buffer:
                                s_idx = buffer.find(b"\x02")
                                e_idx = buffer.find(b"\x03", s_idx)
                                if e_idx != -1:
                                    packet = buffer[s_idx:e_idx + 1]
                                    buffer = buffer[e_idx + 1:]

                            if packet is None:
                                for sep in [b"\r\n", b"\n", b"\r"]:
                                    if sep in buffer:
                                        packet, buffer = buffer.split(sep, 1)
                                        break

                            if packet is None and len(buffer) >= 10:
                                packet = buffer[:10]
                                buffer = buffer[10:]

                            if packet is not None:
                                weight, raw_info = self._parse_weight(packet)
                                if weight is not None:
                                    got_valid_data = True
                                    self.weight_updated.emit(weight)
                                    self._check_stability(weight)
                                    self.status_changed.emit(
                                        True, "已成功锁定 %s (%d bps) | 读数: %.3fkg" %
                                        (current_port, current_baud, weight)
                                    )
                            else:
                                if len(buffer) > 128:
                                    buffer = buffer[-32:]
                                break

                        # 一旦在这个端口/波特率上收到了有效数据，就进入持久监听循环！
                        if got_valid_data:
                            # 自动更新并保存最新匹配到的配置
                            if (self.config.get("scale_port") != current_port or
                                    self.config.get("scale_baudrate") != current_baud):
                                self.config["scale_port"] = current_port
                                self.config["scale_baudrate"] = current_baud
                                save_config(self.config)

                            # 进入长期监听死循环
                            self._listen_forever(current_port, current_baud, init_cmds)
                            return

                    time.sleep(0.05)

                # 3 秒内这个组合没有响应，切换到下一个候选端口/波特率
                cand_idx = (cand_idx + 1) % len(candidates)
                current_port, current_baud = candidates[cand_idx]

            except Exception as e:
                err_str = str(e)
                if "PermissionError" in err_str or "Access is denied" in err_str:
                    msg = "串口 %s 被公司原POS软件占用！请先关闭原软件或用 VSPE 分流" % current_port
                    self.status_changed.emit(False, msg)
                    time.sleep(1.0)

                cand_idx = (cand_idx + 1) % len(candidates)
                current_port, current_baud = candidates[cand_idx]
                time.sleep(0.2)

    def _listen_forever(self, port, baud, init_cmds):
        """成功锁定硬件后，进入高效持久接收循环"""
        buffer = b""
        last_query_t = 0
        query_idx = 0

        while self._running:
            now = time.time()
            if now - last_query_t > 0.3:
                try:
                    self._serial.write(init_cmds[query_idx % len(init_cmds)])
                    query_idx += 1
                except Exception:
                    pass
                last_query_t = now

            if self._serial.in_waiting > 0:
                data = self._serial.read(self._serial.in_waiting)
                buffer += data

                while len(buffer) > 0:
                    packet = None
                    if b"\x02" in buffer and b"\x03" in buffer:
                        s_idx = buffer.find(b"\x02")
                        e_idx = buffer.find(b"\x03", s_idx)
                        if e_idx != -1:
                            packet = buffer[s_idx:e_idx + 1]
                            buffer = buffer[e_idx + 1:]

                    if packet is None:
                        for sep in [b"\r\n", b"\n", b"\r"]:
                            if sep in buffer:
                                packet, buffer = buffer.split(sep, 1)
                                break

                    if packet is None and len(buffer) >= 10:
                        packet = buffer[:10]
                        buffer = buffer[10:]

                    if packet is not None:
                        weight, raw_info = self._parse_weight(packet)
                        if weight is not None:
                            self.weight_updated.emit(weight)
                            self._check_stability(weight)
                            self.status_changed.emit(
                                True, "已连接 %s (%d bps) | 读数: %.3fkg | %s" %
                                (port, baud, weight, raw_info)
                            )
                    else:
                        if len(buffer) > 128:
                            buffer = buffer[-32:]
                        break
            else:
                time.sleep(0.05)

    def _parse_weight(self, raw):
        """解析电子秤数据 tuple: (weight_kg, display_str)"""
        try:
            cleaned = bytearray()
            for b in raw:
                if 0x20 <= b <= 0x7E:
                    cleaned.append(b)

            text = cleaned.decode("ascii", errors="ignore").strip()
            if not text:
                return None, raw.hex(' ')

            match = re.search(r'([+-]?\s*\d{1,5}\.\d{1,4})\s*(kg|g|jin|斤)?', text, re.IGNORECASE)
            if match:
                val_str = match.group(1).replace(" ", "")
                unit_str = (match.group(2) or "").lower()
                val = float(val_str)

                if unit_str in ("g", "克"):
                    kg_val = val / 1000.0
                elif unit_str in ("jin", "斤"):
                    kg_val = val / 2.0
                elif abs(val) > 30:
                    kg_val = val / 1000.0
                else:
                    kg_val = val

                return round(abs(kg_val), 3), text

            digits = re.sub(r'\D', '', text)
            if len(digits) >= 4:
                g_val = float(digits[:6]) if len(digits) >= 6 else float(digits)
                kg_val = round(g_val / 1000.0, 3)
                if kg_val < 50:
                    return kg_val, text

        except Exception:
            pass

        return None, raw.hex(' ')

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
