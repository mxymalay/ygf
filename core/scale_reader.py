"""
称重秤读取模块 — 官方收银系统强绑定与实时同步引擎
PyQt5 + Python 3.8 兼容 (Windows 零锁共享读取，防 EBUSY 报错)
"""
import re
import os
import sys
import time
import ctypes
import threading
from ctypes import wintypes
from PyQt5.QtCore import QObject, pyqtSignal
from config import save_config
from core.official_pos import find_active_official_log


def read_file_shared(filepath: str) -> str:
    """
    以 Windows 原生 FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE 共享模式无锁读取文件。
    彻底避免官方收银软件 (yangguofu-pos) 写入日志时出现 EBUSY: resource busy or locked 错误！
    """
    if not os.path.exists(filepath):
        return ""

    if sys.platform == "win32":
        try:
            GENERIC_READ = 0x80000000
            FILE_SHARE_READ = 0x00000001
            FILE_SHARE_WRITE = 0x00000002
            FILE_SHARE_DELETE = 0x00000004
            OPEN_EXISTING = 3
            FILE_ATTRIBUTE_NORMAL = 0x80

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateFileW(
                filepath,
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            if handle != 0 and handle != -1 and handle != 0xFFFFFFFF:
                try:
                    size = kernel32.GetFileSize(handle, None)
                    if size > 0 and size != 0xFFFFFFFF:
                        buf = ctypes.create_string_buffer(size)
                        bytes_read = wintypes.DWORD()
                        if kernel32.ReadFile(handle, buf, size, ctypes.byref(bytes_read), None):
                            return buf.raw[:bytes_read.value].decode("utf-8", errors="ignore")
                finally:
                    kernel32.CloseHandle(handle)
        except Exception:
            pass

    # 回退到短连接读取 (打开即读，读完立刻关闭)
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


class ScaleReader(QObject):
    """
    称重秤读取器，运行在后台线程中。
    绑定官方系统串口日志实时无锁读取
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

        self._locked_weight = -1.0

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
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self.start()

    def _apply_fluctuation_filter(self, w: float) -> float:
        """
        消除 0.01kg 范围内的读数跳动：
        1. 初次或跳动超过 0.01kg，说明是真实重量改变（放上/拿走），重新锁定。
        2. 如果在 0.01kg 范围内跳动，取较大的值并锁定，不再向下跳动。
        """
        # 强制归零信任：如果电子秤读数归零，立刻解除防抖，避免卡在 0.008 等微小数值
        if w <= 0.001:
            self._locked_weight = 0.0
            return 0.0
            
        if self._locked_weight < 0 or abs(w - self._locked_weight) > 0.01:
            self._locked_weight = w
        else:
            if w > self._locked_weight:
                self._locked_weight = w
        return self._locked_weight

    def _run_loop(self):
        """主循环 — 根据配置选择数据源"""
        source = self.config.get("scale_source", "official")
        if source == "com":
            self._run_loop_com()
        else:
            self._run_loop_official()

    def _run_loop_official(self):
        """官方系统串口日志读取模式"""
        while self._running:
            active_log = self._find_active_ygf_log()
            if active_log:
                self._read_from_ygf_log(active_log)
            else:
                self.status_changed.emit(False, "● 警告：检测到【官方收银软件】已被关闭，请先打开官方软件！")
                time.sleep(1.5)

    def _run_loop_com(self):
        """COM 串口直连迪宝 ACS-G315 读取模式。

        该秤当前配置为 Samsung-China 轮询协议：主机以 5Hz 发送 ASCII
        ``$`` (0x24)，秤返回 ``000.402\\r`` 形式的 kg 重量。此参数由
        官方 yangguofu-pos 对 COM2 的实际串口记录确认。
        """
        import serial
        port = self.config.get("scale_port", "COM2")
        baudrate = int(self.config.get("scale_baudrate", 9600))
        
        self.status_changed.emit(False, "● 正在连接串口 %s ..." % port)
        
        while self._running:
            try:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.05,
                    write_timeout=0.5,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False,
                )
                # 和官方 POS 一致：DTR 开、RTS 关。不要打开 RTS 或混发探测命令。
                self._serial.dtr = True
                self._serial.rts = False

                self.status_changed.emit(True, "● 已连接串口秤 %s (波特率 %d)" % (port, baudrate))
                
                buffer = bytearray()
                poll_interval = 0.2  # 官方 POS 的实际轮询频率：5 次/秒
                next_poll_time = time.monotonic()

                while self._running:
                    try:
                        now = time.monotonic()
                        if now >= next_poll_time:
                            # ACS-G315 当前协议的唯一查询命令：0x24（ASCII '$'）。
                            self._serial.write(b"$")
                            self._serial.flush()
                            next_poll_time = now + poll_interval

                        # 读取可能被拆成多段的回包，例如 "0" + "00.402\\r"。
                        waiting = self._serial.in_waiting
                        data = self._serial.read(waiting or 1)
                        if data:
                            buffer.extend(data)
                            while True:
                                frame_end = next(
                                    (i for i, b in enumerate(buffer) if b in (0x0D, 0x0A)),
                                    -1,
                                )
                                if frame_end < 0:
                                    break
                                frame = bytes(buffer[:frame_end])
                                del buffer[:frame_end + 1]
                                # CRLF 时丢弃紧接的第二个终止符。
                                if buffer and buffer[0] in (0x0D, 0x0A):
                                    del buffer[0]
                                line = frame.decode("ascii", errors="ignore").strip()
                                if not line:
                                    continue
                                w = self._parse_com_weight(line)
                                if w is not None:
                                    w = self._apply_fluctuation_filter(w)
                                    self.weight_updated.emit(w)
                                    self._check_stability(w)
                                    self.status_changed.emit(
                                        True, "● 串口秤 %s | 读数: %.3f kg" % (port, w)
                                    )
                    except serial.SerialException:
                        break
                    except Exception:
                        time.sleep(0.1)
                        
            except Exception as e:
                self.status_changed.emit(False, "● 串口 %s 连接失败: %s" % (port, str(e)))
                time.sleep(2.0)
            finally:
                if self._serial:
                    try:
                        self._serial.close()
                    except Exception:
                        pass
                    self._serial = None

    def _parse_com_weight(self, line: str):
        """
        从串口原始数据行中解析重量值 (单位: kg)。
        兼容迪宝 (DIBAL ACS-G315)、顶尖、大华、梅特勒/托利多等常见电子秤协议格式：
        - 迪宝(DIBAL)连续模式: "\x02ST,GS,+0.350kg\x03" 或 "WW0.350" / "+0.350kg"
        - 纯数字: "0.350" 或 "+0.350" 或 "-0.350"
        - 日志与串口包裹格式: "read - 000.350" / "WN000.350"
        - 克重格式: "350g" 或 "350克"
        """
        if not line:
            return None

        # 清除 STX (\x02), ETX (\x03), ACK/NACK 等控制字符
        line = line.strip('\x00\x01\x02\x03\x04\r\n ')
        
        # 尝试带小数点标准格式: 例如 "+ 0.350kg", "0.350", "- 00.350", "WW0.350kg", "ST,GS,+0.350"
        m = re.search(r'([+-]?\s*\d{1,5}\.\d{1,4})', line)
        if m:
            try:
                val = float(m.group(1).replace(" ", ""))
                if val > 50:
                    val = val / 1000.0
                return round(abs(val), 3)
            except Exception:
                pass

        # 尝试带单位的整型克重格式: 例如 "350g" / "350克"
        m2 = re.search(r'([+-]?\s*\d{3,6})\s*(?:g|克)', line, re.IGNORECASE)
        if m2:
            try:
                val = float(m2.group(1).replace(" ", "")) / 1000.0
                return round(abs(val), 3)
            except Exception:
                pass

        return None

    def _find_active_ygf_log(self) -> str:
        """Find the configured or compatible official POS log location."""
        return find_active_official_log(self.config)

    def _parse_ygf_log_line(self, line: str):
        """从日志行中提取重量: 例如 '["00.350","00.350",...] --- 6' 或 '[Sat Aug 01...] DI_BAO read - 000.350'"""
        if not line:
            return None

        # 匹配 JSON 数组格式: ["00.000","00.350","00.350",...]
        matches = re.findall(r'"([+-]?\d{1,5}\.\d{1,4})"', line)
        if matches:
            # 如果有多个数值，优先选取非零有效重量；若全为零则取第一个
            valid_vals = []
            for item in matches:
                try:
                    v = float(item)
                    if v > 50:
                        v = v / 1000.0
                    v = round(abs(v), 3)
                    valid_vals.append(v)
                except Exception:
                    pass
            if valid_vals:
                non_zeros = [v for v in valid_vals if v > 0.001]
                return non_zeros[0] if non_zeros else valid_vals[0]

        # 单值正则匹配
        m = re.search(r'read\s*-\s*([+-]?\d{1,5}\.\d{1,4})', line, re.IGNORECASE)
        if not m:
            m = re.search(r'-\s*([+-]?\d{1,5}\.\d{1,4})', line)
        if not m:
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
        """从官方系统实时日志中拉取重量 (Windows 共享无锁模式)"""
        self.status_changed.emit(True, "● 已连接官方称重服务 (%s)" % os.path.basename(target_file))
        last_weight = None

        while self._running:
            current_log = self._find_active_ygf_log()
            if not current_log:
                break  # 官方系统关闭

            content = read_file_shared(current_log)
            if content:
                lines = content.strip().splitlines()
                found_new = False
                for line in reversed(lines[-50:]):
                    raw_w = self._parse_ygf_log_line(line)
                    if raw_w is not None:
                        w = self._apply_fluctuation_filter(raw_w)
                        self.weight_updated.emit(w)
                        self._check_stability(w)
                        last_weight = w
                        found_new = True
                        self.status_changed.emit(
                            True, "● 已同步官方收银称重 | 读数: %.3f kg" % w
                        )
                        break

                if not found_new and last_weight is not None:
                    self.weight_updated.emit(last_weight)
                    self._check_stability(last_weight)

            time.sleep(0.2)

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
