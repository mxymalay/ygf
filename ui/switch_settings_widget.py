"""
自动切换算法设置页面 (Auto Switch Algorithm Settings)
包含：全自动分流参数调节 + 右侧算法实时追踪 (支持每页 20 条分页)
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QFormLayout, QFrame, QMessageBox, QScrollArea, QGroupBox, QTextEdit,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from config import save_config
from core.app_logger import log_event, CAT_SYSTEM, read_logs, CAT_DECISION, CAT_SWITCH, CAT_PANIC


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

    LOG_PAGE_SIZE = 20

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.filtered_algo_logs = []
        self.log_current_page = 1
        self.total_log_pages = 1

        self._build_ui()
        self._load_config()
        
        # 定时刷新日志 (仅当页面可见时)
        self.log_timer = QTimer(self)
        self.log_timer.setInterval(2000)
        self.log_timer.timeout.connect(self._refresh_logs)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_logs()
        self.log_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.log_timer.stop()

    def _build_ui(self):
        # Use one page-level vertical scroll area.  The configuration form and
        # the trace panel are both allowed to use their natural height; the
        # operator scrolls the whole page instead of fighting nested scrollbars.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        page_scroll = QScrollArea(self)
        page_scroll.setWidgetResizable(True)
        page_scroll.setMinimumWidth(0)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        page_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 14px; background: #0F172A; border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: #475569; border-radius: 7px; min-height: 60px;
            }
        """)
        page_container = QWidget()
        page_container.setMinimumWidth(0)
        page_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        page_layout = QVBoxLayout(page_container)
        page_layout.setContentsMargins(16, 12, 16, 24)
        page_layout.setSpacing(18)

        # ==========================================
        # 左侧：配置项 (占 60% 宽度)
        # ==========================================
        left_panel = QWidget()
        left_panel.setMinimumWidth(0)
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题区
        lbl_title = QLabel(u"全自动分流算法设置")
        lbl_title.setStyleSheet("font-size: 26px; font-weight: 900; color: #F8FAFC;")
        left_layout.addWidget(lbl_title)

        # 配置表单不再使用内层滚动框；它完整展开，由页面级滚动条统一承载。
        left_panel.setStyleSheet("""
            QGroupBox {
                background-color: #1E293B; border-radius: 12px; border: 1px solid #334155;
                margin-top: 24px; padding-top: 24px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 4px 12px; color: #38BDF8; font-size: 16px; font-weight: bold;
                background-color: #0F172A; border-radius: 8px; border: 1px solid #334155;
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

        form_container = QWidget()
        form_container.setMinimumWidth(0)
        form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form_vlayout = QVBoxLayout(form_container)
        form_vlayout.setContentsMargins(10, 10, 20, 20)
        form_vlayout.setSpacing(20)

        # --- 场景 1：总控与智能过滤 ---
        grp1 = QGroupBox(u"总控与智能过滤设置")
        lay1 = QFormLayout(grp1)
        lay1.setContentsMargins(20, 30, 20, 20)
        lay1.setSpacing(16)
        
        self.chk_enabled = QCheckBox(u"开启智能自动分流 (若关闭，则需要手动控制悬浮球)")
        lay1.addRow(QLabel(u"系统总控开关:"), self.chk_enabled)
        
        self.sp_ratio = TouchSpinBox(30, 0, 100, 5, " %")
        lay1.addRow(QLabel(u"目标私域重量占比:"), self.sp_ratio)

        lbl_ratio_tip = QLabel(u"算法按称重重量控制目标比例，不是按订单次数，也不是官方实际营业额。官方金额无法读取时，重量是最可靠的可观测代理。")
        lbl_ratio_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_ratio_tip.setWordWrap(True)
        lay1.addRow(QLabel(), lbl_ratio_tip)
        
        self.sp_weight = TouchDoubleSpinBox(0.25, 0.00, 5.00, 0.05, " kg")
        lay1.addRow(QLabel(u"轻量小单切回门限:"), self.sp_weight)
        
        lbl_w_tip = QLabel(u"场景说明：低于该重量的一律判定为小单/加菜，自动分配给官方收银机。")
        lbl_w_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_w_tip.setWordWrap(True)
        lay1.addRow(QLabel(), lbl_w_tip)

        self.sp_max_daily_limit = TouchDoubleSpinBox(0.0, 0.0, 999999.0, 100.0, " 元")
        lay1.addRow(QLabel(u"当日累计收款上限:"), self.sp_max_daily_limit)

        lbl_limit_tip = QLabel(u"场景说明：设置今日私域本POS累计收款金额上限。当今日收款达到/超过此金额时，全自动停止切换为本POS，分配给官方收银。0 元表示不限制。")
        lbl_limit_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_limit_tip.setWordWrap(True)
        lay1.addRow(QLabel(), lbl_limit_tip)
        form_vlayout.addWidget(grp1)

        # --- 场景 2：连续收银防打断 ---
        grp2 = QGroupBox(u"连续收银防打断保护")
        lay2 = QFormLayout(grp2)
        lay2.setContentsMargins(20, 30, 20, 20)
        lay2.setSpacing(16)
        
        self.sp_official_lock = TouchSpinBox(60, 0, 300, 5, " 秒")
        lay2.addRow(QLabel(u"官方界面连单保护:"), self.sp_official_lock)
        lbl_o_tip = QLabel(u"场景说明：一单刚分配给官方，此时间内就算来了大单也继续走官方，防止弹窗打断店员。")
        lbl_o_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_o_tip.setWordWrap(True)
        lay2.addRow(QLabel(), lbl_o_tip)

        self.sp_zeroing_unlock = TouchSpinBox(5, 1, 60, 1, " 秒")
        lay2.addRow(QLabel(u"称重归零离场解锁:"), self.sp_zeroing_unlock)
        lbl_z_tip = QLabel(u"场景说明：顾客端走碗，秤归零保持该时长后，自动解除上述连单保护，重新开始评判。")
        lbl_z_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_z_tip.setWordWrap(True)
        lay2.addRow(QLabel(), lbl_z_tip)

        self.sp_private_lock = TouchSpinBox(300, 10, 3600, 10, " 秒")
        lay2.addRow(QLabel(u"私域连单判定时长:"), self.sp_private_lock)
        lbl_p_tip = QLabel(u"场景说明：此时长内的新碗视为同一笔私域连单；超过后若购物车仍有商品，系统继续保留订单，不会自动清空。")
        lbl_p_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_p_tip.setWordWrap(True)
        lay2.addRow(QLabel(), lbl_p_tip)
        form_vlayout.addWidget(grp2)

        # --- 场景 3：异常抖动与人工干预 ---
        grp3 = QGroupBox(u"秤具防抖与人工干预门限")
        lay3 = QFormLayout(grp3)
        lay3.setContentsMargins(20, 30, 20, 20)
        lay3.setSpacing(16)
        
        self.sp_min_valid_weight = TouchDoubleSpinBox(0.08, 0.01, 0.50, 0.01, " kg")
        lay3.addRow(QLabel(u"起漂过滤门限:"), self.sp_min_valid_weight)
        
        self.sp_stable_threshold = TouchDoubleSpinBox(0.01, 0.01, 0.05, 0.01, " kg")
        lay3.addRow(QLabel(u"稳定读数波动范围:"), self.sp_stable_threshold)
        try:
            stable_count = max(2, int(self.config.get("stable_count", 5) or 5))
        except (TypeError, ValueError):
            stable_count = 5
        lbl_stable_tip = QLabel(u"连续 %d 次读数的最大差值不超过此范围，才认定重量稳定。" % stable_count)
        lbl_stable_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_stable_tip.setWordWrap(True)
        lay3.addRow(QLabel(), lbl_stable_tip)
        
        self.sp_manual_override_lock = TouchSpinBox(30, 5, 120, 5, " 秒")
        lay3.addRow(QLabel(u"悬浮球手动强锁定:"), self.sp_manual_override_lock)
        lbl_m_tip = QLabel(u"场景说明：只要店员手点悬浮球切屏，该时长内算法绝对静默，100% 尊重人工。")
        lbl_m_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_m_tip.setWordWrap(True)
        lay3.addRow(QLabel(), lbl_m_tip)
        form_vlayout.addWidget(grp3)

        # --- 场景 4：订单收尾 ---
        grp4 = QGroupBox(u"结账收尾动作设置")
        lay4 = QFormLayout(grp4)
        lay4.setContentsMargins(20, 30, 20, 20)
        lay4.setSpacing(16)
        
        self.sp_delay = TouchSpinBox(10, 0, 30, 1, " 秒")
        lay4.addRow(QLabel(u"结账出票后隐退延时:"), self.sp_delay)
        form_vlayout.addWidget(grp4)

        left_layout.addWidget(form_container)

        # 底部保存按钮
        self.btn_save = QPushButton(u"💾 保存算法设置")
        self.btn_save.setFixedHeight(50)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0284C7; color: white;
                font-size: 16px; font-weight: bold; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #0369A1; }
            QPushButton:pressed { background-color: #075985; }
        """)
        self.btn_save.clicked.connect(self._on_save)
        left_layout.addWidget(self.btn_save)

        # ==========================================
        # 右侧：实时日志监控 (占 40% 宽度，带分页)
        # ==========================================
        right_panel = QWidget()
        right_panel.setMinimumWidth(0)
        # Keep a generous touch-friendly log viewport.  The previous 170-230px
        # cap made the real-time trace practically unreadable on POS screens.
        right_panel.setMinimumHeight(520)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(10)

        lbl_log_title = QLabel(u"📡 算法实时追踪 (自动刷新)")
        lbl_log_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #38BDF8;")
        right_layout.addWidget(lbl_log_title)

        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setStyleSheet("""
            QTextEdit {
                background-color: #0F172A; color: #F8FAFC; font-size: 13px; font-family: monospace;
                border: 1px solid #334155; border-radius: 8px; padding: 10px;
            }
        """)
        right_layout.addWidget(self.txt_logs, stretch=1)

        # ── 右侧底部分页控制栏 ──
        log_paging_bar = QHBoxLayout()
        log_paging_bar.setContentsMargins(0, 4, 0, 0)
        log_paging_bar.setSpacing(8)

        self.btn_log_prev = QPushButton(u"◀ 上一页")
        self.btn_log_prev.setFixedHeight(34)
        self.btn_log_prev.setCursor(Qt.PointingHandCursor)
        self.btn_log_prev.setStyleSheet("""
            QPushButton {
                background-color: #1E293B; color: #F8FAFC; font-size: 13px; font-weight: bold;
                padding: 4px 14px; border-radius: 6px; border: 1px solid #334155;
            }
            QPushButton:hover { background-color: #334155; color: #38BDF8; border-color: #38BDF8; }
            QPushButton:disabled { background-color: #0F172A; color: #475569; border-color: #1E293B; }
        """)
        self.btn_log_prev.clicked.connect(self._prev_log_page)
        log_paging_bar.addWidget(self.btn_log_prev)

        self.lbl_log_page = QLabel(u"第 1 / 1 页 (共 0 条)")
        self.lbl_log_page.setAlignment(Qt.AlignCenter)
        self.lbl_log_page.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: bold;")
        log_paging_bar.addWidget(self.lbl_log_page, stretch=1)

        self.btn_log_next = QPushButton(u"下一页 ▶")
        self.btn_log_next.setFixedHeight(34)
        self.btn_log_next.setCursor(Qt.PointingHandCursor)
        self.btn_log_next.setStyleSheet("""
            QPushButton {
                background-color: #1E293B; color: #F8FAFC; font-size: 13px; font-weight: bold;
                padding: 4px 14px; border-radius: 6px; border: 1px solid #334155;
            }
            QPushButton:hover { background-color: #334155; color: #38BDF8; border-color: #38BDF8; }
            QPushButton:disabled { background-color: #0F172A; color: #475569; border-color: #1E293B; }
        """)
        self.btn_log_next.clicked.connect(self._next_log_page)
        log_paging_bar.addWidget(self.btn_log_next)

        right_layout.addLayout(log_paging_bar)

        # 纵向排列，整页统一滚动，实时追踪区域不再被屏幕高度截断。
        page_layout.addWidget(left_panel)
        page_layout.addWidget(right_panel)
        page_scroll.setWidget(page_container)
        root.addWidget(page_scroll)

    def _refresh_logs(self):
        """拉取日志，仅筛选 决策、切换、避险"""
        all_logs = read_logs(limit=2000)
        self.filtered_algo_logs = [L for L in all_logs if L.get("cat") in (CAT_DECISION, CAT_SWITCH, CAT_PANIC)]
        self._render_log_page()

    def _render_log_page(self):
        """仅渲染当前页面的 20 条算法日志，消除卡顿"""
        total = len(self.filtered_algo_logs)
        self.total_log_pages = max(1, (total + self.LOG_PAGE_SIZE - 1) // self.LOG_PAGE_SIZE)

        if self.log_current_page > self.total_log_pages:
            self.log_current_page = self.total_log_pages
        if self.log_current_page < 1:
            self.log_current_page = 1

        if not self.filtered_algo_logs:
            self.txt_logs.setHtml("<div style='color: #475569; text-align: center; margin-top: 40px; font-weight: bold;'>暂无算法追踪日志</div>")
            self.lbl_log_page.setText("第 0 / 0 页")
            self.btn_log_prev.setEnabled(False)
            self.btn_log_next.setEnabled(False)
            return

        start_idx = (self.log_current_page - 1) * self.LOG_PAGE_SIZE
        end_idx = min(start_idx + self.LOG_PAGE_SIZE, total)
        page_entries = self.filtered_algo_logs[start_idx:end_idx]

        html = ""
        for entry in page_entries:
            cat = entry.get("cat")
            msg = entry.get("msg", "")
            detail = entry.get("detail", "")
            ts = entry.get("ts", "")[-8:] # 只取时间部分 HH:MM:SS

            color = "#94A3B8"
            if cat == CAT_DECISION: color = "#A855F7"
            elif cat == CAT_SWITCH: color = "#FF781F"
            elif cat == CAT_PANIC: color = "#EF4444"

            html += f"<div style='margin-bottom: 8px; border-bottom: 1px dashed #1E293B; padding-bottom: 6px;'>"
            html += f"<span style='color: #475569;'>[{ts}]</span> "
            html += f"<b style='color: {color};'>[{cat}]</b> "
            html += f"<span style='color: #E2E8F0;'>{msg}</span><br>"
            if detail:
                html += f"<span style='color: #94A3B8; font-size: 12px;'> - {detail}</span>"
            html += f"</div>"

        self.txt_logs.setHtml(html)
        self.lbl_log_page.setText(f"第 {self.log_current_page} / {self.total_log_pages} 页 · 共 {total} 条")

        self.btn_log_prev.setEnabled(self.log_current_page > 1)
        self.btn_log_next.setEnabled(self.log_current_page < self.total_log_pages)

    def _prev_log_page(self):
        if self.log_current_page > 1:
            self.log_current_page -= 1
            self._render_log_page()

    def _next_log_page(self):
        if self.log_current_page < self.total_log_pages:
            self.log_current_page += 1
            self._render_log_page()

    def _load_config(self):
        self.chk_enabled.setChecked(self.config.get("auto_switch_enabled", True))
        self.sp_ratio.setValue(int(self.config.get("private_ratio_percent", 30)))
        self.sp_weight.setValue(float(self.config.get("min_private_weight_kg", 0.25)))
        self.sp_max_daily_limit.setValue(float(self.config.get("max_daily_revenue_limit", 0.0)))
        self.sp_min_valid_weight.setValue(float(self.config.get("min_valid_weight_kg", 0.08)))
        self.sp_stable_threshold.setValue(float(self.config.get("stable_threshold", 0.01)))
        
        self.sp_official_lock.setValue(int(self.config.get("official_lock_sec", 60)))
        self.sp_zeroing_unlock.setValue(int(self.config.get("zeroing_unlock_sec", 5)))
        self.sp_private_lock.setValue(int(self.config.get("private_lock_sec", 300)))
        self.sp_manual_override_lock.setValue(int(self.config.get("manual_override_lock_sec", 30)))
        self.sp_delay.setValue(int(self.config.get("auto_hide_delay_sec", 10)))

    def _on_save(self):
        # 1. 获取新值
        new_enabled = self.chk_enabled.isChecked()
        new_ratio = self.sp_ratio.value()
        new_weight = self.sp_weight.value()
        new_max_daily_limit = self.sp_max_daily_limit.value()
        new_min_valid = self.sp_min_valid_weight.value()
        new_stable_threshold = self.sp_stable_threshold.value()
        new_official_lock = self.sp_official_lock.value()
        new_zeroing_unlock = self.sp_zeroing_unlock.value()
        new_private_lock = self.sp_private_lock.value()
        new_manual_override = self.sp_manual_override_lock.value()
        new_delay = self.sp_delay.value()

        # 2. 更新 config
        self.config["auto_switch_enabled"] = new_enabled
        self.config["private_ratio_percent"] = new_ratio
        self.config["min_private_weight_kg"] = new_weight
        self.config["max_daily_revenue_limit"] = new_max_daily_limit
        self.config["min_valid_weight_kg"] = new_min_valid
        self.config["stable_threshold"] = new_stable_threshold
        self.config["official_lock_sec"] = new_official_lock
        self.config["zeroing_unlock_sec"] = new_zeroing_unlock
        self.config["private_lock_sec"] = new_private_lock
        self.config["manual_override_lock_sec"] = new_manual_override
        self.config["auto_hide_delay_sec"] = new_delay
        
        save_config(self.config)

        # 3. 记录日志
        detail = (f"开关: {'开' if new_enabled else '关'} | "
                  f"目标重量比: {new_ratio}% | "
                  f"门限: {new_weight:.2f}kg | 当日上限: {new_max_daily_limit:.2f}元 | "
                  f"防抖(起漂{new_min_valid:.2f}, 稳定波动{new_stable_threshold:.2f}) | "
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
        if hasattr(parent_mw, 'sale_page') and parent_mw.sale_page:
            if not parent_mw.sale_page.restart_scale():
                QMessageBox.warning(
                    self,
                    u"称重读取器尚未重启",
                    u"算法参数已保存，但旧称重线程未能安全退出。请退出并重新打开本 POS 后生效。",
                )
                return

        QMessageBox.information(self, u"保存成功", u"分流算法参数已保存并立即生效！")
        self._refresh_logs() # 手动触发一次
