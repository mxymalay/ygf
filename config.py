"""
杨国福麻辣烫 · 独立称重打印系统 — 全局配置
"""
import os
import json

# ─── 应用版本号 ───────────────────────────────────────
APP_VERSION = "v2.1.0"

# ─── 路径 ───────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "sales.db")
CONFIG_FILE = os.path.join(DATA_DIR, "settings.json")

# ─── 默认配置 ────────────────────────────────────────
DEFAULT_CONFIG = {
    # 打印机设置 — Xprinter XP-A160M / XP-80C
    "printer_type": "windows",
    "printer_name": "shouyin",          # 店内真实打印机名称: shouyin
    "printer_ip": "192.168.1.100",
    "printer_port": 9100,
    "printer_serial_port": "COM4",

    # 业务设置
    "unit_price": 1.00,                 # 默认单价：1.00 元/kg
    "price_unit": "per_kg",             # 默认按公斤计价
    "shop_name": "杨国福麻辣烫",
    "shop_subtitle": "杨国福(肥西水晶城店)",
    "is_first_run": True,               # 首次使用初始化弹窗标记

    # 系统设置
    "auto_print": False,                # 称重稳定后自动打印
    "stable_threshold": 0.01,           # 重量稳定判断阈值(kg)
    "stable_count": 5,                  # 连续稳定次数才认为稳定
}


def load_config() -> dict:
    """加载配置文件，不存在则用默认配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = {**DEFAULT_CONFIG, **saved}
            merged.pop("simulation_mode", None)  # 移除旧的模拟模式字段
            # 清理历史称重串口相关字段
            for k in ["scale_model", "scale_port", "scale_baudrate", "scale_bytesize", "scale_parity", "scale_stopbits"]:
                merged.pop(k, None)
            return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    """保存配置到 JSON 文件"""
    cfg.pop("simulation_mode", None)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
