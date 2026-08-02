# -*- coding: utf-8 -*-
"""
外卖打印中继与菜品智能排序核心引擎
外卖单默认即为【外卖打包】，自动包含打包醒目提醒与分类重排
"""
import time
import re
import threading
from PyQt5.QtCore import QObject, pyqtSignal, QThread


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


def classify_item(item_name: str, custom_categories: list = None) -> str:
    """根据菜品名关键词识别分类"""
    cats = custom_categories if (custom_categories and isinstance(custom_categories, list)) else DEFAULT_CATEGORIES
    for cat in cats:
        for kw in cat.get("keywords", []):
            if kw in item_name:
                return cat.get("id", "veg")
    return "veg"


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
    custom_categories = opts.get("custom_categories", DEFAULT_CATEGORIES)

    is_meituan = "美团外卖" in raw_text or "美团" in raw_text
    is_eleme = "饿了么" in raw_text or "ELE" in raw_text
    is_waimai = is_meituan or is_eleme or "外卖" in raw_text

    # 识别是否预订单 / 定时单
    is_preorder = "预订单" in raw_text or "预约" in raw_text or "送达时间" in raw_text
    preorder_time_match = re.search(r"(\d{1,2}:\d{2})\s*前送达", raw_text)
    preorder_time_str = preorder_time_match.group(1) if preorder_time_match else ""

    # 提取单号 (如 #18)
    order_no_match = re.search(r"#\s*(\d+)", raw_text)
    order_no = f"#{order_no_match.group(1)}" if order_no_match else "#---"

    # 提取地址
    address_match = re.search(r"地址[:：]\s*(.+)", raw_text)
    address_str = address_match.group(1).strip() if address_match else "默认地址 / 门自取"

    # 提取下单时间
    time_match = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", raw_text)
    order_time_str = time_match.group(0) if time_match else time.strftime("%Y-%m-%d %H:%M:%S")

    # 提取完整订单号
    full_id_match = re.search(r"订单号[:：]\s*(\d+)", raw_text)
    full_order_id = full_id_match.group(1) if full_id_match else ""

    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # 按动态分类分组
    categorized_items = {cat.get("id"): [] for cat in custom_categories}
    categorized_items["other"] = []

    for line in lines:
        if any(skip in line for skip in ["美团外卖", "饿了么", "存根", "联", "实付", "原价", "配送费", "下单时间", "地址"]):
            continue

        # 尝试正则匹配数量 (如 肥牛 x 2 或 肥牛 2份)
        qty_match = re.search(r"[xX*×]\s*(\d+)|(\d+)\s*份", line)
        qty = 1
        if qty_match:
            qty_str = qty_match.group(1) or qty_match.group(2)
            qty = int(qty_str)

        # 同菜品多份加 ⭐ 标记
        formatted_line = line
        if mark_star and qty >= 2:
            formatted_line = f"⭐ 【多份x{qty}】 {line}"

        # 价格隐藏处理
        if not show_prices:
            formatted_line = re.sub(r"￥\s*\d+(\.\d+)?", "", formatted_line).strip()

        cat_id = classify_item(line, custom_categories)
        if cat_id in categorized_items:
            categorized_items[cat_id].append(formatted_line)
        else:
            categorized_items["other"].append(formatted_line)

    # 组装票据文本
    platform_name = "美团外卖" if is_meituan else ("饿了么" if is_eleme else "外卖订单")
    sorted_lines = []

    # 1. 顶端默认密集【外卖打包】提醒
    sorted_lines.append("外卖打包  " * 6)

    if is_preorder and show_preorder_alert:
        p_str = f"⏰ 预订单 ({preorder_time_str} 前送达)" if preorder_time_str else "⏰ 预订单 (定时送达)"
        sorted_lines.append("================================================")
        sorted_lines.append(f"       {p_str}")
        sorted_lines.append("================================================")

    # 2. 头部标题
    sorted_lines.append("================================================")
    sorted_lines.append(f"      【{platform_name} {order_no} 检菜单-外卖打包】")
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

    sorted_lines.append("外卖打包  " * 6)

    sorted_text = "\n".join(sorted_lines)

    return {
        "is_waimai": is_waimai,
        "platform": platform_name,
        "order_no": order_no,
        "is_preorder": is_preorder,
        "address": address_str,
        "order_time": order_time_str,
        "full_order_id": full_order_id,
        "raw_text": raw_text,
        "sorted_text": sorted_text,
    }


class TakeoutPrintInterceptor(QThread):
    """Windows 打印机中继拦截服务线程"""
    order_intercepted = pyqtSignal(dict)
    status_changed = pyqtSignal(str)

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.is_enabled = self.config.get("takeout_interceptor_enabled", True)
        self.printer_name = self.config.get("printer_name", "shouyin")
        self._running = True

    def set_enabled(self, enabled: bool):
        self.is_enabled = enabled
        status_str = "● 中继就绪 (监听中...)" if enabled else "○ 中继关闭 (官方POS直连)"
        self.status_changed.emit(status_str)

    def run(self):
        self.set_enabled(self.is_enabled)
        while self._running:
            try:
                if not self.is_enabled:
                    time.sleep(1)
                    continue
                time.sleep(2)
            except Exception as e:
                print(f"[TakeoutInterceptor] 监听异常: {e}")
                time.sleep(2)

    def stop(self):
        self._running = False
        self.quit()
        self.wait()
