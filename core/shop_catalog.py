"""Configurable shop SKU/category catalogue.

The catalogue is deliberately kept in the normal application config so old
installations continue to use the built-in menu until an operator saves the
new page.  The helper only normalizes data; it does not write files.
"""

from copy import deepcopy


DEFAULT_SHOP_CATEGORIES = [
    {
        "id": "soup", "name": u"汤底", "order": 0,
        "show_flavor": True, "default": True,
        "items": [
            {"id": "soup_1", "name": u"经典草本骨汤", "price": None, "order": 0, "kind": "soup",
             "show_flavor": True, "flavor_auto_hide_sec": 1.0,
             "flavor_options": [u"原汤", u"微辣", u"中辣", u"重辣"]},
            {"id": "soup_2", "name": u"酸甜番茄汤", "price": None, "order": 1, "kind": "soup",
             "show_flavor": False, "flavor_auto_hide_sec": 1.0,
             "flavor_options": [u"不辣", u"原汤", u"微辣", u"中辣", u"重辣"]},
            {"id": "soup_3", "name": u"石磨醇香麻辣拌", "price": None, "order": 2, "kind": "soup",
             "show_flavor": False, "flavor_auto_hide_sec": 1.0,
             "flavor_options": [u"不辣", u"原汤", u"微辣", u"中辣", u"重辣"]},
            {"id": "soup_4", "name": u"草本穹顶菌汤", "price": None, "order": 3, "kind": "soup", "special": True,
             "show_flavor": False, "flavor_auto_hide_sec": 1.0,
             "flavor_options": [u"不辣", u"原汤", u"微辣", u"中辣", u"重辣"]},
            {"id": "soup_5", "name": u"草本酸辣金汤", "price": None, "order": 4, "kind": "soup", "special": True,
             "show_flavor": False, "flavor_auto_hide_sec": 1.0,
             "flavor_options": [u"不辣", u"原汤", u"微辣", u"中辣", u"重辣"]},
        ],
    },
    {"id": "packing", "name": u"打包", "order": 1, "show_flavor": False, "default": True,
     "items": [{"id": "item_box", "name": u"打包盒", "price": 1.0, "order": 0, "kind": "box"}]},
    {"id": "skewer", "name": u"精品串", "order": 2, "show_flavor": False, "default": True,
     "items": [{"id": "item_skewer_%d" % i, "name": u"精品串 %d元" % i, "price": float(i), "order": i - 1, "kind": "skewer"}
                for i in range(1, 7)]},
    {"id": "drink", "name": u"饮料", "order": 3, "show_flavor": False, "default": True,
     "items": [{"id": "item_%d" % i, "name": u"%d元饮料" % i, "price": float(i), "order": i - 1, "kind": "item"}
                for i in range(1, 11)]},
]


def default_flavor_options(name):
    """Return the built-in flavor choices for a soup SKU."""
    if u"草本骨汤" in str(name or ""):
        return [u"原汤", u"微辣", u"中辣", u"重辣"]
    return [u"不辣", u"原汤", u"微辣", u"中辣", u"重辣"]


def _flavor_options(value, name):
    if isinstance(value, str):
        value = [part.strip() for part in value.replace("，", ",").split(",")]
    if not isinstance(value, (list, tuple)):
        value = []
    result = []
    for option in value:
        text = str(option or "").strip()
        if text and text not in result:
            result.append(text)
    return result or default_flavor_options(name)


def _flavor_seconds(value, default=1.0):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = float(default)
    return round(max(0.0, min(60.0, seconds)), 1)


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def get_shop_categories(config):
    """Return a normalized, sorted catalogue without mutating *config*."""
    raw = config.get("shop_sku_categories")
    if not isinstance(raw, list) or not raw:
        raw = deepcopy(DEFAULT_SHOP_CATEGORIES)
    result = []
    for ci, category in enumerate(raw):
        if not isinstance(category, dict):
            continue
        cid = str(category.get("id") or "category_%d" % ci).strip() or "category_%d" % ci
        items = []
        for ii, item in enumerate(category.get("items") or []):
            if not isinstance(item, dict):
                continue
            iid = str(item.get("id") or "%s_item_%d" % (cid, ii)).strip() or "%s_item_%d" % (cid, ii)
            kind = str(item.get("kind") or ("soup" if cid == "soup" else "item"))
            is_soup = kind == "soup"
            name = str(item.get("name") or iid)
            items.append({
                "id": iid,
                "name": name,
                "price": None if item.get("price") is None else round(_number(item.get("price")), 2),
                "order": int(_number(item.get("order"), ii)),
                "kind": kind,
                "special": bool(item.get("special", False)),
                # Per-SKU flavor settings replace the old category-wide
                # switch.  Legacy saved catalogs default only the classic
                # herbal bone soup to the original one-second popup.
                "show_flavor": bool(item.get("show_flavor", is_soup and name == u"经典草本骨汤")) if is_soup else False,
                "flavor_auto_hide_sec": _flavor_seconds(item.get("flavor_auto_hide_sec", 1.0)) if is_soup else 0.0,
                "flavor_options": _flavor_options(item.get("flavor_options"), name) if is_soup else [],
            })
        result.append({
            "id": cid,
            "name": str(category.get("name") or cid),
            "order": int(_number(category.get("order"), ci)),
            "show_flavor": bool(category.get("show_flavor", cid == "soup")) if cid == "soup" else False,
            "default": bool(category.get("default", cid in ("soup", "packing", "skewer", "drink"))),
            "items": sorted(items, key=lambda x: (x["order"], x["id"])),
        })
    return sorted(result, key=lambda x: (x["order"], x["id"]))


def save_shop_categories(config, categories):
    """Store a clean JSON-compatible copy in config and return it."""
    clean = []
    for ci, category in enumerate(categories or []):
        if not isinstance(category, dict):
            continue
        cid = str(category.get("id") or "category_%d" % ci)
        items = []
        for ii, item in enumerate(category.get("items") or []):
            if not isinstance(item, dict):
                continue
            value = item.get("price")
            kind = str(item.get("kind") or ("soup" if cid == "soup" else "item"))
            is_soup = kind == "soup"
            name = str(item.get("name") or u"未命名商品")
            items.append({
                "id": str(item.get("id") or "%s_item_%d" % (cid, ii)),
                "name": name,
                "price": None if value is None else round(_number(value), 2),
                "order": int(_number(item.get("order"), ii)),
                "kind": kind,
                "special": bool(item.get("special", False)),
                "show_flavor": bool(item.get("show_flavor", is_soup and name == u"经典草本骨汤")) if is_soup else False,
                "flavor_auto_hide_sec": _flavor_seconds(item.get("flavor_auto_hide_sec", 1.0)) if is_soup else 0.0,
                "flavor_options": _flavor_options(item.get("flavor_options"), name) if is_soup else [],
            })
        clean.append({
            "id": cid,
            "name": str(category.get("name") or cid),
            "order": int(_number(category.get("order"), ci)),
            "show_flavor": bool(category.get("show_flavor", False)) if cid == "soup" else False,
            "default": bool(category.get("default", False)),
            "items": sorted(items, key=lambda x: (x["order"], x["id"])),
        })
    config["shop_sku_categories"] = sorted(clean, key=lambda x: (x["order"], x["id"]))
    return config["shop_sku_categories"]
