"""
价格计算模块 — 兼容 Python 3.8+
"""


def calculate_price(weight_kg, unit_price, price_unit):
    """
    根据重量和单价计算总价。

    Args:
        weight_kg:  重量，单位：公斤
        unit_price: 单价
        price_unit: 计价单位 "per_jin"=元/斤  "per_kg"=元/公斤

    Returns:
        总价（保留两位小数）
    """
    if price_unit == "per_jin":
        # 1 公斤 = 2 斤
        weight_jin = weight_kg * 2
        total = weight_jin * unit_price
    elif price_unit == "per_kg":
        total = weight_kg * unit_price
    else:
        raise ValueError("未知计价单位: %s" % price_unit)

    return round(total, 2)


def weight_display(weight_kg, price_unit):
    """
    格式化重量显示。

    根据计价单位决定显示公斤还是斤。
    """
    if price_unit == "per_jin":
        return "%.2f 斤" % (weight_kg * 2)
    else:
        return "%.3f kg" % weight_kg


def price_unit_label(price_unit):
    """返回单价的单位标签 (如: 斤 / kg)"""
    if price_unit == "per_jin":
        return "斤"
    else:
        return "kg"
