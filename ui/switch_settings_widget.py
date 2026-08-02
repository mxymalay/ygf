"""
自动切换算法设置页面 (Auto Switch Algorithm Settings)
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QFormLayout, QFrame, QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt
from config import save_config
from core.app_logger import log_event, CAT_SYSTEM


class TouchSpinBox(QWidget):
    """触屏友好的数字加减控件 (整数)"""
    def __init__(self, value, min_val, max_val, step=1, suffix="", parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.suffix = suffix
        self._value = value
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.btn_minus = QPushButton(u"－")
        self.btn_minus.setFixedSize(40, 40)
        self.btn_minus.setCursor(Qt.PointingHandCursor)
        self.btn_minus.clicked.connect(self.decrement)
        
        self.lbl_val = QLabel()
        self.lbl_val.setAlignment(Qt.AlignCenter)
        self.lbl_val.setMinimumWidth(80)
        
        self.btn_plus = QPushButton(u"＋")
        self.btn_plus.setFixedSize(40, 40)
        self.btn_plus.setCursor(Qt.PointingHandCursor)
        self.btn_plus.clicked.connect(self.increment)
        
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.lbl_val)
        layout.addWidget(self.btn_plus)
        layout.addStretch()
        
        self.update_display()
        self.setStyleSheet("""
            QPushButton {
                background-color: #334155; color: white;
                font-size: 20px; font-weight: bold; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #475569; }
            QPushButton:pressed { background-color: #64748B; }
            QLabel {
                background-color: #0F172A; color: #F8FAFC;
                font-size: 16px; font-weight: bold; border-radius: 6px;
                border: 1px solid #475569; padding: 4px;
            }
        """)

    def value(self):
        return self._value
        
    def setValue(self, val):
        # For floating point precision issues, we use round if it's float
        if isinstance(self.step, float):
            self._value = round(max(self.min_val, min(self.max_val, val)), 3)
        else:
            self._value = max(self.min_val, min(self.max_val, val))
        self.update_display()
        
    def increment(self):
        self.setValue(self._value + self.step)
        
    def decrement(self):
        self.setValue(self._value - self.step)
        
    def update_display(self):
        self.lbl_val.setText(f"{self._value}{self.suffix}")


class TouchDoubleSpinBox(TouchSpinBox):
    """触屏友好的数字加减控件 (浮点数)"""
    def update_display(self):
        self.lbl_val.setText(f"{self._value:.2f}{self.suffix}")


class SwitchSettingsWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(15)

        # 标题区
        lbl_title = QLabel(u"🤖 全自动分流算法设置")
        lbl_title.setStyleSheet("font-size: 26px; font-weight: 900; color: #F8FAFC;")
        root.addWidget(lbl_title)

        lbl_sub = QLabel(u"触屏专用：使用加减号控制核心算法门限参数，禁止鼠标滑动产生误操作。")
        lbl_sub.setStyleSheet("font-size: 14px; color: #94A3B8; margin-bottom: 10px;")
        root.addWidget(lbl_sub)

        # 核心滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 12px; background: #0F172A; border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #334155; border-radius: 6px;
            }
        """)

        form_frame = QFrame()
        form_frame.setObjectName("formFrame")
        form_frame.setStyleSheet("""
            #formFrame {
                background-color: #1E293B;
                border-radius: 12px;
                border: 1px solid #334155;
            }
            QLabel {
                font-size: 15px; color: #E2E8F0; font-weight: bold; border: none; background: transparent;
            }
            QCheckBox {
                font-size: 15px; color: #F8FAFC; font-weight: bold;
            }
            QCheckBox::indicator {
                width: 24px; height: 24px;
            }
        """)
        
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(30, 30, 30, 30)
        form_layout.setSpacing(24)

        # 1. 开关
        self.chk_enabled = QCheckBox(u"开启智能自动分流 (若关闭，则需要手动控制悬浮球切换)")
        form_layout.addRow(QLabel(u"系统总控开关:"), self.chk_enabled)

        # 2. 目标私域比例
        self.sp_ratio = TouchSpinBox(70, 0, 100, 5, " %")
        form_layout.addRow(QLabel(u"目标私域截留比例:"), self.sp_ratio)

        # 3. 门限过滤
        self.sp_weight = TouchDoubleSpinBox(0.25, 0.00, 5.00, 0.05, " kg")
        form_layout.addRow(QLabel(u"轻量小单自动切回门限:"), self.sp_weight)
        
        lbl_weight_tip = QLabel(u"低于该重量的单子一律判定为小单/加菜，自动分配给官方收银机。")
        lbl_weight_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal; border: none;")
        form_layout.addRow(QLabel(), lbl_weight_tip)

        # 3.1 称重起漂过滤门限
        self.sp_min_valid_weight = TouchDoubleSpinBox(0.08, 0.01, 0.50, 0.01, " kg")
        form_layout.addRow(QLabel(u"最低有效称重(防空秤抖动):"), self.sp_min_valid_weight)

        # 3.2 剧增防抖修正门限
        self.sp_surge_correction = TouchDoubleSpinBox(0.15, 0.05, 1.00, 0.05, " kg")
        form_layout.addRow(QLabel(u"手放碗剧增防抖修正门限:"), self.sp_surge_correction)

        # 4. 官方界面连单锁定 (60s)
        self.sp_official_lock = TouchSpinBox(60, 0, 300, 5, " 秒")
        form_layout.addRow(QLabel(u"官方界面连单保护时长:"), self.sp_official_lock)

        # 5. 称重归零解锁判定 (5s)
        self.sp_zeroing_unlock = TouchSpinBox(5, 1, 60, 1, " 秒")
        form_layout.addRow(QLabel(u"称重归零离场解锁判定:"), self.sp_zeroing_unlock)
        
        lbl_zeroing_tip = QLabel(u"当秤上重量归零并保持该时长后，自动解除上方设定的官方连单保护锁。")
        lbl_zeroing_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal; border: none;")
        form_layout.addRow(QLabel(), lbl_zeroing_tip)

        # 6. 私域死锁超时 (300s)
        self.sp_private_lock = TouchSpinBox(300, 10, 3600, 10, " 秒")
        form_layout.addRow(QLabel(u"私域购物车超时清理:"), self.sp_private_lock)
        
        lbl_private_tip = QLabel(u"若私域购物车有菜品但长期未结账超过此时长，自动清空以释放连单锁。")
        lbl_private_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal; border: none;")
        form_layout.addRow(QLabel(), lbl_private_tip)

        # 6.5 手动干预保护
        self.sp_manual_override_lock = TouchSpinBox(30, 5, 120, 5, " 秒")
        form_layout.addRow(QLabel(u"手动点击悬浮球强制锁定:"), self.sp_manual_override_lock)
        
        lbl_manual_tip = QLabel(u"店员点击悬浮球切屏后，该时长内算法完全静默，100% 尊重店员选择。")
        lbl_manual_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal; border: none;")
        form_layout.addRow(QLabel(), lbl_manual_tip)

        # 7. 延时隐退
        self.sp_delay = TouchSpinBox(3, 0, 30, 1, " 秒")
        form_layout.addRow(QLabel(u"结账出票后自动隐退延时:"), self.sp_delay)

        scroll.setWidget(form_frame)
        root.addWidget(scroll, stretch=1)

        # 底部按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton(u"💾 保存算法参数")
        self.btn_save.setFixedHeight(50)
        self.btn_save.setMinimumWidth(200)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0284C7; color: white;
                font-size: 16px; font-weight: bold;
                border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #0369A1; }
            QPushButton:pressed { background-color: #075985; }
        """)
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        root.addLayout(btn_layout)

    def _load_config(self):
        self.chk_enabled.setChecked(self.config.get("auto_switch_enabled", True))
        self.sp_ratio.setValue(int(self.config.get("private_ratio_percent", 70)))
        self.sp_weight.setValue(float(self.config.get("min_private_weight_kg", 0.25)))
        self.sp_min_valid_weight.setValue(float(self.config.get("min_valid_weight_kg", 0.08)))
        self.sp_surge_correction.setValue(float(self.config.get("surge_correction_weight_kg", 0.15)))
        
        self.sp_official_lock.setValue(int(self.config.get("official_lock_sec", 60)))
        self.sp_zeroing_unlock.setValue(int(self.config.get("zeroing_unlock_sec", 5)))
        self.sp_private_lock.setValue(int(self.config.get("private_lock_sec", 300)))
        self.sp_manual_override_lock.setValue(int(self.config.get("manual_override_lock_sec", 30)))
        self.sp_delay.setValue(int(self.config.get("auto_hide_delay_sec", 3)))

    def _on_save(self):
        # 1. 获取新值
        new_enabled = self.chk_enabled.isChecked()
        new_ratio = self.sp_ratio.value()
        new_weight = self.sp_weight.value()
        new_min_valid = self.sp_min_valid_weight.value()
        new_surge = self.sp_surge_correction.value()
        new_official_lock = self.sp_official_lock.value()
        new_zeroing_unlock = self.sp_zeroing_unlock.value()
        new_private_lock = self.sp_private_lock.value()
        new_manual_override = self.sp_manual_override_lock.value()
        new_delay = self.sp_delay.value()

        # 2. 更新 config
        self.config["auto_switch_enabled"] = new_enabled
        self.config["private_ratio_percent"] = new_ratio
        self.config["min_private_weight_kg"] = new_weight
        self.config["min_valid_weight_kg"] = new_min_valid
        self.config["surge_correction_weight_kg"] = new_surge
        self.config["official_lock_sec"] = new_official_lock
        self.config["zeroing_unlock_sec"] = new_zeroing_unlock
        self.config["private_lock_sec"] = new_private_lock
        self.config["manual_override_lock_sec"] = new_manual_override
        self.config["auto_hide_delay_sec"] = new_delay
        
        save_config(self.config)

        # 3. 记录日志
        detail = (f"开关: {'开' if new_enabled else '关'} | "
                  f"截留比: {new_ratio}% | "
                  f"门限: {new_weight:.2f}kg (起漂{new_min_valid:.2f}, 剧增{new_surge:.2f}) | "
                  f"锁: 官{new_official_lock}s, 离{new_zeroing_unlock}s, 私{new_private_lock}s, 手{new_manual_override}s | "
                  f"隐退: {new_delay}s")
        log_event(CAT_SYSTEM, "全自动分流算法所有参数被修改", detail)

        # 4. 同步至实时生效的控制器
        parent_mw = self.window()
        if hasattr(parent_mw, 'switch_controller') and parent_mw.switch_controller:
            parent_mw.switch_controller.update_config(self.config)
            parent_mw.switch_controller._update_floating_ball_status(
                is_private=getattr(parent_mw.switch_controller, '_current_is_private', False), 
                reason="算法配置已更新"
            )

        QMessageBox.information(self, u"保存成功", u"分流算法参数已保存并立即生效！")
