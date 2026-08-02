"""
杨国福麻辣烫 · 独立称重打印系统 — 全局配置
支持模块化数据存储 (data/settings/ 目录下拆分存储)
"""
import os
import json
import shutil
import zipfile
import sys

# ─── 应用版本号 ───────────────────────────────────────
APP_VERSION = "v1.1.0"

# ─── 路径 ───────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 拆分后的模块化配置文件目录 data/settings/
SETTINGS_DIR = os.path.join(DATA_DIR, "settings")
os.makedirs(SETTINGS_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "sales.db")
CONFIG_FILE = os.path.join(DATA_DIR, "settings.json")
TEMPLATE_FILE = os.path.join(DATA_DIR, "settings.json.template")

# 模块化 JSON 文件路径
MODULE_FILES = {
    "sys": os.path.join(SETTINGS_DIR, "base.json"),
    "takeout": os.path.join(SETTINGS_DIR, "takeout.json"),
    "algo": os.path.join(SETTINGS_DIR, "algo.json"),
    "shouqianba": os.path.join(SETTINGS_DIR, "shouqianba.json"),
}

# ─── 默认配置 ────────────────────────────────────────
DEFAULT_CONFIG = {
    # 1. 系统与打印机、店铺配置 (base.json)
    "printer_type": "windows",
    "printer_name": "shouyin",
    "printer_ip": "192.168.1.100",
    "printer_port": 9100,
    "printer_serial_port": "COM4",
    "unit_price": 47.60,
    "special_soup_price": 50.00,
    "price_unit": "per_kg",
    "shop_name": u"杨国福麻辣烫",
    "shop_subtitle": u"杨国福(测试店)",
    "is_first_run": True,
    "auto_print": False,
    "stable_threshold": 0.01,
    "stable_count": 5,
    "auto_start_enabled": True,
    "auto_start_delay": 8,
    "auto_switch_enabled": True,
    "floating_ball_enabled": True,
    "panic_hotkey": "F10",
    "auto_hide_delay_sec": 3,
    "scale_source": "official",
    "scale_port": "COM2",
    "scale_baudrate": 9600,

    # 2. 切换算法配置 (algo.json)
    "private_ratio_percent": 30,
    "min_private_weight_kg": 0.25,

    # 3. 收钱吧配置 (shouqianba.json)
    "shouqianba_enabled": True,
    "shouqianba_port": "COM1",
    "shouqianba_baudrate": 2400,
    "shouqianba_format": "QA",
    "shouqianba_hotkey": "Shift+Q",

    # 4. 外卖排序与中继配置 (takeout.json)
    "takeout_interceptor_enabled": True,
    "takeout_categories": [
        {"id": "cat_1", "name": u"主食类", "keywords": [u"面", u"米饭", u"粉丝", u"年糕", u"方便面"]},
        {"id": "cat_2", "name": u"肉类", "keywords": [u"牛肉", u"肥牛", u"羊肉", u"鸡肉", u"培根", u"火腿", u"肉丸"]},
        {"id": "cat_3", "name": u"海鲜类", "keywords": [u"虾", u"蟹棒", u"鱼丸", u"鱿鱼", u"巴沙鱼"]},
        {"id": "cat_4", "name": u"蔬菜类", "keywords": [u"白菜", u"菠菜", u"金针菇", u"土豆", u"藕片", u"生菜", u"西兰花"]},
        {"id": "cat_5", "name": u"豆制品类", "keywords": [u"豆腐", u"腐竹", u"豆皮", u"豆干"]},
        {"id": "cat_6", "name": u"饮料酒水", "keywords": [u"可乐", u"雪碧", u"王老吉", u"酸梅汤", u"矿泉水"]}
    ],
    "takeout_match_mode": "contains",
    "takeout_font_hdr": 1,
    "takeout_font_cat": 1,
    "takeout_font_item": 1,
    "takeout_mark_star": True,
    "takeout_show_prices": False,
    "takeout_kitchen_copies": 1,
    "takeout_cust_copies": 0,
    "takeout_show_address": True,
    "takeout_show_time": True,
    "takeout_show_full_id": False,
    "takeout_show_preorder": True,
}

# Key 属于哪个模块文件的映射规则
MODULAR_KEYS = {
    "takeout": lambda k: k.startswith("takeout_"),
    "algo": lambda k: k in ("private_ratio_percent", "min_private_weight_kg"),
    "shouqianba": lambda k: k.startswith("shouqianba_"),
}

def _get_module_name(key: str) -> str:
    for mod, check_fn in MODULAR_KEYS.items():
        if check_fn(key):
            return mod
    return "sys"


def load_config() -> dict:
    """从模板、data/settings/ 模块化 JSON 文件以及 settings.json 中加载并合并配置"""
    base_defaults = DEFAULT_CONFIG.copy()

    # 1. 检查 template 模板
    if os.path.exists(TEMPLATE_FILE):
        try:
            with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
                template_data = json.load(f)
                base_defaults.update(template_data)
        except Exception:
            pass

    merged = base_defaults.copy()

    # 2. 读取旧的 data/settings.json (优先覆盖)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                merged.update(saved)
        except Exception:
            pass

    # 3. 读取拆分后的 data/settings/*.json (模块化覆盖)
    for mod, path in MODULE_FILES.items():
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    mod_data = json.load(f)
                    merged.update(mod_data)
            except Exception:
                pass

    merged.pop("simulation_mode", None)
    
    # 自动保存/同步拆分文件
    save_config(merged)
    return merged


def save_config(cfg: dict):
    """保存配置：同步更新 data/settings.json 以及 data/settings/ 下各个模块化文件"""
    cfg.pop("simulation_mode", None)

    # 1. 保存总的 data/settings.json (保留兼容性)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 2. 按模块拆分保存到 data/settings/*.json
    module_buckets = {"sys": {}, "takeout": {}, "algo": {}, "shouqianba": {}}
    for k, v in cfg.items():
        mod = _get_module_name(k)
        module_buckets[mod][k] = v

    for mod, bucket in module_buckets.items():
        filepath = MODULE_FILES[mod]
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(bucket, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def reset_module_config(cfg: dict, module_name: str) -> dict:
    """还原指定模块的配置为出厂默认值"""
    for k, v in DEFAULT_CONFIG.items():
        if _get_module_name(k) == module_name:
            cfg[k] = v
    save_config(cfg)
    return cfg


def export_config_bundle(cfg: dict, target_file_path: str):
    """导出配置包（支持 Zip 打包或 JSON 格式）"""
    save_config(cfg)
    if target_file_path.endswith(".zip"):
        with zipfile.ZipFile(target_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 写入主配置文件
            if os.path.exists(CONFIG_FILE):
                zipf.write(CONFIG_FILE, arcname="settings.json")
            # 写入模块化目录
            for mod, path in MODULE_FILES.items():
                if os.path.exists(path):
                    zipf.write(path, arcname=f"settings/{os.path.basename(path)}")
    else:
        with open(target_file_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


def import_config_bundle(file_path: str) -> dict:
    """导入配置包，还原并合并 settings"""
    if file_path.endswith(".zip"):
        with zipfile.ZipFile(file_path, 'r') as zipf:
            zipf.extractall(DATA_DIR)
        return load_config()
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            imported = json.load(f)
        current = load_config()
        current.update(imported)
        save_config(current)
        return current
