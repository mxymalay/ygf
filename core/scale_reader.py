"""
称重秤读取模块 — 官方收银系统强绑定与实时同步引擎
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
    绑定官方系统串口日志实时读取
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
        """从官方系统实时日志中拉取重量"""
        self.status_changed.emit(True, "● 已连接官方称重服务 (%s)" % os.path.basename(target_file))
        last_weight = None

        try:
            # 启动时首先读取最后 50 行，立刻显示当前读数！
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

            # 持续轮询监听新写入行
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                last_pos = f.tell()

                while self._running:
                    current_log = self._find_active_ygf_log()
                    if not current_log:
                        break  # 官方系统关闭

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

                    found_new = False
                    for line in reversed(lines):
                        w = self._parse_ygf_log_line(line)
                        if w is not None:
                            self.weight_updated.emit(w)
                            self._check_stability(w)
                            last_weight = w
                            found_new = True
                            break

                    # 若日志没有新行（说明读数静止未变），持续推送当前静止重量给 UI 判定稳定！
                    if not found_new and last_weight is not None:
                        self.weight_updated.emit(last_weight)
                        self._check_stability(last_weight)

                    time.sleep(0.2)

        except Exception:
            time.sleep(0.5)

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
