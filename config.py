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
import tempfile
import time
from datetime import datetime

# ─── 应用版本号 ───────────────────────────────────────
APP_VERSION = "v2.0.0"
CONFIG_SCHEMA_VERSION = 3

# ─── 路径 ───────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_DIR = os.path.join(DATA_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)

# 可由店员在系统设置中选择的应用 Logo。配置只保存稳定的 preset id，
# 不保存开发机绝对路径，这样复制到另一台收银机或打包成 exe 后仍能使用。
APP_LOGO_PRESETS = {
    "yangguofu": (u"内置杨国福", "app_logo_yangguofu.png"),
    "netease_music": (u"网易云音乐", "app_logo_netease_music.png"),
    "windows": (u"Windows", "app_logo_windows.png"),
    "qq_penguin": (u"QQ 企鹅", "app_logo_qq_penguin.png"),
    "dollar": (u"美元", "app_logo_dollar.png"),
    "settings_gears": (u"蓝色齿轮", "app_logo_settings_gears.png"),
    "red_music_note": (u"红色音符", "app_logo_red_music_note.png"),
    "gold_blue_mark": (u"蓝金图标", "app_logo_gold_blue_mark.png"),
    "green_dollar": (u"绿色美元", "app_logo_green_dollar.png"),
    "instagram": (u"Instagram", "app_logo_instagram.png"),
    "google": (u"Google", "app_logo_google.png"),
    "alert": (u"警告", "app_logo_alert.png"),
    "coca_cola": (u"可口可乐", "app_logo_coca_cola.png"),
}

# The shortcut icon also identifies the kind of tool being installed.  Keep
# the wording in one place so the installer, settings page and password/login
# screen always agree.  The list is intentionally longer than the bundled
# icon list: custom uploaded icons can use any of these categories.
APP_CATEGORY_OPTIONS = {
    "pos": (u"POS / 收银", u"POS 辅助系统", u"POS Auxiliary System Environment Check"),
    "music": (u"音乐", u"音乐管理助手", u"Music Management Assistant"),
    "driver": (u"驱动", u"硬件驱动配置向导", u"Hardware Driver Setup Wizard"),
    "browser": (u"浏览器", u"浏览器应用中心", u"Browser Application Center"),
    "google": (u"Google", u"Google 服务助手", u"Google Services Assistant"),
    "social": (u"社交", u"社交应用助手", u"Social Application Assistant"),
    "finance": (u"财务", u"财务管理助手", u"Finance Management Assistant"),
    "shopping": (u"购物", u"购物订单助手", u"Shopping Order Assistant"),
    "video": (u"视频", u"视频媒体中心", u"Video Media Center"),
    "game": (u"游戏", u"游戏平台启动器", u"Game Platform Launcher"),
    "cloud": (u"云端", u"云端同步助手", u"Cloud Sync Assistant"),
    "communication": (u"通讯", u"通讯消息助手", u"Communication Assistant"),
    "security": (u"安全", u"安全登录中心", u"Security Login Center"),
    "settings": (u"设置", u"系统设置中心", u"System Settings Center"),
    "food": (u"餐饮", u"餐饮运营助手", u"Food Service Operations Assistant"),
    "tools": (u"工具", u"实用工具箱", u"Utility Toolbox"),
    "education": (u"教育", u"学习资料助手", u"Learning Materials Assistant"),
    "custom": (u"自定义", u"自定义应用助手", u"Custom Application Assistant"),
}

APP_ICON_CATEGORY = {
    "yangguofu": "pos",
    "netease_music": "music",
    "windows": "driver",
    "qq_penguin": "social",
    "dollar": "finance",
    "settings_gears": "settings",
    "red_music_note": "music",
    "gold_blue_mark": "pos",
    "green_dollar": "finance",
    "instagram": "social",
    "google": "google",
    "alert": "security",
    "coca_cola": "food",
    "custom": "custom",
}


def app_category_for_icon(icon_id):
    """Return the default category associated with a shortcut icon id."""
    return APP_ICON_CATEGORY.get(str(icon_id or ""), "pos")


def app_branding(config=None):
    """Return login-screen wording for the configured shortcut category."""
    config = config or {}
    category_id = str(config.get("app_category") or "").strip()
    if category_id not in APP_CATEGORY_OPTIONS:
        category_id = app_category_for_icon(
            config.get("shortcut_icon_preset") or config.get("app_logo_preset")
        )
    short_label, title, subtitle = APP_CATEGORY_OPTIONS.get(
        category_id, APP_CATEGORY_OPTIONS["pos"]
    )
    return {
        "category_id": category_id,
        "category_label": short_label,
        "login_title": title,
        "login_subtitle": subtitle,
    }


def app_logo_path(preset_id):
    """Resolve a bundled application Logo preset to an absolute asset path."""
    item = APP_LOGO_PRESETS.get(str(preset_id or "yangguofu"))
    if not item:
        item = APP_LOGO_PRESETS["yangguofu"]
    return os.path.join(DATA_DIR, "assets", item[1])

# 拆分后的模块化配置文件目录 data/settings/
SETTINGS_DIR = os.path.join(DATA_DIR, "settings")
os.makedirs(SETTINGS_DIR, exist_ok=True)

DB_PATH = os.path.join(DB_DIR, "sales.db")
LEGACY_DB_PATH = os.path.join(DATA_DIR, "sales.db")
CONFIG_FILE = os.path.join(DATA_DIR, "settings.json")
TEMPLATE_FILE = os.path.join(DATA_DIR, "settings.json.template")

# 模块化 JSON 文件路径
MODULE_FILES = {
    "sys": os.path.join(SETTINGS_DIR, "base.json"),
    "printer_relay": os.path.join(SETTINGS_DIR, "printer_relay.json"),
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
    # ESC/POS 排版：历史模板固定使用 48 列（更接近 80mm 纸），保留
    # 该默认值以免升级后旧门店出现突然折行；58mm 常用 32 列可在设置页选择。
    "printer_paper_width_mm": 80,
    "printer_chars_per_line": 48,
    "printer_customer_enabled": True,
    "printer_customer_copies": 1,
    "printer_kitchen_enabled": True,
    "printer_kitchen_copies": 1,
    "printer_report_enabled": True,
    "printer_report_copies": 1,
    "printer_auto_cut_enabled": True,
    "printer_feed_lines": 4,
    "printer_cash_drawer_enabled": True,
    "printer_show_tags": True,
    "printer_packaging_banner_enabled": True,
    "printer_packaging_banner_lines": 3,
    "printer_separator_char": "-",
    "printer_customer_title": "POS点餐 堂食",
    "printer_kitchen_title_dinein": "制作单-堂食",
    "printer_kitchen_title_packaging": "制作单-打包",
    "printer_customer_footer": "打印时间：{time}",
    "printer_kitchen_footer": "打印时间：{time}",
    "printer_report_title": "营业汇总报表",
    "printer_report_footer": "打印时间：{time}",
    # 模板方案：legacy 是官方旧版参考模仿，official_v2 是官方新版参考模仿，
    # official_v3 使用从官方原始 ESC/POS 小票提取的精确格式，custom 使用
    # 设置页中的可编辑正文，便于以后换版时无需改程序。
    # 新安装默认使用官方新版格式；已有配置中的 legacy/custom 值会被
    # 原样保留，不在升级时静默覆盖。
    "printer_template_profile": "official_v3",
    "printer_service_phone": "400-6058-777",
    "printer_operator": "",
    "printer_logo_path": "",
    "printer_logo_enabled": True,
    # Official/reference and custom ticket parameters are deliberately kept
    # separate.  The older shared keys above remain as upgrade fallbacks.
    "printer_official_logo_enabled": True,
    "printer_official_service_phone": "400-6058-777",
    "printer_official_operator": "",
    "printer_custom_logo_enabled": True,
    "printer_custom_logo_path": "",
    "printer_custom_service_phone": "400-6058-777",
    "printer_custom_operator": "",
    "printer_logo_width_px": 512,
    "app_logo_preset": "yangguofu",
    "shortcut_icon_preset": "yangguofu",
    "app_category": "pos",
    "custom_shortcut_icon_path": "",
    "custom_shortcut_icon_label": "",
    "printer_customer_template_custom": "",
    "printer_kitchen_template_custom": "",
    "unit_price": 47.60,
    "special_soup_price": 50.00,
    "price_unit": "per_kg",
    # 店铺点菜区的分类/SKU。空列表表示沿用内置默认目录，首次在
    # “商品与分类”页面保存后写入自定义目录。
    "shop_sku_categories": [],
    "shop_name": u"杨国福麻辣烫",
    "shop_subtitle": u"杨国福(测试店)",
    "is_first_run": True,
    "auto_print": False,
    "stable_threshold": 0.01,
    "stable_count": 5,
    # 放碗仍按 stable_count 做完整稳定采样；取碗只需两个连续零读数
    # 即可解锁下一碗，避免高峰期快速换客错过归零窗口。
    "zero_stable_count": 2,
    "scale_zero_threshold_kg": 0.005,
    "scale_max_weight_kg": 15.0,
    "scale_stale_timeout_sec": 3.0,
    "auto_start_enabled": True,
    "auto_start_delay": 8,
    "auto_switch_enabled": True,
    "floating_ball_enabled": True,
    # 用户拖动悬浮球后保存的屏幕坐标；为空时使用销售页右上角默认位置。
    "floating_ball_position": None,
    "panic_hotkey": "F10",
    "auto_hide_delay_sec": 10,
    "scale_source": "official",
    # COM 模式再区分“直接独占物理秤”和“使用 ScaleBridge 虚拟端口”。
    # 旧配置没有该字段时按 direct 兼容。
    "scale_connection_mode": "direct",
    "scale_port": "COM2",
    "scale_baudrate": 9600,
    # 门店现场提醒（均可在系统设置中关闭或调整）。
    "low_price_warning_enabled": True,
    "low_price_warning_threshold": 15.00,
    "packing_reminder_enabled": True,
    "skewer_reminder_enabled": True,
    # 官方 POS 升级后可在设置页选择新的 serial 日志目录；留空时仅尝试
    # 兼容的历史路径和受限自动发现，不会每秒扫描整块硬盘。
    "official_pos_log_dir": "",
    # Official POS identity is selected by the operator.  Generic historical
    # defaults are intentionally not treated as a valid selection because the
    # window identity controls both startup checks and foreground switching.
    "official_pos_window_configured": False,
    "official_pos_window_title": "",
    "official_pos_window_class": "",
    "official_pos_process_name": "",
    "official_pos_process_keywords": [],
    "official_pos_window_keywords": [],
    "config_schema_version": CONFIG_SCHEMA_VERSION,

    # 2. 切换算法配置 (algo.json)
    "private_ratio_percent": 30,
    # Enhanced mode uses verified revenue and keeps an independent target;
    # defaulting to the legacy weight ratio preserves existing behavior.
    "private_amount_ratio_percent": 30,
    # Hysteresis around the target ratio prevents rapid back-and-forth
    # switching.  The settings slider exposes 0% (fastest) to 30% (slowest).
    "switch_hysteresis_percent": 10,
    "min_private_weight_kg": 0.25,
    # 私域 POS 当日累计收款上限。周一至周四、周五、周六、周日分别设置；
    # 旧的周中/周末键和 max_daily_revenue_limit 继续作为迁移兼容别名。
    "mon_thu_max_daily_revenue_limit": 500.0,
    "friday_max_daily_revenue_limit": 500.0,
    "saturday_max_daily_revenue_limit": 1000.0,
    "sunday_max_daily_revenue_limit": 1000.0,
    "weekday_max_daily_revenue_limit": 500.0,
    "weekend_max_daily_revenue_limit": 1000.0,

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
    # 可填写 smskv3 根目录或具体 v版本目录；留空时运行期自动扫描。
    "shouqianba_install_dir": "",

    # 4. 官方 POS 打印中继与订单识别配置 (printer_relay.json)
    # 默认关闭：必须先把官方 POS 打印机改为本机 TCP 中继队列后才启用。
    "printer_relay_enabled": False,
    "printer_relay_port": 9101,
    "printer_relay_queue_name": "",
    "printer_relay_mode_version": 1,
    # Relay health/mode is persisted as a diagnostic hint only.  Any stale or
    # missing value is treated as compatibility mode at runtime.
    "printer_relay_mode": "compatibility",
    # Automatic mode is safe default; force_compatibility is a manual
    # maintenance/test override and never enables enhanced routing by itself.
    "printer_relay_mode_policy": "auto",
    "printer_relay_last_check_at": "",
    "printer_relay_last_success_at": "",
    "printer_relay_last_error": "",
    "printer_relay_last_identification": "",
    "printer_relay_payment_required": True,
    # Official POS receipt field aliases.  Empty/custom values are optional;
    # parser defaults remain active for old configurations.
    "official_pos_field_mapping": {
        "order_id_labels": ["订单号", "订单编号"],
        "amount_labels": ["实付", "实收", "支付金额", "付款金额", "应付", "应收", "合计", "总计", "原价合计"],
        "paid_keywords": ["支付成功", "付款成功", "收款成功", "交易成功", "已支付", "已付款", "已结账", "结账成功", "支付状态:成功"],
        "cancelled_keywords": ["已取消", "取消订单", "退款成功", "已退款"],
        "dinein_keywords": ["堂食", "POS点餐", "收银", "消费小票", "结账单", "制作单-堂食"],
    },
    # Keep a bounded copy of official POS printer samples for test-machine
    # format analysis.  Samples may contain order details; disable after use.
    "printer_relay_capture_enabled": False,
    "printer_relay_capture_max_files": 20,
    "printer_relay_capture_max_bytes": 2097152,
    "printer_relay_auto_print": True,
    "printer_relay_categories": [
        {"id": "cat_1", "name": u"主食类", "keywords": [u"面", u"米饭", u"粉丝", u"年糕", u"方便面"]},
        {"id": "cat_2", "name": u"肉类", "keywords": [u"牛肉", u"肥牛", u"羊肉", u"鸡肉", u"培根", u"火腿", u"肉丸"]},
        {"id": "cat_3", "name": u"海鲜类", "keywords": [u"虾", u"蟹棒", u"鱼丸", u"鱿鱼", u"巴沙鱼"]},
        {"id": "cat_4", "name": u"蔬菜类", "keywords": [u"白菜", u"菠菜", u"金针菇", u"土豆", u"藕片", u"生菜", u"西兰花"]},
        {"id": "cat_5", "name": u"豆制品类", "keywords": [u"豆腐", u"腐竹", u"豆皮", u"豆干"]},
        {"id": "cat_6", "name": u"饮料酒水", "keywords": [u"可乐", u"雪碧", u"王老吉", u"酸梅汤", u"矿泉水"]}
    ],
    "printer_relay_match_mode": "contains",
    "printer_relay_font_hdr": 1,
    "printer_relay_font_cat": 1,
    "printer_relay_font_item": 1,
    "printer_relay_mark_star": True,
    "printer_relay_show_prices": False,
    "printer_relay_kitchen_copies": 1,
    "printer_relay_cust_copies": 0,
    "printer_relay_show_address": True,
    "printer_relay_show_time": True,
    "printer_relay_show_full_id": False,
    "printer_relay_show_preorder": True,
}

# These settings are written by older pages/runtime helpers but are not part
# of the factory defaults above.  Keep them in the migration allow-list so a
# legacy store does not lose queue/switch settings merely because the current
# UI only exposes them on a secondary page.  Anything outside this set is
# treated as an obsolete/foreign field and is deliberately discarded when the
# modular files are rewritten.
OPTIONAL_CONFIG_KEYS = {
    # Runtime diagnostics and operator-defined field aliases maintained by
    # the printer-relay page.  They are intentionally persisted in the
    # canonical printer_relay namespace, not under the former takeout name.
    "printer_relay_capture_dir",
    "printer_relay_field_mapping",
    "printer_relay_pos_field_mapping",
    "printer_relay_mode_changed_at",
    "printer_relay_mode_reason",
    "call_used_numbers",
    "call_last_slot",
    "call_manual_no",
    "call_seq_no",
    "call_last_issued_no",
    "call_recent_numbers",
    "call_pool_date",
    "call_mode",
    "custom_is_seq",
    "custom_start_no",
    "custom_end_no",
    "max_daily_revenue_limit",
    "mon_thu_max_daily_revenue_limit",
    "friday_max_daily_revenue_limit",
    "saturday_max_daily_revenue_limit",
    "sunday_max_daily_revenue_limit",
    "weekday_max_daily_revenue_limit",
    "weekend_max_daily_revenue_limit",
    "min_valid_weight_kg",
    "official_lock_sec",
    "manual_override_lock_sec",
    # Legacy alias used by the first soup-pricing screen.  It is migrated to
    # special_soup_price and is never written back under the old name.
    "soup_price_4",
}

TRANSIENT_CONFIG_KEYS = {"simulation_mode", "is_mock_mode"}

KNOWN_CONFIG_KEYS = frozenset(DEFAULT_CONFIG).union(OPTIONAL_CONFIG_KEYS)

# Key 属于哪个模块文件的映射规则
MODULAR_KEYS = {
    "printer_relay": lambda k: k.startswith("printer_relay_"),
    "algo": lambda k: k in (
        "private_ratio_percent", "private_amount_ratio_percent", "min_private_weight_kg",
        "switch_hysteresis_percent",
        "max_daily_revenue_limit",
        "mon_thu_max_daily_revenue_limit", "friday_max_daily_revenue_limit",
        "saturday_max_daily_revenue_limit", "sunday_max_daily_revenue_limit",
        "weekday_max_daily_revenue_limit", "weekend_max_daily_revenue_limit",
    ),
    "shouqianba": lambda k: k.startswith("shouqianba_"),
}

def _get_module_name(key: str) -> str:
    for mod, check_fn in MODULAR_KEYS.items():
        if check_fn(key):
            return mod
    return "sys"


def _known_config_only(value):
    """Return a shallow copy containing only supported persisted settings."""
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for key, item in value.items():
        if key in TRANSIENT_CONFIG_KEYS:
            continue
        if key in KNOWN_CONFIG_KEYS:
            cleaned[key] = item
    if "soup_price_4" in cleaned:
        cleaned.setdefault("special_soup_price", cleaned["soup_price_4"])
        cleaned.pop("soup_price_4", None)
    return cleaned


def _atomic_json_write(filepath: str, data: dict):
    """Write JSON atomically even when POS and relay processes save together.

    The old implementation always used ``filepath + '.tmp'``.  The main POS
    and detached relay can both call ``save_config`` at the same time; on
    Windows that made the second writer truncate/hold the same temporary file
    and the first ``os.replace`` failed with WinError 32.  A unique temporary
    name removes that collision.  A short retry also covers antivirus/indexer
    handles or a concurrent replacement of the destination file.
    """
    directory = os.path.dirname(filepath)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=os.path.basename(filepath) + ".",
        suffix=".tmp",
        dir=directory,
    )
    os.close(fd)
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        last_error = None
        for attempt in range(8):
            try:
                os.replace(temporary, filepath)
                return
            except OSError as exc:
                last_error = exc
                if attempt >= 7:
                    raise
                time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def migrate_legacy_database():
    """Move the old root-level SQLite file into ``data/db`` exactly once.

    This migration is intentionally independent from configuration choices:
    rebuilding/keeping settings never backs up, deletes, or recreates the
    sales database.  If a new database already exists, the old one is left
    untouched for manual recovery rather than risking an overwrite.
    """
    if os.path.abspath(DB_PATH) == os.path.abspath(LEGACY_DB_PATH):
        return False
    suffixes = ("", "-wal", "-shm")
    old_files = [LEGACY_DB_PATH + suffix for suffix in suffixes if os.path.exists(LEGACY_DB_PATH + suffix)]
    if not old_files or any(os.path.exists(DB_PATH + suffix) for suffix in suffixes):
        return False
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    moved = False
    try:
        for source in old_files:
            target = DB_PATH + source[len(LEGACY_DB_PATH):]
            shutil.move(source, target)
            moved = True
    except OSError as exc:
        print("[数据库迁移 Warning] 无法将旧数据库移动到 %s: %s" % (DB_PATH, exc))
    return moved


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


def detect_legacy_config():
    """Return a read-only snapshot used by the first-run migration dialog."""
    if not os.path.isfile(CONFIG_FILE):
        return None
    items = {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            items = _known_config_only(raw)
    except (OSError, TypeError, ValueError):
        # The migration dialog can still offer rebuild/automatic recovery for
        # a malformed legacy file; it must not crash before the UI appears.
        items = {}
    return {
        "path": CONFIG_FILE,
        "items": items,
        "valid": bool(items),
    }


def _remove_config_files():
    paths = [CONFIG_FILE] + list(MODULE_FILES.values())
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            print("[配置迁移 Warning] 无法删除旧配置 %s: %s" % (path, exc))


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


def load_config(migration_policy="auto", selected_keys=None) -> dict:
    """Load settings and apply the requested legacy migration policy.

    ``auto`` preserves the historical behaviour for non-GUI callers.  The
    main POS startup shows a touch migration dialog first and passes either
    ``rebuild``, ``selective`` or ``auto`` with the selected field names.
    """
    policies = {"auto", "rebuild", "selective"}
    if migration_policy not in policies:
        raise ValueError("未知配置迁移策略: %s" % migration_policy)
    migrate_legacy_database()
    base_defaults = copy.deepcopy(DEFAULT_CONFIG)

    # 1. 检查 template 模板
    if os.path.exists(TEMPLATE_FILE):
        template_data = _load_json_object(TEMPLATE_FILE, "template")
        if template_data:
            base_defaults.update(_known_config_only(template_data))

    merged = base_defaults.copy()
    has_legacy_config = os.path.exists(CONFIG_FILE)
    legacy_backup = ""

    if has_legacy_config and migration_policy in ("rebuild", "selective", "auto"):
        legacy_backup = backup_config_bundle(
            "before_rebuild" if migration_policy == "rebuild" else "legacy_migration"
        )

    if has_legacy_config and migration_policy == "rebuild":
        # Rebuild only settings files.  The database relocation above is the
        # sole database operation and never archives/deletes sales data.
        _remove_config_files()
        has_legacy_config = False

    # 2. 读取旧的 data/settings.json (包含历史全量配置)
    legacy_values = {}
    if has_legacy_config:
        saved = _load_json_object(CONFIG_FILE, "legacy")
        if saved:
            legacy_values = _known_config_only(saved)

    # 3. 读取拆分后的 data/settings/*.json (模块化文件覆盖)
    module_values = {}
    for mod, path in MODULE_FILES.items():
        if os.path.exists(path):
            mod_data = _load_json_object(path, mod)
            if mod_data:
                module_values.update(_known_config_only(mod_data))
    if migration_policy == "auto":
        merged.update(legacy_values)
        # Existing split files are the newer source of truth when both old
        # and new stores are present.
        merged.update(module_values)
    elif migration_policy == "selective":
        merged.update(module_values)
        selected = set(selected_keys or ())
        merged.update({key: value for key, value in legacy_values.items() if key in selected})
    else:
        # Rebuild deliberately ignores both legacy and existing module values.
        pass

    # 将旧的单一上限或周中/周末上限拆分到新的四个星期分组，避免
    # DEFAULT_CONFIG 的新默认值悄悄覆盖门店原有的限额。
    source_values = dict(legacy_values)
    source_values.update(module_values)
    legacy_single = source_values.get("max_daily_revenue_limit", 500.0)
    legacy_weekday = source_values.get("weekday_max_daily_revenue_limit", legacy_single)
    legacy_weekend = source_values.get(
        "weekend_max_daily_revenue_limit",
        legacy_single if "max_daily_revenue_limit" in source_values else 1000.0,
    )
    legacy_split = {
        "mon_thu_max_daily_revenue_limit": legacy_weekday,
        "friday_max_daily_revenue_limit": legacy_weekday,
        "saturday_max_daily_revenue_limit": legacy_weekend,
        "sunday_max_daily_revenue_limit": legacy_weekend,
    }
    for key, value in legacy_split.items():
        if key not in source_values:
            merged[key] = value
    if "max_daily_revenue_limit" in source_values:
        if "weekday_max_daily_revenue_limit" not in source_values:
            merged["weekday_max_daily_revenue_limit"] = legacy_weekday
        if "weekend_max_daily_revenue_limit" not in source_values:
            merged["weekend_max_daily_revenue_limit"] = legacy_weekend

    # 模拟模式是一次运行的临时状态，绝不能写入正式门店配置。
    for key in TRANSIENT_CONFIG_KEYS:
        merged.pop(key, None)

    # v2 stored broad guessed keywords.  They were acceptable for log-path
    # compatibility but are unsafe for window switching; require one explicit
    # operator selection after upgrading to v3.
    legacy_window_keywords = ["杨国福", "官方收银", "店长端", "餐饮管理"]
    legacy_process_keywords = ["yangguofu.exe", "ygf-pos.exe", "ygf.exe"]
    if not merged.get("official_pos_window_configured"):
        if merged.get("official_pos_window_keywords") == legacy_window_keywords:
            merged["official_pos_window_keywords"] = []
        if merged.get("official_pos_process_keywords") == legacy_process_keywords:
            merged["official_pos_process_keywords"] = []
        merged["official_pos_window_title"] = ""
        merged["official_pos_window_class"] = ""
        merged["official_pos_process_name"] = ""
    # Before v1.2 the same flag only controlled a non-functional preview
    # thread.  Never reinterpret an old "enabled" value as permission to
    # start a real local printer proxy after upgrade.
    try:
        printer_relay_mode_version = int(merged.get("printer_relay_mode_version", 0) or 0)
    except (TypeError, ValueError):
        printer_relay_mode_version = 0
    if printer_relay_mode_version < 1:
        merged["printer_relay_enabled"] = False
        merged["printer_relay_mode_version"] = 1
    merged["config_schema_version"] = CONFIG_SCHEMA_VERSION

    # 4. 拆分并同步写回 data/settings/ 目录下各个模块文件
    save_config(merged)

    # 5. 若存在旧版 settings.json 大文件，完成迁移后删除清理
    if os.path.exists(CONFIG_FILE):
        try:
            os.remove(CONFIG_FILE)
            print(f"[配置迁移] 已应用 {migration_policy} 策略，旧配置已备份: {legacy_backup or '未生成'}")
        except Exception as e:
            print(f"[配置迁移 Warning] 物理删除旧配置文件失败: {e}")

    return merged


def save_config(cfg: dict):
    """保存配置：按模块拆分保存到 data/settings/*.json 文件"""
    # Do not let a stale widget/plugin key leak into the new modular files.
    # Keep the caller's dictionary in sync for foreign/legacy fields, but
    # preserve transient runtime flags.  The same dictionary is shared by the
    # running UI; removing ``is_mock_mode`` during an unrelated settings save
    # used to silently switch the sales page to real-scale mode mid-session.
    transient_values = {
        key: cfg[key] for key in TRANSIENT_CONFIG_KEYS if key in cfg
    }
    if "soup_price_4" in cfg:
        cfg.setdefault("special_soup_price", cfg["soup_price_4"])
        cfg.pop("soup_price_4", None)
    for key in list(cfg):
        if key not in KNOWN_CONFIG_KEYS or key in TRANSIENT_CONFIG_KEYS:
            cfg.pop(key, None)
    cfg.update(transient_values)
    cfg["config_schema_version"] = CONFIG_SCHEMA_VERSION
    persisted = {}
    for key, value in cfg.items():
        if key not in KNOWN_CONFIG_KEYS or key in TRANSIENT_CONFIG_KEYS:
            continue
        persisted[key] = value
    # ``soup_price_4`` was removed from the live dictionary above; keep this
    # guard for callers that pass a mapping with unusual iteration behavior.
    persisted.pop("soup_price_4", None)
    persisted["config_schema_version"] = CONFIG_SCHEMA_VERSION

    # 按模块拆分保存到 data/settings/*.json
    module_buckets = {"sys": {}, "printer_relay": {}, "algo": {}, "shouqianba": {}}
    for k, v in persisted.items():
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
                "settings/printer_relay.json": "printer_relay",
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
