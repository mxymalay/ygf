"""Detached local host for the takeout RAW-print interception channel.

The official POS sends an external-order job to a Windows TCP/IP queue that
targets 127.0.0.1.  That TCP listener must *not* live in the PyQt POS process:
closing, restarting, or crashing the screen must not make the official queue
unavailable.  This module runs the listener as a separate per-user process so
it can still use the operator's Windows printer connections.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from config import BASE_DIR, DATA_DIR, MODULE_FILES, load_config, save_config
from core.database import Database
from core.printer import ReceiptPrinter
from core.takeout_interceptor import (
    TakeoutPrintInterceptor,
    build_takeout_escpos_ticket,
    parse_official_pos_text,
)
from core.takeout_jobs import TakeoutJobStore
from core.takeout_relay_service import TakeoutRelayServiceController
from core.takeout_relay import (
    MODE_COMPATIBILITY,
    MODE_POLICY_AUTO,
    enhanced_mode_eligibility,
    validate_relay_config,
)


STATUS_PATH = os.path.join(DATA_DIR, "takeout_proxy_status.json")
CONTROL_PATH = os.path.join(DATA_DIR, "takeout_proxy_control.json")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _atomic_json_write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".",
        suffix=".tmp",
        dir=os.path.dirname(path),
    )
    os.close(fd)
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                return
            except OSError:
                if attempt >= 7:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def read_proxy_status():
    """Return the last host state; malformed/stale files are treated as down."""
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def request_proxy_stop():
    """Ask the detached process to release the local port without killing it."""
    _atomic_json_write(CONTROL_PATH, {"command": "stop", "requested_at": _now()})


def _clear_stop_request():
    try:
        os.remove(CONTROL_PATH)
    except OSError:
        pass


def _stop_requested():
    try:
        with open(CONTROL_PATH, "r", encoding="utf-8") as stream:
            return json.load(stream).get("command") == "stop"
    except (OSError, TypeError, ValueError):
        return False


def _is_process_alive(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    # On some Win7/PyInstaller combinations, os.kill(pid, 0) can leak a
    # SystemError with an already-set Windows error instead of raising the
    # usual OSError when the detached relay PID is stale or inaccessible.
    # A dead/unqueryable relay is a normal degraded state and must never stop
    # the main POS window from starting.
    except (OSError, SystemError, TypeError, ValueError):
        return False


def _config_signature():
    result = []
    for key in ("sys", "takeout"):
        path = MODULE_FILES[key]
        try:
            stat = os.stat(path)
            result.append((path, stat.st_mtime_ns, stat.st_size))
        except OSError:
            result.append((path, 0, 0))
    return tuple(result)


def _takeout_options(config):
    options = {
        "mark_multi_qty_star": bool(config.get("takeout_mark_star", True)),
        "show_prices": bool(config.get("takeout_show_prices", False)),
        "show_address": bool(config.get("takeout_show_address", True)),
        "show_order_time": bool(config.get("takeout_show_time", True)),
        "show_full_order_id": bool(config.get("takeout_show_full_id", False)),
        "show_preorder_alert": bool(config.get("takeout_show_preorder", True)),
        "takeout_match_mode": config.get("takeout_match_mode", "contains"),
        "official_pos_field_mapping": config.get("official_pos_field_mapping", {}),
    }
    categories = config.get("takeout_categories")
    if isinstance(categories, list) and categories:
        options["custom_categories"] = categories
    return options


class TakeoutProxyHost:
    """Owns the listener and the physical-printer forwarding path."""

    def __init__(self):
        self.config = load_config()
        self.jobs = TakeoutJobStore()
        self.official_db = Database()
        self.interceptor = TakeoutPrintInterceptor(self.config, on_order=self._handle_order)
        self.running = False
        self.started_at = _now()
        self.last_message = "正在启动外卖中继守护进程"
        self.last_error = ""
        self.last_order = ""
        self.current_mode = MODE_COMPATIBILITY
        self.last_identified_at = ""
        self.last_enhanced_success_at = str(self.config.get("takeout_relay_last_success_at", "") or "")
        self.last_payload_type = ""
        self.mode_reason = str(self.config.get("takeout_relay_mode_reason", "") or "")
        self.last_mode_change_at = str(self.config.get("takeout_relay_mode_changed_at", "") or "")
        self._last_status_at = 0
        self._config_signature = _config_signature()

    def _set_mode(self, mode, reason=""):
        """Persist automatic mode transitions without deleting configuration."""
        mode = str(mode or MODE_COMPATIBILITY)
        reason = str(reason or "")[:500]
        previous = self.current_mode
        self.current_mode = mode
        self.mode_reason = reason
        if previous == mode:
            self.config["takeout_relay_mode"] = mode
            self.config["takeout_relay_mode_reason"] = reason
            return
        changed_at = _now()
        self.last_mode_change_at = changed_at
        policy = str(self.config.get("takeout_relay_mode_policy", MODE_POLICY_AUTO) or MODE_POLICY_AUTO)
        try:
            self.official_db.record_relay_mode_event(previous, mode, policy, reason, changed_at)
        except Exception:
            pass
        self.config["takeout_relay_mode"] = mode
        self.config["takeout_relay_mode_reason"] = reason
        self.config["takeout_relay_mode_changed_at"] = changed_at
        try:
            save_config(self.config)
            self._config_signature = _config_signature()
        except Exception:
            pass

    def _write_status(self, running=None):
        _atomic_json_write(STATUS_PATH, {
            "running": self.running if running is None else bool(running),
            "pid": os.getpid(),
            "port": self.interceptor.port,
            "started_at": self.started_at,
            "updated_at": _now(),
            "message": self.last_message,
            "last_error": self.last_error,
            "last_order": self.last_order,
            "mode": self.current_mode,
            "mode_policy": str(self.config.get("takeout_relay_mode_policy", MODE_POLICY_AUTO) or MODE_POLICY_AUTO),
            "mode_reason": self.mode_reason,
            "mode_changed_at": self.last_mode_change_at,
            "last_identified_at": self.last_identified_at,
            "last_enhanced_success_at": self.last_enhanced_success_at,
            "payload_type": self.last_payload_type,
        })
        self._last_status_at = time.time()

    def _refresh_status_if_due(self):
        if time.time() - self._last_status_at >= 1:
            self._write_status()

    def _reload_if_changed(self):
        signature = _config_signature()
        if signature == self._config_signature:
            return
        # Config files are atomically written.  A transient error is retried on
        # the next loop instead of stopping a working listener.
        try:
            new_config = load_config()
        except Exception as exc:
            self.last_error = "读取新配置失败：%s" % exc
            return
        self._config_signature = _config_signature()
        self.config = new_config
        self.interceptor.update_config(new_config)
        if str(new_config.get("takeout_relay_mode_policy", MODE_POLICY_AUTO)) != MODE_POLICY_AUTO:
            self._set_mode(MODE_COMPATIBILITY, "用户手动锁定兼容模式")
        if not self.interceptor.is_enabled:
            self.last_message = "配置已停用外卖中继"
            self.running = False
        else:
            self.last_message = "已应用外卖中继新配置"

    def _handle_order(self, intercepted):
        raw_text = str(intercepted.get("raw_text", ""))
        parsed = parse_official_pos_text(raw_text, _takeout_options(self.config))
        raw_payload = intercepted.get("raw_payload") or b""
        self.last_payload_type = str(intercepted.get("payload_type", "binary_or_unknown") or "binary_or_unknown")
        parse_failed = bool(intercepted.get("parse_failed")) or not (
            parsed.get("is_official_receipt") and (
                parsed.get("item_count") or parsed.get("order_amount") is not None
                or parsed.get("full_order_id")
            )
        )
        if parse_failed:
            # The relay owns the physical output path.  Preserve the original
            # receipt whenever recognition cannot be trusted; parsing must
            # never turn into a silent print loss.
            queue_name = str(self.config.get("takeout_proxy_queue_name", "")).strip().casefold()
            physical_name = str(self.config.get("printer_name", "")).strip().casefold() if str(self.config.get("printer_type", "windows")).lower() == "windows" else ""
            if str(self.config.get("printer_type", "windows")).lower() == "windows" and not physical_name:
                try:
                    import win32print
                    physical_name = str(win32print.GetDefaultPrinter() or "").strip().casefold()
                except Exception:
                    pass
            if queue_name and queue_name == physical_name:
                self.last_error = "真实打印机不能等于中继队列，已阻止原始转发回环"
                self.last_message = "解析失败且配置存在回环风险，已降级并阻止转发"
                self._set_mode(MODE_COMPATIBILITY, "中继队列与实体打印机相同，已阻止打印回环")
                return
            if raw_payload:
                printer = ReceiptPrinter(self.config)
                if printer.print_raw(raw_payload):
                    self.last_error = ""
                    self.last_message = "订单状态未知，已原始转发打印；继续使用兼容模式"
                else:
                    self.last_error = printer.last_error or "原始小票转发失败"
                    self.last_message = "订单状态未知，原始小票转发失败；已降级到兼容模式"
            else:
                self.last_error = "无法取得原始打印数据"
                self.last_message = "订单状态未知且无原始数据，已降级到兼容模式"
            self._set_mode(MODE_COMPATIBILITY, self.last_message)
            return

        # Dine-in/customer receipts share the relay queue but must keep their
        # original layout. They are audited and can contribute verified
        # official revenue, while only external orders use the takeout
        # reformatting/reprint path below.
        if parsed.get("receipt_kind") == "dinein":
            parsed["raw_text"] = raw_text
            self.last_identified_at = _now()
            try:
                created, _row = self.official_db.record_official_receipt(
                    parsed.get("receipt_key"), parsed=parsed,
                    payload_type=self.last_payload_type,
                    capture_path=intercepted.get("capture_path", ""),
                    observed_at=self.last_identified_at,
                )
            except Exception as exc:
                created = True
                _row = None
                self.last_error = "官方票据流水入账失败：%s" % exc
            parsed["duplicate"] = not created
            parsed["conflict_detected"] = bool((_row or {}).get("conflict_detected"))
            self.last_order = "%s %s" % (
                parsed.get("platform", "官方POS-堂食"),
                parsed.get("full_order_id") or parsed.get("order_no") or "无订单号",
            )
            eligibility = enhanced_mode_eligibility(
                self.config,
                {"running": self.running and self.interceptor._running},
                parsed,
            )
            self._set_mode(eligibility["mode"], "；".join(eligibility.get("reasons") or []) or "官方堂食票据已验证")
            if eligibility.get("eligible") and not parsed.get("conflict_detected"):
                self.last_enhanced_success_at = self.last_identified_at
                try:
                    self.official_db.record_official_revenue(
                        order_key=parsed.get("receipt_key"),
                        platform=parsed.get("platform", "官方POS-堂食"),
                        order_id=parsed.get("full_order_id") or parsed.get("order_no", ""),
                        amount=parsed.get("order_amount"),
                        payment_status="PAID",
                        source="official_pos_relay",
                        created_at=self.last_identified_at,
                    )
                except Exception as exc:
                    self.last_error = "官方营业额入账失败：%s" % exc
                try:
                    self.config["takeout_relay_last_success_at"] = self.last_enhanced_success_at
                    save_config(self.config)
                except Exception:
                    pass
            if raw_payload:
                printer = ReceiptPrinter(self.config)
                if printer.print_raw(raw_payload):
                    self.last_error = ""
                    self.last_message = (
                        "堂食票据已原样转发并记录：%s" %
                        ("重复观察" if parsed.get("duplicate") else "已保存")
                    )
                else:
                    self.last_error = printer.last_error or "堂食原始小票转发失败"
                    self.last_message = "堂食票据已记录，但原始转发失败"
            else:
                self.last_error = "无法取得堂食原始打印数据"
                self.last_message = "堂食票据已记录，但没有原始数据可转发"
            return

        parsed["raw_text"] = raw_text
        self.last_identified_at = _now()
        self.last_payload_type = str(intercepted.get("payload_type", "text_or_raw") or "text_or_raw")
        try:
            _receipt_created, _receipt_row = self.official_db.record_official_receipt(
                parsed.get("receipt_key"), parsed=parsed,
                payload_type=self.last_payload_type,
                capture_path=intercepted.get("capture_path", ""),
                observed_at=self.last_identified_at,
            )
            parsed["conflict_detected"] = bool((_receipt_row or {}).get("conflict_detected"))
        except Exception as exc:
            self.last_error = "官方票据流水入账失败：%s" % exc
        job, created = self.jobs.create_or_get(parsed, raw_text)
        parsed["duplicate"] = not created
        try:
            self.official_db.record_takeout_order(
                job.get("key"), parsed=parsed, job=job,
                duplicate=not created, observed_at=self.last_identified_at,
            )
        except Exception as exc:
            # The SQLite audit ledger is auxiliary to printing; do not block
            # the receipt path if a local database is temporarily locked.
            self.last_error = "外卖流水入账失败：%s" % exc
        eligibility = enhanced_mode_eligibility(
            self.config,
            {"running": self.running and self.interceptor._running},
            parsed,
        )
        self._set_mode(eligibility["mode"], "；".join(eligibility.get("reasons") or []) or "官方外卖票据已验证")
        if eligibility.get("eligible"):
            self.last_enhanced_success_at = self.last_identified_at
            if not job.get("conflict_detected"):
                try:
                    self.official_db.record_official_revenue(
                        order_key=job.get("key"),
                        platform=job.get("platform", "外卖订单"),
                        order_id=job.get("full_order_id") or job.get("order_no", ""),
                        amount=parsed.get("order_amount"),
                        payment_status="PAID",
                        source="takeout_relay",
                        created_at=self.last_identified_at,
                    )
                except Exception as exc:
                    # A reporting ledger failure must never interrupt the
                    # original receipt forwarding path.
                    self.last_error = "官方营业额入账失败：%s" % exc
            try:
                self.config["takeout_relay_last_success_at"] = self.last_enhanced_success_at
                save_config(self.config)
            except Exception:
                pass
        self.last_order = "%s %s（%d 项）" % (
            job.get("platform", "外卖"), job.get("order_no", "#---"), parsed.get("item_count", 0)
        )
        if not created:
            if job.get("conflict_detected"):
                self.last_message = "同一订单金额/状态发生变化，未重复计算分流：" + self.last_order
            else:
                self.last_message = "重复外卖单已拦截，未自动重打：" + self.last_order
            return
        if not self.config.get("takeout_auto_print", True):
            self.last_message = "已保存外卖单，已按设置跳过自动打印：" + self.last_order
            return

        queue_name = str(self.config.get("takeout_proxy_queue_name", "")).strip().casefold()
        physical_name = str(self.config.get("printer_name", "")).strip().casefold() if str(self.config.get("printer_type", "windows")).lower() == "windows" else ""
        if str(self.config.get("printer_type", "windows")).lower() == "windows" and not physical_name:
            try:
                import win32print
                physical_name = str(win32print.GetDefaultPrinter() or "").strip().casefold()
            except Exception:
                pass
        if queue_name and queue_name == physical_name:
            self.last_error = "真实打印机不能等于外卖中继队列，否则会形成打印回环"
            self.last_message = "已拦截订单，但已阻止打印回环"
            self.jobs.update_print_result(job.get("id"), False, 0, self.last_error)
            try:
                self.official_db.update_takeout_order_print_result(job.get("key"), False, 0, self.last_error)
            except Exception:
                pass
            return

        kitchen = max(0, int(self.config.get("takeout_kitchen_copies", 1) or 0))
        stub = max(0, int(self.config.get("takeout_cust_copies", 0) or 0))
        copies = kitchen + stub
        if copies <= 0:
            self.last_error = "制作联和存根联均为 0，无法自动打印"
            self.last_message = "已保存外卖单，未打印"
            self.jobs.update_print_result(job.get("id"), False, 0, self.last_error)
            try:
                self.official_db.update_takeout_order_print_result(job.get("key"), False, 0, self.last_error)
            except Exception:
                pass
            return

        raw_ticket = bytearray()
        for _ in range(kitchen):
            raw_ticket.extend(build_takeout_escpos_ticket(parsed.get("sorted_text", ""), self.config, "kitchen"))
        for _ in range(stub):
            raw_ticket.extend(build_takeout_escpos_ticket(parsed.get("sorted_text", ""), self.config, "stub"))
        printer = ReceiptPrinter(self.config)
        success = printer.print_raw(bytes(raw_ticket))
        self.jobs.update_print_result(job.get("id"), success, copies, printer.last_error)
        try:
            self.official_db.update_takeout_order_print_result(job.get("key"), success, copies, printer.last_error)
        except Exception:
            pass
        if success:
            self.last_error = ""
            self.last_message = "已转发并打印：%s（%d 联）" % (self.last_order, copies)
        else:
            self.last_error = printer.last_error or "真实打印机未返回成功"
            self.last_message = "已拦截订单，但转发打印失败：" + self.last_order

    def run(self):
        _clear_stop_request()
        if not self.interceptor.is_enabled:
            self.last_message = "外卖中继未启用"
            self.current_mode = MODE_COMPATIBILITY
            self._write_status(False)
            return 0
        basic_report = validate_relay_config(self.config, check_windows=False)
        if basic_report.get("errors"):
            self.last_error = "; ".join(basic_report["errors"])
            self.last_message = "中继配置不完整，继续使用兼容模式"
            self.current_mode = MODE_COMPATIBILITY
            self._write_status(False)
            return 2
        self.running = self.interceptor.start()
        if not self.running:
            self.last_error = self.interceptor.last_error or "127.0.0.1 端口不可用"
            self.last_message = "中继无法启动"
            self.current_mode = MODE_COMPATIBILITY
            self._write_status(False)
            return 3

        self.last_message = "中继守护进程运行中：127.0.0.1:%d" % self.interceptor.port
        self._write_status(True)
        try:
            while self.running:
                if _stop_requested():
                    self.last_message = "收到停止请求"
                    break
                self._reload_if_changed()
                if not self.running:
                    break
                if not self.interceptor._running:
                    self.last_error = self.interceptor.last_error or "监听已意外停止"
                    self.last_message = "中继监听已停止"
                    self.current_mode = MODE_COMPATIBILITY
                    self.running = False
                    break
                self._refresh_status_if_due()
                time.sleep(0.25)
        finally:
            self.interceptor.stop()
            self.running = False
            self._write_status(False)
        return 0


def run_takeout_proxy_host():
    """CLI entry point used by ``main.py --takeout-proxy-host``."""
    return TakeoutProxyHost().run()


class TakeoutProxyController:
    """Small GUI-side controller.  It never owns the local socket itself."""

    def __init__(self, config):
        self.config = config
        self.last_error = ""
        self._last_start_attempt = 0.0
        # A manual temporary stop must not be undone by the settings-page
        # watchdog until the operator explicitly starts the relay again.
        self._temporarily_stopped = False
        # The Windows service is opt-in and independently survives GUI exits
        # and reboots.  Until it is installed, retain the existing detached
        # per-user host for backwards compatibility.
        self.service_controller = TakeoutRelayServiceController()

    def service_state(self):
        try:
            return self.service_controller.query()
        except Exception as exc:
            return None

    def _service_installed(self):
        state = self.service_state()
        return bool(state and state.installed)

    @property
    def port(self):
        try:
            return int(self.config.get("takeout_proxy_port", 9101))
        except (TypeError, ValueError):
            return 9101

    @property
    def _running(self):
        service_state = self.service_state()
        if service_state and service_state.installed:
            status = read_proxy_status()
            return bool(service_state.state_code == 4 and status.get("running") and status.get("port") == self.port)
        state = read_proxy_status()
        return bool(
            state.get("running") and state.get("port") == self.port and _is_process_alive(state.get("pid"))
        )

    def get_status(self):
        state = read_proxy_status()
        if self._running:
            return state
        if state.get("last_error"):
            return state
        return {"running": False, "port": self.port, "message": "外卖中继守护进程未运行"}

    def start(self):
        self._temporarily_stopped = False
        if self._running:
            return True
        self._last_start_attempt = time.time()
        _clear_stop_request()
        if self._service_installed():
            try:
                return bool(self.service_controller.start() or self._running)
            except Exception as exc:
                self.last_error = str(exc)
                return False
        command = [sys.executable]
        if getattr(sys, "frozen", False):
            command.append("--takeout-proxy-host")
        else:
            command.extend([os.path.join(BASE_DIR, "main.py"), "--takeout-proxy-host"])
        kwargs = {"cwd": BASE_DIR, "close_fds": True}
        if os.name == "nt":
            kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        try:
            subprocess.Popen(command, **kwargs)
            return True
        except OSError as exc:
            self.last_error = str(exc)
            return False

    def ensure_running(self):
        """Best-effort watchdog restart with a quiet retry cooldown."""
        if self._temporarily_stopped:
            return False
        if not self.config.get("takeout_interceptor_enabled", False):
            return False
        if not str(self.config.get("takeout_proxy_queue_name", "")).strip():
            return False
        if self._running:
            return True
        if time.time() - self._last_start_attempt < 10.0:
            return False
        return self.start()

    def stop(self):
        self._temporarily_stopped = True
        if self._service_installed():
            try:
                self.service_controller.stop()
            except Exception as exc:
                self.last_error = str(exc)
            return
        request_proxy_stop()

    def update_config(self, config):
        self.config = config
        if self._service_installed():
            try:
                if config.get("takeout_interceptor_enabled", False):
                    self._temporarily_stopped = False
                    return self.start()
                self.stop()
                return True
            except Exception as exc:
                self.last_error = str(exc)
                return False
        if config.get("takeout_interceptor_enabled", False):
            self._temporarily_stopped = False
            return self.start()
        self.stop()
        return True

    def install_service(self):
        return self.service_controller.install()

    def start_service(self):
        return self.service_controller.start()

    def stop_service(self):
        return self.service_controller.stop()

    def remove_service(self):
        return self.service_controller.remove()
