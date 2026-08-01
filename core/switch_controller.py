"""
智能双系统无缝流转控制器 (Auto Switch Controller)
监听电子秤重量与打单事件，实现放碗自动弹出、打完小票自动退场
"""
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from utils.window_utils import bring_official_to_front, bring_our_pos_to_front


class AutoSwitchController(QObject):
    """自动切换控制器"""

    def __init__(self, main_window, config: dict, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.config = config

        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        self._auto_hide_delay_sec = self.config.get("auto_hide_delay_sec", 3)

        self._has_auto_popped = False  # 防止在同一个重量上重复弹出

        # 退场延时定时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_auto_hide_timeout)

    def on_weight_changed(self, weight_kg: float):
        """当称重数据变动时被触发"""
        if not self._auto_switch_enabled:
            return

        # 重量门限判断 (例如大于 0.08kg 视为有放碗动作)
        if weight_kg > 0.08:
            if not self._has_auto_popped:
                # 终止任何准备隐退的定时器
                self._hide_timer.stop()
                # 自动将本软件弹出到最前
                bring_our_pos_to_front(self.main_window)
                self._has_auto_popped = True
                print(f"[AutoSwitch] 检测到有效称重 {weight_kg:.3f}kg，自动弹出本 POS 界面")
        else:
            # 称上重量归零，重置弹出标记
            self._has_auto_popped = False

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
        # 更新悬浮球状态（如果存在）
        if hasattr(self.main_window, 'floating_ball') and self.main_window.floating_ball:
            self.main_window.floating_ball.is_our_pos_active = False
            self.main_window.floating_ball.lbl_text.setText("官方")
            self.main_window.floating_ball.update()

    def update_config(self, config: dict):
        """更新配置参数"""
        self.config = config
        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        self._auto_hide_delay_sec = self.config.get("auto_hide_delay_sec", 3)
