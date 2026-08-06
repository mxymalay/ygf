"""Payment method and split-payment formatting helpers."""

import json


PAYMENT_LABELS = {
    "shouqianba": "收钱吧",
    "scan": "手持机器",
    "cash": "现金",
    "qr": "被扫",
}


def parse_payment_breakdown(value):
    """Return a safe ``{method: amount}`` mapping from JSON or a dict."""
    if isinstance(value, dict):
        data = value
    elif isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            return {}
    else:
        return {}
    if not isinstance(data, dict):
        return {}

    result = {}
    for method, amount in data.items():
        try:
            normalized = round(float(amount), 2)
        except (TypeError, ValueError):
            continue
        if normalized > 0.0001:
            result[str(method)] = normalized
    return result


def format_payment_breakdown(value):
    """Format split amounts for receipts, history and operator messages."""
    breakdown = parse_payment_breakdown(value)
    parts = []
    for method, amount in breakdown.items():
        label = PAYMENT_LABELS.get(method, method)
        parts.append("%s ¥%.2f" % (label, amount))
    return " + ".join(parts)


def payment_display_label(method, breakdown=None):
    """Return the user-facing label for one payment method or a split."""
    method = str(method or "").lower()
    if method == "mixed":
        detail = format_payment_breakdown(breakdown)
        return "混合支付（%s）" % detail if detail else "混合支付"
    return PAYMENT_LABELS.get(method, method)
