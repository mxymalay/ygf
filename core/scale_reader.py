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

    def _apply_fluctuation_filter(self, w: float) -> float:
        """
        消除 0.01kg 范围内的读数跳动：
        1. 初次或跳动超过 0.01kg，说明是真实重量改变（放上/拿走），重新锁定。
        2. 如果在 0.01kg 范围内跳动，取较大的值并锁定，不再向下跳动。
        """
        if self._locked_weight < 0 or abs(w - self._locked_weight) > 0.01:
            self._locked_weight = w
        else:
            if w > self._locked_weight:
                self._locked_weight = w
        return self._locked_weight

    def _run_loop(self):
        """主循环 — 绑定官方系统串口日志读取"""
        while self._running:
            active_log = self._find_active_ygf_log()
            if active_log:
                self._read_from_ygf_log(active_log)
            else:
                self.status_changed.emit(False, "● 警告：检测到【官方收银软件】已被关闭，请先打开官方软件！")
                time.sleep(1.5)

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
                        # 官方收银开着时每秒写入，5 秒内有写入判定为活跃
                        if time.time() - mtime < 5.0:
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

        m = re.search(r'read\s*-\s*([+-]?\d{1,5}\.\d{1,4})', line, re.IGNORECASE)
        if not m:
            m = re.search(r'"([+-]?\d{1,5}\.\d{1,4})"', line)
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
