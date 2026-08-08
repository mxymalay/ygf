# -*- coding: utf-8 -*-
"""
外卖打印中继与菜品智能排序核心引擎
外卖单默认即为【外卖打包】，自动包含打包醒目提醒与分类重排
"""
import re
import time
import threading
import socket
import hashlib
from PyQt5.QtCore import QObject, pyqtSignal
from core.printer_relay_capture import capture_print_payload


# 默认菜品分类关键词规则
DEFAULT_CATEGORIES = [
    {
        "id": "soup",
        "name": "🍲 汤底 / 辣度 / 忌口偏好",
        "keywords": ["汤", "辣", "葱", "蒜", "香菜", "麻辣", "牛油", "番茄", "骨汤", "清汤", "忌口", "打包", "不要", "少辣", "微辣", "特辣"]
    },
    {
        "id": "meat",
        "name": "🥩 肉类 / 海鲜 / 主料",
        "keywords": ["牛", "羊", "猪", "鸡", "鸭", "鱼", "虾", "蟹", "肉", "丸", "蛋", "肠", "培根", "午餐肉", "毛肚", "百叶", "黄喉", "掌中宝", "鱿鱼", "排骨"]
    },
    {
        "id": "veg",
        "name": "🥬 蔬菜 / 菌菇 / 豆制品",
        "keywords": ["菜", "菇", "豆", "笋", "腐", "面", "粉", "海带", "木耳", "土豆", "莲藕", "山药", "冬瓜", "萝卜", "海带结", "宽粉", "金针菇", "木耳", "油菜", "菠菜", "生菜", "豆腐皮"]
    },
    {
        "id": "drink",
        "name": "🥤 饮品 / 小吃 / 主食",
        "keywords": ["水", "汁", "茶", "奶", "可乐", "雪碧", "王老吉", "加多宝", "啤酒", "饮", "饭", "冰淇淋", "酸奶"]
    }
]


def clean_dish_name(raw_name: str) -> str:
    """清理菜品名称中的序号、数量、价格与全半角空格，以便精准匹配关键字"""
    # 1. 剔除前导序号 (如 1. 2. #1)
    # ``1元串``/``10元饮料`` are legitimate SKU names, not row numbers.
    s = str(raw_name or "")
    if not re.match(r"^\d+元", s):
        s = re.sub(r"^\d+[\.\、\s]*", "", s)
    # 2. 剔除数量后缀 (如 x 2, ×1, 2份)
    s = re.sub(r"[xX*×]\s*\d+|\d+\s*份", "", s)
    # 3. 剔除价格 (￥30.00)
    s = re.sub(r"[￥¥]\s*\d+(\.\d+)?", "", s)
    # 4. 剔除所有全角/半角空格、换行符
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _is_takeout_metadata_line(line: str) -> bool:
    """Exclude platform headers/totals without discarding actual dish names."""
    compact = re.sub(r"\s+", "", line)
    if not compact or re.fullmatch(r"[-=*_]+", compact):
        return True
    if compact.startswith("[") and compact.endswith("]"):
        return True
    prefixes = (
        "美团", "饿了么", "外卖订单", "订单号", "订单编号", "实付", "应付", "原价",
        "合计", "配送费", "包装费", "下单时间", "订单时间", "送餐地址", "收货地址",
        "地址", "联系电话", "顾客", "备注", "预计送达", "送达时间", "商家",
        "堂食", "POS点餐", "取餐号", "名称", "规格", "单价", "数量", "小计",
        "支付", "付款", "结账", "打印时间", "服务热线", "操作人",
    )
    return compact.startswith(prefixes)


def _format_item_line(line: str, show_prices: bool, mark_star: bool):
    """Return printable food text and quantity, or ``('', 0)`` for metadata."""
    if _is_takeout_metadata_line(line):
        return "", 0
    qty_match = re.search(r"(?:[xX*×]\s*(\d+)|(\d+)\s*份)", line)
    qty = int(qty_match.group(1) or qty_match.group(2)) if qty_match else 1
    text = re.sub(r"^\s*(?:\d+\s*[\.、]|#\s*\d+\s*)", "", line).strip()
    if not show_prices:
        text = re.sub(r"\s*[￥¥]\s*\d+(?:\.\d+)?", "", text).strip()
    if not text or len(clean_dish_name(text)) < 1:
        return "", 0
    if mark_star and qty >= 2:
        text = "⭐ 【多份x%d】 %s" % (qty, text)
    return text, qty


def _is_official_pos_customer_text(raw_text: str) -> bool:
    """Return whether text is the official POS customer settlement slip."""
    compact = re.sub(r"\s+", "", str(raw_text or ""))
    return (
        "取餐号" in compact
        and "POS点餐" in compact
        and "制作单" not in compact
    )


def _official_pos_item_name(line: str) -> str:
    """Remove official POS column values while keeping the product name.

    The Windows POS driver often removes column spacing when the receipt is
    captured.  A row such as ``经典草本骨汤（KG） KG 47.60 0.006 0.29`` can
    therefore arrive as one long string.  Use the unit marker or the final
    quantity/amount columns as a boundary instead of treating those numbers
    as part of the product name.
    """
    text = re.sub(r"\s+", " ", str(line or "")).strip()
    if not text:
        return ""
    # A collapsed row number is normally separated from the product name
    # (``1 经典草本骨汤``), but products such as ``1元串/小食`` use the same
    # leading digits as part of their actual name.  Strip only the former;
    # never remove a price-prefixed product name.
    if not re.match(r"^\d+元", text):
        text = re.sub(r"^\d+(?=[\u4e00-\u9fff])", "", text).strip()

    unit = re.search(r"(?:（\s*kg\s*）|\(\s*kg\s*\)|\bkg\b)", text, re.IGNORECASE)
    if unit:
        suffix = text[unit.end():]
        numbers = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", suffix)
        if len(numbers) >= 2 and not re.search(r"[\u4e00-\u9fff]", suffix):
            return text[:unit.end()].strip()

    # Non-weight products are commonly printed as ``商品名份1.001.00`` or
    # ``商品名 1.00 1.00`` (quantity and subtotal).  Strip only the trailing
    # numeric columns, never digits embedded in a legitimate product name.
    text = re.sub(r"(?:\s*份)?\s*\d+\.\d{2}\s+\d+(?:\.\d+)?\s+\d+\.\d{2}\s*$", "", text)
    text = re.sub(r"(?:\s*份)?\s*\d+\.\d{2}\s*\d+\.\d{2}\s*$", "", text)
    text = re.sub(r"(?:\s*份)?\s*(?:\d+\.\d{1,3}\s+){2,}\d+\.\d{1,3}\s*$", "", text)
    return text.strip()


def _official_pos_item_detail(line: str, name: str) -> dict:
    """Parse the numeric columns that follow one official POS product row."""
    text = re.sub(r"\s+", " ", str(line or "")).strip()
    compact = re.sub(r"\s+", "", text)
    text = re.sub(r"^\d+(?=[\u4e00-\u9fff])", "", text).strip()
    compact = re.sub(r"\s+", "", text)
    detail = {"name": name, "spec": "", "unit_price": None, "quantity": None, "subtotal": None}
    unit = re.search(r"(?:（\s*kg\s*）|\(\s*kg\s*\)|\bkg\b)", text, re.IGNORECASE)
    if unit:
        detail["spec"] = "kg"
        suffix = re.sub(r"\s+", "", text[unit.end():])
        match = re.search(r"(\d+\.\d{2})(\d+\.\d{1,3})(\d+\.\d{2})$", suffix)
        if match:
            detail["unit_price"] = float(match.group(1))
            detail["quantity"] = float(match.group(2))
            detail["subtotal"] = float(match.group(3))
        else:
            numbers = re.findall(r"\d+(?:\.\d+)?", suffix)
            if len(numbers) >= 3:
                detail["unit_price"] = float(numbers[0])
                detail["quantity"] = float(numbers[-2])
                detail["subtotal"] = float(numbers[-1])
        return detail

    portion = re.search(r"份(\d+\.\d{2})(\d+(?:\.\d+)?)(\d+\.\d{2})$", compact)
    if portion:
        detail["spec"] = "份"
        detail["unit_price"] = float(portion.group(1))
        detail["quantity"] = float(portion.group(2))
        detail["subtotal"] = float(portion.group(3))
    else:
        portion = re.search(r"份(\d+\.\d{2})(\d+\.\d{2})$", compact)
        if portion:
            detail["spec"] = "份"
            detail["unit_price"] = float(portion.group(1))
            detail["quantity"] = 1.0
            detail["subtotal"] = float(portion.group(2))
    return detail


def _official_flavor_options(options=None):
    """Collect configured flavor labels without tying parsing to one flavor."""
    values = {
        "原味", "原汤", "不辣", "微辣", "中辣", "重辣", "特辣", "少辣",
    }
    if not isinstance(options, dict):
        return values
    for key in ("shop_sku_categories", "custom_categories", "printer_relay_categories"):
        categories = options.get(key)
        if not isinstance(categories, list):
            continue
        for category in categories:
            if not isinstance(category, dict):
                continue
            items = category.get("items") if isinstance(category.get("items"), list) else [category]
            for item in items:
                if not isinstance(item, dict):
                    continue
                configured = item.get("flavor_options") or category.get("flavor_options") or []
                if isinstance(configured, str):
                    configured = re.split(r"[,，、\n]+", configured)
                if isinstance(configured, (list, tuple, set)):
                    values.update(
                        clean_dish_name(value) for value in configured
                        if str(value or "").strip()
                    )
    return values


def _extract_official_pos_item_details(raw_text: str, options=None):
    """Extract product rows and their numeric columns from an official slip."""
    lines = [line.strip() for line in str(raw_text or "").replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines:
        return []

    header_index = -1
    for index, line in enumerate(lines):
        compact = re.sub(r"\s+", "", line)
        if "名称" in compact and "单价" in compact and "数量" in compact:
            header_index = index
            break

    if header_index >= 0:
        candidate_lines = lines[header_index + 1:]
    else:
        # Compact test/driver templates may omit the column header.  Start
        # after the POS marker so the store title and pickup number cannot be
        # mistaken for products.
        start = 0
        for index, line in enumerate(lines):
            compact = re.sub(r"\s+", "", line)
            if "POS点餐" in compact:
                start = index + 1
                break
        candidate_lines = lines[start:]

    stop_prefixes = (
        "合计", "系统抹零", "应付", "实付", "实收", "原价合计", "订单号",
        "订单时间", "下单时间", "打印时间", "服务热线", "加盟咨询热线",
        "联系电话", "送餐地址", "收货地址", "地址", "支付", "付款",
        "操作人", "备注",
    )
    skip_prefixes = (
        "取餐号", "POS点餐", "人民币", "微信", "支付宝", "银行卡", "刷卡",
    )
    details = []
    flavor_options = _official_flavor_options(options)
    for line in candidate_lines:
        compact = re.sub(r"\s+", "", line)
        if not compact:
            break
        if compact.startswith(skip_prefixes):
            continue
        if compact.startswith(stop_prefixes):
            break
        if compact in ("名称规格单价数量小计", "规格单价数量小计"):
            continue
        if re.fullmatch(r"[-=*_]+", compact) or re.fullmatch(r"[\d.]+", compact):
            continue
        name = _official_pos_item_name(line)
        if not name:
            continue
        cleaned = clean_dish_name(name)
        if cleaned:
            # Official POS prints a flavor/remark on its own line directly
            # below the product row.  Use configured labels when available,
            # but also accept any short, Chinese-only, no-number line so a
            # newly configured flavor does not require a code change.
            generic_flavor = (
                bool(details)
                and not re.search(r"\d", compact)
                and len(cleaned) <= 8
                and bool(re.fullmatch(r"[\u4e00-\u9fff]+", cleaned))
            )
            if cleaned in flavor_options or generic_flavor:
                details[-1]["flavor"] = cleaned
                continue
            details.append(_official_pos_item_detail(line, cleaned))
    return details


def _extract_official_pos_item_names(raw_text: str):
    """Backward-compatible names-only view of official POS rows."""
    return [item["name"] for item in _extract_official_pos_item_details(raw_text)]


def classify_item(item_name: str, custom_categories: list = None, match_mode: str = "contains") -> str:
    """
    根据菜品名关键词识别分类
    - 自动清理全半角空格、序号、数量后缀
    - match_mode: 'contains' (部分/模糊包含匹配), 'exact' (全字精确匹配)
    """
    cats = custom_categories if (custom_categories and isinstance(custom_categories, list)) else DEFAULT_CATEGORIES
    clean_name = clean_dish_name(item_name)

    for cat in cats:
        for kw in cat.get("keywords", []):
            # 自动过滤关键字中的多余空格
            clean_kw = re.sub(r"\s+", "", str(kw)).lower()
            if not clean_kw:
                continue
            if match_mode == "exact":
                if clean_kw == clean_name:
                    return cat.get("id", "veg")
            else:  # contains
                if clean_kw in clean_name:
                    return cat.get("id", "veg")
    return "other"


def _mapping_values(mapping, key, defaults):
    """Read comma-separated/list aliases configured for official POS parsing."""
    value = (mapping or {}).get(key, defaults) if isinstance(mapping, dict) else defaults
    if isinstance(value, str):
        values = re.split(r"[,，、\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = defaults
    result = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result or list(defaults)


def _keyword_pattern(values):
    """Build a literal keyword regex while tolerating full/half-width colons."""
    parts = []
    for value in values:
        escaped = re.escape(str(value))
        escaped = escaped.replace(r"\:", r"\s*[:：]?\s*")
        escaped = escaped.replace(":", r"\s*[:：]?\s*")
        escaped = escaped.replace("：", r"\s*[:：]?\s*")
        parts.append(escaped)
    return "|".join(parts)


def parse_and_sort_takeout_text(raw_text: str, options: dict = None) -> dict:
    """
    解析外卖单文本并按检菜规范重排 (默认全量打包规则)
    """
    opts = options or {}
    mark_star = opts.get("mark_multi_qty_star", True)
    show_prices = opts.get("show_prices", False)
    show_address = opts.get("show_address", True)
    show_order_time = opts.get("show_order_time", True)
    show_full_order_id = opts.get("show_full_order_id", False)
    show_preorder_alert = opts.get("show_preorder_alert", True)
    match_mode = opts.get("printer_relay_match_mode", "contains")
    custom_categories = opts.get("custom_categories", DEFAULT_CATEGORIES)
    # Takeout recognition has its own mapping.  The generic official-POS
    # mapping is kept as a compatibility fallback for older configurations,
    # but changes made on the external-order page no longer alter dine-in
    # field recognition.
    mapping = opts.get("printer_relay_field_mapping") or opts.get("official_pos_field_mapping") or opts
    order_id_labels = _mapping_values(mapping, "order_id_labels", ["订单号", "订单编号"])
    amount_labels = _mapping_values(mapping, "amount_labels", ["实付", "实收", "支付金额", "付款金额", "应付", "应收", "合计", "总计", "原价合计"])
    paid_keywords = _mapping_values(mapping, "paid_keywords", ["支付成功", "付款成功", "收款成功", "交易成功", "已支付", "已付款", "已结账", "结账成功", "支付状态:成功"])
    cancelled_keywords = _mapping_values(mapping, "cancelled_keywords", ["已取消", "取消订单", "退款成功", "已退款"])
    takeout_keywords = _mapping_values(mapping, "takeout_keywords", ["外卖", "美团", "饿了么", "制作单"])
    # Official POS refund/void templates use more specific labels than the
    # normal customer ticket. Keep these aliases as parser defaults even when
    # an older saved mapping omits them; they are evidence of a cancellation,
    # never evidence of a successful payment.
    for label in ("实付金额", "应退金额", "退款金额"):
        if label not in amount_labels:
            amount_labels.append(label)
    for keyword in ("退单", "退菜单", "退菜", "应退金额", "退款", "已退款"):
        if keyword not in cancelled_keywords:
            cancelled_keywords.append(keyword)

    raw_text = str(raw_text or "").replace("\r\n", "\n").strip()
    is_meituan = "美团外卖" in raw_text or "美团" in raw_text
    is_eleme = "饿了么" in raw_text or "ELE" in raw_text or "饿了么" in raw_text
    is_waimai = any(keyword in raw_text for keyword in takeout_keywords) or is_meituan or is_eleme

    # 识别是否预订单 / 定时单
    is_preorder = "预订单" in raw_text or "预约" in raw_text or "送达时间" in raw_text
    preorder_time_match = re.search(r"(\d{1,2}:\d{2})\s*前送达", raw_text)
    preorder_time_str = preorder_time_match.group(1) if preorder_time_match else ""

    # 提取单号 (如 #18)
    order_no_match = re.search(r"(?:#\s*|取餐号[:：]?\s*)([A-Za-z0-9-]+)", raw_text)
    order_no = f"#{order_no_match.group(1)}" if order_no_match else "#---"

    # 提取地址
    address_match = re.search(r"(?:送餐|收货|配送)?地址[:：]\s*([^\n]+)", raw_text)
    address_str = address_match.group(1).strip() if address_match else "默认地址 / 门自取"

    # 提取下单时间
    time_match = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", raw_text)
    order_time_str = time_match.group(0) if time_match else time.strftime("%Y-%m-%d %H:%M:%S")

    # 提取完整订单号
    order_label_pattern = "|".join(re.escape(label) for label in order_id_labels)
    full_id_match = re.search(r"(?:%s)[:：]?\s*([A-Za-z0-9#_-]{2,})" % order_label_pattern, raw_text)
    full_order_id = full_id_match.group(1) if full_id_match else ""

    # 金额是可选字段。仅从明确的金额标签中取值，并保留来源；不能把
    # “收到打印任务”或“实付金额存在”当作付款成功证据。
    amount_matches = []
    # Official v2 receipts render these labels as ``合计``, ``应付`` and
    # ``实付``; spacing/alignment varies by driver, so match the visible text
    # rather than the template variable names.
    amount_label_pattern = "|".join(re.escape(label) for label in amount_labels)
    amount_pattern = re.compile(
        r"(%s)\s*[:：]?\s*[￥¥]?\s*([-−－]?\s*[0-9]+(?:[.,][0-9]{1,2})?)" % amount_label_pattern
    )
    for match in amount_pattern.finditer(raw_text):
        try:
            value = float(match.group(2).replace(",", ".").replace("−", "-").replace("－", "-"))
        except (TypeError, ValueError):
            continue
        amount_matches.append((match.group(1), value))
    preferred_amount = None
    amount_source = ""
    for label in amount_labels:
        for source, value in amount_matches:
            if source == label:
                preferred_amount, amount_source = value, source
                break
        if preferred_amount is not None:
            break
    # 只有明确的支付/结账成功语句才会进入 paid；“实付：￥x”仅是金额来源。
    paid_pattern = _keyword_pattern(paid_keywords)
    cancelled_pattern = _keyword_pattern(cancelled_keywords)
    paid_evidence = re.search(r"(?:%s)" % paid_pattern, raw_text, flags=re.IGNORECASE)
    cancelled_evidence = re.search(r"(?:%s)" % cancelled_pattern, raw_text, flags=re.IGNORECASE)
    if paid_evidence:
        payment_status = "paid"
        payment_status_evidence = paid_evidence.group(0)
    elif cancelled_evidence:
        payment_status = "cancelled"
        payment_status_evidence = cancelled_evidence.group(0)
    else:
        payment_status = "unknown"
        payment_status_evidence = ""
    payment_method_matches = re.findall(
        r"人民币|微信支付|支付宝支付|扫码支付|微信|支付宝|银行卡|刷卡",
        raw_text,
        flags=re.IGNORECASE,
    )
    payment_methods = []
    for method in payment_method_matches:
        if method not in payment_methods:
            payment_methods.append(method)
    payment_method = "+".join(payment_methods)
    if payment_status == "cancelled":
        # Refund templates often contain several negative totals. Prefer the
        # explicit refund amount over the generic item/order total while
        # keeping amount_valid=False so it can never enter amount routing.
        for source, value in amount_matches:
            if source in ("应退金额", "退款金额", "实付金额"):
                preferred_amount, amount_source = value, source
                break

    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # 按动态分类分组
    categorized_items = {cat.get("id"): [] for cat in custom_categories}
    categorized_items["other"] = []

    item_count = 0
    item_names = []
    item_details = []
    if _is_official_pos_customer_text(raw_text):
        # Official customer slips have aligned columns rather than the
        # ``name x qty ￥price`` syntax used by takeout platforms.  Parse the
        # product rows separately so headers, hotline text and column numbers
        # never appear as goods in order history.
        item_details = _extract_official_pos_item_details(raw_text, options)
        official_names = [item["name"] for item in item_details]
        for name in official_names:
            cat_id = classify_item(name, custom_categories, match_mode=match_mode)
            if cat_id in categorized_items:
                categorized_items[cat_id].append(name)
            else:
                categorized_items["other"].append(name)
        item_names = official_names
        item_count = len(official_names)
    else:
        for line in lines:
            formatted_line, qty = _format_item_line(line, show_prices, mark_star)
            if not formatted_line:
                continue
            cat_id = classify_item(formatted_line, custom_categories, match_mode=match_mode)
            if cat_id in categorized_items:
                categorized_items[cat_id].append(formatted_line)
            else:
                categorized_items["other"].append(formatted_line)
            item_count += qty
            item_names.append(clean_dish_name(formatted_line))

    # 组装票据文本
    platform_name = "美团外卖" if is_meituan else ("饿了么" if is_eleme else "外卖订单")
    sorted_lines = []

    # 1. 顶端默认密集【外卖打包】提醒
    sorted_lines.append("【外卖打包】" * 4)

    if is_preorder and show_preorder_alert:
        p_str = f"⏰ 预订单 ({preorder_time_str} 前送达)" if preorder_time_str else "⏰ 预订单 (定时送达)"
        sorted_lines.append("================================================")
        sorted_lines.append(f"       {p_str}")
        sorted_lines.append("================================================")

    # 2. 头部标题
    sorted_lines.append("================================================")
    sorted_lines.append(f"      【{platform_name} {order_no} 制作单】")
    sorted_lines.append("================================================")

    # 3. 元数据：下单时间 & 地址
    if show_order_time:
        sorted_lines.append(f"下单时间：{order_time_str}")
    if show_address:
        sorted_lines.append(f"送餐地址：{address_str}")

    sorted_lines.append("------------------------------------------------")

    # 4. 菜品分类明细
    for cat in custom_categories:
        c_id = cat.get("id")
        c_name = cat.get("name", "分类")
        items = categorized_items.get(c_id, [])
        if items:
            sorted_lines.append(f"\n{c_name} (共 {len(items)} 项)")
            for item in items:
                sorted_lines.append(f"  • {item}")

    if categorized_items["other"]:
        sorted_lines.append(f"\n其它项目 (共 {len(categorized_items['other'])} 项)")
        for item in categorized_items["other"]:
            sorted_lines.append(f"  • {item}")

    # 5. 底部信息 (完整订单号等)
    sorted_lines.append("\n------------------------------------------------")
    if show_full_order_id and full_order_id:
        sorted_lines.append(f"完整订单号：{full_order_id}")

    if item_count == 0:
        sorted_lines.append("⚠ 未识别到菜品，请人工核对原始文本")
    sorted_lines.append("【外卖打包】" * 4)

    sorted_text = "\n".join(sorted_lines)

    # 票面合计/实付若同时存在且不一致，只能把金额标为冲突，不能用于
    # 金额分流。金额校验仍是票面内部校验，不等价于付款确认。
    amount_by_label = {label: value for label, value in amount_matches}
    amount_valid = preferred_amount is not None and preferred_amount >= 0
    # Discounts commonly produce both original total and paid total.  That is
    # still a valid amount source when the paid value does not exceed the
    # original/amount-due value.  Conflicting duplicate labels remain invalid.
    for label in ("实付", "实付金额", "实收", "支付金额", "付款金额"):
        values = [value for source, value in amount_matches if source == label]
        if values and len({round(value, 2) for value in values}) > 1:
            amount_valid = False
    if "实付" in amount_by_label and "原价合计" in amount_by_label:
        amount_valid = amount_valid and amount_by_label["实付"] <= amount_by_label["原价合计"] + 0.01
    if "实付" in amount_by_label and "应付" in amount_by_label:
        amount_valid = amount_valid and amount_by_label["实付"] <= amount_by_label["应付"] + 0.01
    if "实收" in amount_by_label and "应收" in amount_by_label:
        amount_valid = amount_valid and amount_by_label["实收"] <= amount_by_label["应收"] + 0.01

    return {
        "is_waimai": is_waimai,
        "receipt_kind": "takeout" if is_waimai else "unknown",
        "platform": platform_name,
        "order_no": order_no,
        "is_preorder": is_preorder,
        "address": address_str,
        "order_time": order_time_str,
        "full_order_id": full_order_id,
        "order_amount": preferred_amount,
        "amount_source": amount_source,
        "amount_valid": amount_valid,
        "payment_status": payment_status,
        "payment_status_evidence": payment_status_evidence,
        "payment_status_confidence": "high" if payment_status in ("paid", "cancelled") else "unknown",
        "payment_method": payment_method,
        "key_confidence": "high" if full_order_id else "low",
        "item_count": item_count,
        "item_names": item_names,
        "item_details": item_details,
        "raw_text": raw_text,
        "sorted_text": sorted_text,
    }


def parse_official_pos_text(raw_text: str, options: dict = None) -> dict:
    """Parse a generic official-POS receipt without changing its output.

    The existing takeout parser remains the source of the external-order
    sorting text.  This wrapper adds a conservative receipt classification and
    a stable deduplication key for dine-in/customer receipts, which are passed
    through unchanged by the relay.  A generic print job alone never becomes
    paid.  This store's recognizable customer settlement receipt is the one
    workflow exception: its settlement shape is recorded as high-confidence
    paid evidence because the POS emits it only after checkout.  Kitchen,
    control and refund templates remain unknown/cancelled.
    """
    parsed = parse_and_sort_takeout_text(raw_text, options)
    mapping = (options or {}).get("official_pos_field_mapping") if isinstance(options, dict) else None
    text = str(raw_text or "").replace("\r\n", "\n").strip()
    compact = re.sub(r"\s+", "", text)
    # The official POS emits a second, raw kitchen ticket for a dine-in
    # checkout.  Its text contains “制作单” and therefore matches the generic
    # takeout keyword list, but the official-only “取餐号” line proves that it
    # is the store's own POS kitchen slip, not an external-platform order.
    # Keep it in the official/dine-in path so the original layout is forwarded
    # instead of being rewritten as an 外卖单.
    has_official_kitchen_markers = (
        "制作单" in compact
        and "取餐号" in compact
        and not any(marker in compact for marker in ("美团", "饿了么", "外卖订单", "外卖打包"))
    )
    if parsed.get("is_waimai") and not has_official_kitchen_markers:
        receipt_kind = "takeout"
        platform = parsed.get("platform") or "外卖订单"
    else:
        dinein_markers = _mapping_values(
            mapping, "dinein_keywords",
            ["堂食", "POS点餐", "收银", "消费小票", "结账单", "制作单-堂食"],
        )
        looks_dinein = any(marker in compact for marker in dinein_markers)
        has_receipt_fields = bool(
            parsed.get("order_amount") is not None
            and (parsed.get("full_order_id") or parsed.get("item_count") or looks_dinein)
        )
        receipt_kind = "dinein" if (looks_dinein or has_receipt_fields or has_official_kitchen_markers) else "unknown"
        platform = "官方POS-堂食" if receipt_kind == "dinein" else "官方POS"

    parsed["receipt_kind"] = receipt_kind
    parsed["platform"] = platform
    parsed["is_official_receipt"] = receipt_kind in ("takeout", "dinein")
    parsed["is_official_kitchen"] = bool(has_official_kitchen_markers)

    # This store's official POS only emits the customer settlement receipt
    # after checkout.  Apply that local workflow rule only when the payload
    # has the recognizable settlement shape; printer self-tests, kitchen
    # slips, and refunds must remain unknown/cancelled.  A generic receipt
    # without these markers still requires explicit payment evidence.
    # Payment-method text is not stable across this POS: cash receipts may
    # show “人民币”, while QR/card receipts can show a different method or
    # omit the method entirely.  The stable part is the customer settlement
    # shape (final amount + order id + order time), not the cash label.
    has_settlement_time = "订单时间" in compact or "下单时间" in compact
    has_final_amount_label = bool(parsed.get("amount_source")) or any(
        label in compact for label in ("应付", "实付", "实收", "合计", "总计")
    )
    settlement_print = (
        receipt_kind == "dinein"
        and bool(parsed.get("full_order_id"))
        and parsed.get("order_amount") is not None
        and parsed.get("amount_valid") is True
        and has_settlement_time
        and has_final_amount_label
        and "制作单" not in compact
        and "后厨" not in compact
        and parsed.get("payment_status") == "unknown"
    )
    if settlement_print:
        parsed["payment_status"] = "paid"
        parsed["payment_status_evidence"] = (
            "官方 POS 结账单打印规则（付款方式：%s）" % parsed.get("payment_method")
            if parsed.get("payment_method") and parsed.get("payment_method") != "人民币"
            else "官方 POS 结账单打印规则"
        )
        parsed["payment_status_confidence"] = "high"

    full_id = str(parsed.get("full_order_id") or "").strip()
    order_no = str(parsed.get("order_no") or "").strip()
    if full_id:
        receipt_key = "official:%s" % full_id
        key_confidence = "high"
    elif order_no and order_no != "#---":
        receipt_key = "official:%s:%s" % (receipt_kind, order_no)
        key_confidence = "medium"
    else:
        # Remove volatile print-time lines so a reprint of the same ticket can
        # still be recognized as the same receipt while retaining a bounded
        # fallback key when the POS exposes no order number at all.
        stable_lines = [
            line.strip() for line in text.splitlines()
            if line.strip() and not re.search(r"打印时间|打印日期", line)
        ]
        basis = "|".join(stable_lines)
        digest = hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()[:24]
        receipt_key = "official:%s:hash:%s" % (receipt_kind, digest)
        key_confidence = "low"
    parsed["receipt_key"] = receipt_key
    parsed["key_confidence"] = key_confidence
    parsed["raw_text"] = text
    return parsed


def escpos_payload_to_text(payload: bytes) -> str:
    """Best-effort extraction of printable GBK text from an ESC/POS RAW job."""
    data = bytearray(payload or b"")
    output = bytearray()
    index = 0
    while index < len(data):
        current = data[index]
        if current == 0x1B:  # ESC commands are usually 2-3 bytes.
            if index + 1 < len(data) and data[index + 1] in (0x40, 0x61, 0x21, 0x45, 0x64, 0x33):
                index += 3 if data[index + 1] in (0x21, 0x61, 0x45, 0x64, 0x33) else 2
            else:
                index += 2
            continue
        if current == 0x1D:  # GS commands, including cut and size controls.
            if index + 1 < len(data) and data[index + 1] in (0x21, 0x56):
                index += 3
            else:
                index += 2
            continue
        if current >= 0x20 or current in (0x0A, 0x0D, 0x09):
            output.append(current)
        index += 1
    return bytes(output).decode("gbk", errors="ignore").replace("\r", "\n")


def classify_print_payload(payload: bytes, extracted_text: str = "") -> str:
    """Classify a captured job without assuming it is text/ESC-POS."""
    data = bytes(payload or b"")
    if not data:
        return "empty"
    if data.startswith(b"\x1b") or b"\x1dV" in data[:256] or b"\x1b@" in data[:256]:
        return "raw_escpos"
    upper = data[:32].upper()
    if upper.startswith((b"%PDF", b"PCL", b"EMF", b"\x89PNG", b"\xff\xd8\xff")):
        return "driver_rendered"
    printable = sum(1 for value in data[:4096] if value in (9, 10, 13) or 32 <= value < 127)
    if extracted_text and printable >= max(8, len(data[:4096]) * 0.35):
        return "text_or_raw"
    return "binary_or_unknown"


def build_takeout_escpos_ticket(sorted_text: str, config: dict, ticket_kind="kitchen") -> bytes:
    """Render a sorted takeout order with the configured ESC/POS emphasis."""
    config = config or {}
    header_size = (0x00, 0x20, 0x30)[min(2, max(0, int(config.get("printer_relay_font_hdr", 1))))]
    category_size = (0x00, 0x08, 0x10)[min(2, max(0, int(config.get("printer_relay_font_cat", 1))))]
    item_size = (0x00, 0x10, 0x30)[min(2, max(0, int(config.get("printer_relay_font_item", 1))))]
    label = "制作联" if ticket_kind == "kitchen" else "存根联"
    data = bytearray(b"\x1b@\x1ba\x01\x1b!" + bytes([header_size]))
    data += ("【外卖%s】\n" % label).encode("gbk", errors="ignore")
    data += b"\x1b!\x00\x1ba\x00"
    for line in str(sorted_text or "").splitlines():
        if not line:
            data += b"\n"
            continue
        if "【" in line or "外卖打包" in line or "制作单" in line:
            size = header_size
            bold = True
        elif "共 " in line or "其它项目" in line or line.startswith(("🍲", "🥩", "🥬", "🥤", "汤 ", "肉 ", "菜 ", "饮 ")):
            size = category_size
            bold = True
        else:
            size = item_size
            bold = False
        data += b"\x1b!" + bytes([size]) + (b"\x1bE\x01" if bold else b"\x1bE\x00")
        data += (line + "\n").encode("gbk", errors="ignore")
    data += b"\x1b!\x00\x1bE\x00\x1bd\x04\x1dV\x01"
    return bytes(data)


class PrinterRelayInterceptor(QObject):
    """A local RAW TCP proxy for an official-POS takeout printer queue.

    Windows cannot reliably intercept and rewrite a job that has already been
    sent to a physical printer.  The official POS therefore prints to a local
    TCP/IP queue (127.0.0.1:<port>); this proxy receives the RAW ESC/POS data
    first, extracts the order text and emits it for reformatting/reprinting.
    The physical receipt printer remains the target configured in this POS.
    """
    order_intercepted = pyqtSignal(object)
    status_changed = pyqtSignal(str)

    def __init__(self, config=None, parent=None, on_order=None):
        super().__init__(parent)
        self.config = config or {}
        # The listener is also used by the detached proxy host, where there is
        # deliberately no Qt event loop.  A regular Python callback keeps the
        # essential forwarding path independent from the POS window.
        self.on_order = on_order
        self.is_enabled = bool(self.config.get("printer_relay_enabled", False))
        self._listener = None
        self._thread = None
        self._running = False
        self.last_error = ""

    @property
    def port(self):
        try:
            return int(self.config.get("printer_relay_port", 9101))
        except (TypeError, ValueError):
            return 9101

    def set_enabled(self, enabled: bool):
        self.is_enabled = enabled
        if enabled:
            self.start()
        else:
            self.stop()

    def update_config(self, config):
        old_port = self.port
        self.config = config or {}
        self.is_enabled = bool(self.config.get("printer_relay_enabled", False))
        if self._running and (not self.is_enabled or self.port != old_port):
            self.stop()
        if self.is_enabled and not self._running:
            self.start()

    def start(self):
        if not self.is_enabled or self._running:
            return self._running
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", self.port))
            listener.listen(5)
            listener.settimeout(0.5)
            self._listener = listener
            self._running = True
            self.last_error = ""
            self._thread = threading.Thread(target=self._serve, name="PrinterRelayRawProxy", daemon=True)
            self._thread.start()
            self.status_changed.emit("● 中继运行中：127.0.0.1:%d" % self.port)
            return True
        except OSError as exc:
            self.last_error = str(exc)
            self._running = False
            self.status_changed.emit("✕ 中继无法启动：%s" % self.last_error)
            return False

    def _serve(self):
        while self._running:
            try:
                try:
                    client, _address = self._listener.accept()
                except socket.timeout:
                    continue
                with client:
                    client.settimeout(0.8)
                    chunks = []
                    size = 0
                    while size < 1024 * 1024:
                        try:
                            part = client.recv(min(8192, 1024 * 1024 - size))
                        except socket.timeout:
                            break
                        if not part:
                            break
                        chunks.append(part)
                        size += len(part)
                    self._handle_payload(b"".join(chunks))
            except OSError:
                if self._running:
                    self.last_error = "中继套接字异常"
                    self.status_changed.emit("✕ " + self.last_error)
            except Exception as exc:
                self.last_error = str(exc)
                self.status_changed.emit("✕ 中继处理失败：%s" % self.last_error)

    def _handle_payload(self, payload):
        if not payload:
            return
        text = escpos_payload_to_text(payload)
        # Pass the saved field mapping through the detached listener as well;
        # otherwise the UI mapping would only affect the preview, not real
        # official-POS print jobs.
        parsed = parse_official_pos_text(text, self.config)
        parsed["raw_text"] = text
        parsed["raw_payload"] = bytes(payload)
        parsed["payload_size"] = len(payload)
        parsed["payload_type"] = classify_print_payload(payload, text)
        parsed["parse_failed"] = not bool(
            parsed.get("is_official_receipt") and (
                parsed.get("item_count") or parsed.get("order_amount") is not None
                or parsed.get("full_order_id")
            )
        )
        parsed["capture_path"] = capture_print_payload(payload, parsed, self.config)
        if self.on_order:
            try:
                self.on_order(parsed)
            except Exception as exc:
                self.last_error = "外卖任务处理失败：%s" % exc
                self.status_changed.emit("✕ " + self.last_error)
                return
        self.order_intercepted.emit(parsed)
        if parsed["parse_failed"]:
            self.status_changed.emit("ⓘ 已捕获但无法完整识别（%s），已进入原始转发兜底" % parsed.get("payload_type"))
        else:
            self.status_changed.emit("✓ 已拦截 %s %s（%d 项）" % (
                parsed.get("platform"), parsed.get("order_no"), parsed.get("item_count", 0)
            ))

    def stop(self):
        self._running = False
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass
        self._listener = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self.status_changed.emit("○ 打印机中继已停止")
