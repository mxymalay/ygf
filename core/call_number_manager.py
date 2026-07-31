"""
叫号牌生成引擎 — 智能避重与自定义叫号模式
支持：
1. 智能避重模式（上午 50-100 / 下午 100-200 / 晚上 200-300 随机不重复）
2. 自定义范围模式（自定义 [Start, End] 顺序/随机不重复）
3. 传统手动模式
"""
import random
from datetime import datetime
from config import load_config, save_config


class CallNumberManager:
    """叫号牌管理器"""

    MODE_SMART = "smart"
    MODE_CUSTOM = "custom"
    MODE_MANUAL = "manual"

    def __init__(self, config):
        self.config = config
        self._used_numbers = set()
        self._last_time_slot = self._get_current_time_slot()
        self._current_manual_no = 1
        self._current_seq_no = None

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
        save_config(self.config)
        self.reset_pool()

    def reset_pool(self):
        """重置已使用号码池"""
        self._used_numbers.clear()
        self._current_seq_no = None

    def get_next_number(self) -> int:
        """根据当前模式产生下一个叫号"""
        mode = self.get_mode()

        if mode == self.MODE_SMART:
            return self._gen_smart_number()
        elif mode == self.MODE_CUSTOM:
            return self._gen_custom_number()
        else:
            # 手动模式
            num = self._current_manual_no
            self._current_manual_no += 1
            return num

    def peek_next_number(self) -> int:
        """预览下一个叫号（不消耗号码）"""
        mode = self.get_mode()
        if mode == self.MODE_MANUAL:
            return self._current_manual_no

        # 对于智能和自定义模式，预览当前可用池中的一个候选值
        if mode == self.MODE_SMART:
            slot = self._get_current_time_slot()
            if slot == "morning":
                low, high = 50, 100
            elif slot == "afternoon":
                low, high = 100, 200
            else:
                low, high = 200, 300

            pool = [n for n in range(low, high + 1) if n not in self._used_numbers]
            if not pool:
                return low
            return pool[0]

        elif mode == self.MODE_CUSTOM:
            low = self.config.get("custom_start_no", 50)
            high = self.config.get("custom_end_no", 500)
            is_seq = self.config.get("custom_is_seq", False)

            if is_seq:
                if self._current_seq_no is None:
                    return low
                return self._current_seq_no
            else:
                pool = [n for n in range(low, high + 1) if n not in self._used_numbers]
                if not pool:
                    return low
                return pool[0]

        return 1

    def set_manual_number(self, val: int):
        self._current_manual_no = val

    def _gen_smart_number(self) -> int:
        """智能避重模式生成"""
        curr_slot = self._get_current_time_slot()
        # 换时间段时自动清空历史防重池
        if curr_slot != self._last_time_slot:
            self._used_numbers.clear()
            self._last_time_slot = curr_slot

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
            return chosen
        else:
            pool = [n for n in range(low, high + 1) if n not in self._used_numbers]
            if not pool:
                self._used_numbers.clear()
                pool = list(range(low, high + 1))
            chosen = random.choice(pool)
            self._used_numbers.add(chosen)
            return chosen
