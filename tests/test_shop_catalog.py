import copy

from config import DEFAULT_CONFIG
from core.shop_catalog import get_shop_categories, save_shop_categories


def test_legacy_config_gets_default_catalog_without_mutation():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.pop("shop_sku_categories", None)
    categories = get_shop_categories(cfg)
    assert [item["name"] for item in categories] == ["汤底", "打包", "精品串", "饮料"]
    assert len(categories[0]["items"]) == 5
    assert categories[0]["items"][0]["show_flavor"] is True
    assert categories[0]["items"][0]["flavor_auto_hide_sec"] == 1.0
    assert all(not item["show_flavor"] for item in categories[0]["items"][1:])
    assert "shop_sku_categories" not in cfg


def test_catalog_save_keeps_custom_order_and_disables_flavor_for_non_soup():
    cfg = {}
    save_shop_categories(cfg, [{
        "id": "custom", "name": "小吃", "order": 2, "show_flavor": True,
        "items": [{"id": "x", "name": "小吃", "price": 3, "order": 0}],
    }])
    assert cfg["shop_sku_categories"][0]["show_flavor"] is False
    assert get_shop_categories(cfg)[0]["items"][0]["price"] == 3.0
    assert get_shop_categories(cfg)[0]["items"][0]["show_flavor"] is False
