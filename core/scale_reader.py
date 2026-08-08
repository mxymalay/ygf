"""
称重秤读取模块 — 官方收银系统强绑定与实时同步引擎
PyQt5 + Python 3.8 兼容 (Windows 零锁共享读取，防 EBUSY 报错)
"""
import re
import os
import sys
import time
import hashlib
import ctypes
import threading
from ctypes import wintypes
from PyQt5.QtCore import QObject, pyqtSignal
from config import save_config
from core.official_pos import find_active_official_log
from core.app_logger import log_event, CAT_SCALE


def clear_serial_buffers(serial_handle) -> None:
    """Discard stale input/output bytes before a serial session starts."""
    for method_name in ("reset_input_buffer", "reset_output_buffer"):
        method = getattr(serial_handle, method_name, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass


def read_file_shared(filepath: str, max_bytes: int = None) -> str:
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
                        read_size = size
                        if max_bytes and size > max_bytes:
                            # Serial logs can grow for the whole business day.
                            # Only the tail contains useful live readings.
                            offset = size - int(max_bytes)
                            kernel32.SetFilePointer(handle, offset, None, 0)
                            read_size = int(max_bytes)
                        buf = ctypes.create_string_buffer(read_size)
                        bytes_read = wintypes.DWORD()
                        if kernel32.ReadFile(handle, buf, read_size, ctypes.byref(bytes_read), None):
                            return buf.raw[:bytes_read.value].decode("utf-8", errors="ignore")
                finally:
                    kernel32.CloseHandle(handle)
        except Exception:
            pass

    # 回退到短连接读取 (打开即读，读完立刻关闭)
    try:
        with open(filepath, "rb") as f:
            if max_bytes:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - int(max_bytes)), os.SEEK_SET)
            return f.read().decode("utf-8", errors="ignore")
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
    weighing_cycle_started = pyqtSignal(float)
    zero_stable = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._running = False
        self._thread = None
        self._serial = None
        self._ever_started = False

        self._last_weights = []
        self._reload_config_values()
        # A newly launched process has no trustworthy memory of the bowl
        # currently on the scale.  Require one real stable zero before it may
        # route a non-zero weight; otherwise a restart can re-route an old
        # official bowl as a new customer.
        self._cycle_armed = False
        self._zero_reported = False
        self._zero_sample_count = 0
        self._last_stable_emitted = None
        self._startup_zero_seen = False

        self._locked_weight = -1.0
        # Diagnostic logging is change-based (plus a 5-second heartbeat), not
        # every 200 ms poll, so long-running POS sessions remain lightweight.
        self._last_logged_weight = None
        self._last_weight_log_monotonic = 0.0
        self._last_logged_source = ""

    def _reload_config_values(self):
        def safe_float(name, default):
            try:
                return float(self.config.get(name, default))
            except (TypeError, ValueError):
                return float(default)

        def safe_int(name, default):
            try:
                return int(self.config.get(name, default))
            except (TypeError, ValueError):
                return int(default)

        self._stable_threshold = max(0.001, safe_float("stable_threshold", 0.01))
        self._stable_count = max(2, safe_int("stable_count", 5))
        # A bowl is physically gone as soon as the scale has produced two
        # fresh zero frames.  Keep the longer stability window for the next
        # non-zero weight, but do not make a fast customer transition wait a
        # full second at zero.
        self._zero_stable_count = max(2, safe_int("zero_stable_count", 2))
        self._zero_threshold = max(0.0, safe_float("scale_zero_threshold_kg", 0.005))
        self._cycle_start_threshold = max(
            self._zero_threshold,
            safe_float("min_valid_weight_kg", 0.08),
        )
        self._maximum_weight = max(1.0, safe_float("scale_max_weight_kg", 15.0))
        self._stale_timeout = max(1.0, safe_float("scale_stale_timeout_sec", 3.0))

    def _log_weight_sample(self, weight_kg, source, raw=""):
        """Persist useful scale samples without flooding app_events.jsonl."""
        now = time.monotonic()
        weight = round(float(weight_kg or 0.0), 3)
        changed = (
            self._last_logged_weight is None
            or abs(weight - self._last_logged_weight) >= 0.001
            or source != self._last_logged_source
        )
        heartbeat = now - self._last_weight_log_monotonic >= 5.0
        if not changed and not heartbeat:
            return
        detail = "来源=%s | 重量=%.3f kg" % (source, weight)
        if raw:
            detail += " | 原始=%s" % str(raw).replace("\r", "").replace("\n", "")[:160]
        log_event(CAT_SCALE, "称重读数", detail)
        self._last_logged_weight = weight
        self._last_weight_log_monotonic = now
        self._last_logged_source = source

    def start(self):
        """启动称重读取"""
        if self._thread and self._thread.is_alive():
            return False
        self._running = True
        self._reset_runtime_state(preserve_cycle=self._ever_started)
        self._ever_started = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

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
            # The official-log loop may be in a 1.5 second wait and a failed
            # COM open waits 2 seconds.  Never turn _running back on while the
            # old worker is still alive, otherwise two readers share one
            # serial handle and duplicate every signal.
            self._thread.join(timeout=3.0)
        if self._thread and self._thread.is_alive():
            message = "旧称重读取线程未能安全退出，本次没有启动第二个读取线程"
            self.status_changed.emit(False, message)
            self.error_occurred.emit(message)
            log_event(CAT_SCALE, "称重读取重启被阻止", message)
            return False
        self._thread = None
        return self.start()

    def _reset_runtime_state(self, preserve_cycle=False):
        self._reload_config_values()
        self._last_weights = []
        self._locked_weight = -1.0
        self._zero_sample_count = 0
        if not preserve_cycle:
            self._cycle_armed = False
            self._zero_reported = False
            self._startup_zero_seen = False
        self._last_stable_emitted = None

    def has_observed_stable_zero(self):
        """Whether this reader has seen a live stable zero since cold start."""
        return bool(self._startup_zero_seen)

    def _apply_fluctuation_filter(self, w: float) -> float:
        """
        保留秤的真实三位小数读数。稳定性由后续对称窗口判断，不能采用
        “只升不降”的最大值锁定，否则会长期向上偏置最多约 10g。
        """
        if w <= self._zero_threshold:
            self._locked_weight = 0.0
            return 0.0
        self._locked_weight = round(float(w), 3)
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
                clear_serial_buffers(self._serial)

                self.status_changed.emit(True, "● 已连接串口秤 %s (波特率 %d)" % (port, baudrate))
                log_event(CAT_SCALE, "称重串口已连接", "端口=%s | 波特率=%d" % (port, baudrate))
                self._last_weights = []
                
                buffer = bytearray()
                poll_interval = 0.2  # 官方 POS 的实际轮询频率：5 次/秒
                next_poll_time = time.monotonic()
                last_valid_reply = time.monotonic()

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
                            if len(buffer) > 512 and not any(b in (0x0D, 0x0A) for b in buffer):
                                log_event(CAT_SCALE, "称重串口丢弃异常长数据", "端口=%s | 长度=%d" % (port, len(buffer)))
                                buffer.clear()
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
                                    last_valid_reply = time.monotonic()
                                    self._log_weight_sample(w, "COM:%s" % port, line)
                                    self.weight_updated.emit(w)
                                    self._check_stability(w)
                                    self.status_changed.emit(
                                        True, "● 串口秤 %s | 读数: %.3f kg" % (port, w)
                                    )
                        if time.monotonic() - last_valid_reply > self._stale_timeout:
                            raise serial.SerialException(
                                "连续 %.1f 秒没有收到有效称重回包" % self._stale_timeout
                            )
                    except serial.SerialException as exc:
                        log_event(CAT_SCALE, "称重串口断开", "端口=%s | %s" % (port, str(exc)[:160]))
                        self.status_changed.emit(False, "● 串口秤 %s 已断开: %s" % (port, exc))
                        break
                    except Exception as exc:
                        log_event(CAT_SCALE, "称重读取循环异常", "端口=%s | %s" % (port, str(exc)[:160]))
                        self.status_changed.emit(False, "● 串口秤 %s 读取异常: %s" % (port, exc))
                        break
                        
            except Exception as e:
                self.status_changed.emit(False, "● 串口 %s 连接失败: %s" % (port, str(e)))
                log_event(CAT_SCALE, "称重串口连接失败", "端口=%s | %s" % (port, str(e)[:160]))
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
                return self._sanitize_weight(val)
            except Exception:
                pass

        # 尝试带单位的整型克重格式: 例如 "350g" / "350克"
        m2 = re.search(r'([+-]?\s*\d{3,6})\s*(?:g|克)', line, re.IGNORECASE)
        if m2:
            try:
                val = float(m2.group(1).replace(" ", "")) / 1000.0
                return self._sanitize_weight(val)
            except Exception:
                pass

        return None

    def _sanitize_weight(self, value):
        """Clamp negative/tare readings to zero and reject impossible loads."""
        value = float(value)
        if value < 0:
            return 0.0
        if value > self._maximum_weight:
            log_event(
                CAT_SCALE,
                "称重读数超出量程",
                "读数=%.3fkg | 最大允许=%.3fkg" % (value, self._maximum_weight),
            )
            return None
        return round(value, 3)

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
            # The array is a rolling sample batch; only the last item is the
            # freshest.  Falling back to an earlier valid/non-zero item would
            # replay the old bowl when the newest sample is zero or invalid.
            try:
                value = float(matches[-1])
                if value > 50:
                    value = value / 1000.0
                return self._sanitize_weight(value)
            except Exception:
                return None

        # 单值正则匹配
        m = re.search(r'read\s*-\s*([+-]?\d{1,5}\.\d{1,4})', line, re.IGNORECASE)
        if not m and re.search(r'(?:DI_BAO|weight|kg|\bW[WN]\b|ST,GS)', line, re.IGNORECASE):
            m = re.search(r'([+-]?\d{1,5}\.\d{1,4})', line)

        if m:
            try:
                val = float(m.group(1))
                if val > 50:
                    val = val / 1000.0
                return self._sanitize_weight(val)
            except Exception:
                pass
        return None

    @staticmethod
    def _ygf_log_snapshot_token(path, stat, content):
        """Identify an official-log snapshot beyond coarse file timestamps.

        Some official POS versions overwrite a fixed-size log record, and
        NTFS/network shares may expose a coarse or unchanged mtime for that
        write. Including the tail content hash catches those real writes
        without treating an idle cached record as a new scale sample.
        """
        mtime_ns = getattr(stat, "st_mtime_ns", int(float(stat.st_mtime) * 1000000000))
        ctime_ns = getattr(stat, "st_ctime_ns", int(float(stat.st_ctime) * 1000000000))
        digest = hashlib.sha1(str(content or "").encode("utf-8", errors="replace")).hexdigest()
        return (str(path), int(mtime_ns), int(ctime_ns), int(stat.st_size), digest)

    def _latest_ygf_log_record(self, content, allow_unterminated=False):
        """Return the newest parseable record only when its line is complete.

        A writer can expose half of a line while it is being overwritten. A
        newline-terminated record is safe immediately; an unterminated final
        line is considered safe only after the identical snapshot has been
        observed on the next poll.
        """
        if not content:
            return None
        if not allow_unterminated and not str(content).endswith(("\n", "\r")):
            return None
        for line in reversed(str(content).splitlines()[-50:]):
            raw_weight = self._parse_ygf_log_line(line)
            if raw_weight is not None:
                return raw_weight, line
        return None

    def _read_from_ygf_log(self, target_file: str):
        """从官方系统实时日志中拉取重量 (Windows 共享无锁模式)"""
        self.status_changed.emit(True, "● 已连接官方称重服务 (%s)" % os.path.basename(target_file))
        log_event(CAT_SCALE, "官方称重日志已连接", "文件=%s" % target_file)
        last_seen_token = None
        last_processed_token = None
        pending_unterminated_token = None
        last_fresh_record_at = time.monotonic()
        stale_reported = False
        self._last_weights = []

        while self._running:
            current_log = self._find_active_ygf_log()
            if not current_log:
                break  # 官方系统关闭

            try:
                stat = os.stat(current_log)
            except OSError:
                time.sleep(0.2)
                continue

            content = read_file_shared(current_log, max_bytes=64 * 1024)
            token = self._ygf_log_snapshot_token(current_log, stat, content)
            if last_seen_token is None:
                # The existing tail can describe a bowl from before this POS
                # was opened.  Do not treat it as a live reading; wait for the
                # official POS to write a fresh sample after startup.
                last_seen_token = token
                last_processed_token = token
                time.sleep(0.2)
                continue
            changed = token != last_seen_token
            last_seen_token = token

            # If the writer is exposing an incomplete last line, wait for a
            # completed write or one identical re-read. Never fall back to a
            # previous complete line, which would replay an old bowl.
            allow_unterminated = False
            if content and not content.endswith(("\n", "\r")):
                if token != pending_unterminated_token:
                    pending_unterminated_token = token
                    time.sleep(0.2)
                    continue
                allow_unterminated = True
            else:
                pending_unterminated_token = None

            if token == last_processed_token:
                if (
                    not stale_reported
                    and time.monotonic() - last_fresh_record_at >= self._stale_timeout
                ):
                    stale_reported = True
                    self.status_changed.emit(
                        False,
                        "官方称重日志连续 %.1f 秒没有新读数，已停止使用旧重量"
                        % self._stale_timeout,
                    )
                time.sleep(0.2)
                continue
            # A changing mtime/ctime with identical bytes is a fresh POS
            # poll; conversely the hash catches same-size block overwrites.
            if not changed and not allow_unterminated:
                time.sleep(0.2)
                continue
            last_processed_token = token

            record = self._latest_ygf_log_record(content, allow_unterminated)
            if record is not None:
                raw_w, line = record
                w = self._apply_fluctuation_filter(raw_w)
                self._log_weight_sample(w, "官方日志", line)
                self.weight_updated.emit(w)
                self._check_stability(w)
                last_fresh_record_at = time.monotonic()
                stale_reported = False
                self.status_changed.emit(
                    True, "● 已同步官方收银称重 | 读数: %.3f kg" % w
                )

            time.sleep(0.2)

    def _check_stability(self, weight):
        """Emit stable values and exactly one start/zero event per bowl."""
        # Zero is a physical release gate, not a price measurement.  Confirm
        # it quickly so "customer A lifts, customer B immediately puts down"
        # does not miss the only zero interval.  The next non-zero bowl still
        # needs the full stable_count window below before it can route.
        if float(weight or 0.0) <= self._zero_threshold:
            self._zero_sample_count += 1
            if self._zero_sample_count >= self._zero_stable_count:
                self._startup_zero_seen = True
                self._cycle_armed = True
                if not self._zero_reported:
                    self._zero_reported = True
                    self.zero_stable.emit()
        else:
            self._zero_sample_count = 0

        self._last_weights.append(weight)
        if len(self._last_weights) > self._stable_count:
            self._last_weights.pop(0)

        if len(self._last_weights) != self._stable_count:
            return
        max_w = max(self._last_weights)
        min_w = min(self._last_weights)
        if (max_w - min_w) > self._stable_threshold:
            return

        avg_weight = round(sum(self._last_weights) / len(self._last_weights), 3)
        if avg_weight <= self._zero_threshold:
            avg_weight = 0.0
        if self._last_stable_emitted is None or abs(avg_weight - self._last_stable_emitted) >= 0.001:
            self._last_stable_emitted = avg_weight
            self.weight_stable.emit(avg_weight)

        if avg_weight <= self._zero_threshold:
            self._startup_zero_seen = True
            self._cycle_armed = True
            if not self._zero_reported:
                self._zero_reported = True
                self.zero_stable.emit()
            return

        self._zero_reported = False
        if avg_weight <= self._cycle_start_threshold:
            return
        if self._cycle_armed:
            self._cycle_armed = False
            self.weighing_cycle_started.emit(avg_weight)
