"""
全局应用日志服务 (Centralized Application Logger)
所有业务事件统一通过该模块写入持久化 JSON Lines 日志文件。
特性：
- 分类标签：称重(SCALE)、打印(PRINT)、决策(DECISION)、切换(SWITCH)、避险(PANIC)、系统(SYSTEM)
- 自动 3 天过期清理
- 线程安全
"""
import os
import json
import time
import threading
from datetime import datetime, timedelta

# 日志分类常量
CAT_SCALE    = "SCALE"      # 称重事件
CAT_PRINT    = "PRINT"      # 打印事件
CAT_DECISION = "DECISION"   # 智能决策引擎事件
CAT_SWITCH   = "SWITCH"     # 系统切换事件
CAT_PANIC    = "PANIC"      # 防督导避险事件
CAT_SYSTEM   = "SYSTEM"     # 系统启动/关闭/配置变更等

ALL_CATEGORIES = [CAT_SCALE, CAT_PRINT, CAT_DECISION, CAT_SWITCH, CAT_PANIC, CAT_SYSTEM]

# 日志文件路径
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_LOG_FILE = os.path.join(_LOG_DIR, "app_events.jsonl")
_LOCK = threading.Lock()
_RETENTION_DAYS = 3


def _ensure_dir():
    os.makedirs(_LOG_DIR, exist_ok=True)


def log_event(category: str, message: str, detail: str = ""):
    """写入一条日志事件 (线程安全)"""
    _ensure_dir()
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cat": category,
        "msg": message,
        "detail": detail,
    }
    with _LOCK:
        try:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def read_logs(category_filter: str = "", keyword: str = "", limit: int = 500) -> list:
    """
    读取日志条目，支持按分类与关键词过滤。
    返回 list[dict]，按时间倒序 (最新在前)。
    """
    _ensure_dir()
    results = []
    if not os.path.exists(_LOG_FILE):
        return results

    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return results

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if category_filter and entry.get("cat") != category_filter:
            continue
        if keyword:
            kw_lower = keyword.lower()
            if kw_lower not in entry.get("msg", "").lower() and kw_lower not in entry.get("detail", "").lower():
                continue

        results.append(entry)
        if len(results) >= limit:
            break
    return results


def cleanup_old_logs():
    """清理超过 _RETENTION_DAYS 天的旧日志条目"""
    _ensure_dir()
    if not os.path.exists(_LOG_FILE):
        return 0

    cutoff = datetime.now() - timedelta(days=_RETENTION_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    kept_lines = []
    removed_count = 0
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("ts", "") >= cutoff_str:
                        kept_lines.append(line)
                    else:
                        removed_count += 1
                except Exception:
                    removed_count += 1

        with open(_LOG_FILE, "w", encoding="utf-8") as f:
            for line in kept_lines:
                f.write(line + "\n")
    except Exception:
        pass
    return removed_count
