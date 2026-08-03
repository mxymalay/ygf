"""
杨国福麻辣烫 · 独立称重打印系统 — 全局配置
支持模块化数据存储 (data/settings/ 目录下拆分存储)
"""
import os
import json
import shutil
import zipfile
import sys
import copy
from datetime import datetime

# ─── 应用版本号 ───────────────────────────────────────
APP_VERSION = "v1.2.0"
CONFIG_SCHEMA_VERSION = 2

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
    # COM 模式再区分“直接独占物理秤”和“使用 ScaleBridge 虚拟端口”。
    # 旧配置没有该字段时按 direct 兼容。
    "scale_connection_mode": "direct",
    "scale_port": "COM2",
    "scale_baudrate": 9600,
    # 官方 POS 升级后可在设置页选择新的 serial 日志目录；留空时仅尝试
    # 兼容的历史路径和受限自动发现，不会每秒扫描整块硬盘。
    "official_pos_log_dir": "",
    "config_schema_version": CONFIG_SCHEMA_VERSION,

    # 2. 切换算法配置 (algo.json)
    "private_ratio_percent": 30,
    "min_private_weight_kg": 0.25,

    # 3. 收钱吧配置 (shouqianba.json)
    "shouqianba_enabled": True,
    # managed: 由本系统创建并维护一对虚拟串口；existing: 使用现场已有配对。
    "shouqianba_pair_mode": "managed",
    # 店内当前默认值；设置页可随时改为任意可用 COM 口。
    "shouqianba_port": "COM10",
    # 收钱吧插件监听端；与 shouqianba_port 是同一虚拟串口配对的两端。
    "shouqianba_plugin_port": "COM11",
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


def _atomic_json_write(filepath: str, data: dict):
    """Never leave a half-written configuration file after a power loss."""
    directory = os.path.dirname(filepath)
    os.makedirs(directory, exist_ok=True)
    temporary = filepath + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, filepath)


def _backup_paths(paths, reason="config"):
    existing = [path for path in paths if os.path.isfile(path)]
    if not existing:
        return ""
    backup_dir = os.path.join(DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(backup_dir, "%s_%s.zip" % (reason, stamp))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in existing:
            archive.write(path, arcname=os.path.join("settings", os.path.basename(path)))
    return target


def backup_config_bundle(reason="manual"):
    """Create a recoverable snapshot before import or reset."""
    return _backup_paths(list(MODULE_FILES.values()) + [CONFIG_FILE], reason)


def _load_json_object(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        if not isinstance(value, dict):
            raise ValueError("根节点必须是对象")
        return value
    except Exception as exc:
        # Do not silently overwrite a malformed store configuration.  Keep an
        # exact copy for recovery, then continue with defaults.
        backup_dir = os.path.join(DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = os.path.join(backup_dir, "%s_corrupt_%s.json" % (label, stamp))
        try:
            shutil.copy2(path, backup)
        except Exception:
            backup = ""
        print("[配置 Warning] 无法读取 %s: %s%s" % (
            path, exc, ("，已备份到 " + backup) if backup else ""
        ))
        return None


def load_config() -> dict:
    """从模板、旧版大 settings.json 以及 data/settings/ 拆分模块文件中加载配置
    若检测到旧版 settings.json，将自动拆分并迁移至 data/settings/ 下各模块 JSON 文件
    """
    base_defaults = copy.deepcopy(DEFAULT_CONFIG)

    # 1. 检查 template 模板
    if os.path.exists(TEMPLATE_FILE):
        template_data = _load_json_object(TEMPLATE_FILE, "template")
        if template_data:
            base_defaults.update(template_data)

    merged = base_defaults.copy()
    has_legacy_config = os.path.exists(CONFIG_FILE)

    # 2. 读取旧的 data/settings.json (包含历史全量配置)
    if has_legacy_config:
        saved = _load_json_object(CONFIG_FILE, "legacy")
        if saved:
            merged.update(saved)

    # 3. 读取拆分后的 data/settings/*.json (模块化文件覆盖)
    for mod, path in MODULE_FILES.items():
        if os.path.exists(path):
            mod_data = _load_json_object(path, mod)
            if mod_data:
                merged.update(mod_data)

    merged.pop("simulation_mode", None)
    # 模拟模式是一次运行的临时状态，绝不能写入正式门店配置。
    merged.pop("is_mock_mode", None)
    merged["config_schema_version"] = CONFIG_SCHEMA_VERSION

    # 4. 自动拆分并同步写回 data/settings/ 目录下各个模块文件 (自动迁移逻辑)
    save_config(merged)

    # 5. 若存在旧版 settings.json 大文件，完成迁移后自动删除清理
    if has_legacy_config:
        try:
            backup = _backup_paths([CONFIG_FILE], "legacy_migration")
            os.remove(CONFIG_FILE)
            print(f"[配置迁移] 已迁移旧配置并保留备份: {backup or '未生成'}")
        except Exception as e:
            print(f"[配置迁移 Warning] 物理删除旧配置文件失败: {e}")

    return merged


def save_config(cfg: dict):
    """保存配置：按模块拆分保存到 data/settings/*.json 文件"""
    cfg.pop("simulation_mode", None)
    cfg.pop("is_mock_mode", None)
    cfg["config_schema_version"] = CONFIG_SCHEMA_VERSION

    # 按模块拆分保存到 data/settings/*.json
    module_buckets = {"sys": {}, "takeout": {}, "algo": {}, "shouqianba": {}}
    for k, v in cfg.items():
        mod = _get_module_name(k)
        module_buckets[mod][k] = v

    for mod, bucket in module_buckets.items():
        filepath = MODULE_FILES[mod]
        _atomic_json_write(filepath, bucket)


def reset_module_config(cfg: dict, module_name: str) -> dict:
    """还原指定模块的配置为出厂默认值"""
    for k, v in DEFAULT_CONFIG.items():
        if _get_module_name(k) == module_name:
            cfg[k] = copy.deepcopy(v)
    save_config(cfg)
    return cfg


def reset_all_config(cfg: dict) -> dict:
    """Restore all modular settings while retaining a dated backup bundle."""
    backup_config_bundle("before_factory_reset")
    cfg.clear()
    cfg.update(copy.deepcopy(DEFAULT_CONFIG))
    save_config(cfg)
    return cfg


def export_config_bundle(cfg: dict, target_file_path: str):
    """导出配置包（支持 Zip 打包或 JSON 格式）"""
    save_config(cfg)
    if target_file_path.endswith(".zip"):
        with zipfile.ZipFile(target_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 写入模块化目录
            for mod, path in MODULE_FILES.items():
                if os.path.exists(path):
                    zipf.write(path, arcname=f"settings/{os.path.basename(path)}")
    else:
        _atomic_json_write(target_file_path, cfg)


def import_config_bundle(file_path: str) -> dict:
    """导入配置包，还原并合并 settings"""
    if file_path.endswith(".zip"):
        with zipfile.ZipFile(file_path, 'r') as zipf:
            allowed = {
                "settings/base.json": "sys",
                "settings/takeout.json": "takeout",
                "settings/algo.json": "algo",
                "settings/shouqianba.json": "shouqianba",
            }
            names = set(zipf.namelist())
            unknown = [name for name in names if name.rstrip("/") and name not in allowed]
            if unknown:
                raise ValueError("配置包包含不允许的文件：%s" % ", ".join(unknown[:3]))
            if not names.intersection(allowed):
                raise ValueError("配置包中没有可识别的 settings/*.json")
            imported = {}
            for archive_name in names.intersection(allowed):
                raw = zipf.read(archive_name).decode("utf-8")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("%s 不是有效配置对象" % archive_name)
                imported.update(value)
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            imported = json.load(f)
        if not isinstance(imported, dict):
            raise ValueError("配置文件根节点必须是对象")
    backup_config_bundle("before_import")
    current = load_config()
    current.update(imported)
    current.pop("is_mock_mode", None)
    save_config(current)
    return current
