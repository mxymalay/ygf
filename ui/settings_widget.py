"""
系统设置界面 — 高端左侧导航栏 + 卡片化极简 UI
PyQt5 + Python 3.8 兼容
"""
import os
import re
import hashlib
import shutil
import json
import html

from PyQt5.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QMessageBox, QScrollArea, QStackedWidget, QButtonGroup,
    QFileDialog, QProgressBar, QApplication, QCheckBox, QPlainTextEdit,
    QTextBrowser, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSizePolicy
)
from PyQt5.QtCore import Qt, QUrl, QObject, QThread, QTimer, QDateTime, QSize, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QKeySequence, QDesktopServices, QIcon, QPixmap, QImage, QPainter

from config import (
    BASE_DIR, DATA_DIR, save_config, reset_module_config, reset_all_config,
    export_config_bundle, import_config_bundle, backup_config_bundle,
    APP_LOGO_PRESETS, APP_CATEGORY_OPTIONS, app_category_for_icon, app_logo_path,
)
from utils.port_scanner import scan_printers
from utils.window_utils import (
    apply_official_window_selection,
    find_official_window_info,
    is_official_window_configured,
)
from core.printer_relay_mode import (
    MODE_COMPATIBILITY,
    MODE_POLICY_AUTO,
    MODE_POLICY_FORCE_COMPATIBILITY,
    mode_label,
    validate_relay_config,
)
from core.shop_catalog import get_shop_categories, save_shop_categories, default_flavor_options


SQB_INSTALLER_NAME = u"PC收款安装包v4.0.4.exe"
SQB_INSTALLER_SHA256 = "666EFBA745C7D20D33C22B65E765B027D431E32B7C8CAA4BF8B65A86AD6F15AC"


class _MaintenanceWorker(QObject):
    """Run an elevated driver/port operation away from the UI thread."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    @pyqtSlot()
    def run(self):
        try:
            self.succeeded.emit(self.operation())
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)


class _MaintenanceBusyDialog(QDialog):
    """Touch-friendly animated dialog shown while com0com is being changed."""

    _FRAMES = (u"◐", u"◓", u"◑", u"◒")

    def __init__(self, title, message, parent=None, stages=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        # Never keep this dialog above Windows installer/UAC prompts.  On a
        # fullscreen Win7 POS that made the required driver confirmation
        # visible but impossible to click.
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumWidth(500)
        self.setStyleSheet(
            "QDialog { background: #172136; border: 2px solid #7C3AED; border-radius: 16px; }"
            "QLabel { color: #F8FAFC; background: transparent; border: none; }"
            "QProgressBar { background: #0F172A; border: none; border-radius: 4px; height: 8px; }"
            "QProgressBar::chunk { background: #8B5CF6; border-radius: 4px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        self.lbl_spinner = QLabel(self._FRAMES[0])
        self.lbl_spinner.setAlignment(Qt.AlignCenter)
        self.lbl_spinner.setStyleSheet(
            "color: #C4B5FD; font-size: 42px; font-weight: 900; border: none;"
        )
        layout.addWidget(self.lbl_spinner)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 21px; font-weight: 900;")
        layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("color: #CBD5E1; font-size: 15px;")
        layout.addWidget(message_label)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        layout.addWidget(progress)

        self.lbl_stage = QLabel("")
        self.lbl_stage.setWordWrap(True)
        self.lbl_stage.setStyleSheet(
            "color: #E9D5FF; background: #24144A; border: 1px solid #6D28D9; "
            "border-radius: 8px; padding: 10px 12px; font-size: 15px; font-weight: bold;"
        )
        layout.addWidget(self.lbl_stage)

        self.txt_stage_log = QPlainTextEdit()
        self.txt_stage_log.setReadOnly(True)
        self.txt_stage_log.setMinimumHeight(84)
        self.txt_stage_log.setMaximumHeight(126)
        self.txt_stage_log.setStyleSheet(
            "QPlainTextEdit { color: #CBD5E1; background: #0F172A; border: 1px solid #334155; "
            "border-radius: 8px; padding: 6px; font-size: 12px; }"
        )
        layout.addWidget(self.txt_stage_log)

        hint = QLabel(
            u"正在执行系统驱动/虚拟串口操作，请勿关闭程序或拔出设备。\n"
            u"如 Windows 弹出安装确认，请点击下方按钮后在 Windows 对话框继续。"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #FDE68A; font-size: 13px;")
        layout.addWidget(hint)

        self.btn_minimize_for_windows = QPushButton(u"最小化 POS，继续 Windows 安装确认")
        self.btn_minimize_for_windows.setMinimumHeight(52)
        self.btn_minimize_for_windows.setStyleSheet(
            "QPushButton { background: #334155; color: #F8FAFC; border: 1px solid #64748B; "
            "border-radius: 10px; font-size: 15px; font-weight: bold; padding: 8px 16px; }"
            "QPushButton:pressed { background: #475569; }"
        )
        self.btn_minimize_for_windows.clicked.connect(self._minimize_for_windows_prompt)
        layout.addWidget(self.btn_minimize_for_windows)

        self._frame_index = 0
        self._finishing = False
        self._minimized_for_windows_prompt = False
        self._parent_was_fullscreen = False
        self._stages = [str(item) for item in (stages or []) if str(item).strip()]
        if not self._stages:
            self._stages = [message, u"等待 Windows 驱动、串口或服务返回", u"正在核对操作结果"]
        self._stage_index = 0
        self._timer = QTimer(self)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._advance_frame)
        self._stage_timer = QTimer(self)
        self._stage_timer.setInterval(2600)
        self._stage_timer.timeout.connect(self._advance_stage)
        self.set_stage(self._stages[0])

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()
        self._stage_timer.start()

    def closeEvent(self, event):
        if self._timer.isActive() and not self._finishing:
            event.ignore()
            return
        super().closeEvent(event)

    def finish(self):
        self._finishing = True
        self._timer.stop()
        self._stage_timer.stop()
        # Allow the controlled close after the operation has completed.
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.done(0)
        # This dialog is shown with ApplicationModal (rather than exec_()).
        # Explicit deletion is required on Qt 5/Win7 to remove it from
        # QApplication.activeModalWidget(); hiding alone can leave an
        # invisible modal window swallowing every click and scroll event.
        self.deleteLater()

    def _minimize_for_windows_prompt(self):
        """Yield the foreground to an installer window without cancelling work."""
        parent_window = self.window()
        self._minimized_for_windows_prompt = True
        self._parent_was_fullscreen = bool(
            parent_window is not None and parent_window.isFullScreen()
        )
        # A hidden application-modal dialog can otherwise remain the active
        # modal widget on Qt 5/Win7 and keep swallowing the installer click.
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.hide()
        if parent_window is not None:
            parent_window.showMinimized()

    def restore_parent_after_windows_prompt(self):
        if not self._minimized_for_windows_prompt:
            return
        parent_window = self.window()
        self._minimized_for_windows_prompt = False
        if parent_window is None:
            return
        if self._parent_was_fullscreen:
            parent_window.showFullScreen()
        else:
            parent_window.showNormal()
        parent_window.raise_()
        parent_window.activateWindow()

    def _advance_frame(self):
        self._frame_index = (self._frame_index + 1) % len(self._FRAMES)
        self.lbl_spinner.setText(self._FRAMES[self._frame_index])

    def set_stage(self, stage):
        """Show the current maintenance phase and retain a screenshotable log."""
        text = str(stage or "").strip()
        if not text:
            return
        self.lbl_stage.setText(u"当前步骤：" + text)
        stamp = QDateTime.currentDateTime().toString("HH:mm:ss")
        lines = self.txt_stage_log.toPlainText().splitlines()
        lines.append(u"[%s] %s" % (stamp, text))
        self.txt_stage_log.setPlainText("\n".join(lines[-6:]))
        self.txt_stage_log.verticalScrollBar().setValue(
            self.txt_stage_log.verticalScrollBar().maximum()
        )

    def stage_log(self):
        return self.txt_stage_log.toPlainText()

    def _advance_stage(self):
        if len(self._stages) < 2:
            return
        self._stage_index = (self._stage_index + 1) % len(self._stages)
        self.set_stage(self._stages[self._stage_index])


class HotKeyRecorderEdit(QLineEdit):
    """按键实时录制框：鼠标点击后直接在键盘上敲击组合键 (如 Shift+Q 或 F12) 自动录制"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(u"点击此处并按快捷键 (如 Shift+Q 或 F12)")
        self.setStyleSheet("""
            QLineEdit {
                background-color: #0F172A;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 2px solid #38BDF8;
                background-color: #1E293B;
            }
        """)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.AltModifier:
            parts.append("Alt")

        key_str = ""
        if Qt.Key_F1 <= key <= Qt.Key_F12:
            key_str = f"F{key - Qt.Key_F1 + 1}"
        else:
            txt = event.text().upper()
            if txt and (txt.isalnum() or txt in "+-*/"):
                key_str = txt
            else:
                key_str = QKeySequence(key).toString().upper()

        if key_str:
            parts.append(key_str)
            hk_text = "+".join(parts)
            self.setText(hk_text)


class SettingsWidget(QWidget):
    """系统设置界面"""

    NAV_ITEMS = [
        ("biz", u"🏪  店铺与计价"),
        ("sys", u"⚙️  系统与流转"),
        ("scale", u"⚖️  电子秤设置"),
        ("bridge", u"⇄  POS 称桥接"),
        ("sqb", u"💵  收钱吧插件"),
        ("relay", u"↔  打印机中继"),
        ("printer", u"♨  打印纸格式"),
        ("danger", u"⚠️  还原与重置"),
    ]

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.nav_buttons = []
        # Keep the last rendered batch while the relay status file is being
        # atomically replaced.  A 1.2s poll can briefly read an empty file;
        # that transient must not make the monitor flash back to "no data".
        self._relay_live_html_cache = ""
        self._relay_live_started_at = ""
        self._relay_live_records_cache = []
        self._relay_live_records_signature = ""
        self._build_ui()
        # Keep the relay page live while the operator is preparing the
        # official POS test.  The poll only reads the small status JSON and
        # never starts/stops a listener or writes configuration.
        self._relay_status_timer = QTimer(self)
        self._relay_status_timer.setInterval(1200)
        self._relay_status_timer.timeout.connect(self._refresh_relay_status)
        self._relay_status_timer.start()

    def _make_label(self, text):
        """统一生成适合触屏收银机阅读的字段标签。"""
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setStyleSheet("color: #CBD5E1; font-size: 16px; font-weight: 700; background: transparent; padding-right: 8px;")
        return lbl

    def _style_save_btn(self, btn):
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(60)
        btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10B981);
                color: #FFFFFF;
                font-size: 17px;
                font-weight: bold;
                padding: 14px 28px;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover {
                background: #10B981;
            }
            QPushButton:pressed {
                background: #047857;
            }
        """)

    def _style_touch_action_btn(self, btn, tone="secondary"):
        """为设置页的非保存操作提供足够大的触屏点击区域。"""
        palettes = {
            "secondary": ("#334155", "#F8FAFC", "#475569", "#475569"),
            "blue": ("#0369A1", "#FFFFFF", "#0284C7", "#0284C7"),
            "purple": ("#6D28D9", "#FFFFFF", "#7C3AED", "#7C3AED"),
            "danger": ("#7F1D1D", "#FEE2E2", "#DC2626", "#991B1B"),
        }
        background, color, border, hover = palettes.get(tone, palettes["secondary"])
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(56)
        btn.setStyleSheet(
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: 10px; padding: 12px 18px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background: %s; }"
            "QPushButton:pressed { padding-top: 14px; padding-bottom: 10px; }"
            % (background, color, border, hover)
        )

    def _create_section_card(self, title_icon, title_text, subtitle_text=""):
        """创建一个高端卡片容器"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame#SettingCard {
                background-color: #1E293B;
                border-radius: 16px;
                border: 1px solid #334155;
            }
        """)
        card.setObjectName("SettingCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(18)

        # 头部标题
        header_box = QVBoxLayout()
        header_box.setSpacing(6)
        
        lbl_head = QLabel(f"{title_icon} {title_text}")
        lbl_head.setStyleSheet("font-size: 24px; font-weight: 900; color: #F8FAFC; border: none; background: transparent;")
        header_box.addWidget(lbl_head)

        if subtitle_text:
            lbl_sub = QLabel(subtitle_text)
            lbl_sub.setStyleSheet("font-size: 15px; color: #94A3B8; border: none; background: transparent;")
            header_box.addWidget(lbl_sub)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #334155; border: none; min-height: 1px; max-height: 1px;")

        card_layout.addLayout(header_box)
        card_layout.addWidget(line)

        return card, card_layout

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ════════════════════════════════════════════════════════════
        # 左侧导航栏 (Left Sidebar)
        # ════════════════════════════════════════════════════════════
        sidebar = QFrame()
        # Keep enough room for the labels while leaving the actual settings
        # form usable on the narrow Win7 POS display.
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet("""
            QFrame#SettingsSidebar {
                background-color: #0F172A;
                border-right: 1px solid #1E293B;
            }
            QLabel {
                background: transparent;
            }
        """)
        sidebar.setObjectName("SettingsSidebar")

        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(14, 18, 14, 18)
        sb_layout.setSpacing(8)

        # 侧边栏标题
        lbl_sb_title = QLabel(u"⚙️ 系统设置")
        lbl_sb_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #F8FAFC; padding-left: 8px; margin-bottom: 8px;")
        sb_layout.addWidget(lbl_sb_title)

        # 导航按钮组
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for idx, (nav_id, label) in enumerate(self.NAV_ITEMS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(56)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 12px 14px;
                    font-size: 17px;
                    font-weight: 600;
                    color: #94A3B8;
                    background-color: transparent;
                    border-radius: 10px;
                    border: none;
                }
                QPushButton:hover {
                    color: #F1F5F9;
                    background-color: #1E293B;
                }
                QPushButton:checked {
                    color: #38BDF8;
                    background-color: #1E293B;
                    font-weight: bold;
                    border-left: 4px solid #38BDF8;
                }
            """)
            self.btn_group.addButton(btn, idx)
            self.nav_buttons.append(btn)
            sb_layout.addWidget(btn)

        sb_layout.addStretch()

        main_layout.addWidget(sidebar)

        # ════════════════════════════════════════════════════════════
        # 右侧 QStackedWidget (各个设置卡片)
        # ════════════════════════════════════════════════════════════
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("""
            QStackedWidget {
                background-color: #0B1120;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 16px;
                background: transparent;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 12px 16px;
                font-size: 16px;
                min-height: 30px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #38BDF8;
                background-color: #0F172A;
            }
            /* Native arrows are unreliable on Win7; the shared touch style
               below supplies explicit buttons and CSS triangle arrows. */
        """)

        # 1. 店铺与计价设置页
        self.stacked_widget.addWidget(self._build_biz_page())
        # 2. 系统与流转设置页
        self.stacked_widget.addWidget(self._build_sys_page())
        # 3. 电子秤设置页
        self.stacked_widget.addWidget(self._build_scale_page())
        # 4. 官方/私有 POS 共享电子秤
        self.stacked_widget.addWidget(self._build_bridge_page())
        # 5. 收钱吧设置页
        self.stacked_widget.addWidget(self._build_sqb_page())
        # 6. 打印机中继页
        self.stacked_widget.addWidget(self._build_relay_page())
        # 7. 打印纸格式页
        self.stacked_widget.addWidget(self._build_printer_page())
        # 8. 重置与恢复设置页
        self.stacked_widget.addWidget(self._build_danger_page())

        main_layout.addWidget(self.stacked_widget, stretch=1)

        # 绑定导航栏切换
        self.btn_group.buttonClicked[int].connect(self._on_settings_page_changed)
        self.nav_buttons[0].setChecked(True)

        # 全局触控下拉框、选择框与数字框统一美化
        from ui.styles import apply_touch_combo_style, apply_touch_checkbox_style, apply_touch_spinbox_style
        from PyQt5.QtWidgets import QCheckBox
        for combo in self.findChildren(QComboBox):
            combo.setMinimumHeight(56)
            apply_touch_combo_style(combo, item_height=60)
        for chk in self.findChildren(QCheckBox):
            apply_touch_checkbox_style(chk)
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            spin.setMinimumHeight(56)
            apply_touch_spinbox_style(spin)
        for text_input in self.findChildren(QLineEdit):
            # QComboBox/QSpinBox expose an internal QLineEdit.  Styling that
            # child as a standalone field creates a second rectangle which
            # can cover the parent's lower border on Win7.
            if isinstance(text_input.parentWidget(), (QComboBox, QSpinBox, QDoubleSpinBox)):
                continue
            text_input.setMinimumHeight(56)
            text_input.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for action_btn in self.findChildren(QPushButton):
            if action_btn not in self.nav_buttons:
                action_btn.setMinimumHeight(max(action_btn.minimumHeight(), 54))

        self._disable_wheel_events()

    def _wrap_in_scroll(self, card_widget, menu_items=None):
        """将卡片包裹在滚动区域中，并提供固定在顶部的三级导航。"""
        outer = QWidget()
        outer.setStyleSheet("background: #0B1120;")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0B1120; }")

        # 三级菜单固定在页面顶端，只负责定位，不改变原有配置控件和保存逻辑。
        if menu_items:
            menu_frame = QFrame()
            menu_frame.setObjectName("SettingsThirdLevelMenu")
            menu_frame.setStyleSheet(
                "QFrame#SettingsThirdLevelMenu { background: #0F172A; border-bottom: 1px solid #1E293B; }"
                "QPushButton { background: transparent; color: #94A3B8; border: none; "
                "border-bottom: 3px solid transparent; border-radius: 0; padding: 10px 16px; "
                "font-size: 15px; font-weight: 700; }"
                "QPushButton:hover { background: #1E293B; color: #F8FAFC; }"
                "QPushButton:checked { background: #172554; color: #7DD3FC; border-bottom-color: #38BDF8; }"
            )
            menu_layout = QHBoxLayout(menu_frame)
            menu_layout.setContentsMargins(20, 10, 20, 10)
            menu_layout.setSpacing(8)
            menu_buttons = []
            visibility_state = {}
            active_indices = set()

            def first_widget(item):
                if item is None:
                    return None
                widget = item.widget()
                if widget is not None:
                    return widget
                child_layout = item.layout()
                if child_layout is None:
                    return None
                for child_index in range(child_layout.count()):
                    found = first_widget(child_layout.itemAt(child_index))
                    if found is not None:
                        return found
                return None

            def set_item_visible(item, visible):
                if item is None:
                    return
                widget = item.widget()
                if widget is not None:
                    if visible:
                        widget.setVisible(visibility_state.get(widget, True))
                    else:
                        widget.setVisible(False)
                    return
                child_layout = item.layout()
                if child_layout is None:
                    return
                for child_index in range(child_layout.count()):
                    set_item_visible(child_layout.itemAt(child_index), visible)

            def remember_item_visibility(item):
                if item is None:
                    return
                widget = item.widget()
                if widget is not None:
                    visibility_state[widget] = not widget.isHidden()
                    return
                child_layout = item.layout()
                if child_layout is not None:
                    for child_index in range(child_layout.count()):
                        remember_item_visibility(child_layout.itemAt(child_index))

            def scroll_to(target_indices, button, ensure_visible=True):
                nonlocal active_indices
                if isinstance(target_indices, (int, str)):
                    target_indices = [target_indices]
                target_indices = {int(index) for index in (target_indices or [])}
                card_layout = card_widget.layout()
                target = None
                if card_layout is not None:
                    # 保存当前分区内控件自己的可见状态（例如电子秤页面
                    # 根据数据源动态隐藏 COM 端口），切换菜单时不覆盖它。
                    for index in active_indices:
                        if 0 <= index < card_layout.count():
                            remember_item_visibility(card_layout.itemAt(index))
                    # 标题和分割线一直保留；正文只显示当前三级菜单分区。
                    for index in range(2, card_layout.count()):
                        item = card_layout.itemAt(index)
                        set_item_visible(item, index in target_indices)
                        if target is None and index in target_indices:
                            target = first_widget(item)
                    active_indices = target_indices
                if target is not None and ensure_visible:
                    scroll.ensureWidgetVisible(target, 0, 12)
                for menu_button in menu_buttons:
                    menu_button.setChecked(menu_button is button)

            for title, target_indices in menu_items:
                button = QPushButton(title)
                button.setCheckable(True)
                button.setMinimumHeight(44)
                button.clicked.connect(
                    lambda checked=False, target=target_indices, btn=button: scroll_to(target, btn)
                )
                menu_layout.addWidget(button, 1)
                menu_buttons.append(button)
            menu_layout.addStretch()
            if menu_buttons:
                card_layout = card_widget.layout()
                if card_layout is not None:
                    for index in range(2, card_layout.count()):
                        remember_item_visibility(card_layout.itemAt(index))
                scroll_to(menu_items[0][1], menu_buttons[0], ensure_visible=False)
            outer_layout.addWidget(menu_frame)

        wrapper = QWidget()
        # Let the settings page follow the available viewport.  Long labels
        # or previews must not widen the whole second-level page when the
        # outer horizontal scrollbar is disabled.
        wrapper.setMinimumWidth(0)
        wrapper.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        wrapper.setStyleSheet("background: transparent;")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(20, 20, 20, 20)
        wrapper_layout.addWidget(card_widget)
        wrapper_layout.addStretch()

        scroll.setWidget(wrapper)
        outer_layout.addWidget(scroll, stretch=1)
        return outer

    # ────────────────────────────────────────────────────────────
    # 页面 3: 电子秤数据源设置
    # ────────────────────────────────────────────────────────────
    def _build_scale_page(self):
        card, layout = self._create_section_card(
            u"⚖️", u"电子秤使用方式", u"先选择实际使用方式；只有需要串口时才显示端口"
        )
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"数据来源："), 0, 0)
        self.cmb_scale_source = QComboBox()
        self.cmb_scale_source.addItem(u"跟随官方 POS 读取重量（无需选择 COM，推荐）", "official")
        self.cmb_scale_source.addItem(u"本 POS 独占物理电子秤（不能与官方 POS 同时读秤）", "direct")
        self.cmb_scale_source.addItem(u"官方 POS 与本 POS 同时读秤（先初始化 POS 称桥接）", "bridge")
        source = self.config.get("scale_source", "official")
        if source == "com":
            connection_mode = self.config.get("scale_connection_mode", "direct")
            self.cmb_scale_source.setCurrentIndex(2 if connection_mode == "bridge" else 1)
        self.cmb_scale_source.currentIndexChanged.connect(self._on_scale_source_changed)
        grid.addWidget(self.cmb_scale_source, 0, 1, 1, 2)

        # COM口配置 (仅串口模式可见)
        self.lbl_scale_port = self._make_label(u"电子秤端口：")
        grid.addWidget(self.lbl_scale_port, 1, 0)
        self.cmb_scale_port = QComboBox()
        self.cmb_scale_port.setEditable(True)
        self._refresh_scale_com_ports()
        grid.addWidget(self.cmb_scale_port, 1, 1)

        self.btn_refresh_scale_ports = QPushButton(u"🔄 扫描COM端口")
        self._style_touch_action_btn(self.btn_refresh_scale_ports)
        self.btn_refresh_scale_ports.clicked.connect(lambda: self._refresh_scale_com_ports(show_toast=True))
        grid.addWidget(self.btn_refresh_scale_ports, 1, 2)

        self.lbl_scale_baud = self._make_label(u"波特率：")
        grid.addWidget(self.lbl_scale_baud, 2, 0)
        self.cmb_scale_baud = QComboBox()
        self.cmb_scale_baud.addItems(["2400", "4800", "9600", "19200", "38400", "115200"])
        cur_baud = str(self.config.get("scale_baudrate", 9600))
        self.cmb_scale_baud.setCurrentText(cur_baud)
        grid.addWidget(self.cmb_scale_baud, 2, 1, 1, 2)

        self.lbl_official_log_dir = self._make_label(u"官方日志目录（可选）：")
        grid.addWidget(self.lbl_official_log_dir, 3, 0)
        self.txt_official_log_dir = QLineEdit(self.config.get("official_pos_log_dir", ""))
        self.txt_official_log_dir.setPlaceholderText(u"留空自动兼容旧目录；官方升级后在此选择 serial 文件夹")
        grid.addWidget(self.txt_official_log_dir, 3, 1)
        self.btn_pick_official_log_dir = QPushButton(u"选择目录")
        self._style_touch_action_btn(self.btn_pick_official_log_dir, "blue")
        self.btn_pick_official_log_dir.clicked.connect(self._pick_official_log_dir)
        grid.addWidget(self.btn_pick_official_log_dir, 3, 2)

        # 提示信息
        self.lbl_scale_hint = QLabel("")
        self.lbl_scale_hint.setWordWrap(True)
        self.lbl_scale_hint.setStyleSheet("color: #CBD5E1; font-size: 15px; padding: 14px 16px; background: #0F172A; border-radius: 10px; border: 1px solid #1E293B;")
        grid.addWidget(self.lbl_scale_hint, 5, 0, 1, 3)

        # 数据源、COM 端口和官方日志目录所在的三级页面必须直接提供
        # 保存入口放在“数据源与端口”页；检测页只负责验证状态，避免重复保存。
        self.btn_save_scale_source = QPushButton(u"💾 保存数据源与端口")
        self._style_save_btn(self.btn_save_scale_source)
        self.btn_save_scale_source.clicked.connect(self._on_save_scale)
        grid.addWidget(self.btn_save_scale_source, 6, 0, 1, 3)

        layout.addLayout(grid)

        btn_box = QGridLayout()
        btn_box.setHorizontalSpacing(12)
        btn_box.setVerticalSpacing(12)
        btn_box.setColumnStretch(0, 1)
        btn_box.setColumnStretch(1, 1)

        # Source-aware test action: official mode verifies the live official
        # log, direct mode tests the physical COM, and bridge mode tests the
        # private virtual channel.  The recommended official mode must not
        # leave the operator without a verification button.
        self.btn_test_scale_com = QPushButton(u"⚡ 检测官方读数")
        self._style_touch_action_btn(self.btn_test_scale_com, "blue")
        self.btn_test_scale_com.clicked.connect(self._test_selected_scale_source)
        btn_box.addWidget(self.btn_test_scale_com, 0, 0)

        self.btn_go_scale_bridge = QPushButton(u"前往 POS 称桥接")
        self._style_touch_action_btn(self.btn_go_scale_bridge, "purple")
        self.btn_go_scale_bridge.clicked.connect(lambda: self._open_settings_page(3))
        btn_box.addWidget(self.btn_go_scale_bridge, 0, 1)

        layout.addLayout(btn_box)

        # 初始化显示/隐藏
        self._on_scale_source_changed(self.cmb_scale_source.currentIndex())

        return self._wrap_in_scroll(card, [(u"数据源与端口", [2]), (u"检测与状态", [3])])

    # ────────────────────────────────────────────────────────────
    # 页面 4: 官方 / 私有 POS 共享电子秤
    # ────────────────────────────────────────────────────────────
    def _build_bridge_page(self):
        card, layout = self._create_section_card(
            u"⇄", u"POS 称桥接", u"让官方 POS 和本 POS 同时读取同一台物理电子秤"
        )

        overview = QLabel(
            u"<b>什么时候使用本页？</b><br>"
            u"只有“官方 POS 和本 POS 必须同时读取同一台电子秤”时才需要桥接。"
            u"如果本 POS 跟随官方 POS 取重量，或只让本 POS 独占电子秤，请返回“电子秤设置”，无需配置本页。"
            u"<br><b>本页只处理电子秤，与收钱吧完全无关。</b>"
        )
        overview.setWordWrap(True)
        overview.setStyleSheet(
            "color: #E0F2FE; background: #0C4A6E; border: 1px solid #0284C7; "
            "border-radius: 12px; padding: 16px; font-size: 16px;"
        )
        layout.addWidget(overview)

        self.lbl_scale_bridge_overall_status = QLabel("")
        self.lbl_scale_bridge_overall_status.setWordWrap(True)
        self.lbl_scale_bridge_overall_status.setStyleSheet(
            "color: #FDE68A; background: #422006; border: 1px solid #A16207; "
            "border-radius: 12px; padding: 14px 16px; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(self.lbl_scale_bridge_overall_status)

        def step_panel(number, title, description):
            panel = QFrame()
            panel.setObjectName("BridgeStep%s" % number)
            panel.setStyleSheet(
                "QFrame { background: #132235; border: 1px solid #334155; border-radius: 12px; }"
                "QLabel { border: none; background: transparent; }"
            )
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(18, 16, 18, 16)
            panel_layout.setSpacing(12)
            title_label = QLabel(u"步骤 %s　%s" % (number, title))
            title_label.setStyleSheet("font-size: 18px; color: #60A5FA; font-weight: 900;")
            panel_layout.addWidget(title_label)
            description_label = QLabel(description)
            description_label.setWordWrap(True)
            description_label.setStyleSheet("color: #CBD5E1; font-size: 15px;")
            panel_layout.addWidget(description_label)
            return panel, panel_layout

        # Step 1: physical device discovery and confirmed protocol test.
        step1, step1_layout = step_panel(
            1,
            u"选择并测试物理电子秤",
            u"正式安装必须先选择并测试 DIBAL ACS-G315。开发机没有真实电子秤时，请使用下方的无秤开发验证；它会启动开发模拟秤和真实 ScaleBridge 服务。",
        )
        physical_grid = QGridLayout()
        physical_grid.setHorizontalSpacing(12)
        physical_grid.setVerticalSpacing(12)
        physical_grid.setColumnStretch(0, 1)
        physical_grid.addWidget(self._make_label(u"物理秤端口："), 0, 0)
        self.cmb_bridge_physical_port = QComboBox()
        self.cmb_bridge_physical_port.setEditable(True)
        physical_grid.addWidget(self.cmb_bridge_physical_port, 1, 0)
        self.btn_refresh_bridge_devices = QPushButton(u"① 识别物理设备")
        self._style_touch_action_btn(self.btn_refresh_bridge_devices, "blue")
        self.btn_refresh_bridge_devices.clicked.connect(self._refresh_scale_bridge_devices)
        physical_grid.addWidget(self.btn_refresh_bridge_devices, 2, 0)
        self.btn_test_bridge_physical = QPushButton(u"② 测试物理秤")
        self._style_touch_action_btn(self.btn_test_bridge_physical, "purple")
        self.btn_test_bridge_physical.clicked.connect(self._test_scale_bridge_physical)
        physical_grid.addWidget(self.btn_test_bridge_physical, 3, 0)
        step1_layout.addLayout(physical_grid)
        layout.addWidget(step1)

        # Step 2: only the two POS-facing endpoints are operator choices.
        step2, step2_layout = step_panel(
            2,
            u"填写准备创建给两个 POS 的端口号",
            u"这里填写的是“希望初始化时新建的虚拟 COM 名称”，不是从当前已有串口中选择。"
            u"端口现在不存在是正常的；官方 POS 和本 POS 必须使用不同的名称。",
        )
        port_grid = QGridLayout()
        port_grid.setHorizontalSpacing(12)
        port_grid.setVerticalSpacing(10)
        port_grid.setColumnStretch(1, 1)
        port_grid.addWidget(self._make_label(u"为官方 POS 创建："), 0, 0)
        self.txt_bridge_official_pos = QLineEdit()
        self.txt_bridge_official_pos.setPlaceholderText("例如 COM2（当前不存在也正常）")
        port_grid.addWidget(self.txt_bridge_official_pos, 0, 1, 1, 3)
        self.txt_bridge_official_peer = QLineEdit(step2)
        self.txt_bridge_official_peer.setReadOnly(True)
        self.txt_bridge_official_peer.hide()
        port_grid.addWidget(self._make_label(u"为本 POS 创建："), 1, 0)
        self.txt_bridge_private_pos = QLineEdit()
        self.txt_bridge_private_pos.setPlaceholderText("例如 COM3（当前不存在也正常）")
        port_grid.addWidget(self.txt_bridge_private_pos, 1, 1, 1, 3)
        self.txt_bridge_private_peer = QLineEdit(step2)
        self.txt_bridge_private_peer.setReadOnly(True)
        self.txt_bridge_private_peer.hide()
        step2_layout.addLayout(port_grid)
        self.btn_save_scale_bridge = QPushButton(u"可选：保存草稿，稍后继续（不会创建端口）")
        self._style_touch_action_btn(self.btn_save_scale_bridge)
        self.btn_save_scale_bridge.clicked.connect(self._save_scale_bridge_config)
        step2_layout.addWidget(self.btn_save_scale_bridge)
        layout.addWidget(step2)

        # Step 3: one explicit button performs the complete idempotent setup.
        step3, step3_layout = step_panel(
            3,
            u"初始化桥接",
            u"建议先完成上方 com0com 驱动安装，再初始化桥接。初始化会测试物理秤、创建两组秤端口、安装并启动 Windows 服务。开发测试会使用模拟秤验证同一条服务链路。",
        )
        driver_hint = QLabel(
            u"首次使用或设备管理器显示黄色叹号时，请先单独安装 com0com 驱动。"
            u"安装只处理驱动，不创建串口、不启动桥接服务；Windows 可能会弹出驱动确认。"
        )
        driver_hint.setWordWrap(True)
        driver_hint.setStyleSheet(
            "color: #FDE68A; background: #422006; border: 1px solid #A16207; "
            "border-radius: 8px; padding: 10px 12px; font-size: 14px;"
        )
        step3_layout.addWidget(driver_hint)
        self.btn_install_com0com = QPushButton(u"③-0 安装 / 检查 com0com 驱动")
        self._style_touch_action_btn(self.btn_install_com0com, "purple")
        self.btn_install_com0com.clicked.connect(self._install_com0com_driver)
        step3_layout.addWidget(self.btn_install_com0com)
        self.lbl_com0com_status = QLabel("")
        self.lbl_com0com_status.setWordWrap(True)
        self.lbl_com0com_status.setStyleSheet(
            "color: #94A3B8; background: #0F172A; border-radius: 8px; padding: 8px 10px; font-size: 13px;"
        )
        step3_layout.addWidget(self.lbl_com0com_status)
        self.btn_initialize_scale_bridge = QPushButton(u"③ 初始化 / 修复 POS 称桥接")
        self._style_save_btn(self.btn_initialize_scale_bridge)
        self.btn_initialize_scale_bridge.clicked.connect(self._initialize_scale_bridge)
        step3_layout.addWidget(self.btn_initialize_scale_bridge)
        self.btn_test_bridge_virtual_only = QPushButton(u"③ 开发测试：模拟秤并启动服务")
        self._style_touch_action_btn(self.btn_test_bridge_virtual_only, "purple")
        self.btn_test_bridge_virtual_only.clicked.connect(self._test_scale_bridge_virtual_only)
        step3_layout.addWidget(self.btn_test_bridge_virtual_only)
        self.lbl_scale_bridge_config = QLabel("")
        self.lbl_scale_bridge_config.setWordWrap(True)
        self.lbl_scale_bridge_config.setStyleSheet(
            "color: #BFDBFE; font-size: 14px; padding: 12px 14px; background: #0F172A; border-radius: 8px;"
        )
        step3_layout.addWidget(self.lbl_scale_bridge_config)
        layout.addWidget(step3)

        # Step 4: acceptance is deliberately split into four visible checks.
        step4, step4_layout = step_panel(
            4,
            u"按顺序验收",
            u"先检查服务与配对，再分别关闭占用对应端口的 POS，测试官方通道和本 POS 通道。四项都通过才算完成。",
        )
        check_grid = QGridLayout()
        check_grid.setHorizontalSpacing(12)
        check_grid.setVerticalSpacing(12)
        self.btn_scale_bridge_status = QPushButton(u"④-1 查看服务状态")
        self._style_touch_action_btn(self.btn_scale_bridge_status)
        self.btn_scale_bridge_status.clicked.connect(self._show_scale_bridge_status)
        check_grid.addWidget(self.btn_scale_bridge_status, 0, 0)
        self.btn_check_scale_bridge_pairs = QPushButton(u"④-2 检查两组端口配对")
        self._style_touch_action_btn(self.btn_check_scale_bridge_pairs)
        self.btn_check_scale_bridge_pairs.clicked.connect(self._check_scale_bridge_pairs)
        check_grid.addWidget(self.btn_check_scale_bridge_pairs, 0, 1)
        self.btn_test_official_scale_channel = QPushButton(u"④-3 测试官方 POS 秤通道")
        self._style_touch_action_btn(self.btn_test_official_scale_channel, "blue")
        self.btn_test_official_scale_channel.clicked.connect(
            lambda _checked=False: self._test_scale_bridge_channel("official")
        )
        check_grid.addWidget(self.btn_test_official_scale_channel, 1, 0)
        self.btn_test_private_scale_channel = QPushButton(u"④-4 测试本 POS 秤通道")
        self._style_touch_action_btn(self.btn_test_private_scale_channel, "blue")
        self.btn_test_private_scale_channel.clicked.connect(
            lambda _checked=False: self._test_scale_bridge_channel("private")
        )
        check_grid.addWidget(self.btn_test_private_scale_channel, 1, 1)
        step4_layout.addLayout(check_grid)

        self.btn_use_scale_bridge = QPushButton(u"⑤ 验收完成，让本 POS 使用桥接端口")
        self._style_save_btn(self.btn_use_scale_bridge)
        self.btn_use_scale_bridge.clicked.connect(self._activate_scale_bridge_for_pos)
        step4_layout.addWidget(self.btn_use_scale_bridge)
        layout.addWidget(step4)

        maintenance = QFrame()
        maintenance.setStyleSheet(
            "QFrame { background: #0F172A; border: 1px solid #334155; border-radius: 10px; }"
        )
        maintenance_layout = QVBoxLayout(maintenance)
        maintenance_title = QLabel(u"维护操作（正常首次安装不需要使用）")
        maintenance_title.setStyleSheet("color: #CBD5E1; font-size: 16px; font-weight: bold; border: none;")
        maintenance_layout.addWidget(maintenance_title)
        maintenance_buttons = QGridLayout()
        maintenance_buttons.setHorizontalSpacing(12)
        maintenance_buttons.setVerticalSpacing(12)
        self.btn_start_scale_bridge = QPushButton(u"启动服务")
        self._style_touch_action_btn(self.btn_start_scale_bridge)
        self.btn_start_scale_bridge.clicked.connect(self._start_scale_bridge_service)
        maintenance_buttons.addWidget(self.btn_start_scale_bridge, 0, 0)
        self.btn_stop_scale_bridge = QPushButton(u"停止服务")
        self._style_touch_action_btn(self.btn_stop_scale_bridge)
        self.btn_stop_scale_bridge.clicked.connect(self._stop_scale_bridge_service)
        maintenance_buttons.addWidget(self.btn_stop_scale_bridge, 0, 1)
        self.btn_export_scale_bridge_diagnostics = QPushButton(u"生成诊断报告")
        self._style_touch_action_btn(self.btn_export_scale_bridge_diagnostics)
        self.btn_export_scale_bridge_diagnostics.clicked.connect(self._export_scale_bridge_diagnostics)
        maintenance_buttons.addWidget(self.btn_export_scale_bridge_diagnostics, 1, 0)
        self.btn_remove_scale_bridge = QPushButton(u"删除 POS 称桥接")
        self._style_touch_action_btn(self.btn_remove_scale_bridge, "danger")
        self.btn_remove_scale_bridge.clicked.connect(self._remove_scale_bridge)
        maintenance_buttons.addWidget(self.btn_remove_scale_bridge, 1, 1)
        maintenance_layout.addLayout(maintenance_buttons)
        layout.addWidget(maintenance)

        self._load_scale_bridge_form()
        self._refresh_com0com_status()
        self._refresh_scale_bridge_overall_status()
        return self._wrap_in_scroll(card, [(u"① 选择物理秤", [2, 3, 4]), (u"② 创建端口", [5]), (u"③ 初始化桥接", [6]), (u"④ 验收", [7]), (u"维护", [8])])

    # ────────────────────────────────────────────────────────────
    # 页面 6: 打印机中继
    # ────────────────────────────────────────────────────────────
    def _build_relay_page(self):
        card, layout = self._create_section_card(
            u"↔", u"打印机中继", u"统一管理中继端口、Windows 队列、实体输出打印机和识别/测试状态"
        )

        def step_panel(number, title, description):
            panel = QFrame()
            panel.setObjectName("RelayStep%s" % number)
            panel.setStyleSheet(
                "QFrame { background: #132235; border: 1px solid #334155; border-radius: 12px; }"
                "QLabel { border: none; background: transparent; }"
            )
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(18, 16, 18, 16)
            panel_layout.setSpacing(12)
            title_label = QLabel(u"步骤 %s　%s" % (number, title))
            title_label.setStyleSheet("font-size: 18px; color: #60A5FA; font-weight: 900;")
            panel_layout.addWidget(title_label)
            description_label = QLabel(description)
            description_label.setWordWrap(True)
            description_label.setStyleSheet("color: #CBD5E1; font-size: 15px;")
            panel_layout.addWidget(description_label)
            return panel, panel_layout

        intro = QLabel(
            u"推荐按页面顺序完成：先配置中继与实体输出，再保存并检查队列，随后打印真实测试单，最后确认识别结果。\n"
            u"实体打印方式表示中继向实体打印机输出的通道，不是官方 POS 连接中继的方式。"
            u"兼容/增强模式是全局运行状态，会同时影响打印识别和分流设置；本页只负责中继条件和模式策略。"
            u"识别不到可靠付款状态时，系统会继续使用兼容模式，不会把打印任务当成结账成功。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #BAE6FD; background: #082F49; border: 1px solid #0369A1; border-radius: 10px; padding: 14px;")
        layout.addWidget(intro)
        mode_help = QLabel(
            u"模式说明：兼容模式＝沿用原有连单锁和按重量分流；增强模式＝中继已运行，"
            u"订单号、金额和明确付款状态均已验证，可按金额参与分流；候选/状态未知/降级＝正在测试或数据不可靠，"
            u"仍按兼容模式处理。收到打印任务本身不等于已结账。每天第一笔自动分流默认先走官方 POS；"
            u"首单前店员手动切到私域时，系统尊重手动选择。"
        )
        mode_help.setWordWrap(True)
        mode_help.setStyleSheet("color: #E2E8F0; background: #1E293B; border: 1px solid #475569; border-radius: 10px; padding: 12px;")
        layout.addWidget(mode_help)

        # Step 1: keep all printer/relay choices in one configuration card.
        step1, step1_layout = step_panel(
            1,
            u"配置中继与实体输出",
            u"填写监听端口、选择官方 POS 要发送到的 Windows 队列，再选择中继转发到的实体打印机。"
            u"中继队列和实体输出不能是同一个队列，否则会形成循环打印。",
        )
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self._make_label(u"中继监听端口："), 0, 0)
        self.spin_relay_listen_port = QSpinBox()
        self.spin_relay_listen_port.setRange(1024, 65535)
        self.spin_relay_listen_port.setValue(int(self.config.get("printer_relay_port", 9101) or 9101))
        grid.addWidget(self.spin_relay_listen_port, 0, 1)
        grid.addWidget(self._make_label(u"Windows 中继队列："), 1, 0)
        # Windows 队列不是只能手填：扫描本机已安装的打印队列后可以
        # 直接选择；保留可编辑模式兼容网络映射队列和旧配置名称。
        self.cmb_relay_queue = QComboBox()
        self.cmb_relay_queue.setEditable(True)
        self.cmb_relay_queue.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_relay_queue.setPlaceholderText(u"先检测队列，再选择官方 POS 要指向的队列")
        self.txt_relay_queue = self.cmb_relay_queue  # 旧调用方兼容别名
        self._refresh_relay_queues()
        grid.addWidget(self.cmb_relay_queue, 1, 1)
        self.btn_refresh_relay_queues = QPushButton(u"检测队列")
        self._style_touch_action_btn(self.btn_refresh_relay_queues, "blue")
        self.btn_refresh_relay_queues.clicked.connect(lambda: self._refresh_relay_queues(True))
        grid.addWidget(self.btn_refresh_relay_queues, 1, 2)
        self.lbl_relay_printer_name = self._make_label(u"实体输出打印机：")
        grid.addWidget(self.lbl_relay_printer_name, 2, 0)
        self.cmb_relay_printer_name = QComboBox()
        self.cmb_relay_printer_name.setEditable(True)
        self._refresh_relay_printers()
        grid.addWidget(self.cmb_relay_printer_name, 2, 1)
        self.btn_refresh_relay_printers = QPushButton(u"刷新打印机")
        self._style_touch_action_btn(self.btn_refresh_relay_printers)
        self.btn_refresh_relay_printers.clicked.connect(lambda: self._refresh_relay_printers(True))
        grid.addWidget(self.btn_refresh_relay_printers, 2, 2)
        grid.addWidget(self._make_label(u"实体打印方式："), 3, 0)
        self.cmb_relay_printer_type = QComboBox()
        self.cmb_relay_printer_type.addItems([
            "windows - Windows RAW 队列",
            "network - 网络打印（IP/端口）",
            "serial - 串口打印（COM）",
        ])
        pt = self.config.get("printer_type", "windows")
        for index in range(self.cmb_relay_printer_type.count()):
            if self.cmb_relay_printer_type.itemText(index).startswith(pt):
                self.cmb_relay_printer_type.setCurrentIndex(index)
                break
        grid.addWidget(self.cmb_relay_printer_type, 3, 1, 1, 2)
        self.lbl_relay_ip = self._make_label(u"网络实体打印机 IP：")
        grid.addWidget(self.lbl_relay_ip, 4, 0)
        self.txt_relay_ip = QLineEdit(self.config.get("printer_ip", "192.168.1.100"))
        grid.addWidget(self.txt_relay_ip, 4, 1)
        self.lbl_relay_printer_port = self._make_label(u"网络端口：")
        grid.addWidget(self.lbl_relay_printer_port, 5, 0)
        self.spin_relay_printer_port = QSpinBox()
        self.spin_relay_printer_port.setRange(1, 65535)
        self.spin_relay_printer_port.setValue(int(self.config.get("printer_port", 9100) or 9100))
        grid.addWidget(self.spin_relay_printer_port, 5, 1)
        self.lbl_relay_serial_port = self._make_label(u"串口：")
        grid.addWidget(self.lbl_relay_serial_port, 6, 0)
        self.txt_relay_serial_port = QLineEdit(self.config.get("printer_serial_port", "COM4"))
        self.txt_relay_serial_port.setPlaceholderText(u"例如：COM4")
        grid.addWidget(self.txt_relay_serial_port, 6, 1)
        self.chk_relay_enabled = QCheckBox(u"启用中继监听（取消勾选并保存可停用）")
        self.chk_relay_enabled.setChecked(bool(self.config.get("printer_relay_enabled", False)))
        grid.addWidget(self.chk_relay_enabled, 7, 1)
        capture_hint = QLabel(u"原始 .bin/.json 会自动保存，实时监控直接读取这些文件；保留数量不能为 0，否则实时监控没有文件可显示。数量越大占用磁盘越多。")
        capture_hint.setWordWrap(True)
        capture_hint.setStyleSheet("color: #BAE6FD; background: #082F49; border: 1px solid #0369A1; border-radius: 8px; padding: 8px;")
        grid.addWidget(capture_hint, 8, 1, 1, 2)
        grid.addWidget(self._make_label(u"最多保留采样条数："), 9, 0)
        self.spin_relay_capture_max_files = QSpinBox()
        self.spin_relay_capture_max_files.setRange(1, 10000)
        self.spin_relay_capture_max_files.setValue(int(self.config.get("printer_relay_capture_max_files", 20) or 20))
        self.spin_relay_capture_max_files.setToolTip(u"超过数量后按时间删除最旧的采样，.bin 和 .json 成对删除。")
        grid.addWidget(self.spin_relay_capture_max_files, 9, 1)
        self.cmb_relay_mode_policy = QComboBox()
        self.cmb_relay_mode_policy.addItem(u"自动判断（推荐）", MODE_POLICY_AUTO)
        self.cmb_relay_mode_policy.addItem(u"强制兼容模式（测试/故障）", MODE_POLICY_FORCE_COMPATIBILITY)
        policy = self.config.get("printer_relay_mode_policy", MODE_POLICY_AUTO)
        policy_index = self.cmb_relay_mode_policy.findData(policy)
        self.cmb_relay_mode_policy.setCurrentIndex(policy_index if policy_index >= 0 else 0)
        self.cmb_relay_mode_policy.setToolTip(u"不会提供强制增强模式；增强模式必须由已验证的官方 POS 数据自动触发。")
        grid.addWidget(self._make_label(u"模式策略："), 10, 0)
        grid.addWidget(self.cmb_relay_mode_policy, 10, 1, 1, 2)
        self.cmb_relay_printer_type.currentIndexChanged.connect(self._on_relay_printer_type_changed)
        self._on_relay_printer_type_changed(self.cmb_relay_printer_type.currentIndex())
        step1_layout.addLayout(grid)
        self.btn_save_relay = QPushButton(u"💾 保存中继配置")
        self._style_save_btn(self.btn_save_relay)
        self.btn_save_relay.clicked.connect(self._on_save_relay)
        step1_layout.addWidget(self.btn_save_relay)
        layout.addWidget(step1)

        # Step 2: save and verify the transport before asking the operator to
        # print a real ticket.
        step2, step2_layout = step_panel(
            2,
            u"保存配置并检查连接",
            u"先保存配置，再检查 Windows 队列和中继监听状态。这里出现异常时不要进入增强模式，系统会继续使用兼容模式。",
        )
        self.lbl_relay_config_status = QLabel()
        self.lbl_relay_config_status.setWordWrap(True)
        self.lbl_relay_config_status.setStyleSheet("color: #FDE68A; background: #422006; border: 1px solid #A16207; border-radius: 10px; padding: 12px;")
        step2_layout.addWidget(self.lbl_relay_config_status)
        self.lbl_relay_runtime_status = QLabel()
        self.lbl_relay_runtime_status.setWordWrap(True)
        self.lbl_relay_runtime_status.setStyleSheet("color: #CBD5E1; background: #0F172A; border: 1px solid #334155; border-radius: 10px; padding: 12px;")
        step2_layout.addWidget(self.lbl_relay_runtime_status)
        self.lbl_relay_degrade_hint = QLabel()
        self.lbl_relay_degrade_hint.setWordWrap(True)
        self.lbl_relay_degrade_hint.setStyleSheet(
            "color: #FDE68A; background: #422006; border: 1px solid #A16207; "
            "border-radius: 10px; padding: 12px; font-weight: 700;"
        )
        self.lbl_relay_degrade_hint.setVisible(False)
        step2_layout.addWidget(self.lbl_relay_degrade_hint)

        action_row = QGridLayout()
        action_row.setHorizontalSpacing(12)
        action_row.setVerticalSpacing(12)
        self.btn_check_relay_queue = QPushButton(u"② 检查 Windows 队列")
        self._style_touch_action_btn(self.btn_check_relay_queue, "blue")
        self.btn_check_relay_queue.clicked.connect(self._check_relay_queue)
        action_row.addWidget(self.btn_check_relay_queue, 0, 0)
        queue_hint = QLabel(u"队列检查通过后，再进入下一步打印和识别测试。")
        queue_hint.setWordWrap(True)
        queue_hint.setStyleSheet("color: #94A3B8; font-size: 14px;")
        action_row.addWidget(queue_hint, 0, 1)
        step2_layout.addLayout(action_row)
        layout.addWidget(step2)

        # Steps 3 and 4 are one runtime operation: start/stop the temporary
        # listener, then refresh the same live state card.  Keeping them
        # together avoids making the operator jump between two panels while
        # the official POS is waiting for its queue connection.
        step3, step3_layout = step_panel(
            3,
            u"中继控制",
            u"官方 POS 显示收银机未连接时，先启动临时中继。关闭只停止本次监听，不会删除配置；需要恢复时再次启动。",
        )
        runtime_action_row = QGridLayout()
        runtime_action_row.setHorizontalSpacing(12)
        runtime_action_row.setVerticalSpacing(12)
        self.btn_start_relay_listener = QPushButton(u"③ 启动临时中继")
        self._style_touch_action_btn(self.btn_start_relay_listener, "purple")
        self.btn_start_relay_listener.clicked.connect(self._start_relay_listener)
        runtime_action_row.addWidget(self.btn_start_relay_listener, 0, 0)
        self.btn_stop_relay_listener = QPushButton(u"③ 关闭临时中继")
        self._style_touch_action_btn(self.btn_stop_relay_listener, "danger")
        self.btn_stop_relay_listener.clicked.connect(self._stop_relay_listener)
        runtime_action_row.addWidget(self.btn_stop_relay_listener, 0, 1)
        step3_layout.addLayout(runtime_action_row)
        action_title = QLabel(
            u"下一步：刷新中继状态　→　④ 回官方 POS 准备真实测试单。"
            u"收到打印任务本身不等于已结账；下方会实时显示最近一笔收到的数据。"
        )
        action_title.setWordWrap(True)
        action_title.setStyleSheet("color: #FDE68A; background: #422006; border: 1px solid #A16207; border-radius: 8px; padding: 10px; font-weight: bold;")
        test_row = QGridLayout()
        test_row.setHorizontalSpacing(12)
        test_row.setVerticalSpacing(12)
        self.btn_refresh_relay_status = QPushButton(u"④ 刷新中继状态")
        self._style_touch_action_btn(self.btn_refresh_relay_status)
        self.btn_refresh_relay_status.clicked.connect(self._on_refresh_relay_status_clicked)
        test_row.addWidget(self.btn_refresh_relay_status, 0, 0)
        self.lbl_relay_refresh_result = QLabel(u"尚未手动刷新中继状态")
        self.lbl_relay_refresh_result.setStyleSheet("color: #94A3B8; font-size: 14px;")
        test_row.addWidget(self.lbl_relay_refresh_result, 1, 0, 1, 2)
        step3_layout.addWidget(action_title)
        step3_layout.addLayout(test_row)
        layout.addWidget(step3)

        # Step 4: ask the operator to print one real ticket from the official
        # POS.  The button never fabricates a payload or assumes payment.
        step5, step5_layout = step_panel(
            4,
            u"准备官方 POS 真实测试",
            u"回到官方 POS，选择已配置的 Windows 中继队列打印真实测试单；打印任务本身不等于已结账。",
        )
        self.btn_test_relay_print = QPushButton(u"④ 准备官方 POS 真实测试")
        self._style_touch_action_btn(self.btn_test_relay_print, "blue")
        self.btn_test_relay_print.clicked.connect(self._test_relay_print)
        step5_layout.addWidget(self.btn_test_relay_print)
        self.lbl_relay_live_test = self._make_relay_live_monitor()
        step5_layout.addWidget(self.lbl_relay_live_test)
        layout.addWidget(step5)

        # Step 5: mapping is an optional recognition aid, not a transport
        # setting. Keeping it after the test makes the dependency explicit.
        step6, step6_layout = step_panel(
            5,
            u"字段重映射",
            u"这里配置“票面文字对应什么字段”，不是直接改订单数据。多个关键词用逗号分隔；留空使用系统默认规则。"
            u"例如官方模板写“流水号”而不是“订单号”，就在订单号标签中填：订单号,订单编号,流水号。",
        )
        mapping = self.config.get("official_pos_field_mapping") or {}
        mapping_defaults = {
            "order_id_labels": ["订单号", "订单编号"],
            "amount_labels": ["实付", "实收", "支付金额", "付款金额", "应付", "应收", "合计", "总计", "原价合计"],
            "paid_keywords": ["支付成功", "付款成功", "收款成功", "交易成功", "已支付", "已付款", "已结账", "结账成功", "支付状态:成功"],
            "cancelled_keywords": ["已取消", "取消订单", "退款成功", "已退款"],
            "dinein_keywords": ["堂食", "POS点餐", "收银", "消费小票", "结账单", "制作单-堂食"],
        }
        mapping_grid = QGridLayout()
        mapping_grid.setSpacing(10)
        mapping_grid.setColumnStretch(1, 1)
        mapping_fields = (
            ("order_id_labels", u"订单号标签：", u"订单号,订单编号,流水号"),
            ("amount_labels", u"金额标签：", u"实付,实收,应付,合计"),
            ("paid_keywords", u"付款成功关键词：", u"支付成功,已支付,已结账"),
            ("cancelled_keywords", u"取消/退款关键词：", u"已取消,退款成功"),
            ("dinein_keywords", u"堂食识别关键词：", u"堂食,POS点餐,消费小票"),
        )
        self.relay_mapping_fields = {}
        for row, (key, label, placeholder) in enumerate(mapping_fields):
            mapping_grid.addWidget(self._make_label(label), row, 0)
            field = QLineEdit()
            saved = mapping.get(key, mapping_defaults.get(key, [])) if isinstance(mapping, dict) else mapping_defaults.get(key, [])
            if isinstance(saved, (list, tuple)):
                field.setText(",".join(str(item) for item in saved if str(item).strip()))
            else:
                field.setText(str(saved or ""))
            field.setPlaceholderText(placeholder + u"（留空使用默认）")
            field.setMinimumHeight(50)
            mapping_grid.addWidget(field, row, 1, 1, 2)
            self.relay_mapping_fields[key] = field
        step6_layout.addLayout(mapping_grid)
        self.lbl_relay_live_mapping = self._make_relay_live_monitor()
        step6_layout.addWidget(self.lbl_relay_live_mapping)
        self.btn_save_relay_mapping = QPushButton(u"⑤ 保存映射并刷新状态")
        self._style_save_btn(self.btn_save_relay_mapping)
        self.btn_save_relay_mapping.clicked.connect(self._on_save_relay)
        step6_layout.addWidget(self.btn_save_relay_mapping)
        layout.addWidget(step6)

        # Step 6: service lifecycle is intentionally last and separated from
        # the everyday queue/test workflow.
        step7, step7_layout = step_panel(
            6,
            u"独立中继服务维护（可选）",
            u"只有需要开机自启、私域 POS 未启动时仍能监听时，才使用下面的服务操作。日常配置和测试不需要先安装服务。",
        )
        service_title = QLabel(u"服务名：ppposPrinterRelay。安装/启动需要管理员权限；临时停止不会删除配置。")
        service_title.setWordWrap(True)
        service_title.setStyleSheet("color: #DDD6FE; background: #2E1065; border: 1px solid #7C3AED; border-radius: 8px; padding: 10px; font-weight: bold;")
        step7_layout.addWidget(service_title)
        service_action_row = QGridLayout()
        self.btn_install_relay_service = QPushButton(u"安装独立服务")
        self._style_touch_action_btn(self.btn_install_relay_service, "purple")
        self.btn_install_relay_service.clicked.connect(self._install_relay_service)
        service_action_row.addWidget(self.btn_install_relay_service, 0, 0)
        self.btn_start_relay_service = QPushButton(u"启动独立服务")
        self._style_touch_action_btn(self.btn_start_relay_service, "blue")
        self.btn_start_relay_service.clicked.connect(self._start_relay_service)
        service_action_row.addWidget(self.btn_start_relay_service, 0, 1)
        self.btn_stop_relay_service = QPushButton(u"临时停止服务")
        self._style_touch_action_btn(self.btn_stop_relay_service, "danger")
        self.btn_stop_relay_service.clicked.connect(self._stop_relay_service)
        service_action_row.addWidget(self.btn_stop_relay_service, 1, 0)
        self.btn_remove_relay_service = QPushButton(u"卸载独立服务")
        self._style_touch_action_btn(self.btn_remove_relay_service, "danger")
        self.btn_remove_relay_service.clicked.connect(self._remove_relay_service)
        service_action_row.addWidget(self.btn_remove_relay_service, 1, 1)
        step7_layout.addLayout(service_action_row)
        service_hint = QLabel(
            u"安装＝注册 Windows 服务；启动＝运行服务；临时停止＝只停止本次运行；卸载＝删除服务注册。"
            u"安装后中继可在界面关闭、私域 POS 未启动或机器重启后继续工作；"
            u"安装/控制需要管理员权限。Windows 服务账号可能看不到用户映射的打印队列，请优先使用本机队列或网络打印并做真实测试。"
            u"服务操作点击后立即生效，不需要额外保存。"
        )
        service_hint.setWordWrap(True)
        service_hint.setStyleSheet("color: #C4B5FD; background: #2E1065; border: 1px solid #7C3AED; border-radius: 10px; padding: 12px;")
        step7_layout.addWidget(service_hint)
        layout.addWidget(step7)
        self._refresh_relay_status()
        return self._wrap_in_scroll(card, [
            (u"① 中继配置", [2, 3, 4]),
            (u"② 连接检查", [5]),
            (u"③ 中继控制", [6]),
            (u"④ 真实测试", [7]),
            (u"⑤ 字段重映射", [8]),
            (u"服务维护", [9]),
        ])

    # ────────────────────────────────────────────────────────────
    # 页面 7: 打印纸格式
    # ────────────────────────────────────────────────────────────
    def _build_printer_page(self):
        card, layout = self._create_section_card(
            u"♨", u"打印纸格式", u"只设置纸张、字体、份数和小票内容排版"
        )
        note = QLabel(
            u"使用流程：先完成“打印机中继”配置，再在本页分别保存纸张走纸、单据份数和打印模板。\n"
            u"打印机选择、连接方式、网络端口、Windows 队列、连接状态和测试打印已统一放在“打印机中继”。\n"
            u"本页只保存打印纸张和票面排版，避免两个页面重复维护同一项连接配置。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #BAE6FD; background: #082F49; border: 1px solid #0369A1; border-radius: 10px; padding: 14px;")
        layout.addWidget(note)

        # 说明：旧版打印代码固定使用 48 个半角列（更接近 80mm 纸），
        # 但 58mm 热敏纸通常只有 32 列。这里把纸宽、列数、走纸和切刀
        # 都显式化，避免继续依赖散落在 printer.py 里的硬编码。
        width_hint = QLabel(
            u"版式说明：中文按 2 列、英文/数字按 1 列计算。旧版默认 48 列；"
            u"常见 58mm 纸请选择 32 列，打印内容会自动使用紧凑表头。"
        )
        width_hint.setWordWrap(True)
        width_hint.setStyleSheet("color: #94A3B8; font-size: 14px; background: transparent;")
        layout.addWidget(width_hint)

        layout.addWidget(self._printer_section_title(u"纸宽与走纸参数"))
        format_grid = QGridLayout()
        format_grid.setSpacing(14)
        format_grid.setColumnStretch(1, 1)
        format_grid.addWidget(self._make_label(u"纸张预设："), 0, 0)
        self.cmb_printer_width = QComboBox()
        self.cmb_printer_width.addItems([
            u"80 mm - 48 列（当前模板）",
            u"58 mm - 32 列（常见窄纸）",
            u"自定义列数",
        ])
        try:
            saved_width = int(self.config.get("printer_paper_width_mm", 80) or 0)
            saved_columns = int(self.config.get("printer_chars_per_line", 48) or 48)
        except (TypeError, ValueError):
            saved_width, saved_columns = 80, 48
        if saved_width == 58 and saved_columns == 32:
            self.cmb_printer_width.setCurrentIndex(1)
        elif saved_width != 80 or saved_columns != 48:
            self.cmb_printer_width.setCurrentIndex(2)
        format_grid.addWidget(self.cmb_printer_width, 0, 1)

        format_grid.addWidget(self._make_label(u"每行列数："), 1, 0)
        self.spin_printer_columns = QSpinBox()
        self.spin_printer_columns.setRange(16, 64)
        self.spin_printer_columns.setValue(int(self.config.get("printer_chars_per_line", 48) or 48))
        format_grid.addWidget(self.spin_printer_columns, 1, 1)

        format_grid.addWidget(self._make_label(u"分隔线字符："), 2, 0)
        self.txt_printer_separator = QLineEdit(str(self.config.get("printer_separator_char", "-") or "-"))
        self.txt_printer_separator.setMaxLength(1)
        self.txt_printer_separator.setPlaceholderText(u"例如：-")
        format_grid.addWidget(self.txt_printer_separator, 2, 1)

        format_grid.addWidget(self._make_label(u"末尾走纸行数："), 3, 0)
        self.spin_printer_feed_lines = QSpinBox()
        self.spin_printer_feed_lines.setRange(0, 12)
        self.spin_printer_feed_lines.setValue(int(self.config.get("printer_feed_lines", 4) or 4))
        format_grid.addWidget(self.spin_printer_feed_lines, 3, 1)

        self.chk_printer_auto_cut = QCheckBox(u"打印完成后自动切纸")
        self.chk_printer_auto_cut.setChecked(bool(self.config.get("printer_auto_cut_enabled", True)))
        format_grid.addWidget(self.chk_printer_auto_cut, 4, 1)
        self.chk_printer_cash_drawer = QCheckBox(u"现金收款时发送钱箱开启指令")
        self.chk_printer_cash_drawer.setChecked(bool(self.config.get("printer_cash_drawer_enabled", True)))
        format_grid.addWidget(self.chk_printer_cash_drawer, 5, 1)
        self.btn_save_printer_paper = QPushButton(u"保存纸张与走纸设置")
        self._style_touch_action_btn(self.btn_save_printer_paper, "blue")
        self.btn_save_printer_paper.clicked.connect(self._on_save_printer_paper)
        format_grid.addWidget(self.btn_save_printer_paper, 6, 1, 1, 2)
        layout.addLayout(format_grid)

        layout.addWidget(self._printer_section_title(u"单据开关与打印份数"))
        slips_grid = QGridLayout()
        slips_grid.setSpacing(14)
        slips_grid.setColumnStretch(1, 1)
        slips_grid.setColumnStretch(3, 0)

        self.chk_printer_customer = QCheckBox(u"打印顾客单")
        self.chk_printer_customer.setChecked(bool(self.config.get("printer_customer_enabled", True)))
        slips_grid.addWidget(self.chk_printer_customer, 0, 0, 1, 2)
        slips_grid.addWidget(self._make_label(u"份数："), 0, 2)
        self.spin_printer_customer_copies = QSpinBox()
        self.spin_printer_customer_copies.setRange(0, 20)
        self.spin_printer_customer_copies.setValue(int(self.config.get("printer_customer_copies", 1) or 0))
        slips_grid.addWidget(self.spin_printer_customer_copies, 0, 3)

        self.chk_printer_kitchen = QCheckBox(u"打印后厨制作单")
        self.chk_printer_kitchen.setChecked(bool(self.config.get("printer_kitchen_enabled", True)))
        slips_grid.addWidget(self.chk_printer_kitchen, 1, 0, 1, 2)
        slips_grid.addWidget(self._make_label(u"每个汤底份数："), 1, 2)
        self.spin_printer_kitchen_copies = QSpinBox()
        self.spin_printer_kitchen_copies.setRange(0, 20)
        self.spin_printer_kitchen_copies.setValue(int(self.config.get("printer_kitchen_copies", 1) or 0))
        slips_grid.addWidget(self.spin_printer_kitchen_copies, 1, 3)

        self.chk_printer_report = QCheckBox(u"允许打印营业汇总报表")
        self.chk_printer_report.setChecked(bool(self.config.get("printer_report_enabled", True)))
        slips_grid.addWidget(self.chk_printer_report, 2, 0, 1, 2)
        slips_grid.addWidget(self._make_label(u"报表份数："), 2, 2)
        self.spin_printer_report_copies = QSpinBox()
        self.spin_printer_report_copies.setRange(0, 20)
        self.spin_printer_report_copies.setValue(int(self.config.get("printer_report_copies", 1) or 0))
        slips_grid.addWidget(self.spin_printer_report_copies, 2, 3)

        self.chk_printer_show_tags = QCheckBox(u"小票显示口味/备注标签")
        self.chk_printer_show_tags.setChecked(bool(self.config.get("printer_show_tags", True)))
        slips_grid.addWidget(self.chk_printer_show_tags, 3, 0, 1, 2)
        self.chk_printer_takeout_banner = QCheckBox(u"打包制作单显示醒目“打包”标记")
        self.chk_printer_takeout_banner.setChecked(bool(self.config.get("printer_packaging_banner_enabled", True)))
        slips_grid.addWidget(self.chk_printer_takeout_banner, 4, 0, 1, 2)
        slips_grid.addWidget(self._make_label(u"标记行数："), 4, 2)
        self.spin_printer_packaging_banner_lines = QSpinBox()
        self.spin_printer_packaging_banner_lines.setRange(0, 8)
        self.spin_printer_packaging_banner_lines.setValue(int(self.config.get("printer_packaging_banner_lines", 3) or 0))
        slips_grid.addWidget(self.spin_printer_packaging_banner_lines, 4, 3)
        self.btn_save_printer_slips = QPushButton(u"保存单据与份数设置")
        self._style_touch_action_btn(self.btn_save_printer_slips, "blue")
        self.btn_save_printer_slips.clicked.connect(self._on_save_printer_slips)
        slips_grid.addWidget(self.btn_save_printer_slips, 5, 0, 1, 4)
        layout.addLayout(slips_grid)
        takeout_note = QLabel(
            u"说明：中继端口、队列、实体打印机、连接状态和测试统一在“打印机中继”维护；"
            u"外卖内容、分类排序和份数在“外卖设置 → 外卖格式”维护；这里仅控制打印内容和纸张排版。"
        )
        takeout_note.setWordWrap(True)
        takeout_note.setStyleSheet("color: #94A3B8; font-size: 14px; background: transparent;")
        layout.addWidget(takeout_note)

        layout.addWidget(self._printer_section_title(u"打印模板"))
        template_hint = QLabel(
            u"以下内容支持变量：顾客单标题可使用 {shop_name}、{shop_subtitle}、{call_no}；"
            u"制作单标题可使用 {call_no}、{index}、{service_type}；底部可使用 {time}。"
        )
        template_hint.setWordWrap(True)
        template_hint.setStyleSheet("color: #94A3B8; font-size: 14px; background: transparent;")
        layout.addWidget(template_hint)
        profile_grid = QGridLayout()
        profile_grid.setSpacing(14)
        profile_grid.setColumnStretch(1, 1)
        profile_grid.addWidget(self._make_label(u"模板方案："), 0, 0)
        self.cmb_printer_template_profile = QComboBox()
        self.cmb_printer_template_profile.addItems([
            u"旧版当前格式（保持原样）",
            u"官方新版参考（80mm）",
            u"自定义模板（以后换版用）",
        ])
        profile = str(self.config.get("printer_template_profile", "official_v2") or "official_v2")
        profile_index = {"legacy": 0, "official_v2": 1, "custom": 2}.get(profile, 1)
        self.cmb_printer_template_profile.setCurrentIndex(profile_index)
        profile_grid.addWidget(self.cmb_printer_template_profile, 0, 1)
        layout.addLayout(profile_grid)

        self.lbl_printer_custom_template_hint = QLabel(
            u"自定义模板语法：每行前可加 [C]居中、[L]左对齐、[R]右对齐、[B]粗体、[D]双倍高度、[X]双倍宽高、[Y]三倍宽高。"
            u"可用变量：{shop_name}、{call_no}、{items}、{total}、{payment_method}、{order_id}、"
            u"{total_line}、{due_line}、{paid_line}、{kitchen_call_no}、{item_name}、{weight}、"
            u"{item_line}、{flavor}、{operator}、{time}、{service_phone}、{separator}。"
        )
        self.lbl_printer_custom_template_hint.setWordWrap(True)
        self.lbl_printer_custom_template_hint.setStyleSheet("color: #FDE68A; font-size: 14px; background: transparent;")
        layout.addWidget(self.lbl_printer_custom_template_hint)

        self.lbl_printer_customer_template = self._make_label(u"自定义顾客单正文：")
        layout.addWidget(self.lbl_printer_customer_template, alignment=Qt.AlignLeft)
        self.txt_printer_customer_template = QPlainTextEdit()
        self.txt_printer_customer_template.setPlainText(
            self.config.get("printer_customer_template_custom", "") or self._official_customer_template_text()
        )
        self.txt_printer_customer_template.setMinimumHeight(190)
        self.txt_printer_customer_template.setStyleSheet(
            "QPlainTextEdit { background: #0F172A; color: #F8FAFC; border: 1px solid #334155; "
            "border-radius: 10px; padding: 12px; font-size: 14px; }"
        )
        layout.addWidget(self.txt_printer_customer_template)

        self.lbl_printer_kitchen_template = self._make_label(u"自定义制作单正文：")
        layout.addWidget(self.lbl_printer_kitchen_template, alignment=Qt.AlignLeft)
        self.txt_printer_kitchen_template = QPlainTextEdit()
        self.txt_printer_kitchen_template.setPlainText(
            self.config.get("printer_kitchen_template_custom", "") or self._official_kitchen_template_text()
        )
        self.txt_printer_kitchen_template.setMinimumHeight(150)
        self.txt_printer_kitchen_template.setStyleSheet(
            "QPlainTextEdit { background: #0F172A; color: #F8FAFC; border: 1px solid #334155; "
            "border-radius: 10px; padding: 12px; font-size: 14px; }"
        )
        layout.addWidget(self.txt_printer_kitchen_template)
        logo_grid = QGridLayout()
        logo_grid.setSpacing(14)
        logo_grid.setColumnStretch(1, 1)
        self.chk_printer_logo = QCheckBox(u"官方新版/自定义顾客单打印 Logo")
        self.chk_printer_logo.setChecked(bool(self.config.get("printer_logo_enabled", True)))
        logo_grid.addWidget(self.chk_printer_logo, 0, 0)
        self.txt_printer_logo_path = QLineEdit(self.config.get("printer_logo_path", ""))
        self.txt_printer_logo_path.setPlaceholderText(u"留空使用内置杨国福 Logo 图片")
        logo_grid.addWidget(self.txt_printer_logo_path, 0, 1)
        self.btn_browse_printer_logo = QPushButton(u"选择图片")
        self._style_touch_action_btn(self.btn_browse_printer_logo)
        self.btn_browse_printer_logo.clicked.connect(self._browse_printer_logo)
        logo_grid.addWidget(self.btn_browse_printer_logo, 0, 2)
        layout.addLayout(logo_grid)
        template_grid = QGridLayout()
        template_grid.setSpacing(14)
        template_grid.setColumnStretch(1, 1)
        self.lbl_printer_customer_title = self._make_label(u"顾客单标题（旧版）：")
        template_grid.addWidget(self.lbl_printer_customer_title, 0, 0)
        self.txt_printer_customer_title = QLineEdit(self.config.get("printer_customer_title", "POS点餐 堂食"))
        template_grid.addWidget(self.txt_printer_customer_title, 0, 1)
        self.lbl_printer_customer_footer = self._make_label(u"顾客单底部（旧版）：")
        template_grid.addWidget(self.lbl_printer_customer_footer, 1, 0)
        self.txt_printer_customer_footer = QLineEdit(self.config.get("printer_customer_footer", "打印时间：{time}"))
        template_grid.addWidget(self.txt_printer_customer_footer, 1, 1)
        self.lbl_printer_kitchen_title_dinein = self._make_label(u"堂食制作单标题（旧版）：")
        template_grid.addWidget(self.lbl_printer_kitchen_title_dinein, 2, 0)
        self.txt_printer_kitchen_title_dinein = QLineEdit(self.config.get("printer_kitchen_title_dinein", "制作单-堂食"))
        template_grid.addWidget(self.txt_printer_kitchen_title_dinein, 2, 1)
        self.lbl_printer_kitchen_title_packaging = self._make_label(u"打包制作单标题（旧版）：")
        template_grid.addWidget(self.lbl_printer_kitchen_title_packaging, 3, 0)
        self.txt_printer_kitchen_title_packaging = QLineEdit(self.config.get("printer_kitchen_title_packaging", "制作单-打包"))
        template_grid.addWidget(self.txt_printer_kitchen_title_packaging, 3, 1)
        self.lbl_printer_kitchen_footer = self._make_label(u"制作单底部（旧版）：")
        template_grid.addWidget(self.lbl_printer_kitchen_footer, 4, 0)
        self.txt_printer_kitchen_footer = QLineEdit(self.config.get("printer_kitchen_footer", "打印时间：{time}"))
        template_grid.addWidget(self.txt_printer_kitchen_footer, 4, 1)
        self.lbl_printer_report_title = self._make_label(u"营业报表标题（报表）：")
        template_grid.addWidget(self.lbl_printer_report_title, 5, 0)
        self.txt_printer_report_title = QLineEdit(self.config.get("printer_report_title", "营业汇总报表"))
        template_grid.addWidget(self.txt_printer_report_title, 5, 1)
        self.lbl_printer_report_footer = self._make_label(u"营业报表底部（报表）：")
        template_grid.addWidget(self.lbl_printer_report_footer, 6, 0)
        self.txt_printer_report_footer = QLineEdit(self.config.get("printer_report_footer", "打印时间：{time}"))
        template_grid.addWidget(self.txt_printer_report_footer, 6, 1)
        self.lbl_printer_service_phone = self._make_label(u"加盟电话（官方新版/自定义）：")
        template_grid.addWidget(self.lbl_printer_service_phone, 7, 0)
        self.txt_printer_service_phone = QLineEdit(self.config.get("printer_service_phone", "400-6058-777"))
        template_grid.addWidget(self.txt_printer_service_phone, 7, 1)
        self.lbl_printer_operator = self._make_label(u"制作单操作人（官方新版/自定义）：")
        template_grid.addWidget(self.lbl_printer_operator, 8, 0)
        self.txt_printer_operator = QLineEdit(self.config.get("printer_operator", ""))
        self.txt_printer_operator.setPlaceholderText(u"留空则打印“收银员”")
        template_grid.addWidget(self.txt_printer_operator, 8, 1)
        self.btn_save_printer_template = QPushButton(u"保存打印模板设置")
        self._style_touch_action_btn(self.btn_save_printer_template, "blue")
        self.btn_save_printer_template.clicked.connect(self._on_save_printer_template)
        template_grid.addWidget(self.btn_save_printer_template, 9, 0, 1, 2)
        layout.addLayout(template_grid)

        self.cmb_printer_width.currentIndexChanged.connect(self._on_printer_width_changed)
        self.cmb_printer_template_profile.currentIndexChanged.connect(self._on_printer_template_profile_changed)
        self._on_printer_width_changed()
        self._on_printer_template_profile_changed(self.cmb_printer_template_profile.currentIndex())

        return self._wrap_in_scroll(card, [(u"① 纸张与走纸", [2, 3, 4, 5]), (u"② 单据与份数", [6, 7, 8]), (u"③ 打印模板", [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])])

    def _printer_section_title(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            "color: #38BDF8; font-size: 18px; font-weight: 900; "
            "padding-top: 8px; background: transparent;"
        )
        return label

    def _browse_printer_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            u"选择打印 Logo 图片",
            "",
            u"图片文件 (*.png *.jpg *.jpeg *.bmp *.svg);;所有文件 (*.*)",
        )
        if path:
            self.txt_printer_logo_path.setText(path)

    def _relay_runtime_state(self):
        parent = self.window()
        controller = getattr(parent, "printer_relay_controller", None)
        if controller is None:
            return {"running": False, "message": "中继控制器未加载"}
        try:
            return controller.get_status()
        except Exception as exc:
            return {"running": False, "last_error": str(exc)}

    def _relay_service_controller(self):
        controller = getattr(self.window(), "printer_relay_controller", None)
        return getattr(controller, "service_controller", None)

    def _relay_service_action(self, action, success_text, title, message, stages):
        from ui.custom_dialog import show_info, show_warning
        controller = getattr(self.window(), "printer_relay_controller", None)
        if controller is None:
            show_warning(self, u"中继服务不可用", u"当前窗口尚未加载打印机中继控制器。")
            return

        def on_success(_result):
            self._refresh_relay_status()
            show_info(self, u"独立打印机中继服务", success_text)

        self._run_maintenance_with_spinner(
            title,
            message,
            lambda: action(controller),
            on_success,
            u"独立打印机中继服务操作失败",
            [
                self.btn_install_relay_service,
                self.btn_start_relay_service,
                self.btn_stop_relay_service,
                self.btn_remove_relay_service,
            ],
            on_failure=self._refresh_relay_status,
            stages=stages,
        )

    def _install_relay_service(self):
        self._relay_service_action(
            lambda controller: controller.install_service(),
            u"pposPrinterRelay 已安装。请保存并启用中继配置后点击“启动独立服务”。",
            u"正在安装打印机中继服务",
            u"正在注册 Windows 服务并检查旧版本服务迁移状态，请稍候。",
            [
                u"检查管理员权限和当前服务状态",
                u"迁移旧版打印机中继服务（如存在）",
                u"注册 ppposPrinterRelay Windows 服务",
                u"核对服务安装结果",
            ],
        )

    def _start_relay_service(self):
        self._relay_service_action(
            lambda controller: controller.start_service(),
            u"ppposPrinterRelay 已启动。请刷新状态并打印真实测试单。",
            u"正在启动打印机中继服务",
            u"正在启动 ppposPrinterRelay，并等待 Windows 返回运行状态。",
            [
                u"检查服务是否已安装",
                u"发送启动请求",
                u"等待 Windows 服务进入运行状态",
                u"读取打印机中继监听状态",
            ],
        )

    def _start_relay_listener(self):
        """Start the normal detached listener or the installed relay service."""
        from ui.custom_dialog import show_info, show_warning
        candidate = self._relay_config_from_form()
        if not candidate.get("printer_relay_enabled"):
            show_warning(
                self,
                u"中继尚未启用",
                u"请先勾选“启用中继监听”，点击保存中继配置后再启动。",
            )
            return
        report = validate_relay_config(candidate, check_windows=False)
        if report.get("errors"):
            show_warning(self, u"无法启动中继", "\n".join(report["errors"]) + u"\n\n请先修复配置并保存。")
            return
        controller = getattr(self.window(), "printer_relay_controller", None)
        if controller is None:
            show_warning(self, u"中继控制器未加载", u"请重新启动本 POS 后重试。")
            return
        self.config.update(candidate)
        save_config(self.config)
        try:
            started = bool(controller.start())
        except Exception as exc:
            started = False
            controller.last_error = str(exc)
        self._refresh_relay_status()
        if not started:
            show_warning(
                self,
                u"中继启动失败",
                getattr(controller, "last_error", "") or u"未能启动监听进程，请检查端口和服务状态。",
            )
            return
        QTimer.singleShot(800, self._refresh_relay_status)
        show_info(
            self,
            u"中继启动请求已发送",
            u"请稍等片刻，点击“刷新中继状态”确认监听正常；确认后回到官方 POS 打印真实测试单。",
        )

    def _stop_relay_listener(self):
        """Temporarily stop the listener without disabling or clearing config."""
        from ui.custom_dialog import show_info, show_warning
        controller = getattr(self.window(), "printer_relay_controller", None)
        if controller is None:
            show_warning(self, u"中继控制器未加载", u"请重新启动本 POS 后重试。")
            return
        try:
            controller.stop()
        except Exception as exc:
            show_warning(self, u"临时停止中继失败", str(exc))
            return
        self._refresh_relay_status()
        show_info(
            self,
            u"中继已临时停止",
            u"本次监听已停止，配置和独立服务安装状态均保留。需要恢复时点击“启动临时中继”；"
            u"官方 POS 在停止期间会显示收银机未连接。",
        )

    def _stop_relay_service(self):
        self._relay_service_action(
            lambda controller: controller.stop_service(),
            u"ppposPrinterRelay 已临时停止；若仍勾选启用，中继可能在守护检查时重新启动。",
            u"正在停止打印机中继服务",
            u"正在安全停止 ppposPrinterRelay，本次停止不会删除配置。",
            [
                u"检查当前服务状态",
                u"发送停止请求",
                u"等待 Windows 服务完全停止",
                u"确认监听端口已释放",
            ],
        )

    def _remove_relay_service(self):
        self._relay_service_action(
            lambda controller: controller.remove_service(),
            u"ppposPrinterRelay 已卸载；配置和识别日志均已保留。",
            u"正在卸载打印机中继服务",
            u"正在停止并删除 ppposPrinterRelay 服务注册，配置和识别日志会保留。",
            [
                u"核对服务状态和删除范围",
                u"停止打印机中继服务",
                u"删除 Windows 服务注册",
                u"确认服务已卸载并刷新状态",
            ],
        )

    def _refresh_relay_printers(self, show_toast=False):
        if not hasattr(self, "cmb_relay_printer_name"):
            return
        self.cmb_relay_printer_name.clear()
        printers = scan_printers()
        for name in printers:
            self.cmb_relay_printer_name.addItem(name)
        current = str(self.config.get("printer_name", "") or "")
        if current and current not in printers:
            self.cmb_relay_printer_name.addItem(current)
        if current:
            self.cmb_relay_printer_name.setCurrentText(current)
        if show_toast:
            from ui.custom_dialog import show_info, show_warning
            if printers:
                show_info(self, u"打印机扫描完成", u"检测到 %d 台 Windows 打印机，请确认实体输出打印机不是中继队列。" % len(printers))
            else:
                show_warning(self, u"未检测到实体打印机", u"请检查驱动或选择网络/串口输出方式。")

    def _refresh_relay_queues(self, show_toast=False):
        """扫描本机 Windows 打印队列，并把已保存名称保留为可选项。"""
        if not hasattr(self, "cmb_relay_queue"):
            return
        current = str(self.config.get("printer_relay_queue_name", "") or "").strip()
        typed = str(self.cmb_relay_queue.currentText() or "").strip()
        selected = typed or current
        self.cmb_relay_queue.blockSignals(True)
        self.cmb_relay_queue.clear()
        queues = []
        try:
            queues = list(scan_printers() or [])
        except Exception:
            queues = []
        seen = set()
        for name in queues:
            name = str(name).strip()
            if name and name not in seen:
                seen.add(name)
                self.cmb_relay_queue.addItem(name)
        if selected and selected not in queues:
            self.cmb_relay_queue.addItem(selected)
        if selected:
            self.cmb_relay_queue.setCurrentText(selected)
        self.cmb_relay_queue.blockSignals(False)
        if show_toast:
            from ui.custom_dialog import show_info, show_warning
            if queues:
                show_info(self, u"Windows 队列检测完成", u"检测到 %d 个队列，请选择官方 POS 要指向的中继队列。\n实体输出打印机要选择另一台，避免循环打印。" % len(queues))
            else:
                show_warning(self, u"未检测到 Windows 队列", u"请确认打印机驱动已安装；也可以暂时手动输入队列名称后保存。")

    def _relay_config_from_form(self):
        config = dict(self.config)
        config["printer_relay_port"] = self.spin_relay_listen_port.value()
        config["printer_relay_queue_name"] = self.cmb_relay_queue.currentText().strip()
        config["printer_relay_enabled"] = self.chk_relay_enabled.isChecked()
        config["printer_relay_capture_max_files"] = self.spin_relay_capture_max_files.value()
        config["printer_relay_mode_policy"] = self.cmb_relay_mode_policy.currentData() or MODE_POLICY_AUTO
        config["printer_name"] = self.cmb_relay_printer_name.currentText().strip()
        config["printer_type"] = self.cmb_relay_printer_type.currentText().split(" - ")[0].strip()
        config["printer_ip"] = self.txt_relay_ip.text().strip()
        config["printer_port"] = self.spin_relay_printer_port.value()
        config["printer_serial_port"] = self.txt_relay_serial_port.text().strip()
        config["official_pos_field_mapping"] = {
            key: [item.strip() for item in field.text().split(",") if item.strip()]
            for key, field in getattr(self, "relay_mapping_fields", {}).items()
        }
        return config

    def _on_relay_printer_type_changed(self, index=None):
        """只显示当前实体输出方式需要的配置，其他旧值继续保留。"""
        if not hasattr(self, "cmb_relay_printer_type"):
            return
        printer_type = self.cmb_relay_printer_type.currentText().split(" - ")[0].strip().lower()
        is_windows = printer_type == "windows"
        is_network = printer_type == "network"
        is_serial = printer_type == "serial"
        for widget in (self.lbl_relay_printer_name, self.cmb_relay_printer_name, self.btn_refresh_relay_printers):
            widget.setVisible(is_windows)
        for widget in (self.lbl_relay_ip, self.txt_relay_ip, self.lbl_relay_printer_port, self.spin_relay_printer_port):
            widget.setVisible(is_network)
        for widget in (self.lbl_relay_serial_port, self.txt_relay_serial_port):
            widget.setVisible(is_serial)

    def _on_save_relay(self):
        from ui.custom_dialog import show_info, show_warning
        candidate = self._relay_config_from_form()
        report = validate_relay_config(candidate, check_windows=False)
        if report.get("errors") and candidate.get("printer_relay_enabled"):
            show_warning(self, u"中继配置异常", "\n".join(report["errors"]))
            self.config.update(candidate)
            # 即使启用条件尚未满足，也要保留用户刚填写的配置，避免
            # 用户修复队列/打印机后重新打开页面时全部恢复成旧值。
            save_config(self.config)
            self._refresh_relay_status()
            return
        self.config.update(candidate)
        save_config(self.config)
        controller = getattr(self.window(), "printer_relay_controller", None)
        if controller is not None:
            try:
                controller.update_config(self.config)
            except Exception:
                pass
        self._refresh_relay_status()
        is_mapping_save = self.sender() is getattr(self, "btn_save_relay_mapping", None)
        if report.get("errors"):
            show_warning(self, u"配置已保存但尚未完成", u"中继当前停用，已保留配置。启用前请修复：\n" + "\n".join(report["errors"]))
        else:
            if is_mapping_save:
                show_info(
                    self, u"字段映射已保存",
                    u"已刷新当前中继状态。若当前仍是兼容模式，请回官方 POS 打印一张真实测试单；"
                    u"系统会根据新映射自动判断，不能仅凭手动刷新把未知数据强制变成增强模式。",
                )
            else:
                show_info(self, u"保存成功", u"打印机中继配置已保存。下一步请检查 Windows 队列并打印真实测试单。")

    def _check_relay_queue(self):
        from ui.custom_dialog import show_info, show_warning
        candidate = self._relay_config_from_form()
        report = validate_relay_config(candidate, check_windows=True)
        self.config["printer_relay_last_check_at"] = report.get("checked_at", "")
        self.config["printer_relay_last_error"] = "; ".join(report.get("errors", []))
        save_config(self.config)
        self._refresh_relay_status()
        if report.get("ok"):
            queue = report.get("queue_check") or {}
            show_info(self, u"中继队列检查通过", u"队列：%s\n端口：127.0.0.1:%s\n实体输出：%s" % (
                report.get("queue"), report.get("relay_port"), report.get("physical_printer") or u"默认打印机"))
        else:
            show_warning(self, u"中继配置异常", "\n".join(report.get("errors") or [u"请完成配置后重试"]))

    def _test_relay_print(self):
        from ui.custom_dialog import show_info, show_warning
        config = self._relay_config_from_form()
        report = validate_relay_config(config, check_windows=False)
        if report.get("errors"):
            show_warning(self, u"无法开始官方 POS 测试", "\n".join(report["errors"]) + u"\n\n请先完成中继配置并保存。")
            return
        state = self._relay_runtime_state()
        if not state.get("running"):
            show_warning(
                self,
                u"中继未启动，无法接收官方 POS 数据",
                u"当前中继监听未运行。此时官方 POS 会显示收银机未连接，不能把测试打印任务发送到本系统。\n\n"
                u"请按顺序处理：\n"
                u"1. 在“中继配置”勾选启用并保存；\n"
                u"2. 如果使用独立服务，到“服务维护”安装/启动 ppposPrinterRelay；\n"
                u"3. 点击“刷新中继状态”，确认显示“连接/监听正常”；\n"
                u"4. 回到官方 POS，选择 Windows 中继队列打印真实测试单。",
            )
            return
        show_info(
            self,
            u"中继已就绪，请从官方 POS 打印",
            u"监听地址：127.0.0.1:%s\n\n"
            u"本按钮不会伪造官方 POS 数据，也不会代替官方 POS 出单。请现在回到官方 POS，"
            u"选择已配置的 Windows 中继队列，打印一张真实测试单；打印完成后回到本页点击“刷新中继状态”。"
            % (state.get("port") or config.get("printer_relay_port") or 9101),
        )

    def _refresh_relay_status(self):
        if not hasattr(self, "lbl_relay_config_status"):
            return
        config = self._relay_config_from_form() if hasattr(self, "spin_relay_listen_port") else self.config
        report = validate_relay_config(config, check_windows=False)
        printer_type = str(config.get("printer_type", "windows") or "windows").lower()
        output_target = report.get("physical_printer") or u"默认打印机"
        if printer_type == "network":
            output_target = u"网络 %s:%s" % (
                config.get("printer_ip") or u"未填写",
                config.get("printer_port") or u"未填写",
            )
        elif printer_type == "serial":
            output_target = u"串口 %s" % (config.get("printer_serial_port") or u"未填写")
        if report.get("errors"):
            self.lbl_relay_config_status.setText(u"配置异常：\n" + "\n".join(report["errors"]))
        else:
            self.lbl_relay_config_status.setText(
                u"配置已填写：监听 127.0.0.1:%s；队列：%s；实体输出：%s\n"
                u"队列与实体打印机已做回环冲突检查。" % (
                    report.get("relay_port"), report.get("queue") or u"未填写",
                    output_target))
        state = self._relay_runtime_state()
        running = bool(state.get("running"))
        controller = getattr(self.window(), "printer_relay_controller", None)
        temporarily_stopped = bool(getattr(controller, "_temporarily_stopped", False))
        service_state = None
        service_controller = self._relay_service_controller()
        if service_controller is not None:
            try:
                service_state = service_controller.query()
            except Exception:
                service_state = None
        mode = state.get("mode") or self.config.get("printer_relay_mode", MODE_COMPATIBILITY)
        policy = state.get("mode_policy") or self.config.get("printer_relay_mode_policy", MODE_POLICY_AUTO)
        mode_reason = state.get("mode_reason") or self.config.get("printer_relay_mode_reason", "") or u"等待验证"
        mode_changed = state.get("mode_changed_at") or self.config.get("printer_relay_mode_changed_at", "") or u"暂无"
        detail = state.get("last_error") or state.get("message") or (u"监听运行中" if running else u"监听未运行")
        if temporarily_stopped and not running:
            detail = u"已由用户临时关闭监听；配置未清除，点击“启动临时中继”可恢复"
        # Only show data observed by the running relay.  A former offline
        # parser result is not evidence that the official POS sent anything
        # and must not make the page look successfully identified.
        source = state.get("payload_type") or u"等待官方 POS 真实测试单"
        identified_at = state.get("last_identified_at") or u"暂无"
        enhanced_at = state.get("last_enhanced_success_at") or u"暂无"
        service_detail = u"独立服务：未安装"
        if service_state is not None and service_state.installed:
            service_detail = u"独立服务：%s（ppposPrinterRelay）" % service_state.state
        policy_label = u"自动判断" if policy == MODE_POLICY_AUTO else u"强制兼容模式"
        self.lbl_relay_runtime_status.setText(u"当前状态：%s\n工作模式：%s（策略：%s）\n切换原因：%s\n最近模式切换：%s\n数据来源/识别：%s\n最近捕获：%s；最近增强成功：%s\n%s\n%s" % (
            u"连接/监听正常" if running else u"未运行或已降级", mode_label(mode),
            policy_label, mode_reason, mode_changed, source, identified_at,
            enhanced_at, detail, service_detail))
        # The capture sidecar is the source for the monitor.  The relay status
        # file is only a lightweight runtime signal and can be momentarily
        # empty while it is atomically replaced.  Scan sidecars so every
        # saved JSON gets its own tab and remains visible until retention
        # cleanup removes that file.
        capture_records = self._load_relay_capture_records(config, state)
        # Keep this as an inline, persistent reminder instead of a modal
        # dialog.  A parse failure/unknown ticket is actionable: the operator
        # needs to inspect the corresponding saved JSON in the live monitor,
        # not just be told that the relay is in compatibility mode.  A normal
        # not-configured/not-running fallback gets a separate, less alarming
        # explanation.
        received = state.get("last_received") if isinstance(state, dict) else {}
        received = received if isinstance(received, dict) else {}
        # Do not infer the reason from an old capture file: historical samples
        # are displayed for investigation, but they must not create a fresh
        # downgrade warning on their own.
        unknown_job = bool(received.get("parse_failed"))
        reason_text = u"%s %s" % (mode_reason, detail)
        unknown_job = unknown_job or any(
            marker in reason_text for marker in (u"未知", u"解析", u"无法识别", u"无法确认", u"状态未知")
        )
        degraded_mode = str(mode or "") in (MODE_COMPATIBILITY, "degraded")
        if hasattr(self, "lbl_relay_degrade_hint"):
            if degraded_mode and unknown_job:
                self.lbl_relay_degrade_hint.setText(
                    u"降级提醒：系统刚看到一张未知单子类型的官方 POS 打印单（暂时无法确认类型），"
                    u"已尝试保留原始打印路径并切回兼容模式。请打开“④ 真实测试”或“⑤ 字段重映射”"
                    u"中的实时监控，切换对应 JSON 标签查看识别结果；如标注不正确，请前往⑤字段重映射进行调整。"
                )
                self.lbl_relay_degrade_hint.setVisible(True)
            elif degraded_mode and (not running or report.get("errors")):
                self.lbl_relay_degrade_hint.setText(
                    u"兼容模式提示：中继当前未运行或配置尚未完成，系统继续使用原有连单锁和按重量分流。"
                    u"原因：%s" % (detail or mode_reason)
                )
                self.lbl_relay_degrade_hint.setVisible(True)
            else:
                self.lbl_relay_degrade_hint.clear()
                self.lbl_relay_degrade_hint.setVisible(False)
        signature = json.dumps(capture_records, ensure_ascii=False, sort_keys=True)
        if signature != self._relay_live_records_signature:
            self._relay_live_records_signature = signature
            self._relay_live_records_cache = capture_records
        for attr in ("lbl_relay_live_test", "lbl_relay_live_mapping"):
            monitor = getattr(self, attr, None)
            if monitor is not None:
                if getattr(monitor, "_relay_rendered_signature", "") != self._relay_live_records_signature:
                    self._set_relay_monitor_tabs(monitor, self._relay_live_records_cache)
                    monitor._relay_rendered_signature = self._relay_live_records_signature
        if hasattr(self, "lbl_relay_refresh_result"):
            self.lbl_relay_refresh_result.setText(
                u"状态已刷新：%s（%s）" % (
                    QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"),
                    u"监听正常" if running else u"未运行或已降级",
                )
            )

    @staticmethod
    def _make_relay_live_browser():
        browser = QTextBrowser()
        browser.setReadOnly(True)
        browser.setOpenExternalLinks(False)
        browser.setOpenLinks(False)
        browser.setStyleSheet(
            "QTextBrowser { color: #E0F2FE; background: #082F49; "
            "border: 1px solid #0369A1; border-radius: 10px; padding: 8px; "
            "font-size: 14px; }"
        )
        return browser

    @classmethod
    def _make_relay_live_monitor(cls):
        """Create a large tabbed monitor; one tab is one saved JSON sidecar."""
        monitor = QTabWidget()
        monitor.setMinimumHeight(460)
        monitor.setMaximumHeight(900)
        monitor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        monitor.setDocumentMode(False)
        monitor.setStyleSheet(
            "QTabWidget::pane { background: #082F49; border: 1px solid #0369A1; "
            "border-radius: 10px; }"
            "QTabBar::tab { background: #1E293B; color: #CBD5E1; padding: 10px 14px; "
            "font-size: 13px; min-width: 120px; }"
            "QTabBar::tab:selected { background: #0369A1; color: #FFFFFF; font-weight: 900; }"
        )
        monitor.addTab(cls._make_relay_live_browser(), u"等待 JSON")
        return monitor

    @staticmethod
    def _load_relay_capture_records(config, state):
        """Read saved JSON sidecars and merge live-only duplicate/link flags."""
        root = str(config.get("printer_relay_capture_dir") or os.path.join(DATA_DIR, "printer_relay_capture"))
        try:
            limit = max(1, int(config.get("printer_relay_capture_max_files", 20) or 20))
        except (TypeError, ValueError):
            limit = 20
        try:
            names = [name for name in os.listdir(root) if name.lower().endswith(".json")]
            names.sort(key=lambda name: os.path.getmtime(os.path.join(root, name)), reverse=True)
        except OSError:
            names = []
        live_records = {}
        if isinstance(state, dict):
            for record in state.get("recent_received") or []:
                if isinstance(record, dict) and record.get("capture_json_file"):
                    live_records[record.get("capture_json_file")] = record
        records = []
        for name in names[:limit]:
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    metadata = json.load(stream)
            except (OSError, TypeError, ValueError):
                continue
            if not isinstance(metadata, dict):
                continue
            stem = os.path.splitext(name)[0]
            # A sidecar can be an older saved capture rather than a packet
            # received during this UI session.  Keep that distinction visible
            # instead of presenting every file as a new live POS event.
            live_record = live_records.get(name, {})
            bin_path = os.path.join(root, stem + ".bin")
            extracted_text = str(metadata.get("extracted_text", "") or "")
            payment_method = str(metadata.get("payment_method", "") or "")
            if not payment_method:
                methods = []
                for method in re.findall(r"人民币|微信支付|支付宝支付|扫码支付|微信|支付宝|银行卡|刷卡", extracted_text):
                    if method not in methods:
                        methods.append(method)
                payment_method = "+".join(methods)
            recognized_fields = []
            if metadata.get("full_order_id"):
                recognized_fields.append("order_id")
            if metadata.get("order_no") and str(metadata.get("order_no")) != "#---":
                recognized_fields.append("call_no")
            if metadata.get("order_amount") is not None and metadata.get("amount_valid"):
                recognized_fields.append("amount")
            if str(metadata.get("payment_status") or "unknown") != "unknown":
                recognized_fields.append("payment_status")
            if payment_method:
                recognized_fields.append("payment_method")
            if metadata.get("item_count"):
                recognized_fields.append("items")
            record = {
                "received_at": metadata.get("captured_at", ""),
                "payload_type": metadata.get("payload_type", "binary_or_unknown"),
                "parse_failed": bool(metadata.get("parse_failed")),
                "receipt_kind": metadata.get("receipt_kind", "unknown"),
                "platform": metadata.get("platform", "官方 POS"),
                "order_id": metadata.get("full_order_id", ""),
                "call_no": metadata.get("order_no", ""),
                "amount": metadata.get("order_amount"),
                "amount_valid": bool(metadata.get("amount_valid")),
                "payment_status": metadata.get("payment_status", "unknown"),
                "payment_evidence": metadata.get("payment_status_evidence", ""),
                "payment_method": payment_method,
                "confidence": metadata.get("payment_status_confidence", "unknown"),
                "key_confidence": metadata.get("key_confidence", "low"),
                "item_count": int(metadata.get("item_count", 0) or 0),
                "capture_file": stem + ".bin",
                "capture_json_file": name,
                "capture_json_exists": True,
                "capture_bin_exists": os.path.isfile(bin_path),
                "capture_source": "live" if live_record else "saved_capture",
                "payload_size": int(metadata.get("payload_size", 0) or 0),
                "order_time": metadata.get("order_time", ""),
                "amount_source": metadata.get("amount_source", ""),
                "recognized_fields": recognized_fields,
                "extracted_text_preview": extracted_text[:500],
            }
            record.update({key: value for key, value in live_record.items()
                           if key in ("duplicate", "conflict_detected", "refund_linked",
                                      "refund_match_status", "refund_match_reason",
                                      "refund_original_order_key", "refund_original_order_id")})
            records.append(record)
        return records

    @staticmethod
    def _set_relay_monitor_tabs(monitor, records):
        selected = monitor.currentIndex()
        monitor.blockSignals(True)
        try:
            monitor.clear()
            if not records:
                monitor.addTab(SettingsWidget._make_relay_live_browser(), u"等待 JSON")
                monitor.widget(0).setHtml(SettingsWidget._relay_live_monitor_html({}))
                return
            total = len(records)
            for index, record in enumerate(records, 1):
                browser = SettingsWidget._make_relay_live_browser()
                browser.setHtml(SettingsWidget._relay_live_monitor_html({"recent_received": [record]}))
                filename = str(record.get("capture_json_file") or (u"任务%d" % index))
                tab_title = filename if len(filename) <= 24 else filename[:21] + "..."
                monitor.addTab(browser, u"%d %s" % (index, tab_title))
                monitor.setTabToolTip(monitor.count() - 1, filename)
            monitor.setCurrentIndex(min(max(0, selected), monitor.count() - 1))
        finally:
            monitor.blockSignals(False)

    @staticmethod
    def _relay_live_monitor_html(state):
        """Render the bounded capture batch with highlighted recognized fields."""
        records = state.get("recent_received") if isinstance(state, dict) else None
        if not isinstance(records, list) or not records:
            received = state.get("last_received") if isinstance(state, dict) else None
            records = [received] if isinstance(received, dict) and received else []
        if not records:
            return (
                u"<div style='font-size:16px;color:#BAE6FD;font-weight:700'>"
                u"实时监控：尚未收到官方 POS 打印数据</div>"
                u"<div style='color:#94A3B8;margin-top:6px'>启动中继后，官方 POS 每个打印任务都会在这里单独显示；"
                u"解析失败的任务也会保留，便于字段重映射。</div>"
            )

        kind_labels = {"dinein": u"堂食/顾客结账单", "takeout": u"外卖", "unknown": u"未识别"}
        status_labels = {
            "paid": (u"已结账", "#86EFAC"),
            "cancelled": (u"已取消/退款", "#FCA5A5"),
            "unknown": (u"状态未知", "#FDE68A"),
        }
        live_count = sum(1 for item in records if isinstance(item, dict) and item.get("capture_source") == "live")
        cards = [
            u"<div style='font-size:16px;color:#7DD3FC;font-weight:900;margin-bottom:8px'>"
            u"实时监控：已保存的实际捕获文件（%d 条，其中本次会话新收到 %d 条）</div>" % (len(records), live_count)
            + u"<div style='color:#CBD5E1;font-size:12px;margin-bottom:6px'>"
            u"这些记录来自磁盘中真实存在的 .json/.bin 文件；没有新打印时不会清空。"
            u"颜色说明：<span style='color:#F9A8D4;font-weight:900'>粉色字段=内置算法已提取</span>　"
            u"<span style='color:#86EFAC;font-weight:900'>绿色=已结账/金额已校验</span>　"
            u"<span style='color:#FDE68A;font-weight:900'>黄色=状态未知或解析失败</span></div>"
        ]
        for index, record in enumerate(records, 1):
            record = record if isinstance(record, dict) else {}
            filename = record.get("capture_json_file") or record.get("capture_file") or u"未生成 JSON 文件"
            kind = kind_labels.get(str(record.get("receipt_kind") or "unknown"), u"未识别")
            payment, payment_color = status_labels.get(
                str(record.get("payment_status") or "unknown"),
                (str(record.get("payment_status") or u"状态未知"), "#FDE68A"),
            )
            amount = record.get("amount")
            try:
                amount_text = u"¥%.2f" % float(amount) if amount is not None else u"未知"
            except (TypeError, ValueError):
                amount_text = u"未知"
            amount_color = "#86EFAC" if record.get("amount_valid") else "#FDE68A"
            order_id = record.get("order_id") or u"票面未提供"
            call_no = record.get("call_no") or u"未识别"
            parse_failed = bool(record.get("parse_failed"))
            border = "#F59E0B" if parse_failed else ("#22C55E" if payment == u"已结账" else "#0EA5E9")
            flags = []
            if parse_failed:
                flags.append(u"解析失败，已保留原始打印路径")
            if record.get("duplicate"):
                flags.append(u"重复观察，未重复计算")
            if record.get("conflict_detected"):
                flags.append(u"金额/状态冲突，未重复计算")
            flag_text = u"；".join(flags) if flags else u"本条可作为一次独立观察"
            evidence = record.get("payment_evidence") or u"无付款状态依据"
            recognized = record.get("recognized_fields") or []
            if not isinstance(recognized, list):
                recognized = [recognized]
            recognized_text = u"、".join(str(item) for item in recognized) or u"无（需重映射/人工核对）"
            refund_text = u""
            if str(record.get("payment_status") or "") == "cancelled":
                if record.get("refund_linked"):
                    refund_text = u"退款已关联原结账单：%s" % (record.get("refund_original_order_id") or record.get("refund_original_order_key") or u"已匹配")
                else:
                    refund_text = u"退款暂未关联原结账单：%s" % (record.get("refund_match_reason") or u"需要人工核对")
            preview = str(record.get("extracted_text_preview") or "").strip()
            if len(preview) > 360:
                preview = preview[:360] + "…"
            # The JSON-like line intentionally keeps field names visible so a
            # user can compare them with the raw capture while the colored
            # values show exactly what the built-in parser recognized.
            json_line = (
                u'{"receipt_kind":"%s", "platform":"%s", "full_order_id":"%s", "call_no":"%s", '
                u'"amount":%s, "payment_status":"%s", "payment_method":"%s", "item_count":%s}'
                % (html.escape(str(record.get("receipt_kind") or "unknown")),
                   html.escape(str(record.get("platform") or "官方 POS")),
                   html.escape(str(order_id)), html.escape(str(call_no)),
                   html.escape("null" if amount is None else str(amount)),
                   html.escape(str(record.get("payment_status") or "unknown")),
                   html.escape(str(record.get("payment_method") or "未知")),
                   html.escape(str(record.get("item_count") or 0)))
            )
            card = (
                u"<div style='border:1px solid %s;border-left:6px solid %s;"
                u"border-radius:8px;padding:8px;margin:5px 0;background:#0F2740'>"
                u"<div style='color:#BAE6FD;font-weight:900;font-family:Consolas,monospace'>"
                u"[%d] %s</div>"
                u"<div style='color:#94A3B8;font-size:12px'>收到=%s｜格式=%s｜大小=%s bytes｜平台=%s｜类型=%s｜来源=%s｜文件存在=JSON:%s BIN:%s</div>"
                u"<div style='font-family:Consolas,monospace;font-size:13px;margin-top:4px'>"
                u"<span style='color:#A78BFA'>JSON 元数据摘要（从已存在的 sidecar 文件读取）：</span>%s</div>"
                u"<div style='margin-top:4px'>"
                u"<span style='color:#CBD5E1'>识别：</span>"
                u"<span style='color:#F9A8D4;font-weight:900'>完整订单号=%s</span>　"
                u"<span style='color:#F9A8D4;font-weight:900'>POS订单号/叫号=%s</span>　"
                u"<span style='color:%s;font-weight:900'>金额=%s（%s）</span>　"
                u"<span style='color:%s;font-weight:900'>付款=%s</span>　"
                u"<span style='color:#C4B5FD;font-weight:900'>方式=%s</span>　"
                u"<span style='color:#93C5FD'>票据=%s</span>"
                u"</div>"
                u"<div style='color:#CBD5E1;font-size:12px'>依据=%s｜置信度=%s/%s｜%s</div>"
                u"<div style='color:#C4B5FD;font-size:12px'>已识别字段：%s｜金额来源：%s｜订单时间：%s</div>"
                u"<div style='color:#FCA5A5;font-size:12px'>%s</div>"
                % (border, border, index, html.escape(str(filename)),
                   html.escape(str(record.get("received_at") or u"未知")),
                   html.escape(str(record.get("payload_type") or u"未知")),
                   html.escape(str(record.get("payload_size") or 0)),
                   html.escape(str(record.get("platform") or u"官方 POS")), html.escape(kind),
                   u"本次中继收到" if record.get("capture_source") == "live" else u"历史保存捕获",
                   u"是" if record.get("capture_json_exists") else u"否",
                   u"是" if record.get("capture_bin_exists") else u"否",
                   json_line, html.escape(str(order_id)), html.escape(str(call_no)),
                   amount_color, html.escape(amount_text),
                   u"已校验" if record.get("amount_valid") else u"未校验",
                   payment_color, html.escape(payment),
                   html.escape(str(record.get("payment_method") or u"未知")), html.escape(kind),
                   html.escape(str(evidence)),
                   html.escape(str(record.get("confidence") or u"未知")),
                   html.escape(str(record.get("key_confidence") or u"未知")),
                   html.escape(flag_text), html.escape(recognized_text),
                   html.escape(str(record.get("amount_source") or u"未标注")),
                   html.escape(str(record.get("order_time") or u"未识别")),
                   html.escape(refund_text))
            )
            if preview:
                card += (
                    u"<pre style='white-space:pre-wrap;color:#94A3B8;font-size:11px;"
                    u"margin:5px 0 0 0'>原始文本摘要：%s</pre>" % html.escape(preview)
                )
            card += u"</div>"
            cards.append(card)
        cards.append(
            u"<div style='color:#FDE68A;margin-top:8px;font-weight:700'>"
            u"系统只把“官方 POS 结账单”按规则识别为已结账；打印制作单、控制数据或解析失败数据不会计入金额分流。"
            u"如系统标注不正确，请前往⑤字段重映射进行设置。</div>"
        )
        return "".join(cards)

    def _on_refresh_relay_status_clicked(self):
        """Refresh the runtime state and leave visible feedback in step 3."""
        self._refresh_relay_status()

    @staticmethod
    def _official_customer_template_text():
        return (
            "[C][B]{shop_subtitle}\n[L]{separator}\n"
            "[L][B][X]{pickup_line}\n[L]{separator}\n"
            "[L]{table_header}\n[L]{separator}\n[L]{items}\n"
            "[L]{separator}\n[L][B]{total_line}\n[L][B]{due_line}\n"
            "[L][B][D]{paid_line}\n[L]{separator}\n"
            "[L]订单号：{order_id}\n[L]订单时间：{time}\n[L]{separator}\n"
            "[L][B]加盟电话：{service_phone}"
        )

    @staticmethod
    def _official_kitchen_template_text():
        return (
            "[L][B][Y]取餐号：{kitchen_call_no}\n[L]{separator}\n"
            "[L][B][X]{kitchen_title_line}\n[L]{separator}\n"
            "[L][B][X]{item_name}\n[R][B][X]{weight}\n"
            "[L][B][X]  {flavor}\n[L]{separator}\n"
            "[L]操作人：{operator}\n[L]下单时间：{created_at}"
        )

    def _on_printer_template_profile_changed(self, index):
        """只在选择自定义方案时显示自定义模板编辑区。"""
        if not hasattr(self, "txt_printer_customer_template"):
            return
        is_custom = index == 2
        custom_widgets = (
            self.lbl_printer_custom_template_hint,
            self.lbl_printer_customer_template,
            self.txt_printer_customer_template,
            self.lbl_printer_kitchen_template,
            self.txt_printer_kitchen_template,
        )
        for widget in custom_widgets:
            widget.setVisible(is_custom)
            widget.setEnabled(is_custom)
        # 旧版方案使用下方的标题/底部字段；新版和自定义方案以正文模板
        # 为准，避免用户修改了一个当前方案不会读取的输入框。
        legacy_fields = (
            self.lbl_printer_customer_title,
            self.lbl_printer_customer_footer,
            self.lbl_printer_kitchen_title_dinein,
            self.lbl_printer_kitchen_title_packaging,
            self.lbl_printer_kitchen_footer,
            self.txt_printer_customer_title,
            self.txt_printer_customer_footer,
            self.txt_printer_kitchen_title_dinein,
            self.txt_printer_kitchen_title_packaging,
            self.txt_printer_kitchen_footer,
        )
        for field in legacy_fields:
            field.setVisible(index == 0)
            field.setEnabled(index == 0)
        report_fields = (
            self.lbl_printer_report_title,
            self.txt_printer_report_title,
            self.lbl_printer_report_footer,
            self.txt_printer_report_footer,
        )
        for field in report_fields:
            field.setVisible(True)
            field.setEnabled(True)
        template_fields = (
            self.chk_printer_logo,
            self.txt_printer_logo_path,
            self.btn_browse_printer_logo,
            self.lbl_printer_service_phone,
            self.txt_printer_service_phone,
            self.lbl_printer_operator,
            self.txt_printer_operator,
        )
        for field in template_fields:
            field.setVisible(index in (1, 2))
            field.setEnabled(index in (1, 2))
        if index == 1:
            self.txt_printer_customer_template.setPlainText(self._official_customer_template_text())
            self.txt_printer_kitchen_template.setPlainText(self._official_kitchen_template_text())
        elif index == 0:
            self.txt_printer_customer_template.setPlainText(self._official_customer_template_text())
            self.txt_printer_kitchen_template.setPlainText(self._official_kitchen_template_text())

    def _on_printer_width_changed(self):
        """同步纸宽预设与列数；自定义列数时开放数字框。"""
        if not hasattr(self, "cmb_printer_width"):
            return
        index = self.cmb_printer_width.currentIndex()
        if index == 0:
            self.spin_printer_columns.setValue(48)
            self.spin_printer_columns.setEnabled(False)
        elif index == 1:
            self.spin_printer_columns.setValue(32)
            self.spin_printer_columns.setEnabled(False)
        else:
            self.spin_printer_columns.setEnabled(True)

    # ────────────────────────────────────────────────────────────
    # 页面 1: 店铺与计价设置
    # ────────────────────────────────────────────────────────────
    def _build_biz_page(self):
        card, layout = self._create_section_card(
            u"🏪", u"店铺与计价设置", u"设置小票头部标题、分店名称和计价单位；商品价格请在“商品与分类”中维护"
        )
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"店名："), 0, 0)
        self.txt_shop = QLineEdit(self.config.get("shop_name", u"杨国福麻辣烫"))
        grid.addWidget(self.txt_shop, 0, 1, 1, 2)

        grid.addWidget(self._make_label(u"分店名称："), 1, 0)
        self.txt_sub = QLineEdit(self.config.get("shop_subtitle", u""))
        self.txt_sub.setPlaceholderText(u"例如：杨国福(肥西水晶城店)")
        grid.addWidget(self.txt_sub, 1, 1, 1, 2)

        grid.addWidget(self._make_label(u"计价方式："), 2, 0)
        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["per_jin - 按斤计价", "per_kg - 按公斤计价"])
        pu = self.config.get("price_unit", "per_jin")
        for i in range(self.cmb_unit.count()):
            if self.cmb_unit.itemText(i).startswith(pu):
                self.cmb_unit.setCurrentIndex(i)
                break
        grid.addWidget(self.cmb_unit, 2, 1, 1, 2)

        # 店铺信息和计价参数属于同一组配置，保存按钮与字段放在同一
        # 三级页面内，切换页面时不会把保存操作隐藏掉。
        self.btn_save_biz = QPushButton(u"💾 保存店铺与计价设置")
        self._style_save_btn(self.btn_save_biz)
        self.btn_save_biz.clicked.connect(self._on_save_biz)
        grid.addWidget(self.btn_save_biz, 3, 1, 1, 2)

        layout.addLayout(grid)
        # 商品与分类是“店铺与计价”的兄弟三级页面。它和店铺价格保存
        # 分开，避免修改一个商品时覆盖店铺基础信息。
        sku_panel = self._build_sku_catalog_panel()
        layout.addWidget(sku_panel)
        return self._wrap_in_scroll(card, [(u"店铺与计价", [2]), (u"商品与分类", [3])])

    def _build_sku_catalog_panel(self):
        """编辑主界面的分类和 SKU；数据仍保存在普通 config 中。"""
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background: #0F172A; border: 1px solid #334155; border-radius: 12px; }"
            "QLabel { border: none; background: transparent; }"
        )
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
        # Avoid the emoji variation selector here: several Win7 fonts render
        # 🧾 as an empty square.  This monochrome symbol is available in the
        # bundled/system fonts and keeps the title readable on older clients.
        title = QLabel(u"▦ 商品与分类")
        title.setStyleSheet("color: #BAE6FD; font-size: 20px; font-weight: 900;")
        outer.addWidget(title)
        hint = QLabel(u"维护点菜区显示的分类、商品名称、价格和顺序。‘全部’仅是主界面的筛选标签，不会单独保存。汤底的口味选项、点击卡片是否展示及自动隐藏时间在下方逐项配置。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #94A3B8; font-size: 13px;")
        outer.addWidget(hint)

        self._shop_catalog = get_shop_categories(self.config)
        row = QHBoxLayout()
        row.addWidget(self._make_label(u"分类："))
        self.cmb_sku_category = QComboBox()
        self.cmb_sku_category.setMinimumWidth(180)
        row.addWidget(self.cmb_sku_category, 1)
        self.btn_add_sku_category = QPushButton(u"＋新增分类")
        self._style_touch_action_btn(self.btn_add_sku_category, "blue")
        self.btn_add_sku_category.clicked.connect(self._add_sku_category)
        row.addWidget(self.btn_add_sku_category)
        self.btn_delete_sku_category = QPushButton(u"删除分类")
        self._style_touch_action_btn(self.btn_delete_sku_category, "danger")
        self.btn_delete_sku_category.clicked.connect(self._delete_sku_category)
        row.addWidget(self.btn_delete_sku_category)
        outer.addLayout(row)

        cat_grid = QGridLayout()
        cat_grid.setHorizontalSpacing(12)
        cat_grid.setVerticalSpacing(8)
        cat_grid.addWidget(self._make_label(u"分类名称："), 0, 0)
        self.txt_sku_category_name = QLineEdit()
        cat_grid.addWidget(self.txt_sku_category_name, 0, 1)
        cat_grid.addWidget(self._make_label(u"显示顺序："), 0, 2)
        self.spin_sku_category_order = QSpinBox()
        self.spin_sku_category_order.setRange(0, 999)
        cat_grid.addWidget(self.spin_sku_category_order, 0, 3)
        cat_grid.addWidget(self._make_label(u"口味设置："), 1, 0)
        self.lbl_sku_flavor_hint = QLabel(u"请在下方商品列表逐项设置；点击“改口味”始终可打开口味窗口")
        self.lbl_sku_flavor_hint.setStyleSheet("color: #94A3B8; font-size: 12px; background: transparent;")
        self.lbl_sku_flavor_hint.setWordWrap(True)
        cat_grid.addWidget(self.lbl_sku_flavor_hint, 1, 1, 1, 3)
        outer.addLayout(cat_grid)

        self.tbl_sku_items = QTableWidget(0, 6)
        self.tbl_sku_items.setHorizontalHeaderLabels([
            u"商品名称", u"价格（元）", u"顺序", u"点击展示口味", u"自动隐藏（秒）", u"口味选项（逗号分隔）"
        ])
        self.tbl_sku_items.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_sku_items.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tbl_sku_items.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tbl_sku_items.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.tbl_sku_items.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        # Keep functional columns readable on narrow POS screens.  Only the
        # product name expands; the long flavor editor scrolls horizontally
        # instead of shrinking every other column.
        self.tbl_sku_items.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.tbl_sku_items.setColumnWidth(1, 96)
        self.tbl_sku_items.setColumnWidth(2, 64)
        self.tbl_sku_items.setColumnWidth(3, 112)
        self.tbl_sku_items.setColumnWidth(4, 112)
        self.tbl_sku_items.setColumnWidth(5, 300)
        self.tbl_sku_items.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tbl_sku_items.horizontalHeader().setMinimumSectionSize(48)
        self.tbl_sku_items.setMinimumHeight(220)
        self.tbl_sku_items.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_sku_items.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_sku_items.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.tbl_sku_items.setAlternatingRowColors(True)
        self.tbl_sku_items.verticalHeader().setDefaultSectionSize(42)
        self.tbl_sku_items.setStyleSheet(
            "QTableWidget { background: #111827; color: #E2E8F0; font-size: 13px; "
            "gridline-color: #334155; border: 1px solid #334155; "
            "outline: none; } "
            "QTableWidget::item { background: #111827; color: #E2E8F0; "
            "padding: 6px 8px; border: none; } "
            "QTableWidget::item:alternate { background: #172136; color: #E2E8F0; } "
            "QTableWidget::item:selected { background: #334155; color: #F8FAFC; "
            "selection-background-color: #334155; selection-color: #F8FAFC; "
            "border: none; } "
            "QTableWidget::item:alternate:selected { background: #334155; "
            "color: #F8FAFC; } "
            "QLineEdit { background: #1E293B; color: #F8FAFC; "
            "selection-background-color: #0284C7; selection-color: #FFFFFF; "
            "border: 1px solid #38BDF8; border-radius: 4px; padding: 4px 6px; } "
            "QHeaderView::section { background: #1E293B; color: #BAE6FD; "
            "padding: 6px 5px; border: none; font-size: 13px; font-weight: 800; }"
        )
        outer.addWidget(self.tbl_sku_items)

        item_buttons = QHBoxLayout()
        self.btn_add_sku_item = QPushButton(u"＋新增商品")
        self._style_touch_action_btn(self.btn_add_sku_item, "blue")
        self.btn_add_sku_item.clicked.connect(self._add_sku_item)
        item_buttons.addWidget(self.btn_add_sku_item)
        self.btn_delete_sku_item = QPushButton(u"删除选中商品")
        self._style_touch_action_btn(self.btn_delete_sku_item, "danger")
        self.btn_delete_sku_item.clicked.connect(self._delete_sku_item)
        item_buttons.addWidget(self.btn_delete_sku_item)
        item_buttons.addStretch()
        self.btn_save_sku_catalog = QPushButton(u"💾 保存商品与分类")
        self._style_save_btn(self.btn_save_sku_catalog)
        self.btn_save_sku_catalog.clicked.connect(self._on_save_sku_catalog)
        item_buttons.addWidget(self.btn_save_sku_catalog)
        outer.addLayout(item_buttons)

        self.cmb_sku_category.currentIndexChanged.connect(self._load_sku_category_editor)
        self._refresh_sku_category_combo()
        return panel

    def _refresh_sku_category_combo(self, select_id=None):
        if not hasattr(self, "cmb_sku_category"):
            return
        self.cmb_sku_category.blockSignals(True)
        self.cmb_sku_category.clear()
        selected = -1
        for index, category in enumerate(self._shop_catalog):
            self.cmb_sku_category.addItem(u"%d  %s" % (index + 1, category.get("name", "")), category.get("id"))
            if category.get("id") == select_id:
                selected = index
        if selected < 0 and self._shop_catalog:
            selected = 0
        if selected >= 0:
            self.cmb_sku_category.setCurrentIndex(selected)
        self.cmb_sku_category.blockSignals(False)
        self._load_sku_category_editor(selected)

    def _current_sku_category(self):
        index = self.cmb_sku_category.currentIndex()
        return self._shop_catalog[index] if 0 <= index < len(self._shop_catalog) else None

    def _load_sku_category_editor(self, index):
        category = self._current_sku_category()
        if category is None:
            return
        # Flavor settings belong to soup products only.  Hide those columns
        # for ordinary categories instead of leaving disabled editors that
        # look like a broken input field; switching back to 汤底 restores them.
        show_flavor_columns = category.get("id") == "soup"
        for column in (3, 4, 5):
            self.tbl_sku_items.setColumnHidden(column, not show_flavor_columns)
        self.txt_sku_category_name.setText(category.get("name", ""))
        self.spin_sku_category_order.setValue(int(category.get("order", 0)))
        self.tbl_sku_items.setRowCount(0)
        for item in category.get("items", []):
            row = self.tbl_sku_items.rowCount()
            self.tbl_sku_items.insertRow(row)
            name = str(item.get("name", ""))
            is_soup = str(item.get("kind", "")) == "soup" or category.get("id") == "soup"
            self.tbl_sku_items.setItem(row, 0, QTableWidgetItem(name))
            price = item.get("price")
            if price is None and category.get("id") == "soup":
                price = self.config.get("special_soup_price", 50.0) if item.get("special") else self.config.get("unit_price", 47.60)
            price_item = QTableWidgetItem("%.2f" % float(price or 0.0))
            price_item.setTextAlignment(Qt.AlignCenter)
            order_item = QTableWidgetItem(str(item.get("order", row)))
            order_item.setTextAlignment(Qt.AlignCenter)
            self.tbl_sku_items.setItem(row, 1, price_item)
            self.tbl_sku_items.setItem(row, 2, order_item)

            flavor_check = QCheckBox()
            flavor_check.setChecked(bool(item.get("show_flavor", is_soup and name == u"经典草本骨汤")))
            flavor_check.setEnabled(is_soup)
            flavor_check.setToolTip(u"点击这个汤底卡片时是否弹出口味选择")
            flavor_wrap = QWidget()
            flavor_layout = QHBoxLayout(flavor_wrap)
            flavor_layout.setContentsMargins(0, 0, 0, 0)
            flavor_layout.setAlignment(Qt.AlignCenter)
            flavor_layout.addWidget(flavor_check)
            self.tbl_sku_items.setCellWidget(row, 3, flavor_wrap)

            hide_spin = QDoubleSpinBox()
            hide_spin.setRange(0.0, 60.0)
            hide_spin.setSingleStep(0.5)
            hide_spin.setDecimals(1)
            hide_spin.setSuffix(u" 秒")
            hide_spin.setValue(float(item.get("flavor_auto_hide_sec", 1.0) or 0.0))
            hide_spin.setEnabled(is_soup)
            hide_spin.setStyleSheet(
                "QDoubleSpinBox { background: #1E293B; color: #F8FAFC; "
                "border: 1px solid #475569; border-radius: 5px; padding: 3px 22px 3px 5px; "
                "min-width: 76px; font-size: 12px; }"
                "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 19px; "
                "background: #334155; border: none; }"
            )
            hide_spin.setToolTip(u"选择口味后自动关闭；填 0 表示不自动关闭")
            self.tbl_sku_items.setCellWidget(row, 4, hide_spin)

            options = item.get("flavor_options") or default_flavor_options(name)
            options_edit = QLineEdit(u"，".join(str(option) for option in options))
            options_edit.setPlaceholderText(u"例如：不辣，微辣，中辣，重辣")
            options_edit.setEnabled(is_soup)
            self.tbl_sku_items.setCellWidget(row, 5, options_edit)

    def _add_sku_category(self):
        cid = "category_%d" % (len(self._shop_catalog) + 1)
        self._shop_catalog.append({"id": cid, "name": u"新分类", "order": len(self._shop_catalog), "show_flavor": False, "default": False, "items": []})
        self._refresh_sku_category_combo(cid)

    def _delete_sku_category(self):
        category = self._current_sku_category()
        if category is None:
            return
        from ui.custom_dialog import show_question, show_warning
        if len(self._shop_catalog) <= 1:
            show_warning(self, u"无法删除", u"至少保留一个商品分类。")
            return
        if category.get("default"):
            for step in range(1, 4):
                if not show_question(self, u"删除默认分类（第%d/3次确认）" % step, u"确定删除默认分类‘%s’及其商品吗？删除后可重新新增，但不会恢复原有商品。" % category.get("name", "")):
                    return
        elif not show_question(self, u"删除分类", u"确定删除分类‘%s’及其商品吗？" % category.get("name", "")):
            return
        cid = category.get("id")
        self._shop_catalog = [item for item in self._shop_catalog if item.get("id") != cid]
        self._refresh_sku_category_combo()

    def _add_sku_item(self):
        category = self._current_sku_category()
        if category is None:
            return
        row = self.tbl_sku_items.rowCount()
        self.tbl_sku_items.insertRow(row)
        self.tbl_sku_items.setItem(row, 0, QTableWidgetItem(u"新商品"))
        price_item = QTableWidgetItem("1.00")
        price_item.setTextAlignment(Qt.AlignCenter)
        order_item = QTableWidgetItem(str(row))
        order_item.setTextAlignment(Qt.AlignCenter)
        self.tbl_sku_items.setItem(row, 1, price_item)
        self.tbl_sku_items.setItem(row, 2, order_item)
        is_soup = category.get("id") == "soup"
        flavor_check = QCheckBox()
        flavor_check.setChecked(is_soup and row == 0)
        flavor_check.setEnabled(is_soup)
        flavor_wrap = QWidget()
        flavor_layout = QHBoxLayout(flavor_wrap)
        flavor_layout.setContentsMargins(0, 0, 0, 0)
        flavor_layout.setAlignment(Qt.AlignCenter)
        flavor_layout.addWidget(flavor_check)
        self.tbl_sku_items.setCellWidget(row, 3, flavor_wrap)
        hide_spin = QDoubleSpinBox()
        hide_spin.setRange(0.0, 60.0)
        hide_spin.setSingleStep(0.5)
        hide_spin.setDecimals(1)
        hide_spin.setSuffix(u" 秒")
        hide_spin.setValue(1.0 if is_soup else 0.0)
        hide_spin.setEnabled(is_soup)
        hide_spin.setStyleSheet(
            "QDoubleSpinBox { background: #1E293B; color: #F8FAFC; "
            "border: 1px solid #475569; border-radius: 5px; padding: 3px 22px 3px 5px; "
            "min-width: 76px; font-size: 12px; }"
            "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 19px; "
            "background: #334155; border: none; }"
        )
        self.tbl_sku_items.setCellWidget(row, 4, hide_spin)
        options_edit = QLineEdit(u"，".join(default_flavor_options(u"新商品")))
        options_edit.setEnabled(is_soup)
        self.tbl_sku_items.setCellWidget(row, 5, options_edit)

    def _delete_sku_item(self):
        row = self.tbl_sku_items.currentRow()
        if row >= 0:
            self.tbl_sku_items.removeRow(row)

    def _on_save_sku_catalog(self):
        category = self._current_sku_category()
        if category is None:
            return
        category["name"] = self.txt_sku_category_name.text().strip() or category.get("id", u"分类")
        category["order"] = self.spin_sku_category_order.value()
        # The old category-wide switch is retained in stored JSON for legacy
        # readers, but the active setting is now per soup SKU below.
        category["show_flavor"] = category.get("show_flavor", category.get("id") == "soup") if category.get("id") == "soup" else False
        old_items = list(category.get("items", []))
        items = []
        for row in range(self.tbl_sku_items.rowCount()):
            name = self.tbl_sku_items.item(row, 0).text().strip() if self.tbl_sku_items.item(row, 0) else u"新商品"
            try:
                price = float(self.tbl_sku_items.item(row, 1).text()) if self.tbl_sku_items.item(row, 1) else 0.0
            except (TypeError, ValueError):
                price = 0.0
            try:
                order = int(float(self.tbl_sku_items.item(row, 2).text())) if self.tbl_sku_items.item(row, 2) else row
            except (TypeError, ValueError):
                order = row
            previous = old_items[row] if row < len(old_items) else {}
            is_soup = category.get("id") == "soup"
            if is_soup:
                # 与店铺基础单价相同表示“跟随基础单价”，不固化成 SKU
                # 覆盖值；只有不同价格才作为该汤底的独立价格保存。
                base = self.config.get("special_soup_price", 50.0) if previous.get("special", False) else self.config.get("unit_price", 47.60)
                stored_price = None if abs(price - float(base or 0.0)) < 0.0001 else price
            else:
                stored_price = price
            kind = previous.get("kind") or ("soup" if is_soup else "item")
            row_is_soup = kind == "soup"
            flavor_wrap = self.tbl_sku_items.cellWidget(row, 3)
            flavor_check = flavor_wrap.findChild(QCheckBox) if flavor_wrap is not None else None
            show_flavor = bool(flavor_check.isChecked()) if flavor_check is not None and row_is_soup else False
            hide_spin = self.tbl_sku_items.cellWidget(row, 4)
            hide_sec = float(hide_spin.value()) if hide_spin is not None and row_is_soup else 0.0
            options_edit = self.tbl_sku_items.cellWidget(row, 5)
            option_text = options_edit.text() if options_edit is not None and row_is_soup else ""
            flavor_options = [part.strip() for part in option_text.replace(",", "，").split("，") if part.strip()]
            if row_is_soup and not flavor_options:
                flavor_options = default_flavor_options(name)
            items.append({"id": previous.get("id") or "%s_item_%d" % (category.get("id"), row), "name": name, "price": stored_price, "order": order, "kind": kind, "special": bool(previous.get("special", False)), "show_flavor": show_flavor, "flavor_auto_hide_sec": hide_sec, "flavor_options": flavor_options if row_is_soup else []})
        category["items"] = items
        save_shop_categories(self.config, self._shop_catalog)
        save_config(self.config)
        parent_mw = self.window()
        if hasattr(parent_mw, "sale_page") and hasattr(parent_mw.sale_page, "reload_sku_catalog"):
            parent_mw.sale_page.reload_sku_catalog()
        self._refresh_sku_category_combo(category.get("id"))
        from ui.custom_dialog import show_info
        show_info(self, u"商品与分类已保存", u"主界面的分类标签和商品按钮已更新。")

    # ────────────────────────────────────────────────────────────
    # 页面 2: 系统与流转设置
    # ────────────────────────────────────────────────────────────
    def _build_sys_page(self):
        card, layout = self._create_section_card(
            u"⚙️", u"系统运行与触屏悬浮球", u"先配置官方 POS 窗口识别，再设置 Windows 开机自启与桌面常驻悬浮球"
        )

        # 官方 POS 窗口身份同时服务于启动检测和前台切换，不能混在称重
        # 数据源里。首次启动会要求选择一次；这里可以随时重新检测/更换。
        official_panel = QFrame()
        official_panel.setStyleSheet(
            "QFrame { background: #0F172A; border: 2px solid #8B5CF6; border-radius: 12px; }"
            "QLabel { border: none; background: transparent; }"
        )
        official_layout = QVBoxLayout(official_panel)
        official_layout.setContentsMargins(18, 16, 18, 16)
        official_layout.setSpacing(10)
        official_title = QLabel(u"🖥️ 官方 POS 窗口识别（必填）")
        official_title.setStyleSheet("color: #DDD6FE; font-size: 18px; font-weight: 900;")
        official_layout.addWidget(official_title)
        official_hint = QLabel(
            u"本项用于登录检测、自动切换和老板键避险。首次使用请先启动官方 POS，"
            u"点击“检测并选择窗口”；以后每次启动都按这里保存的识别词检测。"
        )
        official_hint.setWordWrap(True)
        official_hint.setStyleSheet("color: #CBD5E1; font-size: 14px;")
        official_layout.addWidget(official_hint)

        official_grid = QGridLayout()
        official_grid.setHorizontalSpacing(12)
        official_grid.setVerticalSpacing(10)
        official_grid.addWidget(self._make_label(u"当前状态："), 0, 0)
        self.lbl_official_window_status = QLabel("")
        self.lbl_official_window_status.setWordWrap(True)
        self.lbl_official_window_status.setStyleSheet("color: #C4B5FD; font-size: 14px;")
        official_grid.addWidget(self.lbl_official_window_status, 0, 1, 1, 2)

        official_grid.addWidget(self._make_label(u"窗口识别词（必填）："), 1, 0)
        self.txt_official_window_keywords = QLineEdit(
            ", ".join(self.config.get("official_pos_window_keywords", []))
        )
        self.txt_official_window_keywords.setPlaceholderText(u"选择窗口后自动填写；多个识别词用逗号分隔")
        official_grid.addWidget(self.txt_official_window_keywords, 1, 1, 1, 2)

        official_grid.addWidget(self._make_label(u"辅助进程名："), 2, 0)
        self.txt_official_process_name = QLineEdit(
            self.config.get("official_pos_process_name", "")
        )
        self.txt_official_process_name.setReadOnly(True)
        self.txt_official_process_name.setPlaceholderText(u"选择窗口后自动填写")
        official_grid.addWidget(self.txt_official_process_name, 2, 1, 1, 2)
        official_layout.addLayout(official_grid)

        official_buttons = QHBoxLayout()
        official_buttons.setSpacing(12)
        self.btn_select_official_window = QPushButton(u"检测并选择窗口")
        self._style_touch_action_btn(self.btn_select_official_window, "purple")
        self.btn_select_official_window.clicked.connect(self._select_official_window)
        official_buttons.addWidget(self.btn_select_official_window)
        self.btn_test_official_window = QPushButton(u"按当前配置检测")
        self._style_touch_action_btn(self.btn_test_official_window, "blue")
        self.btn_test_official_window.clicked.connect(self._test_official_window)
        official_buttons.addWidget(self.btn_test_official_window)
        self.btn_save_official_window = QPushButton(u"保存窗口识别")
        self._style_touch_action_btn(self.btn_save_official_window, "secondary")
        self.btn_save_official_window.clicked.connect(self._save_official_window)
        official_buttons.addWidget(self.btn_save_official_window)
        official_layout.addLayout(official_buttons)
        layout.addWidget(official_panel)
        self._refresh_official_window_status()

        runtime_panel = QFrame()
        runtime_panel.setStyleSheet(
            "QFrame { background: #0F172A; border: 2px solid #0EA5E9; border-radius: 12px; }"
            "QLabel { border: none; background: transparent; }"
        )
        runtime_layout = QVBoxLayout(runtime_panel)
        runtime_layout.setContentsMargins(18, 16, 18, 16)
        runtime_layout.setSpacing(10)
        runtime_title = QLabel(u"⏱ 系统运行参数")
        runtime_title.setStyleSheet("color: #BAE6FD; font-size: 18px; font-weight: 900;")
        runtime_layout.addWidget(runtime_title)
        runtime_hint = QLabel(u"开机启动和触屏悬浮球分别保存，修改一项不会覆盖另一项。")
        runtime_hint.setStyleSheet("color: #CBD5E1; font-size: 14px;")
        runtime_hint.setWordWrap(True)
        runtime_layout.addWidget(runtime_hint)

        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"开机自启动："), 0, 0)
        self.cmb_auto_start = QComboBox()
        self.cmb_auto_start.addItems([u"开启 - 随 Windows 启动并打开点餐系统", u"关闭 - 仅允许手动启动"])
        if not self.config.get("auto_start_enabled", True):
            self.cmb_auto_start.setCurrentIndex(1)
        grid.addWidget(self.cmb_auto_start, 0, 1, 1, 2)

        grid.addWidget(self._make_label(u"自启缓冲延迟："), 1, 0)
        self.spin_auto_start_delay = QSpinBox()
        self.spin_auto_start_delay.setRange(0, 60)
        self.spin_auto_start_delay.setSuffix(u" 秒")
        self.spin_auto_start_delay.setToolTip(u"设置软件随系统开机后静默等待的秒数，用于等待网卡和串口驱动加载完毕。")
        self.spin_auto_start_delay.setValue(self.config.get("auto_start_delay", 8))
        grid.addWidget(self.spin_auto_start_delay, 1, 1, 1, 2)

        grid.addWidget(self._make_label(u"桌面常驻触屏悬浮球："), 2, 0)
        self.cmb_floating_ball = QComboBox()
        self.cmb_floating_ball.addItems([u"开启 - 在屏幕边缘显示半透明触屏切换球", u"关闭 - 隐藏悬浮球"])
        if not self.config.get("floating_ball_enabled", True):
            self.cmb_floating_ball.setCurrentIndex(1)
        grid.addWidget(self.cmb_floating_ball, 2, 1, 1, 2)

        runtime_layout.addLayout(grid)
        runtime_buttons = QHBoxLayout()
        runtime_buttons.setSpacing(12)
        self.btn_save_auto_start = QPushButton(u"保存开机启动")
        self._style_touch_action_btn(self.btn_save_auto_start, "blue")
        self.btn_save_auto_start.clicked.connect(self._save_auto_start_settings)
        runtime_buttons.addWidget(self.btn_save_auto_start)
        self.btn_save_floating_ball = QPushButton(u"保存悬浮球")
        self._style_touch_action_btn(self.btn_save_floating_ball, "purple")
        self.btn_save_floating_ball.clicked.connect(self._save_floating_ball_settings)
        runtime_buttons.addWidget(self.btn_save_floating_ball)
        runtime_layout.addLayout(runtime_buttons)
        layout.addWidget(runtime_panel)

        # 应用 Logo 选择。这里单独保存，避免必须先完成官方 POS 识别词
        # 才能更换 Logo；选择后会同步更新左侧品牌徽标和窗口图标。
        logo_panel = QFrame()
        logo_panel.setStyleSheet(
            "QFrame { background: #0F172A; border: 2px solid #0EA5E9; border-radius: 12px; }"
            "QLabel { border: none; background: transparent; }"
        )
        logo_layout = QVBoxLayout(logo_panel)
        logo_layout.setContentsMargins(18, 16, 18, 16)
        logo_layout.setSpacing(10)
        logo_title = QLabel(u"🎨 应用 Logo")
        logo_title.setStyleSheet("color: #BAE6FD; font-size: 18px; font-weight: 900;")
        logo_layout.addWidget(logo_title)
        logo_hint = QLabel(u"可选择内置候选图标。保存后立即应用到左侧品牌标识和软件窗口图标。")
        logo_hint.setWordWrap(True)
        logo_hint.setStyleSheet("color: #CBD5E1; font-size: 14px;")
        logo_layout.addWidget(logo_hint)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(14)
        self.lbl_app_logo_preview = QLabel()
        self.lbl_app_logo_preview.setFixedSize(82, 82)
        self.lbl_app_logo_preview.setAlignment(Qt.AlignCenter)
        self.lbl_app_logo_preview.setStyleSheet(
            "background: #1E293B; border: 1px solid #475569; border-radius: 12px;"
        )
        logo_row.addWidget(self.lbl_app_logo_preview)
        self.cmb_app_logo = QComboBox()
        self.cmb_app_logo.setIconSize(QSize(52, 52))
        self.cmb_app_logo.setMinimumHeight(60)
        self.cmb_app_logo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        current_logo = str(self.config.get("app_logo_preset", "yangguofu") or "yangguofu")
        for preset_id, (label, _filename) in APP_LOGO_PRESETS.items():
            pixmap = QPixmap(app_logo_path(preset_id))
            self.cmb_app_logo.addItem(QIcon(pixmap), label, preset_id)
        index = self.cmb_app_logo.findData(current_logo)
        self.cmb_app_logo.setCurrentIndex(index if index >= 0 else 0)
        self.cmb_app_logo.currentIndexChanged.connect(self._preview_app_logo)
        logo_row.addWidget(self.cmb_app_logo, stretch=1)
        self.btn_save_app_logo = QPushButton(u"保存并应用 Logo")
        self._style_touch_action_btn(self.btn_save_app_logo, "blue")
        self.btn_save_app_logo.clicked.connect(self._save_app_logo)
        logo_row.addWidget(self.btn_save_app_logo)
        logo_layout.addLayout(logo_row)

        desktop_icon_row = QHBoxLayout()
        desktop_icon_row.setSpacing(12)
        desktop_icon_label = QLabel(u"桌面快捷方式图标：")
        desktop_icon_label.setStyleSheet("color: #E2E8F0; font-size: 15px; font-weight: bold;")
        desktop_icon_row.addWidget(desktop_icon_label)
        self.cmb_desktop_icon = QComboBox()
        self.cmb_desktop_icon.setIconSize(QSize(42, 42))
        self.cmb_desktop_icon.setMinimumHeight(54)
        self.cmb_desktop_icon.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        try:
            from installer_stub import current_shortcut_icon_preset
            current_desktop_icon = current_shortcut_icon_preset()
        except Exception:
            current_desktop_icon = "yangguofu"
        for preset_id, (label, _filename) in APP_LOGO_PRESETS.items():
            icon_path = os.path.join(DATA_DIR, "assets", "app_icon_%s.ico" % preset_id)
            self.cmb_desktop_icon.addItem(QIcon(icon_path), label, preset_id)
        custom_icon_path = self._custom_shortcut_icon_abs_path()
        custom_icon_label = str(self.config.get("custom_shortcut_icon_label", "") or "").strip()
        if os.path.isfile(custom_icon_path):
            custom_label = u"自定义：%s" % (custom_icon_label or u"上传图标")
            self.cmb_desktop_icon.addItem(QIcon(custom_icon_path), custom_label, "custom")
        desktop_index = self.cmb_desktop_icon.findData(current_desktop_icon)
        self.cmb_desktop_icon.setCurrentIndex(desktop_index if desktop_index >= 0 else 0)
        desktop_icon_row.addWidget(self.cmb_desktop_icon, stretch=1)
        self.btn_save_desktop_icon = QPushButton(u"保存桌面图标")
        self._style_touch_action_btn(self.btn_save_desktop_icon, "blue")
        self.btn_save_desktop_icon.clicked.connect(self._save_desktop_icon)
        desktop_icon_row.addWidget(self.btn_save_desktop_icon)
        logo_layout.addLayout(desktop_icon_row)

        custom_icon_row = QHBoxLayout()
        custom_icon_row.setSpacing(12)
        self.lbl_custom_shortcut_icon = QLabel(
            u"已上传：%s" % (custom_icon_label or u"未上传自定义图标")
        )
        self.lbl_custom_shortcut_icon.setStyleSheet("color: #CBD5E1; font-size: 14px;")
        self.lbl_custom_shortcut_icon.setWordWrap(True)
        custom_icon_row.addWidget(self.lbl_custom_shortcut_icon, stretch=1)
        self.btn_upload_shortcut_icon = QPushButton(u"上传快捷图标")
        self._style_touch_action_btn(self.btn_upload_shortcut_icon, "purple")
        self.btn_upload_shortcut_icon.clicked.connect(self._upload_shortcut_icon)
        custom_icon_row.addWidget(self.btn_upload_shortcut_icon)
        logo_layout.addLayout(custom_icon_row)

        category_row = QHBoxLayout()
        category_row.setSpacing(12)
        category_label = QLabel(u"登录界面应用分类：")
        category_label.setStyleSheet("color: #E2E8F0; font-size: 15px; font-weight: bold;")
        category_row.addWidget(category_label)
        self.cmb_shortcut_category = QComboBox()
        self.cmb_shortcut_category.setMinimumHeight(54)
        self.cmb_shortcut_category.setMaxVisibleItems(max(15, len(APP_CATEGORY_OPTIONS)))
        for category_id, (short_label, _title, _subtitle) in APP_CATEGORY_OPTIONS.items():
            self.cmb_shortcut_category.addItem(short_label, category_id)
        current_category = str(self.config.get("app_category", "") or "").strip()
        if current_category not in APP_CATEGORY_OPTIONS:
            current_category = app_category_for_icon(current_desktop_icon)
        category_index = self.cmb_shortcut_category.findData(current_category)
        self.cmb_shortcut_category.setCurrentIndex(category_index if category_index >= 0 else 0)
        category_row.addWidget(self.cmb_shortcut_category, stretch=1)
        self.btn_save_shortcut_category = QPushButton(u"保存登录分类")
        self._style_touch_action_btn(self.btn_save_shortcut_category, "blue")
        self.btn_save_shortcut_category.clicked.connect(self._save_shortcut_category)
        category_row.addWidget(self.btn_save_shortcut_category)
        logo_layout.addLayout(category_row)
        self.cmb_desktop_icon.currentIndexChanged.connect(self._sync_shortcut_category_from_icon)
        layout.addWidget(logo_panel)
        self._preview_app_logo(self.cmb_app_logo.currentIndex())

        reminder_panel = QFrame()
        reminder_panel.setStyleSheet(
            "QFrame { background: #0F172A; border: 2px solid #F59E0B; border-radius: 12px; }"
            "QLabel { border: none; background: transparent; }"
        )
        # Keep the reminder card and its form anchored to the content area's
        # left edge.  Without an explicit expanding policy, Qt may size the
        # grid to its hint width and center it on wide screens.
        reminder_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        reminder_layout = QVBoxLayout(reminder_panel)
        reminder_layout.setContentsMargins(18, 16, 18, 16)
        reminder_layout.setSpacing(10)
        reminder_title = QLabel(u"🔔 提醒设置")
        reminder_title.setStyleSheet("color: #FDE68A; font-size: 18px; font-weight: 900;")
        reminder_layout.addWidget(reminder_title)
        reminder_hint = QLabel(u"控制收银台上的低价、打包和精品串提示；关闭后不会影响计价或结账。")
        reminder_hint.setWordWrap(True)
        reminder_hint.setStyleSheet("color: #CBD5E1; font-size: 14px;")
        reminder_layout.addWidget(reminder_hint)

        reminder_grid = QGridLayout()
        reminder_grid.setHorizontalSpacing(12)
        reminder_grid.setVerticalSpacing(10)
        reminder_grid.setColumnStretch(0, 0)
        reminder_grid.setColumnStretch(1, 1)
        reminder_grid.addWidget(self._make_label(u"低价提醒："), 0, 0)
        self.cmb_low_price_warning = QComboBox()
        self.cmb_low_price_warning.addItems([u"开启", u"关闭"])
        if not self.config.get("low_price_warning_enabled", True):
            self.cmb_low_price_warning.setCurrentIndex(1)
        reminder_grid.addWidget(self.cmb_low_price_warning, 0, 1)

        reminder_grid.addWidget(self._make_label(u"低价阈值："), 1, 0)
        self.spin_low_price_threshold = QDoubleSpinBox()
        self.spin_low_price_threshold.setRange(0.01, 9999.99)
        self.spin_low_price_threshold.setDecimals(2)
        self.spin_low_price_threshold.setSuffix(u" 元")
        self.spin_low_price_threshold.setValue(
            float(self.config.get("low_price_warning_threshold", 15.00) or 15.00)
        )
        reminder_grid.addWidget(self.spin_low_price_threshold, 1, 1)

        reminder_grid.addWidget(self._make_label(u"打包提醒："), 2, 0)
        self.cmb_packing_reminder = QComboBox()
        self.cmb_packing_reminder.addItems([u"开启", u"关闭"])
        if not self.config.get("packing_reminder_enabled", True):
            self.cmb_packing_reminder.setCurrentIndex(1)
        reminder_grid.addWidget(self.cmb_packing_reminder, 2, 1)

        reminder_grid.addWidget(self._make_label(u"精品串提醒："), 3, 0)
        self.cmb_skewer_reminder = QComboBox()
        self.cmb_skewer_reminder.addItems([u"开启", u"关闭"])
        if not self.config.get("skewer_reminder_enabled", True):
            self.cmb_skewer_reminder.setCurrentIndex(1)
        reminder_grid.addWidget(self.cmb_skewer_reminder, 3, 1)
        reminder_layout.addLayout(reminder_grid, 1)
        self.btn_save_reminders = QPushButton(u"保存提醒设置")
        self._style_touch_action_btn(self.btn_save_reminders, "secondary")
        self.btn_save_reminders.clicked.connect(self._save_reminder_settings)
        reminder_layout.addWidget(self.btn_save_reminders, alignment=Qt.AlignRight)
        layout.addWidget(reminder_panel)

        return self._wrap_in_scroll(card, [(u"官方 POS 识别", [2]), (u"运行参数", [3]), (u"Logo 与分类", [4]), (u"提醒设置", [5])])

    # ────────────────────────────────────────────────────────────
    # 页面 5: 收钱吧设置
    # ────────────────────────────────────────────────────────────
    def _build_sqb_page(self):
        card, layout = self._create_section_card(
            u"💵", u"收钱吧 PC 收款助手", u"按“安装助手 → 保存参数 → 创建或检查配对 → 外部设置”的顺序配置"
        )

        intro = QLabel(
            u"<b>为什么这里有两个 COM？</b><br>"
            u"本 POS 把结账金额写入“本 POS 发送端”，收钱吧插件从“插件接收端”读取。"
            u"两个端口之间必须是一条成对的虚拟串口线，不能填写同一个 COM。<br>"
            u"如果现场已经用其他软件建好了配对，就选“使用已有配对”；如果没有，就选“由本系统创建”。"
            u"<br><b>收钱吧配对与电子秤桥接互不影响。</b>"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "color: #E0F2FE; background: #0C4A6E; border: 1px solid #0284C7; "
            "border-radius: 12px; padding: 16px; font-size: 16px;"
        )
        layout.addWidget(intro)

        # 随系统部署的收钱吧 PC 助手安装包：只提供下载/打开目录，不在
        # POS 内静默执行安装，避免管理员权限和正在运行的插件被强行打断。
        installer_panel = QFrame()
        installer_panel.setStyleSheet(
            "QFrame { background: #1E1B4B; border: 2px solid #8B5CF6; border-radius: 12px; }"
            "QLabel { border: none; background: transparent; }"
        )
        installer_layout = QVBoxLayout(installer_panel)
        installer_layout.setContentsMargins(18, 16, 18, 16)
        installer_layout.setSpacing(10)
        installer_title = QLabel(u"步骤 1　安装 / 检查收钱吧 PC 助手（v4.0.4）")
        installer_title.setStyleSheet("color: #DDD6FE; font-size: 18px; font-weight: 900;")
        installer_layout.addWidget(installer_title)
        self.lbl_sqb_installer_status = QLabel("")
        self.lbl_sqb_installer_status.setWordWrap(True)
        self.lbl_sqb_installer_status.setStyleSheet("color: #C4B5FD; font-size: 14px;")
        installer_layout.addWidget(self.lbl_sqb_installer_status)
        installer_buttons = QHBoxLayout()
        installer_buttons.setSpacing(12)
        self.btn_sqb_download = QPushButton(u"下载到桌面")
        self._style_touch_action_btn(self.btn_sqb_download, "purple")
        self.btn_sqb_download.clicked.connect(self._download_sqb_installer)
        installer_buttons.addWidget(self.btn_sqb_download)
        self.btn_sqb_open_folder = QPushButton(u"打开安装包目录")
        self._style_touch_action_btn(self.btn_sqb_open_folder, "purple")
        self.btn_sqb_open_folder.clicked.connect(self._open_sqb_installer_folder)
        installer_buttons.addWidget(self.btn_sqb_open_folder)
        installer_layout.addLayout(installer_buttons)
        layout.addWidget(installer_panel)
        self._refresh_sqb_installer_status()

        sqb_step1_title = QLabel(u"步骤 2　选择连接方式并填写两端参数")
        sqb_step1_title.setStyleSheet("font-size: 18px; color: #5EEAD4; font-weight: 900;")
        layout.addWidget(sqb_step1_title)

        self.sqb_connection_panel = QFrame()
        self.sqb_connection_panel.setStyleSheet(
            "QFrame { background: #132235; border: 1px solid #334155; border-radius: 12px; }"
            "QLabel { border: none; background: transparent; }"
        )
        connection_layout = QVBoxLayout(self.sqb_connection_panel)
        connection_layout.setContentsMargins(18, 16, 18, 16)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"功能开关："), 0, 0)
        self.cmb_sqb_enable = QComboBox()
        self.cmb_sqb_enable.addItems([u"开启 - 自动推送结账金额到收钱吧", u"关闭 - 不推送"])
        if not self.config.get("shouqianba_enabled", True):
            self.cmb_sqb_enable.setCurrentIndex(1)
        grid.addWidget(self.cmb_sqb_enable, 0, 1, 1, 2)

        grid.addWidget(self._make_label(u"虚拟串口来源："), 1, 0)
        self.cmb_sqb_pair_mode = QComboBox()
        self.cmb_sqb_pair_mode.addItem(u"还没有配对，由本系统创建（首次配置推荐）", "managed")
        self.cmb_sqb_pair_mode.addItem(u"现场已有配对，只填写并检查", "existing")
        if self.config.get("shouqianba_pair_mode", "managed") == "existing":
            self.cmb_sqb_pair_mode.setCurrentIndex(1)
        grid.addWidget(self.cmb_sqb_pair_mode, 1, 1, 1, 2)

        grid.addWidget(self._make_label(u"本 POS 发送端："), 2, 0)
        self.cmb_sqb_port = QComboBox()
        self.cmb_sqb_port.setEditable(True)
        self._refresh_com_ports()
        grid.addWidget(self.cmb_sqb_port, 2, 1)

        self.btn_refresh_sqb_ports = QPushButton(u"扫描现场已有 COM")
        self._style_touch_action_btn(self.btn_refresh_sqb_ports)
        self.btn_refresh_sqb_ports.clicked.connect(lambda: self._refresh_com_ports(show_toast=True))
        grid.addWidget(self.btn_refresh_sqb_ports, 2, 2)

        grid.addWidget(self._make_label(u"收钱吧插件接收端："), 3, 0)
        self.txt_sqb_payment_peer = QLineEdit()
        self.txt_sqb_payment_peer.setPlaceholderText("例如 COM11（必须与发送端不同）")
        self.txt_sqb_payment_peer.setText(str(self.config.get("shouqianba_plugin_port", "COM11")))
        grid.addWidget(self.txt_sqb_payment_peer, 3, 1, 1, 2)

        grid.addWidget(self._make_label(u"波特率："), 4, 0)
        self.cmb_sqb_baud = QComboBox()
        self.cmb_sqb_baud.addItems(["2400", "9600", "19200", "38400", "115200"])
        cur_baud = str(self.config.get("shouqianba_baudrate", 2400))
        self.cmb_sqb_baud.setCurrentText(cur_baud)
        grid.addWidget(self.cmb_sqb_baud, 4, 1, 1, 2)

        grid.addWidget(self._make_label(u"金额格式："), 5, 0)
        self.cmb_sqb_fmt = QComboBox()
        self.cmb_sqb_fmt.addItems([
            u"QA - QA标记 (例如 QA12.50)",
            u"FLOAT - 纯数字 (例如 12.50)"
        ])
        fmt = self.config.get("shouqianba_format", "QA")
        if fmt == "FLOAT":
            self.cmb_sqb_fmt.setCurrentIndex(1)
        grid.addWidget(self.cmb_sqb_fmt, 5, 1, 1, 2)

        grid.addWidget(self._make_label(u"插件安装目录："), 6, 0)
        install_dir_box = QVBoxLayout()
        install_dir_box.setSpacing(8)
        self.txt_sqb_install_dir = QLineEdit()
        self.txt_sqb_install_dir.setPlaceholderText(u"例如 C:\\smskv3；也可选择具体的 v4.0.4 目录")
        configured_install_dir = str(self.config.get("shouqianba_install_dir", "") or "").strip()
        if not configured_install_dir:
            try:
                from core.shouqianba_sender import discover_shouqianba_install_dir
                configured_install_dir = discover_shouqianba_install_dir(self.config)
            except Exception:
                configured_install_dir = ""
        self.txt_sqb_install_dir.setText(configured_install_dir)
        self.txt_sqb_install_dir.textChanged.connect(self._refresh_sqb_install_log_status)
        install_dir_box.addWidget(self.txt_sqb_install_dir)

        install_dir_buttons = QHBoxLayout()
        install_dir_buttons.setSpacing(10)
        self.btn_auto_detect_sqb_dir = QPushButton(u"自动检测安装目录")
        self._style_touch_action_btn(self.btn_auto_detect_sqb_dir, "purple")
        self.btn_auto_detect_sqb_dir.clicked.connect(self._auto_detect_sqb_install_dir)
        install_dir_buttons.addWidget(self.btn_auto_detect_sqb_dir)
        self.btn_browse_sqb_dir = QPushButton(u"选择目录")
        self._style_touch_action_btn(self.btn_browse_sqb_dir, "purple")
        self.btn_browse_sqb_dir.clicked.connect(self._browse_sqb_install_dir)
        install_dir_buttons.addWidget(self.btn_browse_sqb_dir)
        install_dir_box.addLayout(install_dir_buttons)

        self.lbl_sqb_log_status = QLabel("")
        self.lbl_sqb_log_status.setWordWrap(True)
        self.lbl_sqb_log_status.setStyleSheet("font-size: 13px; color: #94A3B8; border: none;")
        install_dir_box.addWidget(self.lbl_sqb_log_status)
        log_rule_tip = QLabel(
            u"到账以插件新增日志为准：金额单位为分（100 = 1.00 元），只有最终 PAID 才算支付成功。"
        )
        log_rule_tip.setWordWrap(True)
        log_rule_tip.setStyleSheet("font-size: 13px; color: #C4B5FD; border: none;")
        install_dir_box.addWidget(log_rule_tip)
        grid.addLayout(install_dir_box, 6, 1, 1, 2)
        self._refresh_sqb_install_log_status()

        grid.addWidget(self._make_label(u"唤起快捷键："), 7, 0)
        
        hk_box = QVBoxLayout()
        hk_box.setSpacing(10)
        self.txt_sqb_hotkey = HotKeyRecorderEdit()
        cur_hk = str(self.config.get("shouqianba_hotkey", "Shift+Q"))
        self.txt_sqb_hotkey.setText(cur_hk)
        hk_box.addWidget(self.txt_sqb_hotkey)

        # 快速预设按钮
        self.sqb_hotkey_preset_buttons = []
        hotkey_presets = QGridLayout()
        hotkey_presets.setHorizontalSpacing(10)
        hotkey_presets.setVerticalSpacing(10)
        for hk_item in ["Shift+Q", "F12", "Ctrl+F12", "Alt+S"]:
            btn_hk = QPushButton(hk_item)
            self._style_touch_action_btn(btn_hk)
            btn_hk.clicked.connect(lambda chk, t=hk_item: self.txt_sqb_hotkey.setText(t))
            self.sqb_hotkey_preset_buttons.append(btn_hk)
            index = len(self.sqb_hotkey_preset_buttons) - 1
            hotkey_presets.addWidget(btn_hk, index // 2, index % 2)
        hk_box.addLayout(hotkey_presets)

        grid.addLayout(hk_box, 7, 1, 1, 2)
        connection_layout.addLayout(grid)
        layout.addWidget(self.sqb_connection_panel)

        btn_save_sqb = QPushButton(u"② 保存收钱吧参数")
        self._style_save_btn(btn_save_sqb)
        btn_save_sqb.clicked.connect(self._on_save_sqb)
        layout.addWidget(btn_save_sqb)

        payment_panel = QFrame()
        payment_panel.setObjectName("PaymentPairPanel")
        payment_panel.setStyleSheet("""
            QFrame#PaymentPairPanel {
                background-color: #132235;
                border: 1px solid #0D9488;
                border-radius: 12px;
            }
            QFrame#PaymentPairPanel QLabel { border: none; background: transparent; }
        """)
        payment_layout = QVBoxLayout(payment_panel)
        payment_layout.setContentsMargins(18, 16, 18, 16)
        payment_layout.setSpacing(12)
        payment_title = QLabel(u"步骤 3　创建或检查虚拟串口配对")
        payment_title.setStyleSheet("color: #5EEAD4; font-size: 18px; font-weight: 900;")
        payment_layout.addWidget(payment_title)
        self.lbl_sqb_pair_guidance = QLabel("")
        self.lbl_sqb_pair_guidance.setWordWrap(True)
        self.lbl_sqb_pair_guidance.setStyleSheet("color: #CBD5E1; font-size: 15px;")
        payment_layout.addWidget(self.lbl_sqb_pair_guidance)

        payment_buttons = QGridLayout()
        payment_buttons.setHorizontalSpacing(12)
        payment_buttons.setVerticalSpacing(12)
        self.btn_initialize_payment_pair = QPushButton(u"③ 创建 / 修复虚拟串口")
        self._style_touch_action_btn(self.btn_initialize_payment_pair, "purple")
        self.btn_initialize_payment_pair.clicked.connect(self._initialize_payment_pair)
        payment_buttons.addWidget(self.btn_initialize_payment_pair, 0, 0)
        self.btn_check_payment_pair = QPushButton(u"④ 检查这两个端口是否成对")
        self._style_touch_action_btn(self.btn_check_payment_pair, "blue")
        self.btn_check_payment_pair.clicked.connect(self._check_payment_pair)
        payment_buttons.addWidget(self.btn_check_payment_pair, 0, 1)
        self.btn_test_payment_pair = QPushButton(u"⑤ 关闭两端软件后双向测试")
        self._style_touch_action_btn(self.btn_test_payment_pair, "blue")
        self.btn_test_payment_pair.clicked.connect(self._test_scale_bridge_payment_pair)
        payment_buttons.addWidget(self.btn_test_payment_pair, 1, 0)
        self.btn_remove_payment_pair = QPushButton(u"删除本系统创建的收钱吧配对")
        self._style_touch_action_btn(self.btn_remove_payment_pair, "danger")
        self.btn_remove_payment_pair.clicked.connect(self._remove_payment_pair)
        payment_buttons.addWidget(self.btn_remove_payment_pair, 1, 1)
        payment_layout.addLayout(payment_buttons)
        layout.addWidget(payment_panel)

        tip_frame = QFrame()
        tip_frame.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #0284C7; border-radius: 10px; }"
            "QLabel { border: none; background: transparent; }"
        )
        tip_layout = QVBoxLayout(tip_frame)
        lbl_tip_title = QLabel(u"步骤 4　到收钱吧 PC 助手中完成对应设置")
        lbl_tip_title.setStyleSheet("color: #38BDF8; font-size: 18px; font-weight: 900;")
        tip_layout.addWidget(lbl_tip_title)
        for tip in [
            u"• 【获取金额】选择上方填写的“收钱吧插件接收端”，不要选择本 POS 发送端。",
            u"• 【调出菜单】选择快捷键菜单，并与上方“唤起快捷键”保持一致。",
            u"• 【打印机设置】使用 USB 模式，不要选择兼容模式。",
        ]:
            label = QLabel(tip)
            label.setWordWrap(True)
            label.setStyleSheet("color: #E2E8F0; font-size: 15px;")
            tip_layout.addWidget(label)
        layout.addWidget(tip_frame)

        self.cmb_sqb_enable.currentIndexChanged.connect(self._on_sqb_mode_changed)
        self.cmb_sqb_pair_mode.currentIndexChanged.connect(self._on_sqb_mode_changed)
        self._on_sqb_mode_changed()

        return self._wrap_in_scroll(card, [(u"① 安装助手", [2, 3]), (u"② 参数配置", [4, 5, 6]), (u"③ 配对测试", [7]), (u"④ 外部设置", [8])])

    # ────────────────────────────────────────────────────────────
    # 页面 7: 危险操作与恢复
    # ────────────────────────────────────────────────────────────
    def _build_danger_page(self):
        card, layout = self._create_section_card(
            u"⚠️", u"配置导入导出与模块化还原", u"按需分别还原各模块配置，或导入导出完整设置文件"
        )
        card.setStyleSheet("""
            QFrame#SettingCard {
                background-color: #1E293B;
                border-radius: 16px;
                border: 2px solid #DC2626;
            }
        """)

        # ── 1. 配置文件导入与导出卡片 ──
        io_box = QFrame()
        io_box.setStyleSheet("QFrame { background-color: #0F172A; border-radius: 12px; border: 1px solid #0284C7; padding: 14px; }")
        io_layout = QVBoxLayout(io_box)
        io_layout.setSpacing(10)

        lbl_io_title = QLabel(u"📦 配置文件导入与导出 (快捷一键备份/还原分店设置)")
        lbl_io_title.setStyleSheet("font-size: 15px; font-weight: 900; color: #38BDF8; border: none; background: transparent;")
        io_layout.addWidget(lbl_io_title)

        lbl_io_desc = QLabel(u"将系统设置、打印机中继规则、私域门限及收钱吧等配置导出为 JSON 或 Zip 压缩包，方便快速迁移至其他窗口设备。")
        lbl_io_desc.setWordWrap(True)
        lbl_io_desc.setStyleSheet("font-size: 13px; color: #94A3B8; border: none; background: transparent;")
        io_layout.addWidget(lbl_io_desc)

        btn_row = QHBoxLayout()
        btn_export = QPushButton(u"📤 导出设置文件")
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setStyleSheet("QPushButton { background-color: #0284C7; color: white; font-size: 14px; font-weight: bold; padding: 10px 22px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #0369A1; }")
        btn_export.clicked.connect(self._on_export_config)
        btn_row.addWidget(btn_export)

        btn_import = QPushButton(u"📥 导入设置文件")
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.setStyleSheet("QPushButton { background-color: #0D9488; color: white; font-size: 14px; font-weight: bold; padding: 10px 22px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #0F766E; }")
        btn_import.clicked.connect(self._on_import_config)
        btn_row.addWidget(btn_import)
        btn_row.addStretch()
        io_layout.addLayout(btn_row)

        layout.addWidget(io_box)

        # ── 2. 模块化还原与重置管理 ──
        lbl_warn_title = QLabel(u"🚨 模块化还原与重置管理")
        lbl_warn_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #EF4444; background: transparent; margin-top: 10px;")
        layout.addWidget(lbl_warn_title)

        reset_items = [
            (
                u"⚙️", u"还原【系统与硬件配置】",
                u"仅还原串口、打印机、开机自启等基础系统参数 (base.json) 为出厂默认设置。", 
                u"⚙️ 还原系统配置",
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_sys_config
            ),
            (
                u"↔", u"还原【打印机中继与订单识别规则】",
                u"仅还原打印中继的订单识别、分类、匹配模式及打票字号规则。",
                u"↔ 还原外卖规则",
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_takeout_config
            ),
            (
                u"🧠", u"还原【私域切屏算法规则】",
                u"仅还原私域截留目标百分比与称重触发门限参数 (algo.json)。", 
                u"🧠 还原算法规则",
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_algo_config
            ),
            (
                u"💵", u"还原【收钱吧插件配置】",
                u"仅还原收钱吧推送端口、解析格式及唤起热键参数 (shouqianba.json)。", 
                u"💵 还原收钱吧配置",
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_sqb_config
            ),
            (
                u"🧹", u"清空运行与算法日志",
                u"仅擦除系统运行日志与算法追溯文件 (app_events.jsonl)。不会影响交易账目和参数配置。", 
                u"🧹 清空运行日志",
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_logs
            ),
            (
                u"📊", u"清空历史销售数据库",
                u"仅清空本地 SQLite 销售数据库 (sales.db)，擦除所有历史点餐记录。下次开单将自动重建库。", 
                u"📊 清空销售数据库",
                "background-color: #EA580C; color: white; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #F97316;",
                self._on_reset_db
            ),
            (
                u"🔥", u"一键彻底重置所有数据",
                u"高危全量操作！彻底擦除所有配置文件、销售数据库及日志文件。软件恢复最原始状态。", 
                u"🔥 一键彻底重置",
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #EF4444); color: white; font-size: 14px; font-weight: bold; padding: 10px 22px; border-radius: 8px; border: none;",
                self._on_reset
            ),
        ]

        for icon, title, desc, btn_txt, btn_style, slot_fn in reset_items:
            item_box = QFrame()
            item_box.setStyleSheet("""
                QFrame {
                    background-color: #0F172A;
                    border-radius: 12px;
                    border: 1px solid #334155;
                }
            """)
            h_layout = QHBoxLayout(item_box)
            h_layout.setContentsMargins(16, 12, 16, 12)
            h_layout.setSpacing(16)

            v_info = QVBoxLayout()
            v_info.setSpacing(4)

            t_lbl = QLabel(f"{icon} {title}")
            t_lbl.setStyleSheet("font-size: 15px; font-weight: 900; color: #F8FAFC; border: none; background: transparent;")
            d_lbl = QLabel(desc)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("font-size: 13px; color: #94A3B8; border: none; background: transparent;")
            v_info.addWidget(t_lbl)
            v_info.addWidget(d_lbl)

            h_layout.addLayout(v_info, stretch=1)

            btn = QPushButton(btn_txt)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ {btn_style} }}
                QPushButton:hover {{ border-color: #38BDF8; }}
            """)
            btn.clicked.connect(slot_fn)
            h_layout.addWidget(btn, alignment=Qt.AlignVCenter)

            layout.addWidget(item_box)

        return self._wrap_in_scroll(card, [(u"导入导出", [2]), (u"模块还原", [3, 4]), (u"清空与重置", [5, 6, 7, 8, 9, 10])])

    def _disable_wheel_events(self):
        """禁止鼠标滚轮在控件上意外修改数值"""
        for widget in self.findChildren((QComboBox, QSpinBox, QDoubleSpinBox)):
            widget.wheelEvent = lambda event, w=widget: event.ignore()

    def _run_maintenance_with_spinner(
        self, title, message, operation, on_success, error_title, busy_widgets,
        on_failure=None, stages=None,
    ):
        """Run driver/virtual-port maintenance without freezing touch UI."""
        if getattr(self, "_maintenance_thread", None) is not None:
            return

        states = [(widget, widget.isEnabled()) for widget in busy_widgets]
        for widget, _enabled in states:
            widget.setEnabled(False)

        # Scale-reader events can arrive while com0com changes devices. Pause
        # automatic window routing for the whole maintenance interaction;
        # otherwise a transient weight event can minimise this settings window
        # underneath the loading or result dialog.
        switch_controller = getattr(self.window(), "switch_controller", None)
        switch_paused = False
        if switch_controller and hasattr(switch_controller, "suspend_for_maintenance"):
            switch_controller.suspend_for_maintenance()
            switch_paused = True

        # QGraphicsBlurEffect on a QWidget uses an off-screen backing store.
        # On Win7, closing an application-modal child while a UAC/elevated
        # helper is active can briefly discard that backing store and expose
        # the desktop.  The busy dialog already provides an opaque modal
        # surface, so keep the parent live and stable instead of blurring it.
        blur = None
        self._maintenance_blur = None

        dialog = _MaintenanceBusyDialog(title, message, self, stages=stages)
        thread = QThread(self)
        worker = _MaintenanceWorker(operation)
        worker.moveToThread(thread)
        self._maintenance_dialog = dialog
        self._maintenance_thread = thread
        self._maintenance_worker = worker

        def restore_controls():
            for widget, enabled in states:
                widget.setEnabled(enabled)

        def resume_switch_routing():
            nonlocal switch_paused
            if switch_paused and hasattr(switch_controller, "resume_after_maintenance"):
                switch_controller.resume_after_maintenance()
            switch_paused = False

        def release_busy_visuals():
            restore_controls()
            if blur is not None and getattr(self, "_maintenance_blur", None) is blur:
                self.setGraphicsEffect(None)
                self._maintenance_blur = None

        def finish_thread():
            # Do this both here and immediately before the result dialog.  On
            # slower Win7 machines the QThread.finished event can arrive
            # after a modal success message is shown; the settings page must
            # already be clickable in that interval.
            release_busy_visuals()
            self._maintenance_dialog = None
            self._maintenance_thread = None
            self._maintenance_worker = None
            worker.deleteLater()
            thread.deleteLater()

        def show_success(result):
            try:
                on_success(result)
            except Exception as exc:
                from ui.custom_dialog import show_error
                show_error(self, error_title, str(exc) or exc.__class__.__name__)
            finally:
                # on_success may show a blocking result dialog; only resume
                # automatic routing after that dialog is dismissed.
                resume_switch_routing()

        def show_failure(reason, stage_log=""):
            try:
                if on_failure:
                    on_failure()
            except Exception:
                pass
            from ui.custom_dialog import show_error
            try:
                detail = reason
                if stage_log:
                    detail += u"\n\n操作阶段记录（可截图反馈）：\n" + stage_log
                show_error(self, error_title, detail)
            finally:
                resume_switch_routing()

        def succeeded(result):
            dialog.restore_parent_after_windows_prompt()
            dialog.finish()
            thread.quit()
            release_busy_visuals()
            # Let Qt finish closing the application-modal busy dialog before
            # opening the result message.  This prevents an invisible modal
            # window from swallowing all touch/mouse input.
            QTimer.singleShot(50, lambda: show_success(result))

        def failed(reason):
            stage_log = dialog.stage_log()
            dialog.restore_parent_after_windows_prompt()
            dialog.finish()
            thread.quit()
            release_busy_visuals()
            QTimer.singleShot(50, lambda: show_failure(reason, stage_log))

        worker.succeeded.connect(succeeded)
        worker.failed.connect(failed)
        # Connecting a decorated slot after moving the worker guarantees that
        # the potentially blocking operation runs on the worker thread.  The
        # previous code omitted this connection, leaving the dialog spinning
        # forever with no operation ever started.
        thread.started.connect(worker.run)
        thread.finished.connect(finish_thread)
        dialog.open()
        dialog.raise_()
        dialog.activateWindow()
        QApplication.processEvents()
        thread.start()

    # ─── 刷新 COM 串口列表 ──────────────────────────
    def _on_sqb_mode_changed(self, _index=None):
        """收钱吧先选是否启用、再选配对由谁维护，避免把高级操作混进基础参数。"""
        enabled = self.cmb_sqb_enable.currentIndex() == 0
        managed = self.cmb_sqb_pair_mode.currentIndex() == 0
        self.sqb_connection_panel.setEnabled(True)
        for widget in (
            self.cmb_sqb_pair_mode,
            self.cmb_sqb_port,
            self.btn_refresh_sqb_ports,
            self.txt_sqb_payment_peer,
            self.cmb_sqb_baud,
            self.cmb_sqb_fmt,
            self.txt_sqb_install_dir,
            self.btn_auto_detect_sqb_dir,
            self.btn_browse_sqb_dir,
            self.txt_sqb_hotkey,
        ):
            widget.setEnabled(enabled)
        for button in self.sqb_hotkey_preset_buttons:
            button.setEnabled(enabled)
        self.btn_initialize_payment_pair.setVisible(managed)
        self.btn_remove_payment_pair.setVisible(managed)
        self.btn_refresh_sqb_ports.setVisible(not managed)
        self.btn_check_payment_pair.setEnabled(enabled)
        self.btn_test_payment_pair.setEnabled(enabled)
        self.btn_initialize_payment_pair.setEnabled(enabled)
        self.btn_remove_payment_pair.setEnabled(enabled)
        if not enabled:
            self.lbl_sqb_pair_guidance.setText(u"收钱吧金额推送已关闭；保存后无需配置下面的配对。")
        elif managed:
            self.lbl_sqb_pair_guidance.setText(
                u"当前选择“由本系统创建”。先保存参数，再点击创建/修复；端口现在不存在是正常的。"
                u"创建完成后，将“插件接收端”填写到收钱吧 PC 助手。"
            )
        else:
            self.lbl_sqb_pair_guidance.setText(
                u"当前选择“使用现场已有配对”。本系统不会创建或删除端口；请填写配对两端后先检查。"
                u"如果检查显示不存在，请改选“由本系统创建”。"
            )

    def _refresh_sqb_install_log_status(self, _text=None):
        """Show whether the selected plugin directory exposes reliable logs."""
        if not hasattr(self, "txt_sqb_install_dir") or not hasattr(self, "lbl_sqb_log_status"):
            return
        from core.shouqianba_sender import validate_shouqianba_install_dir
        ok, message = validate_shouqianba_install_dir(self.txt_sqb_install_dir.text())
        color = "#34D399" if ok else "#FBBF24"
        prefix = u"已找到：" if ok else u"尚不可用："
        self.lbl_sqb_log_status.setText(prefix + message)
        self.lbl_sqb_log_status.setStyleSheet(
            "font-size: 13px; color: %s; border: none;" % color
        )

    def _auto_detect_sqb_install_dir(self, _checked=False):
        """Detect the smskv3 root on any local drive and verify its logs."""
        from core.shouqianba_sender import discover_shouqianba_install_dir
        from ui.custom_dialog import show_info, show_warning
        detected = discover_shouqianba_install_dir({})
        if not detected:
            show_warning(
                self,
                u"未检测到收钱吧插件",
                u"没有在本机磁盘根目录找到 smskv3。请先安装收钱吧 PC 助手，或点击“选择目录”手动指定。",
            )
            return
        self.txt_sqb_install_dir.setText(detected)
        self._refresh_sqb_install_log_status()
        show_info(self, u"检测完成", u"已找到收钱吧插件目录：\n%s" % detected)

    def _browse_sqb_install_dir(self, _checked=False):
        """Let the operator choose either smskv3 or a concrete version dir."""
        current = self.txt_sqb_install_dir.text().strip()
        if not os.path.isdir(current):
            current = os.environ.get("SystemDrive", "C:") + os.sep
        selected = QFileDialog.getExistingDirectory(
            self,
            u"选择收钱吧插件安装目录",
            current,
            QFileDialog.ShowDirsOnly,
        )
        if selected:
            self.txt_sqb_install_dir.setText(os.path.normpath(selected))
            self._refresh_sqb_install_log_status()

    def _refresh_com_ports(self, show_toast=False):
        self.cmb_sqb_port.clear()
        try:
            # pyserial can omit com0com CNC endpoints on Windows. Use the
            # shared WMI-backed discovery so old and newly created virtual
            # ports (for example COM13/14/15/16) are selectable here too.
            from scale_bridge.device_discovery import enumerate_serial_ports
            ports = sorted({item.port.upper() for item in enumerate_serial_ports(include_virtual=True)})
        except Exception:
            ports = []
        all_ports = [f"COM{i}" for i in range(1, 13)]
        for p in ports:
            if p not in all_ports:
                all_ports.append(p)
        configured = str(self.config.get("shouqianba_port", "")).strip().upper()
        if configured and configured not in all_ports:
            all_ports.append(configured)
        for p in sorted(all_ports, key=lambda x: int(x.replace("COM", "")) if x.startswith("COM") and x[3:].isdigit() else 99):
            self.cmb_sqb_port.addItem(p)
        cur = self.config.get("shouqianba_port", "COM10")
        if cur:
            self.cmb_sqb_port.setCurrentText(cur)

        if show_toast:
            from ui.custom_dialog import show_info, show_item_selection
            if ports:
                selected_port, ok = show_item_selection(
                    self, u"选择收钱吧串口", 
                    f"检测到 {len(ports)} 个当前系统 COM。这里可能同时包含物理端口和虚拟端口，"
                    u"仅在确认现场已有配对时选择本 POS 的发送端：",
                    ports, self.cmb_sqb_port.currentText()
                )
                if ok and selected_port:
                    self.cmb_sqb_port.setCurrentText(selected_port)
            else:
                show_info(self, u"扫描提示", u"未检测到现有 COM。若尚未建立收钱吧配对，请选择“由本系统创建”，端口当前不存在是正常的。")

    # ─── 收钱吧 PC 助手安装包 ────────────────────────
    def _sqb_installer_path(self):
        """Locate the deployment asset in both source and frozen layouts."""
        candidates = [
            os.path.join(BASE_DIR, "ThirdParty", "shouqianba", SQB_INSTALLER_NAME),
            os.path.join(os.path.dirname(BASE_DIR), "ThirdParty", "shouqianba", SQB_INSTALLER_NAME),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return candidates[0]

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().upper()

    def _refresh_sqb_installer_status(self):
        path = self._sqb_installer_path()
        if not os.path.isfile(path):
            self.lbl_sqb_installer_status.setText(
                u"未找到随系统部署的安装包。请确认 ThirdParty\\shouqianba\\%s 存在。" % SQB_INSTALLER_NAME
            )
            self.lbl_sqb_installer_status.setStyleSheet("color: #FCA5A5; font-size: 14px;")
            self.btn_sqb_download.setEnabled(False)
            self.btn_sqb_open_folder.setEnabled(False)
            return False
        try:
            actual_hash = self._sha256_file(path)
            size_mb = os.path.getsize(path) / (1024.0 * 1024.0)
        except (OSError, IOError) as exc:
            self.lbl_sqb_installer_status.setText(u"安装包读取失败：%s" % exc)
            self.lbl_sqb_installer_status.setStyleSheet("color: #FCA5A5; font-size: 14px;")
            self.btn_sqb_download.setEnabled(False)
            self.btn_sqb_open_folder.setEnabled(False)
            return False
        if actual_hash != SQB_INSTALLER_SHA256:
            self.lbl_sqb_installer_status.setText(
                u"安装包校验失败，已禁止复制。当前 SHA-256：%s" % actual_hash
            )
            self.lbl_sqb_installer_status.setStyleSheet("color: #FCA5A5; font-size: 14px;")
            self.btn_sqb_download.setEnabled(False)
            self.btn_sqb_open_folder.setEnabled(True)
            return False
        self.lbl_sqb_installer_status.setText(
            u"已集成到系统（%.1f MB），校验通过。点击“下载到桌面”即可复制给门店安装。" % size_mb
        )
        self.lbl_sqb_installer_status.setStyleSheet("color: #C4B5FD; font-size: 14px;")
        self.btn_sqb_download.setEnabled(True)
        self.btn_sqb_open_folder.setEnabled(True)
        return True

    @staticmethod
    def _desktop_path():
        user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        return os.path.join(user_profile, "Desktop")

    def _download_sqb_installer(self):
        from ui.custom_dialog import show_info, show_warning
        source = self._sqb_installer_path()
        if not self._refresh_sqb_installer_status():
            show_warning(self, u"安装包不可用", u"安装包不存在或校验失败，未执行复制。")
            return
        desktop = self._desktop_path()
        try:
            os.makedirs(desktop, exist_ok=True)
            destination = os.path.join(desktop, SQB_INSTALLER_NAME)
            if os.path.isfile(destination):
                if self._sha256_file(destination) == SQB_INSTALLER_SHA256:
                    show_info(self, u"安装包已存在", u"桌面已有相同版本安装包：\n%s" % destination)
                    QDesktopServices.openUrl(QUrl.fromLocalFile(desktop))
                    return
                stem, ext = os.path.splitext(SQB_INSTALLER_NAME)
                index = 1
                while os.path.exists(destination):
                    destination = os.path.join(desktop, "%s(%d)%s" % (stem, index, ext))
                    index += 1
            shutil.copy2(source, destination)
            show_info(self, u"下载完成", u"安装包已复制到桌面：\n%s" % destination)
            QDesktopServices.openUrl(QUrl.fromLocalFile(desktop))
        except (OSError, IOError) as exc:
            show_warning(self, u"下载失败", str(exc))

    def _open_sqb_installer_folder(self):
        from ui.custom_dialog import show_warning
        path = self._sqb_installer_path()
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            show_warning(self, u"目录不存在", folder)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ─── 刷新打印机列表 ──────────────────────────────
    def _refresh_printers(self, show_toast=False):
        """Legacy compatibility alias; the visible selector now lives on relay page."""
        return self._refresh_relay_printers(show_toast)

    # ─── 保存设置 ──────────────────────────────────
    def _apply_printer_paper_config(self):
        width_index = self.cmb_printer_width.currentIndex()
        if width_index == 0:
            self.config["printer_paper_width_mm"] = 80
            self.config["printer_chars_per_line"] = 48
        elif width_index == 1:
            self.config["printer_paper_width_mm"] = 58
            self.config["printer_chars_per_line"] = 32
        else:
            self.config["printer_paper_width_mm"] = 0
            self.config["printer_chars_per_line"] = self.spin_printer_columns.value()
        self.config["printer_separator_char"] = self.txt_printer_separator.text() or "-"
        self.config["printer_feed_lines"] = self.spin_printer_feed_lines.value()
        self.config["printer_auto_cut_enabled"] = self.chk_printer_auto_cut.isChecked()
        self.config["printer_cash_drawer_enabled"] = self.chk_printer_cash_drawer.isChecked()

    def _apply_printer_slips_config(self):
        self.config["printer_customer_enabled"] = self.chk_printer_customer.isChecked()
        self.config["printer_customer_copies"] = self.spin_printer_customer_copies.value()
        self.config["printer_kitchen_enabled"] = self.chk_printer_kitchen.isChecked()
        self.config["printer_kitchen_copies"] = self.spin_printer_kitchen_copies.value()
        self.config["printer_report_enabled"] = self.chk_printer_report.isChecked()
        self.config["printer_report_copies"] = self.spin_printer_report_copies.value()
        self.config["printer_show_tags"] = self.chk_printer_show_tags.isChecked()
        self.config["printer_packaging_banner_enabled"] = self.chk_printer_takeout_banner.isChecked()
        self.config["printer_packaging_banner_lines"] = self.spin_printer_packaging_banner_lines.value()

    def _apply_printer_template_config(self):
        self.config["printer_customer_title"] = self.txt_printer_customer_title.text()
        self.config["printer_customer_footer"] = self.txt_printer_customer_footer.text()
        self.config["printer_kitchen_title_dinein"] = self.txt_printer_kitchen_title_dinein.text()
        self.config["printer_kitchen_title_packaging"] = self.txt_printer_kitchen_title_packaging.text()
        self.config["printer_kitchen_footer"] = self.txt_printer_kitchen_footer.text()
        self.config["printer_report_title"] = self.txt_printer_report_title.text()
        self.config["printer_report_footer"] = self.txt_printer_report_footer.text()
        self.config["printer_service_phone"] = self.txt_printer_service_phone.text()
        self.config["printer_operator"] = self.txt_printer_operator.text()
        self.config["printer_logo_enabled"] = self.chk_printer_logo.isChecked()
        self.config["printer_logo_path"] = self.txt_printer_logo_path.text().strip()
        self.config["printer_template_profile"] = {
            0: "legacy",
            1: "official_v2",
            2: "custom",
        }.get(self.cmb_printer_template_profile.currentIndex(), "official_v2")
        self.config["printer_customer_template_custom"] = self.txt_printer_customer_template.toPlainText()
        self.config["printer_kitchen_template_custom"] = self.txt_printer_kitchen_template.toPlainText()

    def _save_printer_section(self, apply_config, title, message):
        apply_config()
        save_config(self.config)
        from ui.custom_dialog import show_info
        show_info(self, title, message)

    def _on_save_printer_paper(self):
        self._save_printer_section(
            self._apply_printer_paper_config,
            u"纸张设置已保存",
            u"纸张宽度、列数、走纸、切纸和钱箱设置已保存。",
        )

    def _on_save_printer_slips(self):
        self._save_printer_section(
            self._apply_printer_slips_config,
            u"单据设置已保存",
            u"单据开关、打印份数和外卖标记设置已保存。",
        )

    def _on_save_printer_template(self):
        self._save_printer_section(
            self._apply_printer_template_config,
            u"打印模板已保存",
            u"模板方案、正文、Logo 和票面文字设置已保存。",
        )

    def _on_save_printer(self):
        """Compatibility entry point: save all three paper-format sections."""
        self._apply_printer_paper_config()
        self._apply_printer_slips_config()
        self._apply_printer_template_config()
        save_config(self.config)
        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"全部打印纸格式设置已保存！")

    def _on_save_biz(self):
        self.config["shop_name"] = self.txt_shop.text()
        self.config["shop_subtitle"] = self.txt_sub.text()
        pu_text = self.cmb_unit.currentText()
        self.config["price_unit"] = pu_text.split(" - ")[0].strip()
        save_config(self.config)
        parent_mw = self.window()
        if hasattr(parent_mw, 'sale_page'):
            parent_mw.sale_page.refresh_unit_price_info()
        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"店铺与计价设置已保存！")

    def _preview_app_logo(self, index):
        """Show the selected bundled Logo before the operator saves it."""
        if not hasattr(self, "cmb_app_logo"):
            return
        preset_id = self.cmb_app_logo.itemData(index) or "yangguofu"
        pixmap = QPixmap(app_logo_path(preset_id))
        if pixmap.isNull():
            self.lbl_app_logo_preview.clear()
            self.lbl_app_logo_preview.setText(u"无预览")
            return
        self.lbl_app_logo_preview.setPixmap(
            pixmap.scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _save_app_logo(self):
        """Persist and apply the Logo without requiring unrelated system fields."""
        preset_id = self.cmb_app_logo.currentData() or "yangguofu"
        self.config["app_logo_preset"] = str(preset_id)
        save_config(self.config)
        parent_mw = self.window()
        if hasattr(parent_mw, "apply_app_logo"):
            parent_mw.apply_app_logo(self.config["app_logo_preset"])
        from ui.custom_dialog import show_info
        show_info(self, u"Logo 已保存", u"应用 Logo 已立即更新。")

    def _custom_shortcut_icon_abs_path(self):
        configured = str(self.config.get("custom_shortcut_icon_path", "") or "").strip()
        if not configured:
            return os.path.join(DATA_DIR, "assets", "custom_shortcut_icon.ico")
        return configured if os.path.isabs(configured) else os.path.abspath(os.path.join(BASE_DIR, configured))

    def _sync_shortcut_category_from_icon(self, index):
        """Use the bundled icon's sensible category as the next default."""
        if not hasattr(self, "cmb_shortcut_category"):
            return
        preset_id = self.cmb_desktop_icon.itemData(index) or "yangguofu"
        if preset_id == "custom":
            return
        category_id = app_category_for_icon(preset_id)
        category_index = self.cmb_shortcut_category.findData(category_id)
        if category_index >= 0:
            self.cmb_shortcut_category.setCurrentIndex(category_index)

    def _upload_shortcut_icon(self):
        from ui.custom_dialog import show_warning, show_info

        source, _filter = QFileDialog.getOpenFileName(
            self,
            u"选择快捷方式图标",
            os.path.expanduser("~"),
            u"图标或图片 (*.ico *.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*.*)",
        )
        if not source:
            return
        image = QImage(source)
        if image.isNull():
            show_warning(self, u"图标上传失败", u"无法读取这个图片文件。")
            return
        assets_dir = os.path.join(DATA_DIR, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        destination = os.path.join(assets_dir, "custom_shortcut_icon.ico")
        canvas = QImage(256, 256, QImage.Format_ARGB32)
        canvas.fill(0)
        scaled = image.convertToFormat(QImage.Format_ARGB32).scaled(
            240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        painter = QPainter(canvas)
        painter.drawImage((256 - scaled.width()) // 2, (256 - scaled.height()) // 2, scaled)
        painter.end()
        if not canvas.save(destination, "ICO"):
            show_warning(self, u"图标上传失败", u"系统无法转换为 Windows 快捷方式图标格式。")
            return

        label = os.path.splitext(os.path.basename(source))[0]
        self.config["custom_shortcut_icon_path"] = os.path.relpath(destination, BASE_DIR)
        self.config["custom_shortcut_icon_label"] = label
        custom_index = self.cmb_desktop_icon.findData("custom")
        custom_text = u"自定义：%s" % label
        if custom_index < 0:
            self.cmb_desktop_icon.addItem(QIcon(destination), custom_text, "custom")
            custom_index = self.cmb_desktop_icon.findData("custom")
        else:
            self.cmb_desktop_icon.setItemIcon(custom_index, QIcon(destination))
            self.cmb_desktop_icon.setItemText(custom_index, custom_text)
        self.cmb_desktop_icon.setCurrentIndex(custom_index)
        self.lbl_custom_shortcut_icon.setText(u"已上传：%s" % label)
        show_info(self, u"图标已上传", u"请选择对应的应用分类，然后点击“保存桌面图标”。")

    def _save_desktop_icon(self):
        """Save a bundled or uploaded shortcut icon and its login category."""
        preset_id = self.cmb_desktop_icon.currentData() or "yangguofu"
        category_id = self.cmb_shortcut_category.currentData() or "pos"
        try:
            if str(preset_id) == "custom":
                from installer_stub import update_current_shortcut_icon_file
                ok, detail = update_current_shortcut_icon_file(self._custom_shortcut_icon_abs_path())
            else:
                from installer_stub import update_current_shortcut_icon
                ok, detail = update_current_shortcut_icon(str(preset_id))
        except Exception as exc:
            ok, detail = False, str(exc)
        if ok:
            self.config["shortcut_icon_preset"] = str(preset_id)
            self.config["app_category"] = str(category_id)
            save_config(self.config)
            from ui.custom_dialog import show_info
            category_label = APP_CATEGORY_OPTIONS.get(str(category_id), (u"POS", "", ""))[0]
            show_info(self, u"桌面图标已保存", u"%s\n登录界面分类：%s" % (detail, category_label))
        else:
            from ui.custom_dialog import show_warning
            show_warning(self, u"桌面图标更新失败", detail)

    def _save_shortcut_category(self):
        """Persist the login-screen category independently from icon files."""
        from ui.custom_dialog import show_info
        category_id = str(self.cmb_shortcut_category.currentData() or "pos")
        self.config["app_category"] = category_id
        # Keep the selected shortcut preset in sync when this is an existing
        # bundled icon; custom uploads are already persisted by their own save.
        preset_id = self.cmb_desktop_icon.currentData() or "yangguofu"
        if preset_id != "custom":
            self.config["shortcut_icon_preset"] = str(preset_id)
        save_config(self.config)
        category_label = APP_CATEGORY_OPTIONS.get(category_id, (u"POS", "", ""))[0]
        show_info(self, u"登录分类已保存", u"下次打开登录页将使用“%s”分类文案。" % category_label)

    def _save_official_window(self):
        """Save only the official POS window identity fields."""
        from ui.custom_dialog import show_warning, show_info
        keywords = [
            value.strip()
            for value in self.txt_official_window_keywords.text().split(",")
            if value.strip()
        ]
        if not keywords:
            show_warning(self, u"缺少窗口识别词", u"请先填写官方 POS 窗口标题关键词。")
            return
        self.config["official_pos_window_configured"] = True
        self.config["official_pos_window_keywords"] = keywords
        process_name = self.txt_official_process_name.text().strip()
        self.config["official_pos_process_name"] = process_name
        self.config["official_pos_process_keywords"] = [process_name] if process_name else []
        save_config(self.config)
        parent_mw = self.window()
        if hasattr(parent_mw, "switch_controller") and parent_mw.switch_controller:
            parent_mw.switch_controller.update_config(self.config)
        self._refresh_official_window_status()
        show_info(self, u"窗口识别已保存", u"官方 POS 窗口识别词和辅助进程名已单独保存。")

    def _save_auto_start_settings(self):
        """Save only Windows auto-start settings and apply them immediately."""
        from ui.custom_dialog import show_info
        self.config["auto_start_enabled"] = (self.cmb_auto_start.currentIndex() == 0)
        self.config["auto_start_delay"] = self.spin_auto_start_delay.value()
        save_config(self.config)
        from utils.system_utils import apply_auto_start_settings
        apply_auto_start_settings(
            self.config["auto_start_enabled"], self.config["auto_start_delay"]
        )
        show_info(self, u"开机启动已保存", u"Windows 开机启动和缓冲延迟已单独保存并立即应用。")

    def _save_floating_ball_settings(self):
        """Save only the floating-ball visibility setting."""
        from ui.custom_dialog import show_info
        self.config["floating_ball_enabled"] = (self.cmb_floating_ball.currentIndex() == 0)
        save_config(self.config)
        parent_mw = self.window()
        ball = getattr(parent_mw, "floating_ball", None)
        if ball:
            if self.config["floating_ball_enabled"]:
                ball.show()
            else:
                ball.hide()
        show_info(self, u"悬浮球设置已保存", u"桌面常驻触屏悬浮球设置已单独保存并立即生效。")

    def _save_reminder_settings(self):
        """Save only cashier reminder switches and threshold."""
        from ui.custom_dialog import show_info
        self.config["low_price_warning_enabled"] = (self.cmb_low_price_warning.currentIndex() == 0)
        self.config["low_price_warning_threshold"] = self.spin_low_price_threshold.value()
        self.config["packing_reminder_enabled"] = (self.cmb_packing_reminder.currentIndex() == 0)
        self.config["skewer_reminder_enabled"] = (self.cmb_skewer_reminder.currentIndex() == 0)
        save_config(self.config)
        parent_mw = self.window()
        sale_page = getattr(parent_mw, "sale_page", None)
        if sale_page is not None and hasattr(sale_page, "config"):
            sale_page.config.update(self.config)
            if hasattr(sale_page, "_low_price_warning_shown"):
                sale_page._low_price_warning_shown = False
        show_info(self, u"提醒设置已保存", u"低价、打包和精品串提醒设置已单独保存。")

    def _on_save_sys(self):
        from ui.custom_dialog import show_warning
        window_keywords = [
            value.strip()
            for value in self.txt_official_window_keywords.text().split(",")
            if value.strip()
        ]
        if not window_keywords:
            show_warning(
                self,
                u"缺少官方 POS 窗口识别词",
                u"窗口识别词是启动检测和界面切换的必填项。请点击“检测并选择窗口”，或手动填写标题关键词。",
            )
            return
        self.config["official_pos_window_configured"] = True
        self.config["official_pos_window_keywords"] = window_keywords
        self.config["official_pos_process_name"] = self.txt_official_process_name.text().strip()
        process_name = self.config["official_pos_process_name"]
        self.config["official_pos_process_keywords"] = [process_name] if process_name else []
        self.config["auto_start_enabled"] = (self.cmb_auto_start.currentIndex() == 0)
        self.config["auto_start_delay"] = self.spin_auto_start_delay.value()
        self.config["floating_ball_enabled"] = (self.cmb_floating_ball.currentIndex() == 0)
        self.config["app_logo_preset"] = self.cmb_app_logo.currentData() or "yangguofu"
        self.config["shortcut_icon_preset"] = self.cmb_desktop_icon.currentData() or "yangguofu"
        self.config["app_category"] = self.cmb_shortcut_category.currentData() or "pos"
        self.config["low_price_warning_enabled"] = (self.cmb_low_price_warning.currentIndex() == 0)
        self.config["low_price_warning_threshold"] = self.spin_low_price_threshold.value()
        self.config["packing_reminder_enabled"] = (self.cmb_packing_reminder.currentIndex() == 0)
        self.config["skewer_reminder_enabled"] = (self.cmb_skewer_reminder.currentIndex() == 0)
        save_config(self.config)

        from utils.system_utils import apply_auto_start_settings
        apply_auto_start_settings(
            self.config["auto_start_enabled"], 
            self.config["auto_start_delay"]
        )

        parent_mw = self.window()
        if hasattr(parent_mw, "apply_app_logo"):
            parent_mw.apply_app_logo(self.config.get("app_logo_preset", "yangguofu"))
        if hasattr(parent_mw, 'switch_controller') and parent_mw.switch_controller:
            parent_mw.switch_controller.update_config(self.config)

        if hasattr(parent_mw, 'floating_ball') and parent_mw.floating_ball:
            if self.config["floating_ball_enabled"]:
                parent_mw.floating_ball.show()
            else:
                parent_mw.floating_ball.hide()

        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"系统运行与智能切换设置已保存！")

    def _official_window_form_config(self):
        """Build a temporary config from the system-settings form."""
        cfg = dict(self.config)
        keywords = [
            value.strip()
            for value in self.txt_official_window_keywords.text().split(",")
            if value.strip()
        ]
        process_name = self.txt_official_process_name.text().strip()
        cfg["official_pos_window_configured"] = bool(keywords)
        cfg["official_pos_window_keywords"] = keywords
        cfg["official_pos_process_name"] = process_name
        cfg["official_pos_process_keywords"] = [process_name] if process_name else []
        return cfg

    def _refresh_official_window_status(self):
        if not hasattr(self, "lbl_official_window_status"):
            return
        if not is_official_window_configured(self.config):
            self.lbl_official_window_status.setText(
                u"未配置。首次启动或点击“检测并选择窗口”完成绑定。"
            )
            self.lbl_official_window_status.setStyleSheet("color: #FCA5A5; font-size: 14px;")
            return
        info = find_official_window_info(self.config)
        if info:
            self.lbl_official_window_status.setText(
                u"已识别：%s（%s）" % (
                    info.get("title", ""), info.get("process_name") or u"未知进程"
                )
            )
            self.lbl_official_window_status.setStyleSheet("color: #34D399; font-size: 14px;")
        else:
            self.lbl_official_window_status.setText(
                u"已配置，但当前未找到窗口。请启动官方 POS 后点击“按当前配置检测”。"
            )
            self.lbl_official_window_status.setStyleSheet("color: #FBBF24; font-size: 14px;")

    def _select_official_window(self):
        from ui.custom_dialog import show_info, show_warning
        from ui.official_window_dialog import OfficialWindowPickerDialog

        current = {
            "title": self.config.get("official_pos_window_title", ""),
            "process_name": self.config.get("official_pos_process_name", ""),
        }
        dialog = OfficialWindowPickerDialog(current=current, parent=self)
        if dialog.exec_() != QDialog.Accepted or not dialog.selected_window:
            return
        if not apply_official_window_selection(self.config, dialog.selected_window):
            show_warning(self, u"选择失败", u"所选窗口信息无效，请重新刷新并选择。")
            return
        self.txt_official_window_keywords.setText(", ".join(self.config["official_pos_window_keywords"]))
        self.txt_official_process_name.setText(self.config.get("official_pos_process_name", ""))
        save_config(self.config)
        self._refresh_official_window_status()
        show_info(self, u"官方 POS 窗口已保存", u"以后启动检测和界面切换将按此窗口识别。")

    def _test_official_window(self):
        from ui.custom_dialog import show_info, show_warning
        cfg = self._official_window_form_config()
        if not cfg.get("official_pos_window_configured"):
            show_warning(self, u"尚未填写识别词", u"窗口识别词不能为空，请先选择窗口或手动填写标题关键词。")
            return
        info = find_official_window_info(cfg)
        if info:
            self.lbl_official_window_status.setText(
                u"检测通过：%s（%s）" % (info.get("title", ""), info.get("process_name") or u"未知进程")
            )
            self.lbl_official_window_status.setStyleSheet("color: #34D399; font-size: 14px;")
            show_info(self, u"官方 POS 检测通过", u"已按当前识别词找到官方 POS 窗口。")
        else:
            self.lbl_official_window_status.setText(u"检测失败：当前未找到匹配窗口。")
            self.lbl_official_window_status.setStyleSheet("color: #F87171; font-size: 14px;")
            show_warning(self, u"未找到官方 POS", u"请确认官方 POS 已启动，或重新选择窗口并保存识别词。")

    def _open_settings_page(self, index):
        """从说明或下一步按钮跳转到指定的系统设置二级页面。"""
        if index < 0 or index >= self.stacked_widget.count():
            return
        self._on_settings_page_changed(index)
        button = self.btn_group.button(index)
        if button is not None:
            button.setChecked(True)

    def _on_settings_page_changed(self, index):
        self.stacked_widget.setCurrentIndex(index)
        if index == 2 and self.cmb_scale_source.currentIndex() == 2:
            self._on_scale_source_changed(2)
        elif index == 3:
            self._refresh_scale_bridge_overall_status()
        elif index == 1:
            self._refresh_official_window_status()
        elif index == 4:
            self._on_sqb_mode_changed()

    def _scale_bridge_runtime_state(self):
        """返回桥接配置、是否可供本 POS 使用及面向操作员的状态文字。"""
        if not os.path.isfile(self._scale_bridge_config_path()):
            return None, False, u"尚未初始化 POS 称桥接"
        try:
            from scale_bridge.configuration import load_config
            bridge_config = load_config(self._scale_bridge_config_path())
        except Exception as exc:
            return None, False, u"桥接配置无法读取：%s" % exc

        configured = bool(
            bridge_config.physical_scale_port
            and bridge_config.official_pos_virtual_port
            and bridge_config.private_pos_virtual_port
            and bridge_config.official_bridge_port
            and bridge_config.private_bridge_port
        )
        if not configured:
            return bridge_config, False, u"桥接配置尚未完成初始化"
        try:
            from scale_bridge.lifecycle import ScaleBridgeServiceController
            service_state = ScaleBridgeServiceController().query()
            running = bool(service_state.installed and service_state.state_code == 4)
            if running:
                return bridge_config, True, u"桥接已就绪，服务正在运行"
            return bridge_config, False, u"桥接端口已创建，但 Windows 服务未运行"
        except Exception as exc:
            return bridge_config, False, u"桥接配置已存在，但无法确认服务状态：%s" % exc

    def _sync_scale_bridge_port_to_form(self):
        """桥接模式的 COM 由桥接结果决定，不让用户再猜或手填。"""
        bridge_config, ready, status = self._scale_bridge_runtime_state()
        port = bridge_config.private_pos_virtual_port if bridge_config is not None else ""
        self.cmb_scale_port.setEditable(True)
        if port:
            self.cmb_scale_port.setEditText(port)
        else:
            self.cmb_scale_port.setEditText(u"等待桥接初始化")
        self.cmb_scale_port.setEnabled(False)
        return bridge_config, ready, status

    def _on_scale_source_changed(self, index):
        """按官方、物理直连、桥接三种互斥方式显示所需字段。"""
        is_com = index in (1, 2)
        is_direct = index == 1
        is_bridge = index == 2
        self.lbl_scale_port.setVisible(is_com)
        self.cmb_scale_port.setVisible(is_com)
        self.btn_refresh_scale_ports.setVisible(is_direct)
        self.lbl_scale_baud.setVisible(is_com)
        self.cmb_scale_baud.setVisible(is_com)
        self.lbl_official_log_dir.setVisible(not is_com)
        self.txt_official_log_dir.setVisible(not is_com)
        self.btn_pick_official_log_dir.setVisible(not is_com)
        if hasattr(self, 'btn_test_scale_com'):
            self.btn_test_scale_com.setVisible(True)
        if hasattr(self, 'btn_go_scale_bridge'):
            self.btn_go_scale_bridge.setVisible(is_bridge)

        if is_direct:
            self.lbl_scale_port.setText(u"物理电子秤 COM：")
            self.cmb_scale_port.setEditable(True)
            self.cmb_scale_port.setEnabled(True)
            self._refresh_scale_com_ports()
            self.cmb_scale_baud.setEnabled(True)
            self.btn_test_scale_com.setText(u"⚡ 测试物理秤连接")
            self.lbl_scale_hint.setText(
                u"💡 本 POS 独占物理秤：\n"
                u"• DIBAL ACS-G315 已验证参数：9600、8N1；程序每 200ms 发送 $ 查询重量。\n"
                u"• 此处选择电子秤真实连接的 COM；使用期间官方 POS 不能同时占用这台秤。\n"
                u"• 如果两个 POS 都要读取重量，请改选“同时读秤”，不要在这里选择虚拟端口。"
            )
        elif is_bridge:
            self.lbl_scale_port.setText(u"本 POS 桥接端口：")
            bridge_config, ready, status = self._sync_scale_bridge_port_to_form()
            self.cmb_scale_baud.setEnabled(False)
            if bridge_config is not None:
                self.cmb_scale_baud.setCurrentText(str(bridge_config.baudrate))
            self.btn_test_scale_com.setText(u"⚡ 测试本 POS 桥接通道")
            status_icon = u"✅" if ready else u"⚠️"
            port_text = (
                bridge_config.private_pos_virtual_port
                if bridge_config is not None and bridge_config.private_pos_virtual_port
                else u"尚未生成"
            )
            self.lbl_scale_hint.setText(
                u"%s %s\n"
                u"• 本 POS 端口由“POS 称桥接”初始化结果自动填写：%s。\n"
                u"• 桥接未完成前不能保存此模式，也不需要从 COM 列表里猜端口。\n"
                u"• 点击“前往 POS 称桥接”，完成后再返回本页启用。"
                % (status_icon, status, port_text)
            )
        else:
            self.cmb_scale_port.setEnabled(True)
            self.cmb_scale_baud.setEnabled(True)
            self.lbl_scale_hint.setText(
                u"💡 官方模式 (推荐·零配置·无冲突)：\n"
                u"• 本 POS 直接读取官方收银软件生成的串口日志，不需要选择任何 COM。\n"
                u"• 官方 POS 必须保持运行；若官方升级改变安装目录，请选择它的 serial 日志文件夹。\n"
                u"• 如果希望本 POS 单独读秤或两个 POS 同时读秤，请选择对应方式。"
            )
            self.btn_test_scale_com.setText(u"⚡ 检测官方读数")

    def _pick_official_log_dir(self):
        selected = QFileDialog.getExistingDirectory(
            self, u"选择官方 POS 的 serial 日志文件夹", self.txt_official_log_dir.text() or "C:\\"
        )
        if selected:
            self.txt_official_log_dir.setText(selected)

    def _test_selected_scale_source(self):
        if self.cmb_scale_source.currentIndex() == 0:
            self._test_official_scale()
            return
        if self.cmb_scale_source.currentIndex() == 2:
            _bridge_config, ready, status = self._scale_bridge_runtime_state()
            if not ready:
                from ui.custom_dialog import show_warning
                show_warning(self, u"POS 称桥接尚未就绪", status + u"\n\n请先完成 POS 称桥接初始化。")
                return
            self._test_scale_bridge_channel("private")
            return
        self._test_scale_com()

    def _test_official_scale(self):
        """检查当前官方 POS 日志并解析一条最新重量。"""
        from ui.custom_dialog import show_info, show_warning
        from core.scale_reader import ScaleReader, read_file_shared

        # Test unsaved directory text too, so a POS upgrade can be verified
        # before the operator commits the new setting.
        test_config = dict(self.config)
        test_config["official_pos_log_dir"] = self.txt_official_log_dir.text().strip()
        reader = ScaleReader(test_config)
        target_file = reader._find_active_ygf_log()
        if not target_file:
            show_warning(
                self,
                u"未检测到官方称重日志",
                u"请确认官方 POS 已启动并正在刷新称重读数。\n\n"
                u"如果官方软件升级过目录，请先选择包含 log_serial_ports 文件的 serial 文件夹，"
                u"然后再次点击“检测官方读数”。",
            )
            return

        content = read_file_shared(target_file)
        latest_weight = None
        for line in reversed(content.splitlines()[-100:]):
            latest_weight = reader._parse_ygf_log_line(line)
            if latest_weight is not None:
                break
        if latest_weight is None:
            show_warning(
                self,
                u"日志已找到，但没有可解析重量",
                u"文件：%s\n\n请把物品放上官方秤，让官方 POS 产生一条新的读数后重试。" % target_file,
            )
            return

        show_info(
            self,
            u"官方读数检测成功",
            u"已读取官方 POS 的实时称重日志。\n\n"
            u"文件：%s\n当前重量：%.3f kg\n\n"
            u"本 POS 运行时会继续跟随该日志读取，不需要选择 COM。"
            % (target_file, latest_weight),
        )

    def _show_scale_bridge_status(self):
        """Read service status through its local named pipe; never opens a serial port."""
        from ui.custom_dialog import show_info, show_warning
        try:
            from scale_bridge.ipc import read_status
            status = read_status()
        except Exception as exc:
            show_warning(
                self, u"桥接服务未连接",
                u"无法读取 ScaleBridge 服务状态。\n\n"
                u"这不会修改现有 POS 设置；若已配置 ScaleBridge，请确认 Windows 服务已启动。\n\n"
                u"原因: " + str(exc),
            )
            return
        show_info(
            self, u"ScaleBridge 状态",
            u"模式: {mode}\n物理秤端口: {port}\n物理秤连接: {opened}\n"
            u"官方 POS / 服务端: {official_pos} / {official_peer}\n"
            u"本 POS / 服务端: {private_pos} / {private_peer}\n"
            u"最近重量: {weight}\n最近官方查询: {official_age}\n最近本 POS 查询: {private_age}\n"
            u"最近秤回包: {reply_age}\n合法/异常帧: {valid}/{invalid}\n"
            u"本 POS 查询抑制次数: {suppressed}\n重连/重新定位: {reconnect}/{rebound}\n"
            u"最近错误: {error}".format(
                mode=status.get("mode", "未知"),
                port=status.get("physical_port", ""),
                opened="是" if status.get("physical_open") else "否",
                official_pos=status.get("official_pos_virtual_port", ""),
                official_peer=status.get("official_bridge_port", ""),
                private_pos=status.get("private_pos_virtual_port", ""),
                private_peer=status.get("private_bridge_port", ""),
                weight=status.get("last_weight_kg", "无"),
                official_age=(str(status.get("last_official_poll_age_ms")) + " ms") if status.get("last_official_poll_age_ms") is not None else "无",
                private_age=(str(status.get("last_private_poll_age_ms")) + " ms") if status.get("last_private_poll_age_ms") is not None else "无",
                reply_age=(str(status.get("last_scale_reply_age_ms")) + " ms") if status.get("last_scale_reply_age_ms") is not None else "无",
                suppressed=status.get("suppressed_private_queries", 0),
                valid=status.get("valid_frames", 0),
                invalid=status.get("invalid_frames", 0),
                reconnect=status.get("reconnect_count", 0),
                rebound=status.get("rebound_count", 0),
                error=status.get("last_error") or "无",
            ),
        )

    @staticmethod
    def _bridge_port_text(value):
        """Extract the editable COM name from the device display text."""
        return str(value or "").split("[", 1)[0].strip().upper()

    def _scale_bridge_config_path(self):
        return os.path.join(DATA_DIR, "scale_bridge.json")

    def _load_scale_bridge_form(self):
        """Load only the independent bridge configuration; never alters POS settings."""
        from scale_bridge.configuration import load_config
        try:
            bridge_config = load_config(self._scale_bridge_config_path())
        except Exception:
            bridge_config = None

        if bridge_config is None:
            return
        self.txt_bridge_official_pos.setText(bridge_config.official_pos_virtual_port)
        self.txt_bridge_official_peer.setText(bridge_config.official_bridge_port)
        self.txt_bridge_private_pos.setText(bridge_config.private_pos_virtual_port)
        self.txt_bridge_private_peer.setText(bridge_config.private_bridge_port)
        self._refresh_scale_bridge_devices(silent=True, preferred_port=bridge_config.physical_scale_port)
        exists = os.path.isfile(self._scale_bridge_config_path())
        self.lbl_scale_bridge_config.setText(
            u"%s：%s。已验证秤协议固定为 9600 / 8N1 / DTR 开 / RTS 关。"
            % (u"已加载桥接配置" if exists else u"尚未保存桥接配置（显示默认值）", self._scale_bridge_config_path())
        )

    def _refresh_scale_bridge_overall_status(self):
        """用一句话显示当前能否真正启用桥接，避免把草稿误认为已完成。"""
        _bridge_config, ready, status = self._scale_bridge_runtime_state()
        if ready:
            self.lbl_scale_bridge_overall_status.setText(u"✅ 当前状态：%s。可以按步骤 4 验收并启用。" % status)
            self.lbl_scale_bridge_overall_status.setStyleSheet(
                "color: #A7F3D0; background: #064E3B; border: 1px solid #059669; "
                "border-radius: 10px; padding: 12px 14px; font-size: 14px; font-weight: bold;"
            )
        else:
            self.lbl_scale_bridge_overall_status.setText(
                u"⚠️ 当前状态：%s。桥接尚不可用，请从步骤 1 开始。" % status
            )
            self.lbl_scale_bridge_overall_status.setStyleSheet(
                "color: #FDE68A; background: #422006; border: 1px solid #A16207; "
                "border-radius: 10px; padding: 12px 14px; font-size: 14px; font-weight: bold;"
            )

    def _activate_scale_bridge_for_pos(self):
        """验收后的明确收尾动作：自动使用初始化生成的本 POS 端口。"""
        bridge_config, ready, status = self._scale_bridge_runtime_state()
        if not ready or bridge_config is None:
            from ui.custom_dialog import show_warning
            show_warning(self, u"桥接尚不可启用", status + u"\n\n请先完成初始化并确认服务正在运行。")
            return
        self.cmb_scale_source.setCurrentIndex(2)
        self._on_scale_source_changed(2)
        self._on_save_scale()
        self._open_settings_page(2)

    def _refresh_scale_bridge_devices(self, checked=False, silent=False, preferred_port=None):
        """Discover only physical serial candidates and retain hardware identity in item data."""
        # `checked` is accepted because this method is also a QPushButton slot.
        del checked
        from scale_bridge.device_discovery import enumerate_serial_ports, probe_serial_port
        from ui.custom_dialog import show_info, show_item_selection, show_warning

        current_port = self._bridge_port_text(preferred_port or self.cmb_bridge_physical_port.currentText())
        try:
            candidates = enumerate_serial_ports(include_virtual=False)
        except Exception as exc:
            candidates = []
            scan_error = str(exc)
        else:
            scan_error = ""

        self.cmb_bridge_physical_port.clear()
        known_ports = set()
        display_items = []
        availability = {}
        for candidate in candidates:
            if silent:
                can_open, state_text = True, u"未测试占用"
            else:
                can_open, detail = probe_serial_port(candidate.port)
                state_text = u"可用" if can_open else u"被占用"
                availability[candidate.port] = (can_open, detail)
            label = "%s  [%s | %s]" % (candidate.port, candidate.friendly_name or candidate.port, state_text)
            self.cmb_bridge_physical_port.addItem(label, candidate)
            display_items.append(label)
            known_ports.add(candidate.port.upper())
        if current_port and current_port not in known_ports:
            # Keep a previously configured physical COM name visible even while
            # its USB adapter is unplugged; saving it intentionally clears no
            # existing identity unless the operator selects a different port.
            self.cmb_bridge_physical_port.addItem(current_port)
        if not self.cmb_bridge_physical_port.count():
            self.cmb_bridge_physical_port.addItem("")
            self.cmb_bridge_physical_port.setEditText("")
        if current_port:
            for index in range(self.cmb_bridge_physical_port.count()):
                if self._bridge_port_text(self.cmb_bridge_physical_port.itemText(index)) == current_port:
                    self.cmb_bridge_physical_port.setCurrentIndex(index)
                    break

        if not silent:
            if candidates:
                selected, ok = show_item_selection(
                    self,
                    u"选择物理电子秤端口",
                    u"已排除虚拟串口。请选择实际连接 DIBAL ACS-G315 的端口：",
                    display_items,
                    self.cmb_bridge_physical_port.currentText(),
                )
                if ok and selected:
                    selected_port = self._bridge_port_text(selected)
                    for index in range(self.cmb_bridge_physical_port.count()):
                        if self._bridge_port_text(self.cmb_bridge_physical_port.itemText(index)) == selected_port:
                            self.cmb_bridge_physical_port.setCurrentIndex(index)
                            break
                    item = next(candidate for candidate in candidates if candidate.port == selected_port)
                    can_open, occupancy = availability.get(selected_port, (False, u"未知"))
                    show_info(
                        self, u"已选择物理电子秤端口",
                        u"端口: %s\n名称: %s\n制造商: %s\nService: %s\nPNPDeviceID: %s\n"
                        u"Hardware ID: %s\nVID/PID: %s/%s\nUSB 序列号: %s\n当前状态: %s%s"
                        % (
                            item.port, item.friendly_name or u"未知", item.manufacturer or u"未知",
                            item.service or u"未知", item.pnp_device_id or u"未知", item.hardware_id or u"未知",
                            item.vid or u"无", item.pid or u"无", item.serial_number or u"无",
                            u"可用" if can_open else u"被占用", (u"（%s）" % occupancy) if not can_open else "",
                        ),
                    )
            else:
                message = u"未识别到可作为物理秤的串口。虚拟串口会被刻意排除。"
                if scan_error:
                    message += u"\n\n原因: " + scan_error
                show_warning(self, u"未识别到物理秤", message)

    def _bridge_config_from_form(self):
        """Merge fields into the separate service config without writing it yet."""
        from scale_bridge.configuration import ScaleDeviceIdentity, load_config

        bridge_config = load_config(self._scale_bridge_config_path())
        saved_official_pos = bridge_config.official_pos_virtual_port
        saved_official_peer = bridge_config.official_bridge_port
        saved_private_pos = bridge_config.private_pos_virtual_port
        saved_private_peer = bridge_config.private_bridge_port
        physical_port = self._bridge_port_text(self.cmb_bridge_physical_port.currentText())
        candidate = self.cmb_bridge_physical_port.currentData()
        if candidate is not None and getattr(candidate, "port", "").upper() == physical_port:
            bridge_config.physical_scale = candidate.to_identity()
        elif bridge_config.physical_scale_port != physical_port:
            # A manually typed different port must not inherit another USB
            # adapter's PnP identity, or it could be re-bound unexpectedly.
            bridge_config.physical_scale = ScaleDeviceIdentity(port=physical_port)
        else:
            bridge_config.physical_scale.port = physical_port

        bridge_config.official_pos_virtual_port = self.txt_bridge_official_pos.text().strip().upper()
        bridge_config.official_bridge_port = self.txt_bridge_official_peer.text().strip().upper()
        bridge_config.private_pos_virtual_port = self.txt_bridge_private_pos.text().strip().upper()
        bridge_config.private_bridge_port = self.txt_bridge_private_peer.text().strip().upper()
        # Remove legacy payment values from the scale-service config. Payment
        # ports now belong exclusively to the Shouqianba settings module.
        bridge_config.payment_pos_port = ""
        bridge_config.payment_plugin_port = ""
        if (
            bridge_config.official_pos_virtual_port != saved_official_pos
            and bridge_config.official_bridge_port == saved_official_peer
        ):
            bridge_config.official_bridge_port = ""
        if (
            bridge_config.private_pos_virtual_port != saved_private_pos
            and bridge_config.private_bridge_port == saved_private_peer
        ):
            bridge_config.private_bridge_port = ""
        bridge_config.baudrate = int(self.cmb_scale_baud.currentText().strip() or "9600")
        return bridge_config

    def _save_scale_bridge_config(self):
        from scale_bridge.configuration import load_config, save_config
        from scale_bridge.lifecycle import ScaleBridgeServiceController
        from ui.custom_dialog import show_error, show_info, show_warning

        try:
            bridge_config = self._bridge_config_from_form()
            bridge_config.validate_for_setup()
            existing = load_config(self._scale_bridge_config_path())
            service_state = ScaleBridgeServiceController().query()
            if service_state.installed and (
                not os.path.isfile(self._scale_bridge_config_path())
                or bridge_config.to_dict() != existing.to_dict()
            ):
                show_warning(
                    self, u"请使用初始化 / 修复应用变更",
                    u"ScaleBridge 服务已经安装。端口变更必须同步检查配对并重启服务，"
                    u"因此不能只保存配置。请直接点击“初始化 / 修复”。",
                )
                return
            save_config(bridge_config, self._scale_bridge_config_path())
        except Exception as exc:
            show_error(self, u"桥接配置无法保存", str(exc))
            return
        self.lbl_scale_bridge_config.setText(
            u"✓ 已保存桥接配置：%s。尚未启动服务，也未变更任何现有 POS 设置或 COM 映射。"
            % self._scale_bridge_config_path()
        )
        self._refresh_scale_bridge_overall_status()
        show_info(
            self, u"桥接配置已保存",
            u"已保存独立的 ScaleBridge 配置。\n\n"
            u"这一步不会切换当前 POS 的称来源、不会改写收钱吧端口、不会安装驱动，也不会创建或修改虚拟串口。\n"
            u"下一步请点击“③ 初始化 / 修复 POS 称桥接”。初始化和验收后，点击步骤 4 下方的“⑤”即可自动让本 POS 使用桥接端口。",
        )

    def _test_scale_bridge_physical(self):
        """Direct first-run test; refuses to compete with a running service."""
        from scale_bridge.lifecycle import ScaleBridgeServiceController, test_physical_scale
        from ui.custom_dialog import show_error, show_info, show_warning

        try:
            bridge_config = self._bridge_config_from_form()
            bridge_config.validate_for_setup()
            service_state = ScaleBridgeServiceController().query()
            if service_state.installed and service_state.state_code == 4:
                show_warning(
                    self, u"请先停止桥接服务",
                    u"服务运行时由它独占物理秤端口。请点“停止服务”后再执行首次物理秤测试。",
                )
                return
        except Exception as exc:
            show_error(self, u"物理秤测试失败", str(exc))
            return

        def on_success(result):
            if result.ok:
                show_info(
                    self, u"物理秤测试通过",
                    u"端口: %s\n重量: %.3f kg\n原始数据: %s\n\n已确认协议：9600 / 8N1 / DTR 开 / RTS 关 / 查询 24。"
                    % (result.port, result.weight_kg, result.raw_hex),
                )
            else:
                show_error(
                    self, u"物理秤测试失败",
                    u"端口: %s\n原因: %s\n已接收数据: %s"
                    % (result.port, result.message, result.raw_hex or u"无"),
                )

        self._run_maintenance_with_spinner(
            u"正在测试物理电子秤",
            u"正在打开真实秤端口并发送查询指令，最多等待 2 秒。",
            lambda: test_physical_scale(bridge_config),
            on_success,
            u"物理秤测试失败",
            [self.btn_test_bridge_physical],
        )

    def _test_scale_bridge_virtual_only(self):
        """Run the real ScaleBridge service against an in-process simulated scale."""
        from scale_bridge.lifecycle import (
            ScaleBridgeLifecycle,
            ScaleBridgeServiceController,
            load_manifest,
            save_manifest,
            test_scale_channel,
        )
        from scale_bridge.configuration import ScaleDeviceIdentity, save_config as save_bridge_config
        from ui.custom_dialog import show_error, show_info, show_question
        import time

        if not show_question(
            self,
            u"开发测试：模拟秤并启动服务",
            u"本操作不会读取真实电子秤，而是使用固定 0.500 kg 的模拟回包。\n\n"
            u"程序会创建/复用两组 com0com 配对，写入临时开发配置，安装/启动真实 ScaleBridge Windows 服务，"
            u"再通过官方 POS 和本 POS 虚拟端口发送查询并验证回包。\n\n"
            u"如果当前服务正在运行，请先停止。测试完成后请点击“停止服务”，程序会恢复测试前的配置。是否继续？",
        ):
            return
        try:
            bridge_config = self._bridge_config_from_form()
            lifecycle = ScaleBridgeLifecycle(self._scale_bridge_config_path())
        except Exception as exc:
            show_error(self, u"无秤开发验证失败", str(exc))
            return

        try:
            existing_state = lifecycle.service.query()
            existing_manifest = load_manifest(lifecycle.manifest_path)
            replace_unowned_service = bool(
                existing_state.installed and not existing_manifest.service_owned
            )
        except Exception as exc:
            show_error(self, u"无秤开发验证失败", u"无法核对现有桥接服务：%s" % exc)
            return

        if replace_unowned_service and not show_question(
            self,
            u"高危操作：替换未登记的旧桥接服务",
            u"开发测试需要重新安装 Windows 服务“ppposScaleBridge”，但当前服务没有本产品所有权记录。\n\n"
            u"它通常来自旧版本或此前的手工调试。确认后只会停止并替换这一个同名服务；"
            u"不会删除未登记的 COM 虚拟串口、收钱吧配对或 com0com 驱动。\n\n"
            u"如果不确定服务来源，请取消并先在“删除 POS 称桥接”中核对。",
        ):
            return

        def operation():
            state = ScaleBridgeServiceController().query()
            if state.installed and state.state_code == 4:
                raise RuntimeError("请先停止正在运行的 ScaleBridge 服务，再进行开发模拟测试")
            report = lifecycle.initialize_virtual_only(bridge_config)
            bridge_config.physical_scale = ScaleDeviceIdentity(
                port="SIMULATED", friendly_name="开发模拟秤（固定 0.500 kg）"
            )
            bridge_config.development_simulation = True
            bridge_config.validate()
            config_path = self._scale_bridge_config_path()
            backup_path = config_path + ".before_development_simulation"
            if os.path.isfile(config_path) and not os.path.isfile(backup_path):
                shutil.copy2(config_path, backup_path)
            save_bridge_config(bridge_config, config_path)
            controller = ScaleBridgeServiceController()
            existing_state = controller.query()
            if existing_state.installed:
                if not existing_manifest.service_owned and not replace_unowned_service:
                    raise RuntimeError("未登记的同名桥接服务未获高危确认，已保留")
                controller.remove()
            installed = controller.install()
            # Subsequent start/stop/delete operations can prove this service
            # was created by the development test itself.
            manifest = load_manifest(lifecycle.manifest_path)
            manifest.service_owned = True
            save_manifest(manifest, lifecycle.manifest_path)
            started = controller.start()
            time.sleep(0.8)
            results = [
                (u"官方 POS", test_scale_channel(bridge_config, bridge_config.official_pos_virtual_port)),
                (u"本 POS", test_scale_channel(bridge_config, bridge_config.private_pos_virtual_port)),
            ]
            return report, installed, started, results, backup_path

        def on_success(result):
            report, installed, started, results, backup_path = result
            self.txt_bridge_official_peer.setText(bridge_config.official_bridge_port)
            self.txt_bridge_private_peer.setText(bridge_config.private_bridge_port)
            lines = []
            all_ok = True
            for label, item in results:
                all_ok = all_ok and item.ok
                detail = (
                    u"模拟回包正常（%.3f kg）" % item.weight_kg
                    if item.ok
                    else item.message
                )
                lines.append(u"%s：%s" % (label, detail))
            show_info(
                self,
                u"开发模拟服务验证完成" if all_ok else u"开发模拟服务验证未通过",
                u"ScaleBridge 服务：%s\n新建配对：%s\n复用配对：%s\n\n%s\n\n"
                u"当前运行的是模拟秤配置，备份文件：%s\n"
                u"测试完成后请点击“停止服务”，恢复测试前配置。"
                % (
                    u"已启动" if started else u"已在运行",
                    u"、".join(report.created) or u"无",
                    u"、".join(report.existing) or u"无",
                    u"\n".join(lines),
                    backup_path,
                ),
            )

        self._run_maintenance_with_spinner(
            u"正在启动开发模拟 ScaleBridge",
            u"正在创建/检查 com0com 配对、启动 Windows 服务并验证两路模拟回包。",
            operation,
            on_success,
            u"开发模拟服务验证失败",
            [self.btn_test_bridge_virtual_only],
            stages=[
                u"检查管理员权限和当前 ScaleBridge 服务",
                u"检查或创建开发测试用的 com0com 配对",
                u"写入临时模拟秤配置",
                u"安装并启动 ScaleBridge Windows 服务",
                u"通过官方 POS 和本 POS 端口验证模拟回包",
            ],
        )

    def _refresh_com0com_status(self):
        """Refresh the independent driver status without changing anything."""
        if not hasattr(self, "lbl_com0com_status"):
            return
        try:
            from scale_bridge.lifecycle import find_com0com_installer, find_setupc
            setupc = find_setupc()
            installer = find_com0com_installer()
            if setupc:
                self.lbl_com0com_status.setText(u"✓ com0com 已安装：%s" % setupc)
                self.lbl_com0com_status.setStyleSheet(
                    "color: #86EFAC; background: #052E16; border: 1px solid #166534; "
                    "border-radius: 8px; padding: 8px 10px; font-size: 13px;"
                )
            elif installer:
                self.lbl_com0com_status.setText(
                    u"尚未检测到 com0com；安装包已就绪：%s" % installer
                )
            else:
                self.lbl_com0com_status.setText(
                    u"尚未检测到 com0com，且当前程序目录没有附带安装包。"
                )
        except Exception as exc:
            self.lbl_com0com_status.setText(u"无法读取 com0com 状态：%s" % exc)

    def _install_com0com_driver(self):
        """Install only the bundled com0com driver; do not create any pairs."""
        from scale_bridge.lifecycle import find_setupc, install_com0com_driver
        from ui.custom_dialog import show_error, show_info, show_question

        if not show_question(
            self,
            u"安装 com0com 驱动",
            u"本操作只安装/检查 com0com 驱动，不创建 COM 配对，不删除现有串口，也不启动 POS 桥接服务。\n\n"
            u"需要管理员权限；安装过程中可能出现 Windows 驱动确认窗口。是否继续？",
        ):
            return

        def operation():
            setupc = find_setupc()
            if setupc:
                return False, setupc
            return True, install_com0com_driver()

        def on_success(result):
            installed, setupc = result
            self._refresh_com0com_status()
            show_info(
                self,
                u"com0com 驱动已就绪",
                (u"本次已完成安装。" if installed else u"检测到已安装，无需重复安装。")
                + u"\nsetupc.exe：%s\n\n下一步请再执行“③ 初始化 / 修复 POS 称桥接”。"
                % setupc,
            )

        self._run_maintenance_with_spinner(
            u"正在安装 / 检查 com0com",
            u"正在单独准备虚拟串口驱动；此步骤不会创建任何端口。",
            operation,
            on_success,
            u"com0com 驱动安装失败",
            [self.btn_install_com0com],
            stages=[
                u"检查管理员权限和现有 setupc.exe",
                u"启动 com0com 安装程序（可能出现 Windows 确认）",
                u"等待安装程序注册驱动文件",
                u"检查 setupc.exe 是否已经可用",
            ],
        )

    def _initialize_scale_bridge(self):
        """Explicit, idempotent first-run/repair workflow."""
        from scale_bridge.lifecycle import ScaleBridgeLifecycle
        from ui.custom_dialog import show_error, show_info, show_question

        if not show_question(
            self, u"初始化或修复 POS 称桥接",
            u"将依次测试物理秤、检查 com0com、只创建官方 POS 与本 POS 的两组称重端口，"
            u"然后安装并启动 Windows 服务。\n\n"
            u"不会创建或修改收钱吧支付配对，也不会修改现有 POS 设置。是否继续？",
        ):
            return
        try:
            bridge_config = self._bridge_config_from_form()
            bridge_config.validate_for_setup()
            lifecycle = ScaleBridgeLifecycle(self._scale_bridge_config_path())
        except Exception as exc:
            show_error(self, u"POS 称桥接初始化失败", str(exc))
            return

        def on_success(report):
            self.txt_bridge_official_peer.setText(bridge_config.official_bridge_port)
            self.txt_bridge_private_peer.setText(bridge_config.private_bridge_port)
            self.lbl_scale_bridge_config.setText(
                u"✓ 初始化完成，服务已安装并运行。配置：%s" % self._scale_bridge_config_path()
            )
            self._refresh_scale_bridge_overall_status()
            if self.cmb_scale_source.currentIndex() == 2:
                self._on_scale_source_changed(2)
            created = u"、".join(report.pairs.created) or u"无（均已存在）"
            existing = u"、".join(report.pairs.existing) or u"无"
            removed = u"、".join(report.pairs.removed_obsolete) or u"无"
            show_info(
                self, u"POS 称桥接初始化完成",
                u"物理秤: %s，当前 %.3f kg\n新建配对: %s\n复用配对: %s\n清理旧配对: %s\n服务: %s\n\n"
                u"下一步：按步骤 4 完成测试，再点击“⑤ 让本 POS 使用桥接端口”。"
                % (
                    report.physical_test.port,
                    report.physical_test.weight_kg,
                    created,
                    existing,
                    removed,
                    u"已安装并启动" if report.service_installed else u"已存在并启动",
                ),
            )

        self._run_maintenance_with_spinner(
            u"正在初始化 / 修复 POS 称桥接",
            u"正在测试物理秤、安装或检查 com0com，并创建称重虚拟串口。",
            lambda: lifecycle.initialize(bridge_config),
            on_success,
            u"POS 称桥接初始化失败",
            [self.btn_initialize_scale_bridge],
            stages=[
                u"测试物理电子秤协议和当前读数",
                u"检查 com0com 驱动与 setupc.exe",
                u"创建或复用官方 POS / 本 POS 两组配对",
                u"等待 Windows 注册新的虚拟 COM 端口",
                u"安装并启动 ScaleBridge Windows 服务",
                u"核对桥接配置和服务状态",
            ],
        )

    def _initialize_payment_pair(self):
        from scale_bridge.lifecycle import PaymentPairLifecycle
        from ui.custom_dialog import show_error, show_info, show_question

        sender = self.cmb_sqb_port.currentText().strip().upper()
        plugin = self.txt_sqb_payment_peer.text().strip().upper()
        if not show_question(
            self,
            u"创建或修复收钱吧支付配对",
            u"将检查/安装 com0com，并确保支付配对为 %s ↔ %s。\n\n"
            u"不会修改 POS 称桥接，也不会改动其他串口配对。是否继续？"
            % (sender or u"未填写", plugin or u"未填写"),
        ):
            return

        def on_success(report):
            self.config["shouqianba_port"] = sender
            self.config["shouqianba_plugin_port"] = plugin
            self.config["shouqianba_pair_mode"] = "managed"
            save_config(self.config)
            created_text = u"、".join(report.created)
            existing_text = u"、".join(report.existing)
            if report.created:
                title = u"支付配对创建成功"
                result_hint = u"已按当前填写的端口新建配对。"
            elif report.existing:
                title = u"支付配对已存在，已复用"
                result_hint = u"没有重复创建；当前填写的端口已经属于下面的现有配对。"
            else:
                title = u"支付配对检查完成"
                result_hint = u"未发现新建或复用记录，请点击检查按钮确认端口状态。"
            show_info(
                self,
                title,
                u"%s\n\n新建：%s\n复用：%s\n清理旧配对：%s\n\n下一步：关闭占用两端口的软件，再点击“双向测试支付配对”。"
                % (
                    result_hint,
                    created_text or u"无",
                    existing_text or u"无",
                    u"、".join(report.removed_obsolete) or u"无",
                ),
            )

        self._run_maintenance_with_spinner(
            u"正在创建 / 修复收钱吧虚拟串口",
            u"正在安装或检查 com0com，并创建收钱吧发送端与插件接收端。",
            lambda: PaymentPairLifecycle().initialize(sender, plugin),
            on_success,
            u"支付配对创建失败",
            [self.btn_initialize_payment_pair],
            stages=[
                u"检查收钱吧发送端和插件接收端端口",
                u"检查 com0com 驱动与现有配对",
                u"创建或复用收钱吧两端虚拟串口",
                u"等待 Windows 注册支付端口",
                u"保存配对所有权和配置结果",
            ],
        )

    def _check_payment_pair(self):
        from scale_bridge.com0com import check_pair, list_pairs
        from ui.custom_dialog import show_error, show_info, show_warning

        sender = self.cmb_sqb_port.currentText().strip().upper()
        plugin = self.txt_sqb_payment_peer.text().strip().upper()

        def on_success(result):
            message = u"%s ↔ %s：%s%s" % (
                sender or u"未填写",
                plugin or u"未填写",
                u"配对正常" if result.present else u"配对不存在",
                (u"（配对 #%d）" % result.pair.index) if result.pair else "",
            )
            if result.present:
                show_info(self, u"支付配对正常", message)
            else:
                next_step = (
                    u"请点击“③ 创建 / 修复虚拟串口”。"
                    if self.cmb_sqb_pair_mode.currentIndex() == 0
                    else u"现场填写的两个端口并未成对；请核对原配对，或改选“由本系统创建”。"
                )
                show_warning(self, u"支付配对缺失", message + u"\n" + next_step)

        self._run_maintenance_with_spinner(
            u"正在检查收钱吧虚拟串口",
            u"正在读取 com0com 当前配对，不会创建或删除任何端口。",
            lambda: check_pair(sender, plugin, list_pairs()),
            on_success,
            u"支付配对检查失败",
            [self.btn_check_payment_pair],
        )

    def _remove_payment_pair(self):
        from scale_bridge.lifecycle import PaymentPairLifecycle
        from ui.custom_dialog import show_error, show_info, show_question

        # Read the exact endpoints before starting the worker.  The fallback
        # cleanup path below uses these values to identify a legacy pair that
        # was created before ownership metadata was introduced.
        sender = self.cmb_sqb_port.currentText().strip().upper()
        plugin = self.txt_sqb_payment_peer.text().strip().upper()

        if not show_question(
            self,
            u"删除收钱吧支付配对",
            u"只会删除本产品所有权清单中精确匹配的支付配对。"
            u"不会删除 POS 称桥接、收钱吧参数或其他串口。是否继续？",
        ):
            return

        def on_success(result):
            removed, skipped = result
            if skipped:
                raise RuntimeError("所有权不匹配，拒绝删除：" + "; ".join(skipped))
            if not removed:
                # Older releases did not persist ownership records. Offer a
                # narrowly scoped migration cleanup, but require a second
                # confirmation and verify the exact two configured endpoints
                # in the worker before deleting anything.
                if not show_question(
                    self,
                    u"高危操作：删除未登记的旧配对",
                    u"本系统没有记录当前收钱吧配对的创建者。\n\n"
                    u"如果这对端口是其他软件创建的，确认后也会被删除，可能导致其他软件无法通信。\n\n"
                    u"仅当你确定 %s ↔ %s 就是本 POS 要清理的旧配对时，才点击“是”。\n"
                    u"如果不知道端口来源，请点击“否”；不会扫描或删除其他虚拟串口。"
                    % (sender or u"未填写", plugin or u"未填写"),
                ):
                    show_info(self, u"支付配对未删除", u"未记录的旧配对已保留，其他端口未改动。")
                    return

                def on_exact_success(exact_result):
                    exact_removed, exact_skipped = exact_result
                    if exact_skipped:
                        raise RuntimeError("旧配对未删除：" + "; ".join(exact_skipped))
                    show_info(
                        self,
                        u"旧支付配对删除完成",
                        u"已精确删除：%s\n其他虚拟串口未改动。\n\n"
                        u"Windows 虚拟串口已删除，再次创建前必须重启电脑。"
                        u"重启后程序会自动恢复创建功能。"
                        % (u"、".join(exact_removed) or u"无"),
                    )

                self._run_maintenance_with_spinner(
                    u"正在清理旧收钱吧配对",
                    u"正在核对并删除当前填写的两个端口，请稍候。",
                    lambda: PaymentPairLifecycle().remove_exact(sender, plugin, allow_unowned=True),
                    on_exact_success,
                    u"旧支付配对删除失败",
                    [self.btn_remove_payment_pair],
                    stages=[
                        u"核对当前配对和所有权记录",
                        u"停止可能占用端口的关联流程",
                        u"删除确认的旧收钱吧配对",
                        u"等待 Windows 注销虚拟端口",
                    ],
                )
                return
            show_info(
                self,
                u"支付配对删除完成",
                u"已删除：%s\n收钱吧设置参数已保留。\n\n"
                u"Windows 虚拟串口已删除，再次创建前必须重启电脑。"
                u"重启后程序会自动恢复创建功能。"
                % (u"、".join(removed) or u"无（本产品未创建该配对）"),
            )

        self._run_maintenance_with_spinner(
            u"正在删除收钱吧虚拟串口",
            u"正在停止并删除本系统创建的收钱吧配对，请稍候。",
            lambda: PaymentPairLifecycle().remove(),
            on_success,
            u"支付配对删除失败",
            [self.btn_remove_payment_pair],
            stages=[
                u"读取本产品创建的支付配对清单",
                u"停止并清理收钱吧配对",
                u"等待 Windows 注销虚拟 COM 端口",
                u"核对其他软件创建的端口未被改动",
            ],
        )

    def _test_scale_bridge_payment_pair(self):
        from scale_bridge.lifecycle import test_virtual_pair
        from ui.custom_dialog import show_error, show_info, show_question

        side_a = self.cmb_sqb_port.currentText().strip().upper()
        side_b = self.txt_sqb_payment_peer.text().strip().upper()
        if not show_question(
            self, u"测试支付虚拟串口",
            u"测试会短暂独占 %s 和 %s，并双向发送随机测试字节。\n"
            u"请先关闭正在使用这两个端口的收钱吧及支付程序。是否继续？" % (side_a or u"未填写", side_b or u"未填写"),
        ):
            return
        def on_success(result):
            if result.ok:
                show_info(self, u"支付配对测试通过", u"%s ↔ %s：双向透明通信正常。" % (side_a, side_b))
            else:
                show_error(
                    self, u"支付配对测试失败",
                    u"%s ↔ %s\n原因: %s\n\n请确认配对已创建且两个端口未被其他程序占用。"
                    % (side_a or u"未填写", side_b or u"未填写", result.message),
                )

        self._run_maintenance_with_spinner(
            u"正在测试收钱吧虚拟串口",
            u"正在短暂独占两个端口并进行双向通信测试。",
            lambda: test_virtual_pair(side_a, side_b),
            on_success,
            u"支付配对测试失败",
            [self.btn_test_payment_pair],
        )

    def _test_scale_bridge_channel(self, channel):
        """End-to-end query through one POS-facing virtual scale port."""
        from scale_bridge.lifecycle import ScaleBridgeServiceController, test_scale_channel
        from ui.custom_dialog import show_error, show_info, show_question

        label = u"官方 POS" if channel == "official" else u"本 POS"
        if not show_question(
            self,
            u"测试%s秤通道" % label,
            u"测试会短暂打开%s虚拟端口并发送已确认的 $ 查询。\n"
            u"请先关闭占用该端口的软件；ScaleBridge 服务必须保持运行。是否继续？" % label,
        ):
            return
        active_scale = None
        try:
            bridge_config = self._bridge_config_from_form()
            bridge_config.validate()
            state = ScaleBridgeServiceController().query()
            if not state.installed or state.state_code != 4:
                raise RuntimeError("ScaleBridge 服务未运行，请先点击“启动服务”")
            port = (
                bridge_config.official_pos_virtual_port
                if channel == "official"
                else bridge_config.private_pos_virtual_port
            )
        except Exception as exc:
            show_error(self, u"%s秤通道测试失败" % label, str(exc))
            return

        # The private POS may already own its endpoint through the live
        # weighing reader. Pause it before entering the worker and restore it
        # from both success and failure paths.
        if channel == "private":
            parent_mw = self.window()
            if hasattr(parent_mw, "sale_page") and hasattr(parent_mw.sale_page, "scale"):
                candidate = parent_mw.sale_page.scale
                if candidate and getattr(candidate, "_running", False):
                    active_scale = candidate
                    active_scale.stop()

        def on_success(result):
            if active_scale:
                active_scale.start()
            if result.ok:
                show_info(
                    self,
                    u"%s秤通道正常" % label,
                    u"端口: %s\n重量: %.3f kg\n原始数据: %s\n\n已验证：POS 虚拟端口 → ScaleBridge → 物理秤 → 回包。"
                    % (result.port, result.weight_kg, result.raw_hex),
                )
            else:
                show_error(
                    self,
                    u"%s秤通道测试失败" % label,
                    u"端口: %s\n原因: %s\n已接收数据: %s"
                    % (result.port, result.message, result.raw_hex or u"无"),
                )

        self._run_maintenance_with_spinner(
            u"正在测试%s秤通道" % label,
            u"正在通过虚拟端口发送查询并等待物理秤回包。",
            lambda: test_scale_channel(bridge_config, port),
            on_success,
            u"%s秤通道测试失败" % label,
            [self.btn_test_official_scale_channel if channel == "official" else self.btn_test_private_scale_channel],
            on_failure=lambda: active_scale.start() if active_scale else None,
        )

    def _start_scale_bridge_service(self):
        from scale_bridge.lifecycle import ScaleBridgeServiceController
        from ui.custom_dialog import show_error, show_info

        def on_success(changed):
            self._refresh_scale_bridge_overall_status()
            show_info(self, u"ScaleBridge 服务", u"服务已启动。" if changed else u"服务原本已在运行。")

        self._run_maintenance_with_spinner(
            u"正在启动 ScaleBridge 服务",
            u"正在启动 Windows 桥接服务，请稍候。",
            lambda: ScaleBridgeServiceController().start(),
            on_success,
            u"服务启动失败",
            [self.btn_start_scale_bridge],
        )

    def _stop_scale_bridge_service(self):
        from scale_bridge.lifecycle import ScaleBridgeServiceController
        from scale_bridge.configuration import load_config as load_bridge_config
        from ui.custom_dialog import show_error, show_info

        def on_success(changed):
            restored = False
            config_path = self._scale_bridge_config_path()
            backup_path = config_path + ".before_development_simulation"
            try:
                current = load_bridge_config(config_path)
                if current.development_simulation:
                    if os.path.isfile(backup_path):
                        shutil.copy2(backup_path, config_path)
                        os.unlink(backup_path)
                    elif os.path.isfile(config_path):
                        os.unlink(config_path)
                    restored = True
            except Exception:
                # Stopping the service already succeeded; leave the files in
                # place so the operator can recover them manually if needed.
                restored = False
            self._refresh_scale_bridge_overall_status()
            message = u"服务已停止。" if changed else u"服务未运行或尚未安装。"
            if restored:
                message += u"\n开发模拟配置已移除，测试前的配置已恢复。"
            show_info(self, u"ScaleBridge 服务", message)

        self._run_maintenance_with_spinner(
            u"正在停止 ScaleBridge 服务",
            u"正在安全停止 Windows 桥接服务，请稍候。",
            lambda: ScaleBridgeServiceController().stop(),
            on_success,
            u"服务停止失败",
            [self.btn_stop_scale_bridge],
        )

    def _export_scale_bridge_diagnostics(self):
        from scale_bridge.lifecycle import collect_diagnostics, write_diagnostic_report
        from ui.custom_dialog import show_error, show_info
        path = os.path.join(DATA_DIR, "scale_bridge_diagnosis.json")
        try:
            bridge_config = self._bridge_config_from_form()
            report = collect_diagnostics(bridge_config)
            write_diagnostic_report(path, report)
        except Exception as exc:
            show_error(self, u"诊断报告生成失败", str(exc))
            return
        show_info(self, u"诊断报告已生成", u"报告路径：\n" + path)

    def _remove_scale_bridge(self):
        """Remove only owned bridge resources and its separate config."""
        from scale_bridge.lifecycle import (
            ScaleBridgeLifecycle,
            load_manifest,
        )
        from ui.custom_dialog import show_error, show_info, show_question

        lifecycle = ScaleBridgeLifecycle(self._scale_bridge_config_path())
        try:
            manifest = load_manifest(lifecycle.manifest_path)
            service_is_legacy = (
                lifecycle.service.query().installed
                and not manifest.service_owned
            )
        except Exception as exc:
            show_error(self, u"无法核对桥接删除范围", str(exc))
            return

        allow_unowned_service = False
        if service_is_legacy:
            # Older builds created the service before a manifest existed.
            # Never silently take over that resource: the exact service name
            # is shown and a second, deliberately high-risk confirmation is
            # required.  COM pairs remain protected by their own ownership
            # records and are not included in this fallback.
            if not show_question(
                self,
                u"高危操作：删除未登记的旧桥接服务",
                u"检测到 Windows 服务“ppposScaleBridge”，但当前系统没有它的创建记录。\n\n"
                u"这通常来自旧版本或早期手工开发测试。确认后会停止并删除这一项同名 Windows 服务，"
                u"并删除当前称桥接配置；如果它实际由其他软件创建，那个软件将无法继续桥接称重。\n\n"
                u"不会删除任何未登记的 COM 虚拟串口、收钱吧配对、com0com 驱动或其他 POS 设置。\n\n"
                u"仅当你确认这是本 POS 的旧称桥接服务时，才点击“确定”；不确定请点击“取消”。",
            ):
                show_info(self, u"旧桥接服务未删除", u"未登记的服务和所有虚拟串口均已保留。")
                return
            allow_unowned_service = True
        elif not show_question(
            self, u"删除 POS 称桥接",
            u"将停止并删除本产品创建的称桥接服务，只删除本产品记录的官方/本 POS 称重配对，"
            u"并删除独立称桥接配置。\n\n不会删除收钱吧支付配对、com0com 驱动、真实串口驱动或其他 POS 设置。是否继续？",
        ):
            return

        def on_success(report):
            self._load_scale_bridge_form()
            self._refresh_scale_bridge_overall_status()
            show_info(
                self, u"POS 称桥接已删除",
                u"服务删除: %s\n已删除称重配对: %s\n称桥接配置删除: %s\n"
                u"收钱吧支付配对和 com0com 驱动均已保留。%s"
                % (
                    u"是" if report.service_removed else u"无需删除",
                    u"、".join(report.removed_pairs) or u"无",
                    u"是" if report.config_deleted else u"文件原本不存在",
                    (u"\n\nWindows 虚拟串口已删除，再次创建前必须重启电脑。"
                     u"重启后程序会自动恢复创建功能。")
                    if report.removed_pairs else u"",
                ),
            )

        self._run_maintenance_with_spinner(
            u"正在删除 POS 称桥接",
            u"正在停止服务、删除称重配对和独立桥接配置，请稍候。",
            lambda: lifecycle.remove(
                remove_driver=False,
                allow_unowned_service=allow_unowned_service,
            ),
            on_success,
            u"删除桥接功能失败",
            [self.btn_remove_scale_bridge],
            stages=[
                u"核对 ScaleBridge 服务和本产品所有权",
                u"停止并删除 ScaleBridge Windows 服务",
                u"删除本产品登记的官方 / 本 POS 称重配对",
                u"等待 Windows 注销虚拟 COM 端口",
                u"删除独立桥接配置并保留其他配对",
            ],
        )

    def _check_scale_bridge_pairs(self):
        """Read pair records and the real Windows COM/PnP state without writes."""
        from scale_bridge.com0com import check_pair, list_pairs
        from ui.custom_dialog import show_error, show_info, show_warning

        try:
            bridge_config = self._bridge_config_from_form()
            bridge_config.validate_for_setup()
        except Exception as exc:
            show_error(
                self, u"无法检查虚拟端口配对",
                u"未改动任何端口。请确认 com0com 已由管理员安装，然后再检查。\n\n原因: " + str(exc),
            )
            return

        def inspect_pairs_and_windows():
            from scale_bridge.device_discovery import (
                enumerate_com0com_device_problems,
                windows_serial_port_exists,
            )
            pairs = list_pairs()
            ports = {
                bridge_config.official_pos_virtual_port.upper(): windows_serial_port_exists(
                    bridge_config.official_pos_virtual_port
                ),
                bridge_config.private_pos_virtual_port.upper(): windows_serial_port_exists(
                    bridge_config.private_pos_virtual_port
                ),
            }
            return pairs, ports, enumerate_com0com_device_problems()

        def on_success(result):
            from scale_bridge.com0com import find_pair_by_endpoint
            pairs, windows_ports, device_problems = result
            if not bridge_config.official_bridge_port:
                pair = find_pair_by_endpoint(bridge_config.official_pos_virtual_port, pairs)
                if pair:
                    bridge_config.official_bridge_port = pair.other(bridge_config.official_pos_virtual_port) or ""
                    self.txt_bridge_official_peer.setText(bridge_config.official_bridge_port)
            if not bridge_config.private_bridge_port:
                pair = find_pair_by_endpoint(bridge_config.private_pos_virtual_port, pairs)
                if pair:
                    bridge_config.private_bridge_port = pair.other(bridge_config.private_pos_virtual_port) or ""
                    self.txt_bridge_private_peer.setText(bridge_config.private_bridge_port)
            checks = [
                (u"官方 POS", check_pair(bridge_config.official_pos_virtual_port, bridge_config.official_bridge_port, pairs)),
                (u"本 POS", check_pair(bridge_config.private_pos_virtual_port, bridge_config.private_bridge_port, pairs)),
            ]
            lines = []
            for name, item in checks:
                suffix = u"（配对 #%d）" % item.pair.index if item.pair else ""
                windows_ready = bool(windows_ports.get(item.client_port.upper()))
                lines.append(u"%s：%s ↔ %s — 配对%s%s；Windows 端口%s" % (
                    name,
                    item.client_port,
                    item.bridge_port,
                    u"存在" if item.present else u"缺失",
                    suffix,
                    u"已注册" if windows_ready else u"未注册",
                ))
            unhealthy = [item for item in device_problems if item.error_code]
            if unhealthy:
                counts = {}
                for item in unhealthy:
                    counts[item.error_code] = counts.get(item.error_code, 0) + 1
                problem_lines = []
                for code, count in sorted(counts.items()):
                    meaning = {
                        28: u"驱动程序未安装",
                        52: u"Windows 无法验证驱动数字签名",
                        10: u"设备无法启动",
                    }.get(code, u"设备异常")
                    problem_lines.append(u"%d 个 com0com 设备：代码 %d（%s）" % (count, code, meaning))
                lines.extend(problem_lines)
            message = (
                u"\n".join(lines)
                + u"\n\n本检查同时读取 setupc 配置和 Windows 实际端口，不创建、删除或重命名端口。"
            )
            pair_ok = all(item.present for _name, item in checks)
            windows_ok = all(windows_ports.values())
            if pair_ok and windows_ok and not unhealthy:
                show_info(self, u"虚拟端口配对及驱动正常", message)
            elif pair_ok:
                show_warning(
                    self,
                    u"配对存在，但 Windows 驱动未生效",
                    message
                    + u"\n\n请点击“初始化 / 修复 POS 称桥接”，程序会执行 setupc update 修复端点驱动。",
                )
            else:
                show_warning(self, u"存在缺失的虚拟端口配对", message)

        self._run_maintenance_with_spinner(
            u"正在检查称重虚拟串口",
            u"正在读取官方 POS 与本 POS 的两组 com0com 配对。",
            inspect_pairs_and_windows,
            on_success,
            u"无法检查虚拟端口配对",
            [self.btn_check_scale_bridge_pairs],
        )

    def _test_scale_com(self):
        """实时测试当前配置的串口电子秤通信状态"""
        port_text = self.cmb_scale_port.currentText().strip()
        port = port_text.split("[")[0].strip()
        try:
            baudrate = int(self.cmb_scale_baud.currentText().strip())
        except Exception:
            baudrate = 9600

        from ui.custom_dialog import show_info, show_error, show_warning
        import time
        import serial
        from core.scale_reader import ScaleReader

        # 若后台已存在运行中的称重线程，先暂时挂起，完成后在 UI 线程恢复。
        parent_mw = self.window()
        active_scale = None
        if hasattr(parent_mw, 'sale_page') and hasattr(parent_mw.sale_page, 'scale'):
            active_scale = parent_mw.sale_page.scale
            if active_scale and getattr(active_scale, '_running', False):
                active_scale.stop()

        def operation():
            ser = None
            received_data = bytearray()
            weight_val = None
            error = None
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.05,
                    write_timeout=0.5,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False,
                )
                ser.dtr = True
                ser.rts = False

                # 按官方 POS 已验证的 ACS-G315 协议测试：每 200ms 发送 '$'。
                start_t = time.monotonic()
                next_poll_time = start_t
                temp_reader = ScaleReader(self.config)
                while time.monotonic() - start_t < 2.0:
                    if time.monotonic() >= next_poll_time:
                        ser.write(b"$")
                        ser.flush()
                        next_poll_time = time.monotonic() + 0.2
                    data = ser.read(ser.in_waiting or 1)
                    if data:
                        received_data.extend(data)
                        if b"\r" in received_data or b"\n" in received_data:
                            text = received_data.decode("ascii", errors="ignore")
                            for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                                line = line.strip()
                                if line:
                                    parsed = temp_reader._parse_com_weight(line)
                                    if parsed is not None:
                                        weight_val = parsed
                                        break
                            if weight_val is not None:
                                break
                    time.sleep(0.01)
            except Exception as exc:
                error = str(exc)
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass
            return weight_val, bytes(received_data), error

        def on_success(result):
            weight_val, received_data, error = result
            if active_scale:
                active_scale.start()
            if error:
                show_error(
                    self, u"串口连接失败",
                    f"无法打开端口【{port}】！\n\n原因: {error}\n\n"
                    u"建议检查电子秤连接线及端口是否被其他软件独占。"
                )
            elif weight_val is not None:
                show_info(
                    self, u"测试连接成功",
                    f"🎉 成功连通电子秤串口【{port}】！\n\n"
                    f"• 通信端口: {port}\n• 通信波特率: {baudrate}\n"
                    f"• 捕获到的实时重量: {weight_val:.3f} kg\n\n"
                    u"硬件通信完全正常，可随时保存使用！"
                )
            elif received_data:
                show_warning(
                    self, u"数据未匹配",
                    f"已连通端口【{port}】但未解析到标准重量。\n\n"
                    f"原始接收数据: \"{received_data.decode('ascii', errors='replace')[:100]}\"\n\n"
                    u"建议检查波特率或电子秤通信协议。"
                )
            else:
                show_warning(
                    self, u"未接收到数据",
                    f"已打开端口【{port}】，但 2 秒内未接收到有效数据。\n\n"
                    u"请确认电子秤已开机、端口选择正确，且没有被官方 POS 独占。"
                )

        self._run_maintenance_with_spinner(
            u"正在测试电子秤串口",
            u"正在打开端口并按 9600 / 8N1 协议查询重量，最多等待 2 秒。",
            operation,
            on_success,
            u"串口测试失败",
            [self.btn_test_scale_com],
        )

    def _refresh_scale_com_ports(self, show_toast=False):
        """扫描可用COM端口 (称重秤专用)"""
        self.cmb_scale_port.clear()
        active_ports = []
        try:
            import serial.tools.list_ports
            active_ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            pass
        all_ports = [f"COM{i}" for i in range(1, 13)]
        for p in active_ports:
            if p not in all_ports:
                all_ports.append(p)
        for p in sorted(all_ports, key=lambda x: int(x.replace("COM", "")) if x.startswith("COM") and x[3:].isdigit() else 99):
            if p in active_ports:
                self.cmb_scale_port.addItem(f"{p}  [已连接]")
            else:
                self.cmb_scale_port.addItem(p)
        cur = self.config.get("scale_port", "COM2")
        if cur:
            for i in range(self.cmb_scale_port.count()):
                if self.cmb_scale_port.itemText(i).startswith(cur):
                    self.cmb_scale_port.setCurrentIndex(i)
                    break
        if show_toast:
            from ui.custom_dialog import show_info, show_item_selection
            if active_ports:
                selected_port, ok = show_item_selection(
                    self, u"选择电子秤串口", 
                    f"检测到 {len(active_ports)} 个当前系统 COM。请选择真实电子秤直接连接的端口；"
                    u"桥接端口请通过“同时读秤”模式自动带入：",
                    active_ports, self.cmb_scale_port.currentText().split("[")[0].strip()
                )
                if ok and selected_port:
                    for i in range(self.cmb_scale_port.count()):
                        if self.cmb_scale_port.itemText(i).startswith(selected_port):
                            self.cmb_scale_port.setCurrentIndex(i)
                            break
            else:
                show_info(self, u"串口扫描提示", u"未检测到现有 COM。请检查电子秤连接和驱动；桥接模式无需在这里手动选择端口。")

    def _on_save_scale(self):
        """保存称重数据源设置"""
        from ui.custom_dialog import show_info, show_warning

        selected_mode = self.cmb_scale_source.currentData() or "official"
        port_text = self.cmb_scale_port.currentText().strip()
        port_text = port_text.split("[")[0].strip()

        if selected_mode == "official":
            self.config["scale_source"] = "official"
            self.config["official_pos_log_dir"] = self.txt_official_log_dir.text().strip()
            success_message = u"已切换为跟随官方 POS 读取重量，无需配置 COM。"
        elif selected_mode == "direct":
            if not port_text:
                show_warning(self, u"尚未选择物理电子秤", u"请先选择真实电子秤 COM，并测试读到重量后再保存。")
                return
            self.config["scale_source"] = "com"
            self.config["scale_connection_mode"] = "direct"
            self.config["scale_port"] = port_text
            success_message = u"已切换为本 POS 独占物理秤：%s。" % port_text
        else:
            bridge_config, ready, status = self._scale_bridge_runtime_state()
            if not ready or bridge_config is None:
                show_warning(
                    self,
                    u"不能启用桥接模式",
                    status + u"\n\n本设置没有保存。请先到“POS 称桥接”完成初始化。",
                )
                self._open_settings_page(3)
                return
            self.config["scale_source"] = "com"
            self.config["scale_connection_mode"] = "bridge"
            self.config["scale_port"] = bridge_config.private_pos_virtual_port
            self.config["scale_baudrate"] = bridge_config.baudrate
            success_message = u"已切换为 POS 称桥接，本 POS 自动使用 %s。" % bridge_config.private_pos_virtual_port

        try:
            if selected_mode != "bridge":
                self.config["scale_baudrate"] = int(self.cmb_scale_baud.currentText().strip())
        except Exception:
            self.config["scale_baudrate"] = 9600
        save_config(self.config)

        parent_mw = self.window()
        if hasattr(parent_mw, 'sale_page') and hasattr(parent_mw.sale_page, 'restart_scale'):
            if not parent_mw.sale_page.restart_scale():
                show_warning(
                    self,
                    u"称重读取器尚未重启",
                    u"旧的称重读取线程没有在安全时限内退出，因此系统没有启动第二个线程。配置已经保存，请退出并重新打开本 POS 后生效。",
                )
                return

        show_info(self, u"电子秤设置已生效", success_message)

    def _on_save_sqb(self):
        from ui.custom_dialog import show_info, show_warning

        enabled = self.cmb_sqb_enable.currentIndex() == 0
        pair_mode = self.cmb_sqb_pair_mode.currentData() or "managed"
        sender = self.cmb_sqb_port.currentText().strip().upper()
        plugin = self.txt_sqb_payment_peer.text().strip().upper()
        install_dir = self.txt_sqb_install_dir.text().strip().strip('"')
        if enabled:
            invalid = [value for value in (sender, plugin) if not re.fullmatch(r"COM[1-9]\d*", value)]
            if invalid:
                show_warning(
                    self,
                    u"收钱吧端口填写不完整",
                    u"发送端和插件接收端都必须填写标准 COM 名称，例如 COM10、COM11。",
                )
                return
            if sender == plugin:
                show_warning(
                    self,
                    u"两个端口不能相同",
                    u"本 POS 发送端与收钱吧插件接收端必须是虚拟串口配对的两端。",
                )
                return
            from core.shouqianba_sender import is_supported_hotkey
            if not is_supported_hotkey(self.txt_sqb_hotkey.text()):
                show_warning(
                    self,
                    u"快捷键不受支持",
                    u"请使用 Ctrl、Alt、Shift、F1-F12、字母、数字、Tab 或 Enter 的组合，例如 Shift+Q。",
                )
                return
            from core.shouqianba_sender import validate_shouqianba_install_dir
            logs_ok, logs_message = validate_shouqianba_install_dir(install_dir)
            if not logs_ok:
                show_warning(
                    self,
                    u"收钱吧安装目录不可用",
                    logs_message + u"\n\n可靠的到账判断需要读取插件 info/debug 日志，本设置尚未保存。",
                )
                return

        self.config["shouqianba_enabled"] = enabled
        self.config["shouqianba_pair_mode"] = pair_mode
        self.config["shouqianba_port"] = sender
        self.config["shouqianba_plugin_port"] = plugin
        try:
            self.config["shouqianba_baudrate"] = int(self.cmb_sqb_baud.currentText().strip())
        except Exception:
            self.config["shouqianba_baudrate"] = 2400
        fmt_text = self.cmb_sqb_fmt.currentText()
        self.config["shouqianba_format"] = fmt_text.split(" - ")[0].strip()
        self.config["shouqianba_hotkey"] = self.txt_sqb_hotkey.text().strip()
        self.config["shouqianba_install_dir"] = os.path.normpath(install_dir) if install_dir else ""
        save_config(self.config)
        if not enabled:
            message = u"收钱吧金额推送已关闭。端口参数已保留，未创建或删除任何配对。"
        elif pair_mode == "managed":
            message = u"参数已保存。下一步请点击“③ 创建 / 修复虚拟串口”。"
        else:
            message = u"参数已保存。下一步请点击“④ 检查这两个端口是否成对”。"
        show_info(
            self,
            u"保存成功",
            message,
        )

    def _on_export_config(self):
        """导出配置文件包 (支持 Zip 或 JSON)"""
        from ui.custom_dialog import show_info, show_error
        file_path, _ = QFileDialog.getSaveFileName(
            self, u"导出系统设置包", "ygf_pos_settings.zip", "Zip 打包配置文件 (*.zip);;JSON 配置文件 (*.json)"
        )
        if not file_path:
            return
        try:
            export_config_bundle(self.config, file_path)
            show_info(self, u"导出成功", f"配置文件已成功导出至：\n{file_path}")
        except Exception as e:
            show_error(self, u"导出失败", f"导出配置文件包时发生错误: {e}")

    def _on_import_config(self):
        """导入配置文件包"""
        from ui.custom_dialog import show_question, show_info, show_error
        file_path, _ = QFileDialog.getOpenFileName(
            self, u"导入系统设置包", "", "设置包文件 (*.zip *.json)"
        )
        if not file_path:
            return
        if not show_question(self, u"导入确认", u"确定要导入并覆盖当前系统的配置参数吗？导入后系统将自动更新。"):
            return
        try:
            imported = import_config_bundle(file_path)
            # Keep the shared dictionary object: MainWindow, SaleWidget,
            # printer and scale reader all hold this same reference.
            self.config.clear()
            self.config.update(imported)
            show_info(
                self, u"导入成功",
                u"导入前的配置已自动备份到 data/backups。\n"
                u"新参数已写入；为保证电子秤、打印机和页面控件全部重新加载，请重启 POS。",
            )
        except Exception as e:
            show_error(self, u"导入失败", f"导入配置文件包时发生错误: {e}")

    def _on_reset_sys_config(self):
        """还原系统与硬件配置 (base.json)"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【系统与硬件配置】还原为出厂默认设置吗？"):
            return
        try:
            backup_config_bundle("before_reset_sys")
            self.config = reset_module_config(self.config, "sys")
            show_info(self, u"还原成功", u"已先创建配置备份。系统与硬件参数已恢复默认；请重启 POS 重新连接设备。")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_takeout_config(self):
        """还原打印机中继与订单识别规则"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【打印机中继与订单识别规则】还原为出厂默认设置吗？"):
            return
        try:
            backup_config_bundle("before_reset_takeout")
            self.config = reset_module_config(self.config, "printer_relay")
            show_info(self, u"还原成功", u"【打印机中继与订单识别规则】已成功还原为出厂默认值！")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_algo_config(self):
        """还原私域切屏算法规则 (algo.json)"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【私域切屏算法规则】还原为出厂默认设置吗？"):
            return
        try:
            backup_config_bundle("before_reset_algo")
            self.config = reset_module_config(self.config, "algo")
            show_info(self, u"还原成功", u"【私域切屏算法规则】(data/settings/algo.json) 已成功还原为出厂默认值！")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_sqb_config(self):
        """还原收钱吧插件配置 (shouqianba.json)"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【收钱吧插件配置】还原为出厂默认设置吗？"):
            return
        try:
            backup_config_bundle("before_reset_shouqianba")
            self.config = reset_module_config(self.config, "shouqianba")
            show_info(self, u"还原成功", u"【收钱吧插件配置】(data/settings/shouqianba.json) 已成功还原为出厂默认值！")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_logs(self):
        """仅重置运行与算法日志"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"清空日志确认", u"确定要清空全部系统运行与算法操作日志 (app_events.jsonl) 吗？该操作不可撤销。"):
            return
        try:
            from core.app_logger import clear_all_logs
            ok = clear_all_logs()
            if ok:
                show_info(self, u"清空成功", u"全部运行与算法操作日志已成功清空！")
            else:
                show_error(self, u"清空失败", u"无法清除日志文件，请检查文件权限。")
        except Exception as e:
            show_error(self, u"操作异常", f"清空日志时发生错误: {e}")

    def _on_reset_db(self):
        """仅重置销售数据库"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"清空数据库确认", u"确定要清空当前本地销售账本吗？旧账本会先归档到 data/backups，便于恢复。"):
            return
        try:
            from core.database import archive_database_files
            backup_path = archive_database_files(reason="manual_clear")
            parent_mw = self.window()
            if hasattr(parent_mw, "db"):
                parent_mw.db._init_db()
            if hasattr(parent_mw, "history_page"):
                parent_mw.history_page.reload_orders()
            if hasattr(parent_mw, "report_page"):
                parent_mw.report_page.reload_report()
            show_info(
                self, u"清空成功",
                u"当前销售库已建立为空账本，可以立即继续开单。\n"
                u"为防误操作，旧库已归档到：\n%s" % (backup_path or u"无需归档（原库不存在）"),
            )
        except Exception as e:
            show_error(self, u"操作异常", f"清空数据库时发生错误: {e}")

    def _on_reset_config(self):
        """仅恢复默认配置"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"恢复默认设置确认", u"确定要重置配置文件 (config.json) 为出厂默认参数吗？软件即将关闭以应用初始设置。"):
            return
        try:
            reset_all_config(self.config)
            show_info(self, u"重置成功", u"原模块化设置已备份，新的出厂设置已写入。程序即刻关闭，请手动重新启动。")
            from PyQt5.QtWidgets import QApplication
            QApplication.quit()
        except Exception as e:
            show_error(self, u"操作异常", f"重置配置文件时发生错误: {e}")

    def _on_reset(self):
        """重置软件（危险操作）"""
        r1 = QMessageBox.warning(
            self, u"严重警告", 
            u"您正在进行危险操作！\n这将会清除所有的本地设置以及所有的历史订单数据！\n您确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r1 != QMessageBox.Yes:
            return

        r2 = QMessageBox.warning(
            self, u"最后警告", 
            u"数据一旦删除将【永远无法恢复】。\n您真的确定要删除数据库和配置文件吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r2 != QMessageBox.Yes:
            return
        
        r3 = QMessageBox.critical(
            self, u"最终确认", 
            u"这是最后一次确认机会。\n点击 Yes 将立即清除数据并关闭软件！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r3 != QMessageBox.Yes:
            return
        
        try:
            import os
            from core.database import archive_database_files
            archive_database_files(reason="factory_reset")
            reset_all_config(self.config)

            try:
                from core.app_logger import clear_all_logs
                clear_all_logs()
            except Exception as e:
                print(f"Failed to remove log file: {e}")
            
            QMessageBox.information(
                self, u"重置成功", 
                u"软件已恢复初始设置。为防误操作，旧销售库和配置均已归档到 data/backups。\n"
                u"程序即将关闭，请手动重新打开。"
            )
            from PyQt5.QtWidgets import QApplication
            QApplication.quit()
            
        except Exception as e:
            QMessageBox.critical(self, u"重置失败", f"重置过程中出现意外错误:\n{e}")
