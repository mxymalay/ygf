"""
智能双系统全自动流转决策引擎 (Smart Quota Auto-Decision Engine)
根据【重量门限】与【目标比例抽样算法】，全自动决策本单走官方还是走私域！
"""
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from utils.window_utils import bring_official_to_front, bring_our_pos_to_front


class AutoSwitchController(QObject):
    """双系统智能决策控制器"""

    def __init__(self, main_window, config: dict, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.config = config

        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        self._auto_hide_delay_sec = self.config.get("auto_hide_delay_sec", 3)
        self._target_private_ratio = float(self.config.get("private_ratio_percent", 70))  # 默认 70%
        self._min_private_weight = float(self.config.get("min_private_weight_kg", 0.25))  # 默认 0.25kg

        self._total_evaluated_orders = 0
        self._private_orders_count = 0
        self._official_orders_count = 0

        self._has_auto_popped = False  # 防止在同一个重量上重复判断

        # 退场延时定时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_auto_hide_timeout)

    def on_weight_changed(self, weight_kg: float):
        """当称重数据变动时被触发，全自动运行决策引擎"""
        if not self._auto_switch_enabled:
            return

        # 重量门限判断 (例如大于 0.08kg 视为有放碗动作)
        if weight_kg > 0.08:
            if not self._has_auto_popped:
                self._has_auto_popped = True
                self._hide_timer.stop()

                # 🤖 执行全自动智能决策算法
                is_private_turn = self._evaluate_decision(weight_kg)

                if is_private_turn:
                    # 决策分配给【私域 POS】 -> 自动将本系统弹出最前
                    bring_our_pos_to_front(self.main_window)
                    self._update_floating_ball_status(is_private=True, reason="智能算法选择: 本单走私域")
                    print(f"[AutoDecisionEngine] 重量 {weight_kg:.3f}kg -> 算法决策：分配给【私域 POS】 (当前实际比例: {self.get_actual_private_ratio():.1f}%)")
                else:
                    # 决策分配给【官方系统】 -> 本系统隐藏在后台，保持/拉出官方界面
                    bring_official_to_front()
                    self._update_floating_ball_status(is_private=False, reason="智能算法选择: 本单走官方")
                    print(f"[AutoDecisionEngine] 重量 {weight_kg:.3f}kg -> 算法决策：分配给【官方收银系统】 (当前实际比例: {self.get_actual_private_ratio():.1f}%)")
        else:
            # 称上重量归零 (放下碗拿走)，重置弹出标记
            self._has_auto_popped = False

    def _evaluate_decision(self, weight_kg: float) -> bool:
        """
        全自动核心决策算法：
        1. 门限过滤：如果重量 < min_private_weight_kg (如 < 0.25kg)，必走官方
        2. 目标比例动态调控：比较当前实际私域比例与目标比例，平滑交替分配
        """
        self._total_evaluated_orders += 1

        # 规则 1：小单过滤，低于设定重量一律分配给官方
        if weight_kg < self._min_private_weight:
            self._official_orders_count += 1
            print(f"[AutoDecisionEngine] 重量 {weight_kg:.3f}kg < {self._min_private_weight:.3f}kg 属于轻量单 -> 全自动分配给【官方】")
            return False

        # 规则 2：动态配额算法 (Quota Balancing Algorithm)
        # 如果当前私域比例低于目标设定比例，分配给私域，否则分配给官方
        current_ratio = self.get_actual_private_ratio()
        if current_ratio < self._target_private_ratio:
            self._private_orders_count += 1
            return True
        else:
            self._official_orders_count += 1
            return False

    def get_actual_private_ratio(self) -> float:
        """计算当前实际的私域比例 (%)"""
        if self._total_evaluated_orders == 0:
            return 0.0
        return (self._private_orders_count / self._total_evaluated_orders) * 100.0

    def on_receipt_printed(self):
        """当打完制作单/小票后被触发"""
        if not self._auto_switch_enabled:
            return

        delay_ms = self._auto_hide_delay_sec * 1000
        print(f"[AutoSwitch] 小票已打印，启动 {self._auto_hide_delay_sec} 秒延时自动隐退程序...")
        self._hide_timer.start(delay_ms)

    def _on_auto_hide_timeout(self):
        """延时结束，隐退切回官方系统"""
        print("[AutoSwitch] 延时结束，自动隐退切回官方收银界面")
        bring_official_to_front()
        self._update_floating_ball_status(is_private=False, reason="出票延时结束")

    def _update_floating_ball_status(self, is_private: bool, reason: str = ""):
        """更新触屏悬浮球的状态与提示"""
        if hasattr(self.main_window, 'floating_ball') and self.main_window.floating_ball:
            fb = self.main_window.floating_ball
            fb.is_our_pos_active = is_private
            fb.lbl_text.setText("YGF" if is_private else "官方")
            actual_pct = int(self.get_actual_private_ratio())
            fb.setToolTip(f"自动决策系统 | 当前私域比: {actual_pct}%\n{reason}\n轻触: 手动切换 | 长按/三连击: 紧急避险销毁")
            fb.update()

    def update_config(self, config: dict):
        """更新配置参数"""
        self.config = config
        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        self._auto_hide_delay_sec = self.config.get("auto_hide_delay_sec", 3)
        self._target_private_ratio = float(self.config.get("private_ratio_percent", 70))
        self._min_private_weight = float(self.config.get("min_private_weight_kg", 0.25))
