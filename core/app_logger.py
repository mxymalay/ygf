"""
全局应用日志服务 (Centralized Application Logger)
所有业务事件统一通过该模块写入持久化 JSON Lines 日志文件。
特性：
- 分类标签：称重(SCALE)、打印(PRINT)、决策(DECISION)、切换(SWITCH)、避险(PANIC)、系统(SYSTEM)
- 自动 3 天过期清理
- 活跃日志文件超过 10 MB 时自动裁剪最旧记录
- 线程安全
"""
import os
import json
import time
import threading
from datetime import datetime, timedelta

# 日志分类常量
CAT_ORDER    = "ORDER"      # 订单交易事件 (开单/叫号生成/交易落库)
CAT_USER     = "USER"       # 用户操作 (点菜/删除/折扣/切换页面等)
CAT_SCALE    = "SCALE"      # 称重事件
CAT_PRINT    = "PRINT"      # 小票打印硬件事件
CAT_DECISION = "DECISION"   # 智能决策引擎事件
CAT_SWITCH   = "SWITCH"     # 系统切换事件
CAT_PANIC    = "PANIC"      # 防督导避险事件
CAT_SYSTEM   = "SYSTEM"     # 系统启动/关闭/配置变更等

ALL_CATEGORIES = [CAT_ORDER, CAT_USER, CAT_SCALE, CAT_PRINT, CAT_DECISION, CAT_SWITCH, CAT_PANIC, CAT_SYSTEM]

import sys

# 动态获取 DATA_DIR (兼容 PyInstaller 封包)
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR = os.path.join(_BASE_DIR, "data")
_LOG_FILE = os.path.join(_LOG_DIR, "app_events.jsonl")
_SCALE_LOG_FILE = os.path.join(_LOG_DIR, "scale_events.jsonl")
_LOCK = threading.Lock()
_RETENTION_DAYS = 3
_MAX_LOG_BYTES = 10 * 1024 * 1024
_TRIM_CHECK_EVERY = 64
_events_since_trim = 0


def _ensure_dir():
    os.makedirs(_LOG_DIR, exist_ok=True)


def log_event(category: str, message: str, detail: str = ""):
    """写入一条日志事件 (线程安全)"""
    global _events_since_trim
    _ensure_dir()
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cat": category,
        "msg": message,
        "detail": detail,
    }
    with _LOCK:
        try:
            encoded = json.dumps(entry, ensure_ascii=False) + "\n"
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(encoded)
            # Keep a dedicated scale trace while retaining the unified app
            # log for the existing log viewer and cross-event correlation.
            if category == CAT_SCALE:
                with open(_SCALE_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(encoded)
            _events_since_trim += 1
            if _events_since_trim >= _TRIM_CHECK_EVERY:
                _events_since_trim = 0
                _trim_log_size_locked()
                _trim_log_size_locked(_SCALE_LOG_FILE)
        except Exception:
            pass


def _trim_log_size_locked(path=None):
    """Keep the newest log lines when the active file exceeds the cap.

    Caller must hold ``_LOCK``.  The retained target is 75% of the cap so the
    file does not trigger a rewrite on every subsequent event.
    """
    try:
        path = path or _LOG_FILE
        if not os.path.exists(path) or os.path.getsize(path) <= _MAX_LOG_BYTES:
            return 0
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        target_bytes = int(_MAX_LOG_BYTES * 0.75)
        kept = []
        size = 0
        for line in reversed(lines):
            encoded_size = len(line.encode("utf-8"))
            if kept and size + encoded_size > target_bytes:
                break
            kept.append(line)
            size += encoded_size
        kept.reverse()
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(kept)
        return max(0, len(lines) - len(kept))
    except Exception:
        return 0


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
    cutoff = datetime.now() - timedelta(days=_RETENTION_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    removed_count = 0
    with _LOCK:
        for path in (_LOG_FILE, _SCALE_LOG_FILE):
            if not os.path.exists(path):
                continue
            kept_lines = []
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
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

                with open(path, "w", encoding="utf-8") as f:
                    for line in kept_lines:
                        f.write(line + "\n")
            except Exception:
                pass
    return removed_count


def clear_all_logs():
    """彻底清空/删除所有本地日志文件 (app_events.jsonl 与 scale_events.jsonl)"""
    _ensure_dir()
    with _LOCK:
        try:
            for path in (_LOG_FILE, _SCALE_LOG_FILE):
                if os.path.exists(path):
                    os.remove(path)
            return True
        except Exception as e:
            print(f"Failed to remove log file {_LOG_FILE}: {e}")
            return False
