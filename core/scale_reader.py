"""
称重秤读取模块 — 官方日志无缝同步 + 串口自适应混合引擎
1. 官方系统打开时：实时无缝同步 C:\\YANGGUOFU-POS\\serial\\ 目录下的日志 (免串口冲突/免VSPE)
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

        self._ygf_serial_dir = r"C:\YANGGUOFU-POS\serial"

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
            active_log = self._find_active_ygf_log()
            if active_log:
                self._read_from_ygf_log(active_log)
            else:
                self._read_from_serial()

    def _find_active_ygf_log(self) -> str:
        """扫描 C:\\YANGGUOFU-POS\\serial 目录下最新更新的日志文件"""
        if not os.path.exists(self._ygf_serial_dir):
            return None

        try:
            candidates = []
            for fname in os.listdir(self._ygf_serial_dir):
                if fname.startswith("log_serial_ports"):
                    full_path = os.path.join(self._ygf_serial_dir, fname)
                    if os.path.isfile(full_path):
                        mtime = os.path.getmtime(full_path)
                        # 只要 10 秒内有文件修改或新建，即判定为活跃
                        if time.time() - mtime < 10.0:
                            candidates.append((mtime, full_path))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1]
        except Exception:
            pass

        return None

    def _parse_ygf_log_line(self, line: str):
        """从日志行中提取重量: 例如 '[Sat Aug 01...] DI_BAO read - 000.350'"""
        if not line:
            return None

        # 模式 1: DI_BAO read - 000.350
        m = re.search(r'read\s*-\s*([+-]?\d{1,5}\.\d{1,4})', line, re.IGNORECASE)
        if not m:
            # 模式 2: ["00.350", "00.350"...]
            m = re.search(r'"([+-]?\d{1,5}\.\d{1,4})"', line)
        if not m:
            # 模式 3: - 000.350
            m = re.search(r'-\s*([+-]?\d{1,5}\.\d{1,4})', line)
        if not m:
            # 模式 4: 浮点数提取
            m = re.search(r'([+-]?\d{1,5}\.\d{1,4})', line)

        if m:
            try:
                val = float(m.group(1))
                if val > 50:
                    val = val / 1000.0
                return round(abs(val), 3)
            except Exception:
                pass
        return None

    def _read_from_ygf_log(self, target_file: str):
        """模式 1：从官方系统实时日志中拉取重量（零串口冲突、零配置）"""
        self.status_changed.emit(True, "● 已连接官方称重服务 (%s)" % os.path.basename(target_file))
        last_weight = None

        try:
            # 启动时首先读取文件末尾最后 50 行，立刻显示当前读数！
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                for line in reversed(lines[-50:]):
                    w = self._parse_ygf_log_line(line)
                    if w is not None:
                        last_weight = w
                        self.weight_updated.emit(w)
                        self._check_stability(w)
                        self.status_changed.emit(
                            True, "● 已同步官方收银称重 | 读数: %.3f kg" % w
                        )
                        break

            # 然后进入持续轮询监听新写入行
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                last_pos = f.tell()

                while self._running:
                    # 每秒检测一次活跃日志文件
                    current_log = self._find_active_ygf_log()
                    if not current_log:
                        break  # 官方服务停止，切回物理串口

                    if current_log != target_file:
                        target_file = current_log
                        f = open(target_file, "r", encoding="utf-8", errors="ignore")
                        f.seek(0, os.SEEK_END)
                        last_pos = f.tell()

                    curr_pos = f.tell()
                    if curr_pos < last_pos:
                        f.seek(0, os.SEEK_SET)

                    lines = f.readlines()
                    last_pos = f.tell()

                    for line in reversed(lines):
                        w = self._parse_ygf_log_line(line)
                        if w is not None:
                            if w != last_weight:
                                last_weight = w
                                self.weight_updated.emit(w)
                                self._check_stability(w)
                                self.status_changed.emit(
                                    True, "● 已同步官方收银称重 | 读数: %.3f kg" % w
                                )
                            break

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
            if self._find_active_ygf_log():
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
                    if self._find_active_ygf_log():
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
            if self._find_active_ygf_log():
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
