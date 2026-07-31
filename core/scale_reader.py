"""
称重秤读取模块 — 官方日志无缝同步 + 串口自适应混合引擎
1. 官方系统打开时：实时无缝同步 C:\\YANGGUOFU-POS\\serial\\log_serial_ports_weight (免串口冲突/免VSPE)
2. 官方系统未打开时：直接打开 COM 串口进行 RTS/DTR 硬件探针读取
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
    双模式：官方系统日志同步模式 + 物理串口直连模式
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

        # 官方 POS 系统串口日志路径
        self._ygf_weight_log = r"C:\YANGGUOFU-POS\serial\log_serial_ports_weight"
        self._ygf_info_log = r"C:\YANGGUOFU-POS\serial\log_serial_ports_info"

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
        """重新连接称重服务"""
        self.stop()
        time.sleep(0.3)
        self.start()

    def _run_loop(self):
        """主循环 — 优先检查官方日志共享模式，其次退回物理串口"""
        while self._running:
            # 检查官方 POS 日志文件是否存在且在 5 秒内有更新
            if self._is_ygf_log_active():
                self._read_from_ygf_log()
            else:
                self._read_from_serial()

    def _is_ygf_log_active(self) -> bool:
        """检查官方系统的称重日志是否处于活跃更新状态"""
        for log_path in [self._ygf_weight_log, self._ygf_info_log]:
            if os.path.exists(log_path):
                try:
                    mtime = os.path.getmtime(log_path)
                    if time.time() - mtime < 5.0:  # 5秒内有写入数据
                        return True
                except Exception:
                    pass
        return False

    def _read_from_ygf_log(self):
        """模式 1：从官方系统实时日志中拉取重量（零串口冲突、零配置）"""
        self.status_changed.emit(True, "● 已同步官方收银系统称重服务 (免串口占用/免VSPE)")
        last_pos = 0
        last_weight = None

        target_file = self._ygf_weight_log if os.path.exists(self._ygf_weight_log) else self._ygf_info_log

        try:
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                last_pos = f.tell()

                while self._running:
                    # 如果日志停更超过 6 秒，退出此模式切回物理串口
                    if not self._is_ygf_log_active():
                        break

                    current_pos = f.tell()
                    if current_pos < last_pos:  # 文件可能被切割重写
                        f.seek(0, os.SEEK_SET)

                    lines = f.readlines()
                    last_pos = f.tell()

                    for line in reversed(lines):
                        line = line.strip()
                        if not line:
                            continue

                        # 格式1: [中国标准时间)] DI_BAO read - 000.350
                        # 格式2: ["00.350", "00.350", ...]
                        m = re.search(r'read\s*-\s*([+-]?\d{1,5}\.\d{1,4})', line)
                        if not m:
                            m = re.search(r'"([+-]?\d{1,5}\.\d{1,4})"', line)
                        if not m:
                            m = re.search(r'([+-]?\d{1,5}\.\d{1,4})', line)

                        if m:
                            try:
                                weight_val = float(m.group(1))
                                # 兼容克与公斤
                                if weight_val > 50:
                                    weight_val = weight_val / 1000.0
                                weight = round(abs(weight_val), 3)

                                if weight != last_weight:
                                    last_weight = weight
                                    self.weight_updated.emit(weight)
                                    self._check_stability(weight)
                                    self.status_changed.emit(
                                        True, "● 已同步官方收银称重 | 读数: %.3f kg" % weight
                                    )
                                break
                            except Exception:
                                pass

                    time.sleep(0.1)

        except Exception:
            time.sleep(0.5)

    def _read_from_serial(self):
        """模式 2：独立物理串口模式 (按波特率及端口全自动自适应)"""
        try:
            import serial
            import serial.tools.list_ports
        except ImportError:
            msg = "未安装 pyserial 库，请运行: pip install pyserial"
            self.error_occurred.emit(msg)
            self.status_changed.emit(False, msg)
            time.sleep(2.0)
            return

        baudrates = [9600, 4800, 2400, 19200]
        init_cmds = [b"\x05", b"\x0201\x03", b"W\r\n", b"\x0200\x03", b"Q\r\n"]

        pref_port = self.config.get("scale_port", "COM1")
        pref_baud = self.config.get("scale_baudrate", 9600)

        com_list = [p.device for p in serial.tools.list_ports.comports()]
        if pref_port not in com_list and os.name == 'nt':
            com_list.insert(0, pref_port)

        if not com_list:
            com_list = ["COM1", "COM2", "COM3", "COM4"]

        candidates = [(pref_port, pref_baud)]
        for p in com_list:
            for b in baudrates:
                if (p, b) not in candidates:
                    candidates.append((p, b))

        cand_idx = 0
        current_port, current_baud = candidates[0]

        while self._running:
            # 随时检测官方日志是否开启，如果开启立刻退出串口模式进入日志同步模式
            if self._is_ygf_log_active():
                return

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

                try:
                    self._serial.dtr = True
                    self._serial.rts = True
                except Exception:
                    pass

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

                while self._running and (time.time() - start_listen_t < 2.5):
                    if self._is_ygf_log_active():
                        return

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

                        if got_valid_data:
                            if (self.config.get("scale_port") != current_port or
                                    self.config.get("scale_baudrate") != current_baud):
                                self.config["scale_port"] = current_port
                                self.config["scale_baudrate"] = current_baud
                                save_config(self.config)

                            self._listen_serial_forever(current_port, current_baud, init_cmds)
                            return

                    time.sleep(0.05)

                cand_idx = (cand_idx + 1) % len(candidates)
                current_port, current_baud = candidates[cand_idx]

            except Exception as e:
                err_str = str(e)
                if "PermissionError" in err_str or "Access is denied" in err_str:
                    msg = "● 官方收银系统正在运行中 (已自动开启日志无缝同步)"
                    self.status_changed.emit(True, msg)
                    time.sleep(1.0)

                cand_idx = (cand_idx + 1) % len(candidates)
                current_port, current_baud = candidates[cand_idx]
                time.sleep(0.2)

    def _listen_serial_forever(self, port, baud, init_cmds):
        """直连物理串口长期接收"""
        buffer = b""
        last_query_t = 0
        query_idx = 0

        while self._running:
            if self._is_ygf_log_active():
                return

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
