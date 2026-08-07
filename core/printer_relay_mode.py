# -*- coding: utf-8 -*-
"""Shared validation and mode decisions for the official-POS print relay.

The relay is deliberately fail-closed for *enhanced routing*: a missing or
uncertain field can never turn into a guessed payment success.  The existing
weight/continuation routing remains the compatibility fallback.
"""
from datetime import datetime


MODE_COMPATIBILITY = "compatibility"
MODE_CANDIDATE = "candidate"
MODE_ENHANCED = "enhanced"
MODE_DEGRADED = "degraded"
MODE_POLICY_AUTO = "auto"
MODE_POLICY_FORCE_COMPATIBILITY = "force_compatibility"


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text(value):
    return str(value or "").strip()


def _port(value, default=9101):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def list_windows_printers():
    """Return installed Windows queues, or a diagnostic error.

    Importing win32print lazily keeps Linux/offline test environments usable.
    """
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        rows = win32print.EnumPrinters(flags, None, 1) or []
        return [str(row[2]) for row in rows if len(row) > 2 and str(row[2]).strip()], ""
    except Exception as exc:
        return [], str(exc) or "无法读取 Windows 打印机列表"


def inspect_windows_queue(queue_name, relay_port=None):
    """Inspect queue existence and, when available, its TCP endpoint.

    A queue name alone is insufficient: a locally installed queue may point to
    a physical printer or a different port.  ``GetPrinter(..., 2)`` supplies
    ``pPortName`` on pywin32 installations.
    """
    queue_name = _text(queue_name)
    result = {
        "queue_name": queue_name,
        "exists": False,
        "port_name": "",
        "targets_relay": None,
        "error": "",
    }
    if not queue_name:
        result["error"] = "未填写 Windows 中继队列名"
        return result
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        rows = win32print.EnumPrinters(flags, None, 1) or []
        names = {str(row[2]) for row in rows if len(row) > 2}
        result["exists"] = queue_name in names
        if not result["exists"]:
            result["error"] = "Windows 中未找到该打印队列"
            return result
        handle = win32print.OpenPrinter(queue_name)
        try:
            info = win32print.GetPrinter(handle, 2) or {}
            result["port_name"] = _text(info.get("pPortName"))
        finally:
            win32print.ClosePrinter(handle)
        if relay_port:
            endpoint = _text(result["port_name"]).casefold()
            port = str(_port(relay_port)).casefold()
            # Standard TCP/IP ports are commonly named IP_127.0.0.1 or
            # 127.0.0.1:9101; accept both forms and leave unknown ports for a
            # human-visible warning instead of claiming success.
            if "127.0.0.1" not in endpoint:
                result["targets_relay"] = False
            elif port in endpoint:
                result["targets_relay"] = True
            else:
                # Windows often stores only ``IP_127.0.0.1`` as the port
                # name; the numeric RAW port is then hidden in the driver.
                result["targets_relay"] = None
    except Exception as exc:
        result["error"] = str(exc) or "读取 Windows 队列失败"
    return result


def validate_relay_config(config, check_windows=True):
    """Return a structured, UI-safe validation report."""
    config = config or {}
    queue = _text(config.get("printer_relay_queue_name"))
    printer_type = _text(config.get("printer_type", "windows")).lower()
    physical = _text(config.get("printer_name")) if printer_type == "windows" else ""
    if printer_type == "windows" and not physical:
        try:
            import win32print
            physical = _text(win32print.GetDefaultPrinter())
        except Exception:
            physical = ""
    relay_port = _port(config.get("printer_relay_port"), 9101)
    report = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "queue": queue,
        "physical_printer": physical,
        "relay_port": relay_port,
        "queue_check": None,
        "checked_at": _now_text(),
    }
    if relay_port < 1024 or relay_port > 65535:
        report["ok"] = False
        report["errors"].append("中继监听端口必须在 1024-65535 之间")
    if not queue:
        report["ok"] = False
        report["errors"].append("未填写 Windows 中继队列名")
    if printer_type == "windows" and queue and physical and queue.casefold() == physical.casefold():
        report["ok"] = False
        report["errors"].append("中继队列不能与实体输出打印机相同，否则会形成打印回环")
    if check_windows and queue:
        queue_check = inspect_windows_queue(queue, relay_port)
        report["queue_check"] = queue_check
        if not queue_check.get("exists"):
            report["ok"] = False
            report["errors"].append(queue_check.get("error") or "Windows 中继队列不可用")
        elif queue_check.get("targets_relay") is False:
            report["ok"] = False
            report["errors"].append("Windows 队列端口没有指向本机中继监听端口")
        elif queue_check.get("targets_relay") is None:
            report["warnings"].append("无法确认 Windows 队列端口，请用真实测试单验证")
    return report


def _has_reliable_payment(parsed):
    return _text(parsed.get("payment_status")).lower() == "paid" and bool(
        parsed.get("payment_status_evidence")
    )


def enhanced_mode_eligibility(config, runtime=None, parsed=None):
    """Explain whether one observation can enable amount-based routing."""
    config = config or {}
    runtime = runtime or {}
    parsed = parsed or {}
    reasons = []
    policy = _text(config.get("printer_relay_mode_policy", MODE_POLICY_AUTO)).lower()
    if policy == MODE_POLICY_FORCE_COMPATIBILITY:
        reasons.append("已手动锁定兼容模式")
    if not bool(config.get("printer_relay_enabled")):
        reasons.append("中继未启用")
    if not runtime.get("running"):
        reasons.append("中继监听未运行")
    if parsed.get("receipt_kind") not in ("takeout", "dinein"):
        reasons.append("不是可确认的官方 POS 票据")
    if not _text(parsed.get("full_order_id")):
        reasons.append("缺少稳定官方订单号")
    if str(parsed.get("key_confidence", "low") or "low").lower() != "high":
        reasons.append("订单关联可信度不足")
    if parsed.get("order_amount") is None or parsed.get("amount_valid") is not True:
        reasons.append("金额缺失或未通过校验")
    if not _has_reliable_payment(parsed):
        reasons.append("付款/结账状态未知或证据不足")
    if parsed.get("conflict_detected"):
        reasons.append("同一订单金额或状态发生变化")
    eligible = not reasons
    return {
        "eligible": eligible,
        "mode": MODE_ENHANCED if eligible else MODE_COMPATIBILITY,
        "reasons": reasons,
        "checked_at": _now_text(),
    }


def mode_label(mode):
    return {
        MODE_COMPATIBILITY: "兼容模式",
        MODE_CANDIDATE: "增强模式候选",
        MODE_ENHANCED: "增强模式",
        MODE_DEGRADED: "已降级到兼容模式",
    }.get(str(mode or ""), "兼容模式")
