"""
智能双系统全自动流转决策引擎 (Smart Quota Auto-Decision Engine)
根据【重量门限】与【目标比例抽样算法】，全自动决策本单走官方还是走私域！
"""
import time
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from utils.window_utils import bring_official_to_front, bring_our_pos_to_front
from core.app_logger import log_event, CAT_SCALE, CAT_DECISION, CAT_SWITCH, CAT_PRINT


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
        self._last_official_time = 0.0  # 记录上一次判定为官方 POS 的时间戳 (用于官方连单保护)

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
                log_event(CAT_SCALE, f"称重检测到放碗动作", f"重量: {weight_kg:.3f}kg")

                # 🤖 执行全自动智能决策算法
                is_private_turn = self._evaluate_decision(weight_kg)

                if is_private_turn:
                    # 决策分配给【私域 POS】 -> 自动将本系统弹出最前
                    bring_our_pos_to_front(self.main_window)
                    self._update_floating_ball_status(is_private=True, reason="智能算法选择: 本单走私域")
                    msg = f"🤖 智能决策：重量 {weight_kg:.2f}kg -> 弹出【私域 POS】 (截留占比: {self.get_actual_private_ratio():.1f}%)"
                    print(f"[AutoDecisionEngine] {msg}")
                    log_event(CAT_DECISION, f"决策: 走私域 POS", f"重量 {weight_kg:.2f}kg | 截留占比: {self.get_actual_private_ratio():.1f}%")
                    if hasattr(self.main_window, 'status'):
                        self.main_window.status.showMessage(msg, 5000)
                else:
                    # 决策分配给【官方系统】 -> 本系统隐藏在后台，保持/拉出官方界面
                    ok = bring_official_to_front()
                    if not ok and self.main_window:
                        self.main_window.showMinimized()
                    self._update_floating_ball_status(is_private=False, reason="智能算法选择: 本单走官方")
                    msg = f"🤖 智能决策：重量 {weight_kg:.2f}kg -> 保持【官方界面】 (截留占比: {self.get_actual_private_ratio():.1f}%)"
                    print(f"[AutoDecisionEngine] {msg}")
                    log_event(CAT_DECISION, f"决策: 走官方系统", f"重量 {weight_kg:.2f}kg | 截留占比: {self.get_actual_private_ratio():.1f}%")
                    if hasattr(self.main_window, 'status'):
                        self.main_window.status.showMessage(msg, 5000)
        else:
            # 称上重量归零 (放下碗拿走)，重置弹出标记
            self._has_auto_popped = False

    def _evaluate_decision(self, weight_kg: float) -> bool:
        """
        全自动核心决策算法：
        0. 连单/多碗保护：如果当前私域 POS 购物车中已有菜品 (正在开单)，继承走私域 POS
        1. 门限过滤：如果重量 < min_private_weight_kg (如 < 0.25kg) 且购物车为空，分配给官方
        2. 目标比例动态调控：比较当前实际私域比例与目标比例，平滑交替分配
        """
        # 规则 0A：私域多碗/连续开单保护 (如果购物车已有未结账项目，保持私域 POS 连续开单)
        if hasattr(self.main_window, 'sale_page') and self.main_window.sale_page:
            cart_items = getattr(self.main_window.sale_page, 'cart_items', [])
            if cart_items:
                print(f"[AutoDecisionEngine] 检测到私域 POS 购物车已有 {len(cart_items)} 项商品，保持【私域 POS】连续开单")
                log_event(CAT_DECISION, "私域连单继承 -> 保持私域 POS", f"购物车已有 {len(cart_items)} 项 | 本次称重 {weight_kg:.3f}kg")
                return True

        # 规则 0B：官方多碗/连续开单保护 (如果 60 秒 (1分钟) 内上一碗刚分配给官方 POS，继承走官方 POS，防止弹窗打断店员官方开单)
        now_ts = time.time()
        if now_ts - self._last_official_time < 60.0:
            elapsed = now_ts - self._last_official_time
            self._last_official_time = now_ts  # 刷新连单锁定期
            print(f"[AutoDecisionEngine] 检测到 60 秒内已有官方开单记录 (间隔 {elapsed:.1f}s)，保持【官方界面】连续开单")
            log_event(CAT_DECISION, "官方连单继承 -> 保持官方界面", f"距离上一单官方操作 {elapsed:.1f}s < 60s | 本次称重 {weight_kg:.3f}kg")
            return False

        self._total_evaluated_orders += 1

        # 规则 1：小单过滤，低于设定重量一律分配给官方
        if weight_kg < self._min_private_weight:
            self._official_orders_count += 1
            self._last_official_time = now_ts
            print(f"[AutoDecisionEngine] 重量 {weight_kg:.3f}kg < {self._min_private_weight:.3f}kg 属于轻量单 -> 全自动分配给【官方】")
            log_event(CAT_DECISION, f"轻量单过滤 -> 走官方", f"重量 {weight_kg:.3f}kg < 门限 {self._min_private_weight:.3f}kg")
            return False

        # 规则 2：动态配额算法 (Quota Balancing Algorithm)
        # 如果当前私域比例低于目标设定比例，分配给私域，否则分配给官方
        current_ratio = self.get_actual_private_ratio()
        if current_ratio < self._target_private_ratio:
            self._private_orders_count += 1
            return True
        else:
            self._official_orders_count += 1
            self._last_official_time = now_ts
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
        log_event(CAT_PRINT, f"小票打印完成", f"启动 {self._auto_hide_delay_sec} 秒延时自动隐退")
        if hasattr(self.main_window, 'floating_ball') and self.main_window.floating_ball:
            self.main_window.floating_ball.start_countdown(self._auto_hide_delay_sec)
        self._hide_timer.start(delay_ms)

    def _on_auto_hide_timeout(self):
        """延时结束，隐退切回官方系统"""
        print("[AutoSwitch] 延时结束，自动隐退切回官方收银界面")
        log_event(CAT_SWITCH, f"自动隐退切回官方系统", f"延时 {self._auto_hide_delay_sec} 秒结束")
        ok = bring_official_to_front()
        if not ok and self.main_window:
            self.main_window.showMinimized()
        self._update_floating_ball_status(is_private=False, reason="出票延时结束")

    def _update_floating_ball_status(self, is_private: bool, reason: str = ""):
        """更新触屏悬浮球的状态与提示"""
        if hasattr(self.main_window, 'floating_ball') and self.main_window.floating_ball:
            fb = self.main_window.floating_ball
            fb.is_our_pos_active = is_private
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
