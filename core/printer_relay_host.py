"""Detached local host for the official-POS printer relay channel.

The official POS sends an external-order job to a Windows TCP/IP queue that
targets 127.0.0.1.  That TCP listener must *not* live in the PyQt POS process:
closing, restarting, or crashing the screen must not make the official queue
unavailable.  This module runs the listener as a separate per-user process so
it can still use the operator's Windows printer connections.
"""
import json
import hashlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from config import BASE_DIR, DATA_DIR, MODULE_FILES, load_config, save_config
from core.database import Database
from core.printer import ReceiptPrinter
from core.printer_relay_interceptor import (
    PrinterRelayInterceptor,
    build_takeout_escpos_ticket,
    parse_official_pos_text,
)
from core.printer_relay_jobs import PrinterRelayJobStore
from core.printer_relay_service import PrinterRelayServiceController
from core.printer_relay_mode import (
    MODE_COMPATIBILITY,
    MODE_ENHANCED,
    MODE_POLICY_AUTO,
    enhanced_mode_eligibility,
    validate_relay_config,
)


STATUS_PATH = os.path.join(DATA_DIR, "printer_relay_status.json")
CONTROL_PATH = os.path.join(DATA_DIR, "printer_relay_control.json")


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


def is_proxy_status_live(state, expected_port=9101, max_age_seconds=6):
    """Check the relay using its heartbeat, with a Win7-safe PID fallback.

    ``os.kill(pid, 0)`` is not reliable for a PyInstaller/Windows-service
    process on some Win7 machines: it can report a live service PID as
    inaccessible.  The detached relay writes ``updated_at`` every second, so
    a fresh heartbeat is stronger evidence than a PID probe and keeps the
    home badge and mode-four gate consistent.
    """
    if not isinstance(state, dict) or not state.get("running"):
        return False
    try:
        if int(state.get("port") or 0) != int(expected_port or 9101):
            return False
    except (TypeError, ValueError):
        return False
    updated = str(state.get("updated_at") or "").strip()
    if updated:
        try:
            age = (datetime.now() - datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")).total_seconds()
            if 0 <= age <= float(max_age_seconds):
                return True
        except (TypeError, ValueError):
            pass
    pid = state.get("pid")
    return bool(pid and _is_process_alive(pid))


def _config_signature():
    result = []
    for key in ("sys", "printer_relay"):
        path = MODULE_FILES[key]
        try:
            stat = os.stat(path)
            result.append((path, stat.st_mtime_ns, stat.st_size))
        except OSError:
            result.append((path, 0, 0))
    return tuple(result)


def _printer_relay_options(config):
    relay_mapping = (
        config.get("printer_relay_field_mapping")
        or config.get("printer_relay_pos_field_mapping")
        or config.get("official_pos_field_mapping", {})
    )
    options = {
        "mark_multi_qty_star": bool(config.get("printer_relay_mark_star", True)),
        "show_prices": bool(config.get("printer_relay_show_prices", False)),
        "show_address": bool(config.get("printer_relay_show_address", True)),
        "show_order_time": bool(config.get("printer_relay_show_time", True)),
        "show_full_order_id": bool(config.get("printer_relay_show_full_id", False)),
        "show_preorder_alert": bool(config.get("printer_relay_show_preorder", True)),
        "printer_relay_match_mode": config.get("printer_relay_match_mode", "contains"),
        # Used by parse_and_sort_takeout_text only.  Keep the generic mapping
        # separately so dine-in/official recognition remains independent.
        "printer_relay_field_mapping": relay_mapping,
        "official_pos_field_mapping": config.get("official_pos_field_mapping", {}),
    }
    categories = config.get("printer_relay_categories")
    if isinstance(categories, list) and categories:
        options["custom_categories"] = categories
    return options


class PrinterRelayHost:
    """Owns the listener and the physical-printer forwarding path."""

    def __init__(self):
        self.config = load_config()
        self.jobs = PrinterRelayJobStore()
        self.official_db = Database()
        self.interceptor = PrinterRelayInterceptor(self.config, on_order=self._handle_order)
        self.running = False
        self.started_at = _now()
        self.last_message = "正在启动打印机中继守护进程"
        self.last_error = ""
        self.last_order = ""
        self.current_mode = MODE_COMPATIBILITY
        self.last_identified_at = ""
        self.last_enhanced_success_at = str(self.config.get("printer_relay_last_success_at", "") or "")
        self.last_payload_type = ""
        # A small, sanitized snapshot for the settings page.  Keep raw
        # printer bytes/text in the optional capture files only; the runtime
        # status is safe to poll and show in real time.
        self.last_received = {}
        # Keep a bounded batch for the test/mapping pages.  A single official
        # checkout commonly produces a customer receipt, a kitchen slip and
        # a short control/noise job.  Showing only ``last_received`` made it
        # impossible to tell which JSON file the parser was using.
        self.recent_received = []
        # Official POS sends the customer receipt and one or more kitchen
        # slips as separate jobs.  Keep the customer item order so kitchen
        # slips can use the same ``POS#0013 - 1`` / ``- 2`` numbering as the
        # private POS official template.
        self._official_kitchen_orders = {}
        self.mode_reason = str(self.config.get("printer_relay_mode_reason", "") or "")
        self.last_mode_change_at = str(self.config.get("printer_relay_mode_changed_at", "") or "")
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
            self.config["printer_relay_mode"] = mode
            self.config["printer_relay_mode_reason"] = reason
            return
        changed_at = _now()
        self.last_mode_change_at = changed_at
        policy = str(self.config.get("printer_relay_mode_policy", MODE_POLICY_AUTO) or MODE_POLICY_AUTO)
        try:
            self.official_db.record_relay_mode_event(previous, mode, policy, reason, changed_at)
        except Exception:
            pass
        self.config["printer_relay_mode"] = mode
        self.config["printer_relay_mode_reason"] = reason
        self.config["printer_relay_mode_changed_at"] = changed_at
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
            "mode_policy": str(self.config.get("printer_relay_mode_policy", MODE_POLICY_AUTO) or MODE_POLICY_AUTO),
            "mode_reason": self.mode_reason,
            "mode_changed_at": self.last_mode_change_at,
            "last_identified_at": self.last_identified_at,
            "last_enhanced_success_at": self.last_enhanced_success_at,
            "payload_type": self.last_payload_type,
            "last_received": self.last_received,
            "recent_received": self.recent_received,
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
        if str(new_config.get("printer_relay_mode_policy", MODE_POLICY_AUTO)) != MODE_POLICY_AUTO:
            self._set_mode(MODE_COMPATIBILITY, "用户手动锁定兼容模式")
        if not self.interceptor.is_enabled:
            self.last_message = "配置已停用打印机中继"
            self.running = False
        else:
            self.last_message = "已应用打印机中继新配置"

    @staticmethod
    def _is_control_or_auxiliary_print(intercepted, parsed, raw_text):
        """Return True for POS control noise or an auxiliary kitchen slip.

        These jobs are still captured and forwarded, but they are not a new
        payment observation and must not undo a previously verified mode.
        """
        text = str(raw_text or "")
        compact = "".join(text.split())
        try:
            size = int((intercepted or {}).get("payload_size") or len((intercepted or {}).get("raw_payload") or b""))
        except (TypeError, ValueError):
            size = 0
        if not parsed.get("is_official_receipt") and size <= 64 and len(compact) <= 32:
            return True
        return any(marker in compact for marker in ("制作单", "后厨", "厨房打印", "出餐单"))

    @staticmethod
    def _official_call_key(parsed):
        """Use the official pickup number to join customer/kitchen jobs."""
        order_no = str((parsed or {}).get("order_no") or "").strip()
        if order_no and order_no != "#---":
            return re.sub(r"[^0-9A-Za-z_-]", "", order_no).casefold()
        order_id = str((parsed or {}).get("full_order_id") or "").strip()
        return order_id.casefold()

    @staticmethod
    def _official_soup_names(raw_text):
        """Extract soup rows from the customer slip in display order."""
        names = []
        for line in str(raw_text or "").replace("\r", "").split("\n"):
            if not re.search(r"(?:（|\()\s*KG\s*(?:）|\))", line, re.IGNORECASE):
                continue
            match = re.search(
                r"([\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9 _（）()\-]{0,60}?(?:（\s*KG\s*）|\(\s*KG\s*\)))",
                line,
                re.IGNORECASE,
            )
            if not match:
                continue
            name = re.sub(r"\s+", "", match.group(1)).strip()
            if name:
                names.append(name)
        return names

    @staticmethod
    def _official_item_key(name):
        value = str(name or "").casefold()
        value = re.sub(r"（\s*kg\s*）|\(\s*kg\s*\)", "", value, flags=re.IGNORECASE)
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value)

    @classmethod
    def _official_kitchen_item(cls, parsed, raw_text):
        """Read one official POS kitchen slip's soup name/weight/flavor."""
        lines = [line.strip() for line in str(raw_text or "").replace("\r", "").split("\n")]
        name = ""
        name_index = -1
        for index, line in enumerate(lines):
            match = re.search(
                r"([\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9 _（）()\-]{0,60}?(?:（\s*KG\s*）|\(\s*KG\s*\)))",
                line,
                re.IGNORECASE,
            )
            if match:
                name = re.sub(r"\s+", "", match.group(1)).strip()
                name_index = index
                break
        if not name:
            for candidate in (parsed or {}).get("item_names") or []:
                if re.search(r"(?:（|\()\s*kg\s*(?:）|\))", str(candidate), re.IGNORECASE):
                    name = str(candidate).strip()
                    break
        if not name:
            name = "经典草本骨汤（KG）"

        weight = 0.0
        for line in lines[max(0, name_index + 1):]:
            match = re.fullmatch(r"\s*(\d+(?:\.\d{1,3})?)\s*", line)
            if match:
                try:
                    weight = float(match.group(1))
                except (TypeError, ValueError):
                    pass
                break
        flavor = ""
        if name_index >= 0:
            for line in lines[name_index + 1:]:
                compact = re.sub(r"\s+", "", line)
                if not compact or re.fullmatch(r"[-=*_]+", compact):
                    continue
                if re.fullmatch(r"\d+(?:\.\d{1,3})?", compact):
                    continue
                if any(marker in compact for marker in ("操作人", "下单时间", "打印时间", "取餐号", "制作单", "POS#")):
                    continue
                flavor = line.strip()
                break
        return {"name": name, "weight": weight, "tag": flavor, "type": "soup"}

    def _remember_official_customer_order(self, parsed, raw_text):
        key = self._official_call_key(parsed)
        if not key:
            return
        names = self._official_soup_names(raw_text)
        if not names:
            return
        existing = self._official_kitchen_orders.get(key) or {}
        used = set(existing.get("used", set()))
        self._official_kitchen_orders[key] = {"names": names, "used": used}
        if len(self._official_kitchen_orders) > 200:
            self._official_kitchen_orders.pop(next(iter(self._official_kitchen_orders)))

    def _official_kitchen_sequence(self, parsed, raw_text):
        key = self._official_call_key(parsed)
        entry = self._official_kitchen_orders.setdefault(key, {"names": [], "used": set()})
        item = self._official_kitchen_item(parsed, raw_text)
        item_key = self._official_item_key(item.get("name"))
        names = entry.get("names") or []
        used = entry.setdefault("used", set())
        index = None
        # Match against the customer's item order first; repeated identical
        # soup names consume successive positions before reprints reuse one.
        for position, name in enumerate(names, 1):
            if position not in used and self._official_item_key(name) == item_key:
                index = position
                break
        if index is None:
            for position, name in enumerate(names, 1):
                if self._official_item_key(name) == item_key:
                    index = position
                    break
        if index is None:
            index = max(used or {0}) + 1
            if index > len(names):
                names.append(item.get("name", "经典草本骨汤（KG）"))
        used.add(index)
        entry["names"] = names
        return item, index, max(1, len(names))

    def _print_official_kitchen(self, parsed, raw_text):
        """Print an official kitchen slip with private-POS-style numbering."""
        item, index, kitchen_count = self._official_kitchen_sequence(parsed, raw_text)
        call_no = str(parsed.get("order_no") or "#---").lstrip("#") or "---"
        all_items = []
        entry = self._official_kitchen_orders.get(self._official_call_key(parsed)) or {}
        names = entry.get("names") or [item.get("name")]
        for name in names[:kitchen_count]:
            all_items.append(dict(item, name=name))
        while len(all_items) < kitchen_count:
            all_items.append(dict(item))
        sale = {
            "call_no": call_no,
            "cart_items": all_items,
            "weight_kg": item.get("weight", 0.0),
            "created_at": parsed.get("order_time") or _now(),
            "shop_subtitle": self.config.get("shop_subtitle", ""),
            "config": self.config,
        }
        template_config = dict(self.config)
        # Use the captured official layout for the re-rendered kitchen slip;
        # the only intentional difference is our ``取餐号 -1/-2`` suffix.
        template_config["printer_template_profile"] = "official_v3"
        template_config["printer_logo_enabled"] = False
        printer = ReceiptPrinter(template_config)
        payload = printer._build_kitchen_slip(sale, item, index)
        return printer.print_raw(payload), printer.last_error

    def _handle_order(self, intercepted):
        raw_text = str(intercepted.get("raw_text", ""))
        parsed = parse_official_pos_text(raw_text, _printer_relay_options(self.config))
        raw_payload = intercepted.get("raw_payload") or b""
        self.last_payload_type = str(intercepted.get("payload_type", "binary_or_unknown") or "binary_or_unknown")
        parse_failed = bool(intercepted.get("parse_failed")) or not (
            parsed.get("is_official_receipt") and (
                parsed.get("item_count") or parsed.get("order_amount") is not None
                or parsed.get("full_order_id")
            )
        )
        self._update_last_received(parsed, intercepted, parse_failed=parse_failed)
        if parse_failed:
            preserve_verified_mode = (
                self.current_mode == MODE_ENHANCED
                and self._is_control_or_auxiliary_print(intercepted, parsed, raw_text)
            )
            # The relay owns the physical output path.  Preserve the original
            # receipt whenever recognition cannot be trusted; parsing must
            # never turn into a silent print loss.
            queue_name = str(self.config.get("printer_relay_queue_name", "")).strip().casefold()
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
                self._write_status()
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
            if preserve_verified_mode:
                self.last_message = "已保留原始打印；控制/辅助打印不改变当前增强模式"
            else:
                self._set_mode(MODE_COMPATIBILITY, self.last_message)
            self._write_status()
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
            if not parsed.get("is_official_kitchen"):
                self._remember_official_customer_order(parsed, raw_text)
            if parsed.get("is_official_kitchen"):
                # The official POS kitchen ticket is a separate print job,
                # not an external order.  Re-render it with the same official
                # exact official template used by private POS so multiple soup rows are
                # visibly numbered (#0013 - 1, #0013 - 2), while the customer
                # receipt remains an untouched original POS ticket.
                self.last_identified_at = _now()
                self._update_last_received(parsed, intercepted, parse_failed=False)
                self.last_order = "%s %s" % (
                    parsed.get("platform", "官方POS-堂食"),
                    parsed.get("full_order_id") or parsed.get("order_no") or "无订单号",
                )
                if self.current_mode == MODE_ENHANCED:
                    self._set_mode(MODE_ENHANCED, "官方 POS 制作单不改变增强模式")
                try:
                    success, error = self._print_official_kitchen(parsed, raw_text)
                except Exception as exc:
                    success, error = False, str(exc)
                if success:
                    self.last_error = ""
                    self.last_message = "官方制作单已按顺序打印：%s" % self.last_order
                else:
                    self.last_error = error or "官方制作单重排打印失败"
                    self.last_message = "官方制作单打印失败：%s" % self.last_error
                self._write_status()
                return
            if parsed.get("payment_status") == "cancelled":
                try:
                    refund_result = self.official_db.record_official_refund(
                        refund_key=parsed.get("receipt_key"),
                        refund_receipt_key=parsed.get("receipt_key"),
                        order_no=parsed.get("order_no"),
                        amount=parsed.get("order_amount"),
                        order_id=parsed.get("full_order_id"),
                        observed_at=self.last_identified_at,
                    )
                except Exception as exc:
                    refund_result = {"linked": False, "status": "UNMATCHED", "reason": str(exc)}
                parsed["refund_linked"] = bool(refund_result.get("linked"))
                parsed["refund_match_status"] = str(refund_result.get("status") or "UNMATCHED")
                parsed["refund_match_reason"] = str(refund_result.get("reason") or "")
                parsed["refund_original_order_key"] = str(refund_result.get("original_order_key") or "")
                parsed["refund_original_order_id"] = str(refund_result.get("original_order_id") or "")
            self._update_last_received(parsed, intercepted, parse_failed=False)
            self.last_order = "%s %s" % (
                parsed.get("platform", "官方POS-堂食"),
                parsed.get("full_order_id") or parsed.get("order_no") or "无订单号",
            )
            eligibility = enhanced_mode_eligibility(
                self.config,
                {"running": self.running and self.interceptor._running},
                parsed,
            )
            if parsed.get("payment_status") == "cancelled" and parsed.get("refund_linked") and self.current_mode == MODE_ENHANCED:
                # A linked refund changes the order's financial state, not the
                # relay's ability to identify future paid receipts.
                self._set_mode(MODE_ENHANCED, "退款已关联原结账单，保持增强模式")
            else:
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
                        order_no=parsed.get("order_no", ""),
                        payment_method=parsed.get("payment_method", ""),
                        payment_breakdown_json=parsed.get("payment_breakdown_json", ""),
                    )
                except Exception as exc:
                    self.last_error = "官方营业额入账失败：%s" % exc
                try:
                    self.config["printer_relay_last_success_at"] = self.last_enhanced_success_at
                    save_config(self.config)
                except Exception:
                    pass
            if raw_payload:
                printer = ReceiptPrinter(self.config)
                if printer.print_raw(raw_payload):
                    self.last_error = ""
                    if parsed.get("payment_status") == "cancelled":
                        refund_text = (
                            "已关联原结账单" if parsed.get("refund_linked")
                            else "未找到唯一原结账单，已保留待核对"
                        )
                        self.last_message = "堂食退款已原样转发并记录：%s" % refund_text
                    else:
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
            self._write_status()
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
        self._update_last_received(parsed, intercepted, parse_failed=False)
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
        preserve_verified_mode = (
            self.current_mode == MODE_ENHANCED
            and self._is_control_or_auxiliary_print(intercepted, parsed, raw_text)
        )
        if preserve_verified_mode:
            self._set_mode(MODE_ENHANCED, "控制/辅助打印不改变当前增强模式")
        else:
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
                        order_no=job.get("order_no", parsed.get("order_no", "")),
                        payment_method=parsed.get("payment_method", ""),
                        payment_breakdown_json=parsed.get("payment_breakdown_json", ""),
                    )
                except Exception as exc:
                    # A reporting ledger failure must never interrupt the
                    # original receipt forwarding path.
                    self.last_error = "官方营业额入账失败：%s" % exc
            try:
                self.config["printer_relay_last_success_at"] = self.last_enhanced_success_at
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
            self._write_status()
            return
        if not self.config.get("printer_relay_auto_print", True):
            self.last_message = "已保存外卖单，已按设置跳过自动打印：" + self.last_order
            self._write_status()
            return

        queue_name = str(self.config.get("printer_relay_queue_name", "")).strip().casefold()
        physical_name = str(self.config.get("printer_name", "")).strip().casefold() if str(self.config.get("printer_type", "windows")).lower() == "windows" else ""
        if str(self.config.get("printer_type", "windows")).lower() == "windows" and not physical_name:
            try:
                import win32print
                physical_name = str(win32print.GetDefaultPrinter() or "").strip().casefold()
            except Exception:
                pass
        if queue_name and queue_name == physical_name:
            self.last_error = "真实打印机不能等于打印机中继队列，否则会形成打印回环"
            self.last_message = "已拦截订单，但已阻止打印回环"
            self.jobs.update_print_result(job.get("id"), False, 0, self.last_error)
            try:
                self.official_db.update_takeout_order_print_result(job.get("key"), False, 0, self.last_error)
            except Exception:
                pass
            self._write_status()
            return

        kitchen = max(0, int(self.config.get("printer_relay_kitchen_copies", 1) or 0))
        stub = max(0, int(self.config.get("printer_relay_cust_copies", 0) or 0))
        copies = kitchen + stub
        if copies <= 0:
            self.last_error = "制作联和存根联均为 0，无法自动打印"
            self.last_message = "已保存外卖单，未打印"
            self.jobs.update_print_result(job.get("id"), False, 0, self.last_error)
            try:
                self.official_db.update_takeout_order_print_result(job.get("key"), False, 0, self.last_error)
            except Exception:
                pass
            self._write_status()
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
        self._write_status()

    def _update_last_received(self, parsed, intercepted, parse_failed=False):
        """Publish only stable identifiers/results for live relay monitoring."""
        parsed = parsed if isinstance(parsed, dict) else {}
        amount = parsed.get("order_amount")
        try:
            amount = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount = None
        try:
            item_count = int(parsed.get("item_count") or 0)
        except (TypeError, ValueError):
            item_count = 0
        received_at = _now()
        capture_path = str((intercepted or {}).get("capture_path") or "")
        capture_file = os.path.basename(capture_path) if capture_path else ""
        capture_json = os.path.splitext(capture_file)[0] + ".json" if capture_file else ""
        raw_payload = (intercepted or {}).get("raw_payload") or b""
        if isinstance(raw_payload, str):
            raw_payload = raw_payload.encode("utf-8", "ignore")
        digest = str((intercepted or {}).get("sha256") or "")
        if not digest and raw_payload:
            try:
                digest = hashlib.sha256(bytes(raw_payload)).hexdigest()
            except Exception:
                digest = ""
        extracted = str(parsed.get("raw_text") or "")
        # The capture sidecar remains the complete source of truth.  Status
        # only carries a short preview so polling the UI does not duplicate
        # sensitive receipt text into the status file.
        preview = extracted[:500]
        if len(extracted) > 500:
            preview += "…"
        payment_status = str(parsed.get("payment_status") or "unknown")
        recognized_fields = []
        if parsed.get("full_order_id"):
            recognized_fields.append("order_id")
        if parsed.get("order_no") and str(parsed.get("order_no")) != "#---":
            recognized_fields.append("call_no")
        if amount is not None and bool(parsed.get("amount_valid")):
            recognized_fields.append("amount")
        if payment_status != "unknown":
            recognized_fields.append("payment_status")
        if parsed.get("payment_method"):
            recognized_fields.append("payment_method")
        if item_count:
            recognized_fields.append("items")
        record = {
            "received_at": received_at,
            "payload_type": self.last_payload_type,
            "parse_failed": bool(parse_failed),
            "receipt_kind": str(parsed.get("receipt_kind") or "unknown"),
            "platform": str(parsed.get("platform") or "官方 POS"),
            "order_id": str(parsed.get("full_order_id") or ""),
            "call_no": str(parsed.get("order_no") or ""),
            "amount": amount,
            "amount_valid": bool(parsed.get("amount_valid")),
            "payment_status": payment_status,
            "payment_evidence": str(parsed.get("payment_status_evidence") or ""),
            "payment_method": str(parsed.get("payment_method") or ""),
            "confidence": str(parsed.get("payment_status_confidence") or parsed.get("confidence") or "unknown"),
            "key_confidence": str(parsed.get("key_confidence") or "unknown"),
            "item_count": item_count,
            "duplicate": bool(parsed.get("duplicate")),
            "conflict_detected": bool(parsed.get("conflict_detected")),
            "refund_linked": bool(parsed.get("refund_linked")),
            "refund_match_status": str(parsed.get("refund_match_status") or ""),
            "refund_match_reason": str(parsed.get("refund_match_reason") or ""),
            "refund_original_order_key": str(parsed.get("refund_original_order_key") or ""),
            "refund_original_order_id": str(parsed.get("refund_original_order_id") or ""),
            "capture_file": capture_file,
            "capture_json_file": capture_json,
            "sha256": digest,
            "payload_size": int((intercepted or {}).get("payload_size") or len(raw_payload) or 0),
            "order_time": str(parsed.get("order_time") or ""),
            "amount_source": str(parsed.get("amount_source") or ""),
            "recognized_fields": recognized_fields,
            "extracted_text_preview": preview,
        }
        self.last_received = record
        # Replace the first observation of a job when the handler later adds
        # duplicate/conflict/forwarding results.  A capture basename is the
        # strongest identity; hash/field tuple handles capture-disabled mode.
        identity = capture_file or digest or "%s|%s|%s" % (
            record.get("received_at"), record.get("payload_size"), record.get("call_no"))
        previous = []
        for item in self.recent_received:
            item_identity = item.get("capture_file") or item.get("sha256") or "%s|%s|%s" % (
                item.get("received_at"), item.get("payload_size"), item.get("call_no"))
            if item_identity != identity:
                previous.append(item)
        self.recent_received = [record] + previous
        del self.recent_received[20:]

    def _restore_verified_mode_after_startup(self):
        """Restore a previously verified enhanced mode after a clean start.

        Starting the detached listener used to reset ``current_mode`` to
        compatibility every time, so the UI appeared to switch modes until a
        new official-POS ticket arrived.  The receipt ledger is the source of
        truth for this startup check; do not require the mode hint or the
        last-success setting to already say ``enhanced`` because either value
        may have been lost during an older packaged upgrade.  A saved database
        row is still not enough by itself: it must be a high-confidence paid
        receipt with a valid amount and stable order id.  If no such evidence
        exists, remain in compatibility mode and wait for a real ticket.
        """
        if str(self.config.get("printer_relay_mode_policy", MODE_POLICY_AUTO) or MODE_POLICY_AUTO) != MODE_POLICY_AUTO:
            return False
        try:
            rows = self.official_db.get_official_receipts(limit=100)
        except Exception:
            return False
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("payment_status") or "").lower() != "paid":
                continue
            parsed = {
                "receipt_kind": str(row.get("receipt_kind") or "unknown"),
                "full_order_id": str(row.get("order_id") or ""),
                "order_amount": row.get("amount"),
                "amount_valid": bool(row.get("amount_valid")),
                "payment_status": "paid",
                "payment_status_evidence": "persisted_paid_receipt",
                "key_confidence": str(row.get("key_confidence") or "low"),
                "conflict_detected": bool(row.get("conflict_detected")),
            }
            eligibility = enhanced_mode_eligibility(
                self.config, {"running": True}, parsed
            )
            if eligibility.get("eligible"):
                observed_at = str(row.get("observed_at") or "")
                self.last_enhanced_success_at = observed_at or self.last_enhanced_success_at
                self._set_mode(MODE_ENHANCED, "启动自检：恢复数据库中最近一次已验证的增强模式")
                self.last_identified_at = str(row.get("observed_at") or "")
                self.last_message = "中继守护进程运行中：启动自检已恢复增强模式"
                return True
        return False

    def run(self):
        _clear_stop_request()
        if not self.interceptor.is_enabled:
            self.last_message = "打印机中继未启用"
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

        restored_enhanced = self._restore_verified_mode_after_startup()
        if not restored_enhanced:
            if str(self.config.get("printer_relay_mode", MODE_COMPATIBILITY) or MODE_COMPATIBILITY) == MODE_ENHANCED:
                self.mode_reason = "启动自检未找到可复用的已验证官方订单，等待实时验证"
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


def run_printer_relay_host():
    """CLI entry point used by ``main.py --printer-relay-host``."""
    return PrinterRelayHost().run()


class PrinterRelayController:
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
        self.service_controller = PrinterRelayServiceController()

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
            return int(self.config.get("printer_relay_port", 9101))
        except (TypeError, ValueError):
            return 9101

    @property
    def _running(self):
        state = read_proxy_status()
        # Use the relay heartbeat as the primary liveness signal.  This also
        # avoids a false negative when Win7 cannot probe a service PID owned by
        # another account.  An old heartbeat still falls back to the PID
        # check inside ``is_proxy_status_live``.
        return is_proxy_status_live(state, self.port)

    def get_status(self):
        state = read_proxy_status()
        running = self._running
        if running:
            return state
        # Preserve the last observed ticket/mode when the listener is down;
        # otherwise the settings page would erase the useful test result as
        # soon as a temporary relay is stopped or auto-degraded.  The
        # diagnostic fields are historical, but ``running`` must always be
        # false here.  Returning a stale ``running: true`` when last_error is
        # present made the home badge claim enhanced mode while mode 4 (which
        # checks the live process) correctly rejected it.
        result = {"running": False, "port": self.port, "message": "打印机中继守护进程未运行"}
        for key in (
            "last_received", "last_identified_at", "last_enhanced_success_at",
            "payload_type", "mode", "mode_policy", "mode_reason", "mode_changed_at",
            "recent_received", "last_error",
        ):
            if key in state:
                result[key] = state.get(key)
        return result

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
            command.append("--printer-relay-host")
        else:
            command.extend([os.path.join(BASE_DIR, "main.py"), "--printer-relay-host"])
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
        if not self.config.get("printer_relay_enabled", False):
            return False
        if not str(self.config.get("printer_relay_queue_name", "")).strip():
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
                if config.get("printer_relay_enabled", False):
                    self._temporarily_stopped = False
                    return self.start()
                self.stop()
                return True
            except Exception as exc:
                self.last_error = str(exc)
                return False
        if config.get("printer_relay_enabled", False):
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
