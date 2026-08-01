"""
杨国福麻辣烫 · 独立称重打印系统 — 全局配置
"""
import os
import json

# ─── 应用版本号 ───────────────────────────────────────
APP_VERSION = "v1.0.0"

import sys

# ─── 路径 ───────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "sales.db")
CONFIG_FILE = os.path.join(DATA_DIR, "settings.json")
TEMPLATE_FILE = os.path.join(DATA_DIR, "settings.json.template")

# ─── 默认配置 ────────────────────────────────────────
DEFAULT_CONFIG = {
    # 打印机设置 — Xprinter XP-A160M / XP-80C
    "printer_type": "windows",
    "printer_name": "shouyin",          # 店内真实打印机名称: shouyin
    "printer_ip": "192.168.1.100",
    "printer_port": 9100,
    "printer_serial_port": "COM4",

    # 业务设置
    "unit_price": 47.60,                # 标准汤底单价：47.60 元/kg
    "special_soup_price": 50.00,        # 精品汤底单价：50.00 元/kg
    "price_unit": "per_kg",             # 默认按公斤计价
    "shop_name": "杨国福麻辣烫",
    "shop_subtitle": "杨国福(测试店)",
    "is_first_run": True,               # 首次使用初始化弹窗标记

    # 系统设置
    "auto_print": False,                # 称重稳定后自动打印
    "stable_threshold": 0.01,           # 重量稳定判断阈值(kg)
    "stable_count": 5,                  # 连续稳定次数才认为稳定
    "auto_start_enabled": True,         # 是否开启开机自启动
    "auto_start_delay": 8,              # 自启动延迟秒数
    "auto_switch_enabled": True,        # 称重自动弹出/打单自动隐退
    "floating_ball_enabled": True,      # 常驻悬浮切换球
    "panic_hotkey": "F10",              # 紧急避险老板键
    "auto_hide_delay_sec": 3,           # 出票后自动隐退延时(秒)

    # 收钱吧 PC收款助手设置
    "shouqianba_enabled": True,         # 开启收钱吧串口/快捷键自动推送
    "shouqianba_port": "COM1",          # 收钱吧监听串口/虚拟串口
    "shouqianba_baudrate": 2400,        # 波特率
    "shouqianba_format": "QA",          # 解析规则: "QA" (QA12.50\r\n) 或 "FLOAT" (12.50\r\n)
    "shouqianba_hotkey": "F12",         # 收钱吧唤起快捷键
}


def load_config() -> dict:
    """加载配置文件，支持从 template 模版自动合并与离线生成"""
    base_defaults = DEFAULT_CONFIG.copy()
    if os.path.exists(TEMPLATE_FILE):
        try:
            with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
                template_data = json.load(f)
                base_defaults.update(template_data)
        except Exception:
            pass

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = {**base_defaults, **saved}
            merged.pop("simulation_mode", None)  # 移除旧字段
            for k in ["scale_model", "scale_port", "scale_baudrate", "scale_bytesize", "scale_parity", "scale_stopbits"]:
                merged.pop(k, None)
            return merged
        except Exception:
            pass

    # 若本地 settings.json 不存在，依据 template 自动生成
    save_config(base_defaults)
    return base_defaults


def save_config(cfg: dict):
    """保存配置到 JSON 文件"""
    cfg.pop("simulation_mode", None)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
