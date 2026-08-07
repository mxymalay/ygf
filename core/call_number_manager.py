"""
叫号牌生成引擎 — 智能避重、自定义与官方错峰叫号模式
支持：
1. 智能避重模式（上午 50-100 / 下午 100-200 / 晚上 200-300 随机不重复）
2. 自定义范围模式（自定义 [Start, End] 顺序/随机不重复）
3. 传统手动模式
4. 官方错峰随机模式（当前官方号 +30~60；四小时前的低号池回收）
"""
import random
import re
import time
from datetime import datetime, timedelta
from config import load_config, save_config


class CallNumberManager:
    """叫号牌管理器"""

    MODE_SMART = "smart"
    MODE_CUSTOM = "custom"
    MODE_MANUAL = "manual"
    # Official-POS-aware mode: keep private call numbers close to the current
    # official sequence while recycling numbers that have been idle for 4h.
    MODE_OFFICIAL_OFFSET = "official_offset"

    def __init__(self, config, official_db=None):
        self.config = config
        self.official_db = official_db
        self._used_numbers = set()
        for value in self.config.get("call_used_numbers", []) or []:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                self._used_numbers.add(number)
        self._last_time_slot = self.config.get("call_last_slot", self._get_current_time_slot())
        self._current_manual_no = self.config.get("call_manual_no", 1)
        self._current_seq_no = self.config.get("call_seq_no", None)
        self._cached_next_number = None
        self._official_pool_cache = None
        self._official_pool_cache_at = 0.0

    def set_official_db(self, official_db):
        """Attach the local official-POS receipt ledger after construction."""
        self.official_db = official_db
        self._official_pool_cache = None
        self._official_pool_cache_at = 0.0
        
    def _save_state(self):
        self.config["call_used_numbers"] = list(self._used_numbers)
        self.config["call_last_slot"] = self._last_time_slot
        self.config["call_manual_no"] = self._current_manual_no
        self.config["call_seq_no"] = self._current_seq_no
        save_config(self.config)

    def _get_current_time_slot(self) -> str:
        """获取当前时间段：morning (5-12), afternoon (12-18), evening (18-5)"""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        else:
            return "evening"

    def get_mode(self) -> str:
        return self.config.get("call_mode", self.MODE_SMART)

    def set_mode(self, mode: str):
        self.config["call_mode"] = mode
        self._cached_next_number = None
        save_config(self.config)

    @staticmethod
    def _numeric_call_no(value):
        """Extract the leading numeric part of an official call number."""
        match = re.search(r"\d+", str(value or ""))
        if not match:
            return None
        try:
            number = int(match.group(0))
        except (TypeError, ValueError):
            return None
        return number if 1 <= number <= 9999 else None

    def _official_number_context(self):
        """Return reusable old numbers and the current official high-water mark.

        The database stores every official receipt observation.  Only the
        latest four hours are considered "current"; older observations from
        the same business day become eligible for recycling. A contiguous
        1..old_max pool follows the store's numbering convention (for example,
        old #10 permits 1..10), while numbers still seen in the current
        four-hour window are removed to avoid a collision.
        """
        now = time.monotonic()
        if self._official_pool_cache is not None and now - self._official_pool_cache_at < 5.0:
            return self._official_pool_cache
        recent = set()
        all_numbers = set()
        today_numbers = set()
        today_old = set()
        cutoff = datetime.now() - timedelta(hours=4)
        today = datetime.now().date()
        db = self.official_db
        if db is not None and hasattr(db, "get_official_receipts"):
            try:
                rows = db.get_official_receipts(limit=2000) or []
            except Exception:
                rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                # Cancelled/refund tickets are not an active official order
                # sequence and must never enlarge the private call pool.
                if str(row.get("payment_status") or "").lower() in ("cancelled", "refunded"):
                    continue
                number = self._numeric_call_no(row.get("order_no"))
                if number is None:
                    continue
                observed = str(row.get("observed_at") or "").strip()
                parsed_time = None
                for candidate in (observed, observed.replace("T", " ")):
                    try:
                        parsed_time = datetime.strptime(candidate[:19], "%Y-%m-%d %H:%M:%S")
                        break
                    except (TypeError, ValueError):
                        continue
                all_numbers.add(number)
                if parsed_time is not None:
                    if parsed_time.date() == today:
                        today_numbers.add(number)
                        if parsed_time < cutoff:
                            today_old.add(number)
                    if parsed_time >= cutoff:
                        recent.add(number)

        # A new business day may restart the official sequence at #1. Reuse
        # low numbers only from the same business day; otherwise yesterday's
        # #10 could collide with today's upcoming #10. The high offset may use
        # the previous high-water mark because it remains safely ahead.
        old_max = max(today_old) if today_old else 0
        reusable = set(range(1, old_max + 1)) - recent
        current_max = max(today_numbers) if today_numbers else (max(all_numbers) if all_numbers else 0)
        context = {
            "reusable": reusable,
            "high": set(range(current_max + 30, current_max + 61)) if current_max else set(),
            "current_max": current_max,
            "old_max": old_max,
        }
        self._official_pool_cache = context
        self._official_pool_cache_at = now
        return context

    def _official_offset_pool(self):
        context = self._official_number_context()
        return set(context["reusable"]) | set(context["high"])

    def official_mode_ready(self):
        """Whether the official-relative mode has a trustworthy high-water mark."""
        return bool(self._official_number_context().get("current_max"))

    def _gen_official_offset_number(self):
        """Choose a random official-relative number without breaking legacy mode."""
        pool = self._official_offset_pool()
        available = sorted(pool - self._used_numbers)
        if not available:
            # Without an official high-water mark there is no safe number:
            # the POS may have started a new day at #1. Never guess a low
            # number and risk colliding with an official customer.
            if not pool:
                return None
            self._used_numbers.clear()
            available = sorted(pool)
        chosen = random.choice(available)
        self._used_numbers.add(chosen)
        self._cached_next_number = None
        self._save_state()
        return chosen

    def reset_pool(self):
        """重置已使用号码池"""
        self._used_numbers.clear()
        self._current_seq_no = None
        self._cached_next_number = None
        self._save_state()

    def get_next_number(self) -> int:
        """根据当前模式产生下一个叫号 (正式消耗并标记为已用)"""
        mode = self.get_mode()

        if mode == self.MODE_SMART:
            if self._cached_next_number is not None and self._cached_next_number not in self._used_numbers:
                chosen = self._cached_next_number
                self._used_numbers.add(chosen)
                self._cached_next_number = None
                self._save_state()
                return chosen
            return self._gen_smart_number()
        elif mode == self.MODE_CUSTOM:
            if self.config.get("custom_is_seq", False):
                return self._gen_custom_number()
            else:
                if self._cached_next_number is not None and self._cached_next_number not in self._used_numbers:
                    chosen = self._cached_next_number
                    self._used_numbers.add(chosen)
                    self._cached_next_number = None
                    self._save_state()
                    return chosen
                return self._gen_custom_number()
        elif mode == self.MODE_OFFICIAL_OFFSET:
            if self._cached_next_number is not None:
                pool = self._official_offset_pool()
                if self._cached_next_number in pool and self._cached_next_number not in self._used_numbers:
                    chosen = self._cached_next_number
                    self._used_numbers.add(chosen)
                    self._cached_next_number = None
                    self._save_state()
                    return chosen
            return self._gen_official_offset_number()
        else:
            # 手动模式
            num = self._current_manual_no
            self._used_numbers.add(num)
            self._current_manual_no = num + 1
            self._cached_next_number = None
            self._save_state()
            return num

    def peek_next_number(self) -> int:
        """预览下一个叫号（随机从池中挑选候选，不消耗号码，保持预览与打票一致）"""
        mode = self.get_mode()
        if mode == self.MODE_MANUAL:
            return self._current_manual_no

        if mode == self.MODE_SMART:
            curr_slot = self._get_current_time_slot()
            if curr_slot != self._last_time_slot:
                self._used_numbers.clear()
                self._last_time_slot = curr_slot
                self._cached_next_number = None

            if self._cached_next_number is not None and self._cached_next_number not in self._used_numbers:
                return self._cached_next_number

            if curr_slot == "morning":
                low, high = 50, 100
            elif curr_slot == "afternoon":
                low, high = 100, 200
            else:
                low, high = 200, 300

            pool = [n for n in range(low, high + 1) if n not in self._used_numbers]
            if not pool:
                self._used_numbers.clear()
                pool = list(range(low, high + 1))

            self._cached_next_number = random.choice(pool)
            return self._cached_next_number

        elif mode == self.MODE_CUSTOM:
            low = self.config.get("custom_start_no", 50)
            high = self.config.get("custom_end_no", 500)
            if low > high:
                low, high = high, low

            is_seq = self.config.get("custom_is_seq", False)

            if is_seq:
                if self._current_seq_no is None or self._current_seq_no < low or self._current_seq_no > high:
                    return low
                return self._current_seq_no
            else:
                if self._cached_next_number is not None and self._cached_next_number not in self._used_numbers:
                    return self._cached_next_number
                pool = [n for n in range(low, high + 1) if n not in self._used_numbers]
                if not pool:
                    self._used_numbers.clear()
                    pool = list(range(low, high + 1))
                self._cached_next_number = random.choice(pool)
                return self._cached_next_number

        elif mode == self.MODE_OFFICIAL_OFFSET:
            pool = self._official_offset_pool()
            available = sorted(pool - self._used_numbers)
            if not available:
                if not pool:
                    return None
                self._used_numbers.clear()
                available = sorted(pool)
            self._cached_next_number = random.choice(available)
            return self._cached_next_number

        return 1

    def set_manual_number(self, val: int):
        self._current_manual_no = val
        self._cached_next_number = None
        self._save_state()

    def _gen_smart_number(self) -> int:
        """智能避重模式生成"""
        curr_slot = self._get_current_time_slot()
        # 换时间段时自动清空历史防重池
        if curr_slot != self._last_time_slot:
            self._used_numbers.clear()
            self._last_time_slot = curr_slot
            self._cached_next_number = None

        if curr_slot == "morning":
            low, high = 50, 100
        elif curr_slot == "afternoon":
            low, high = 100, 200
        else:
            low, high = 200, 300

        pool = [n for n in range(low, high + 1) if n not in self._used_numbers]
        if not pool:
            # 若该时段用光则清空重用
            self._used_numbers.clear()
            pool = list(range(low, high + 1))

        chosen = random.choice(pool)
        self._used_numbers.add(chosen)
        self._cached_next_number = None
        self._save_state()
        return chosen

    def _gen_custom_number(self) -> int:
        """自定义范围模式生成"""
        low = self.config.get("custom_start_no", 50)
        high = self.config.get("custom_end_no", 500)
        if low > high:
            low, high = high, low

        is_seq = self.config.get("custom_is_seq", False)

        if is_seq:
            if self._current_seq_no is None or self._current_seq_no < low or self._current_seq_no > high:
                self._current_seq_no = low
            chosen = self._current_seq_no
            self._current_seq_no += 1
            if self._current_seq_no > high:
                self._current_seq_no = low
            self._save_state()
            return chosen
        else:
            pool = [n for n in range(low, high + 1) if n not in self._used_numbers]
            if not pool:
                self._used_numbers.clear()
                pool = list(range(low, high + 1))
            chosen = random.choice(pool)
            self._used_numbers.add(chosen)
            self._cached_next_number = None
            self._save_state()
            return chosen
