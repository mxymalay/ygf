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
import time
from datetime import datetime

from config import BASE_DIR, DATA_DIR, MODULE_FILES, load_config
from core.printer import ReceiptPrinter
from core.takeout_interceptor import (
    TakeoutPrintInterceptor,
    build_takeout_escpos_ticket,
    parse_and_sort_takeout_text,
)
from core.takeout_jobs import TakeoutJobStore


STATUS_PATH = os.path.join(DATA_DIR, "takeout_proxy_status.json")
CONTROL_PATH = os.path.join(DATA_DIR, "takeout_proxy_control.json")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _atomic_json_write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


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
    except (OSError, TypeError, ValueError):
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
        self.interceptor = TakeoutPrintInterceptor(self.config, on_order=self._handle_order)
        self.running = False
        self.started_at = _now()
        self.last_message = "正在启动外卖中继守护进程"
        self.last_error = ""
        self.last_order = ""
        self._last_status_at = 0
        self._config_signature = _config_signature()

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
        if not self.interceptor.is_enabled:
            self.last_message = "配置已停用外卖中继"
            self.running = False
        else:
            self.last_message = "已应用外卖中继新配置"

    def _handle_order(self, intercepted):
        raw_text = str(intercepted.get("raw_text", ""))
        parsed = parse_and_sort_takeout_text(raw_text, _takeout_options(self.config))
        if not parsed.get("is_waimai") or not parsed.get("item_count"):
            self.last_message = "已忽略非外卖或未识别菜品的打印任务"
            return

        job, created = self.jobs.create_or_get(parsed, raw_text)
        self.last_order = "%s %s（%d 项）" % (
            job.get("platform", "外卖"), job.get("order_no", "#---"), parsed.get("item_count", 0)
        )
        if not created:
            self.last_message = "重复外卖单已拦截，未自动重打：" + self.last_order
            return
        if not self.config.get("takeout_auto_print", True):
            self.last_message = "已保存外卖单，已按设置跳过自动打印：" + self.last_order
            return

        queue_name = str(self.config.get("takeout_proxy_queue_name", "")).strip().casefold()
        physical_name = str(self.config.get("printer_name", "")).strip().casefold()
        if queue_name and queue_name == physical_name:
            self.last_error = "真实打印机不能等于外卖中继队列，否则会形成打印回环"
            self.last_message = "已拦截订单，但已阻止打印回环"
            self.jobs.update_print_result(job.get("id"), False, 0, self.last_error)
            return

        kitchen = max(0, int(self.config.get("takeout_kitchen_copies", 1) or 0))
        stub = max(0, int(self.config.get("takeout_cust_copies", 0) or 0))
        copies = kitchen + stub
        if copies <= 0:
            self.last_error = "制作联和存根联均为 0，无法自动打印"
            self.last_message = "已保存外卖单，未打印"
            self.jobs.update_print_result(job.get("id"), False, 0, self.last_error)
            return

        raw_ticket = bytearray()
        for _ in range(kitchen):
            raw_ticket.extend(build_takeout_escpos_ticket(parsed.get("sorted_text", ""), self.config, "kitchen"))
        for _ in range(stub):
            raw_ticket.extend(build_takeout_escpos_ticket(parsed.get("sorted_text", ""), self.config, "stub"))
        printer = ReceiptPrinter(self.config)
        success = printer.print_raw(bytes(raw_ticket))
        self.jobs.update_print_result(job.get("id"), success, copies, printer.last_error)
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
            self._write_status(False)
            return 0
        if not str(self.config.get("takeout_proxy_queue_name", "")).strip():
            self.last_error = "未填写 Windows 外卖中继队列名"
            self.last_message = "中继未启动"
            self._write_status(False)
            return 2
        self.running = self.interceptor.start()
        if not self.running:
            self.last_error = self.interceptor.last_error or "127.0.0.1 端口不可用"
            self.last_message = "中继无法启动"
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

    @property
    def port(self):
        try:
            return int(self.config.get("takeout_proxy_port", 9101))
        except (TypeError, ValueError):
            return 9101

    @property
    def _running(self):
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
        if self._running:
            return True
        _clear_stop_request()
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

    def stop(self):
        request_proxy_stop()

    def update_config(self, config):
        self.config = config
        if config.get("takeout_interceptor_enabled", False):
            return self.start()
        self.stop()
        return True
