"""
自动切换算法设置页面 (Auto Switch Algorithm Settings)
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, 
    QDoubleSpinBox, QPushButton, QCheckBox, QFormLayout, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt
from config import save_config
from core.app_logger import log_event, CAT_SYSTEM


class SwitchSettingsWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)

        # 标题区
        lbl_title = QLabel(u"🤖 全自动分流算法设置")
        lbl_title.setStyleSheet("font-size: 26px; font-weight: 900; color: #F8FAFC;")
        root.addWidget(lbl_title)

        lbl_sub = QLabel(u"设置按比例自动截留、轻量小单过滤门限、双系统自动跳转延时等高级参数。")
        lbl_sub.setStyleSheet("font-size: 14px; color: #94A3B8; margin-bottom: 20px;")
        root.addWidget(lbl_sub)

        # 表单区
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
            QSpinBox, QDoubleSpinBox {
                background-color: #0F172A; color: #F8FAFC;
                border: 1px solid #475569; border-radius: 6px;
                padding: 8px 12px; font-size: 16px; font-weight: bold;
                min-width: 140px;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button, 
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                width: 30px;
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
        self.sp_ratio = QSpinBox()
        self.sp_ratio.setRange(0, 100)
        self.sp_ratio.setSuffix(" %")
        form_layout.addRow(QLabel(u"目标私域截留比例:"), self.sp_ratio)

        # 3. 门限过滤
        self.sp_weight = QDoubleSpinBox()
        self.sp_weight.setRange(0.00, 5.00)
        self.sp_weight.setSingleStep(0.05)
        self.sp_weight.setSuffix(" kg")
        form_layout.addRow(QLabel(u"轻量单切回门限:"), self.sp_weight)
        
        lbl_weight_tip = QLabel(u"低于该重量的单子一律判定为小单/加菜，自动分配给官方收银机。")
        lbl_weight_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal; border: none;")
        form_layout.addRow(QLabel(), lbl_weight_tip)

        # 4. 官方界面连单锁定 (60s)
        self.sp_official_lock = QSpinBox()
        self.sp_official_lock.setRange(0, 300)
        self.sp_official_lock.setSuffix(u" 秒")
        form_layout.addRow(QLabel(u"官方界面连单保护时长:"), self.sp_official_lock)

        # 5. 称重归零解锁判定 (5s)
        self.sp_zeroing_unlock = QSpinBox()
        self.sp_zeroing_unlock.setRange(1, 60)
        self.sp_zeroing_unlock.setSuffix(u" 秒")
        form_layout.addRow(QLabel(u"称重归零离场解锁判定:"), self.sp_zeroing_unlock)
        
        lbl_zeroing_tip = QLabel(u"当秤上重量归零并保持该时长后，自动解除上方设定的官方连单保护锁。")
        lbl_zeroing_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal; border: none;")
        form_layout.addRow(QLabel(), lbl_zeroing_tip)

        # 6. 私域死锁超时 (300s)
        self.sp_private_lock = QSpinBox()
        self.sp_private_lock.setRange(10, 3600)
        self.sp_private_lock.setSuffix(u" 秒")
        form_layout.addRow(QLabel(u"私域购物车超时清理:"), self.sp_private_lock)
        
        lbl_private_tip = QLabel(u"若私域购物车有菜品但长期未结账超过此时长，自动清空以释放连单锁。")
        lbl_private_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal; border: none;")
        form_layout.addRow(QLabel(), lbl_private_tip)

        # 7. 延时隐退
        self.sp_delay = QSpinBox()
        self.sp_delay.setRange(0, 30)
        self.sp_delay.setSuffix(u" 秒")
        form_layout.addRow(QLabel(u"出票后自动隐退延时:"), self.sp_delay)

        root.addWidget(form_frame)

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
        root.addStretch()

    def _load_config(self):
        self.chk_enabled.setChecked(self.config.get("auto_switch_enabled", True))
        self.sp_ratio.setValue(int(self.config.get("private_ratio_percent", 70)))
        self.sp_weight.setValue(float(self.config.get("min_private_weight_kg", 0.25)))
        self.sp_official_lock.setValue(int(self.config.get("official_lock_sec", 60)))
        self.sp_zeroing_unlock.setValue(int(self.config.get("zeroing_unlock_sec", 5)))
        self.sp_private_lock.setValue(int(self.config.get("private_lock_sec", 300)))
        self.sp_delay.setValue(int(self.config.get("auto_hide_delay_sec", 3)))

    def _on_save(self):
        # 1. 获取新值
        new_enabled = self.chk_enabled.isChecked()
        new_ratio = self.sp_ratio.value()
        new_weight = self.sp_weight.value()
        new_official_lock = self.sp_official_lock.value()
        new_zeroing_unlock = self.sp_zeroing_unlock.value()
        new_private_lock = self.sp_private_lock.value()
        new_delay = self.sp_delay.value()

        # 2. 更新 config
        self.config["auto_switch_enabled"] = new_enabled
        self.config["private_ratio_percent"] = new_ratio
        self.config["min_private_weight_kg"] = new_weight
        self.config["official_lock_sec"] = new_official_lock
        self.config["zeroing_unlock_sec"] = new_zeroing_unlock
        self.config["private_lock_sec"] = new_private_lock
        self.config["auto_hide_delay_sec"] = new_delay
        
        save_config(self.config)

        # 3. 记录日志
        detail = (f"开关: {'开' if new_enabled else '关'} | "
                  f"截留比: {new_ratio}% | "
                  f"门限: {new_weight:.2f}kg | "
                  f"官方锁: {new_official_lock}s | "
                  f"离场判定: {new_zeroing_unlock}s | "
                  f"私域清理: {new_private_lock}s | "
                  f"隐退延时: {new_delay}s")
        log_event(CAT_SYSTEM, "全自动分流算法参数被修改", detail)

        # 4. 同步至实时生效的控制器
        parent_mw = self.window()
        if hasattr(parent_mw, 'switch_controller') and parent_mw.switch_controller:
            parent_mw.switch_controller.update_config(self.config)
            parent_mw.switch_controller._update_floating_ball_status(
                is_private=getattr(parent_mw.switch_controller, '_current_is_private', False), 
                reason="算法配置已更新"
            )

        QMessageBox.information(self, u"保存成功", u"分流算法参数已保存并立即生效！")
