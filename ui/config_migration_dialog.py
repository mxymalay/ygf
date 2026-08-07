# -*- coding: utf-8 -*-
"""Touch-friendly first-run migration choice for the legacy settings file."""
from __future__ import annotations

import json

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


FIELD_LABELS = {
    "printer_type": "打印机类型",
    "printer_name": "打印机名称",
    "printer_ip": "网络打印机地址",
    "printer_port": "网络打印机端口",
    "printer_serial_port": "打印机串口",
    "unit_price": "默认单价",
    "special_soup_price": "特殊汤底单价",
    "price_unit": "计价单位",
    "shop_name": "店铺名称",
    "shop_subtitle": "店铺副标题",
    "scale_source": "称重来源",
    "scale_connection_mode": "称重连接模式",
    "scale_port": "称重串口",
    "scale_baudrate": "称重波特率",
    "official_pos_log_dir": "官方 POS 日志目录",
    "official_pos_window_keywords": "官方 POS 窗口关键词",
    "official_pos_process_keywords": "官方 POS 进程关键词",
    "private_ratio_percent": "私域比例",
    "min_private_weight_kg": "私域最小重量",
    "shouqianba_enabled": "收钱吧启用",
    "shouqianba_pair_mode": "收钱吧配对模式",
    "shouqianba_port": "收钱吧发送端口",
    "shouqianba_plugin_port": "收钱吧插件端口",
    "shouqianba_baudrate": "收钱吧波特率",
    "shouqianba_format": "收钱吧格式",
    "shouqianba_hotkey": "收钱吧快捷键",
    "shouqianba_install_dir": "收钱吧插件安装目录",
    "takeout_interceptor_enabled": "外卖中继启用",
    "takeout_proxy_port": "外卖中继端口",
    "takeout_proxy_queue_name": "外卖中继队列",
    "takeout_auto_print": "外卖自动打印",
    "takeout_relay_mode": "中继工作模式",
    "takeout_relay_mode_policy": "中继模式策略",
    "takeout_relay_last_check_at": "中继最后检查时间",
    "takeout_relay_last_identification": "中继最近识别结果",
    "takeout_categories": "外卖分类规则",
    "takeout_kitchen_copies": "制作联份数",
    "takeout_cust_copies": "存根联份数",
    "takeout_match_mode": "外卖匹配模式",
    "call_mode": "叫号模式",
    "custom_start_no": "自定义叫号起点",
    "custom_end_no": "自定义叫号终点",
    "auto_switch_enabled": "自动切换",
    "auto_start_enabled": "开机自启",
    "auto_start_delay": "开机延迟",
    "floating_ball_enabled": "悬浮球",
}


def _value_text(value):
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > 90:
        text = text[:87] + "..."
    return text


class ConfigMigrationDialog(QDialog):
    """Ask which legacy settings should survive before any file is deleted."""

    def __init__(self, migration_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("旧配置迁移")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.choice = "auto"
        self.selected_keys = []
        self._checks = {}
        self._build_ui(migration_info or {})

    def _button_style(self, color):
        return (
            "QPushButton { background: %s; color: white; border: none; border-radius: 10px; "
            "padding: 14px 24px; font-size: 17px; font-weight: bold; min-height: 58px; }"
            "QPushButton:hover { background: #7C3AED; }" % color
        )

    def _build_ui(self, info):
        card = QFrame(self)
        card.setObjectName("MigrationCard")
        card.setStyleSheet(
            "QFrame#MigrationCard { background: #1E293B; border: 1px solid #475569; border-radius: 16px; }"
            "QRadioButton, QCheckBox { color: #F8FAFC; font-size: 16px; min-height: 54px; }"
            "QRadioButton::indicator, QCheckBox::indicator { width: 26px; height: 26px; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)

        title = QLabel("检测到旧版系统配置")
        title.setStyleSheet("color: #F8FAFC; font-size: 26px; font-weight: 900; border: none;")
        layout.addWidget(title)
        message = QLabel(
            "请选择一次配置迁移方式。旧配置会先备份到 data\\backups，再按选择处理；\n"
            "销售数据库不会被重建、删除或放入配置备份。"
        )
        message.setWordWrap(True)
        message.setStyleSheet("color: #CBD5E1; font-size: 16px; border: none;")
        layout.addWidget(message)

        self.radio_rebuild = QRadioButton("1. 重建配置（清空旧设置，使用默认值）")
        self.radio_rebuild.setToolTip("保留数据库，旧设置先备份后删除")
        self.radio_selective = QRadioButton("2. 选择要保留的配置项目")
        self.radio_auto = QRadioButton("3. 全部由系统自动迁移（推荐）")
        self.radio_auto.setChecked(True)
        for radio in (self.radio_rebuild, self.radio_selective, self.radio_auto):
            layout.addWidget(radio)
            radio.toggled.connect(self._update_selection_visibility)

        self.selection_panel = QWidget()
        selection_layout = QVBoxLayout(self.selection_panel)
        selection_layout.setContentsMargins(26, 0, 0, 0)
        selection_layout.setSpacing(3)
        hint = QLabel("勾选要带入新配置的项目（默认全部勾选）：")
        hint.setStyleSheet("color: #A5B4FC; font-size: 15px; border: none;")
        selection_layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(230)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #475569; border-radius: 8px; background: #0F172A; }")
        rows = QWidget()
        rows_layout = QVBoxLayout(rows)
        rows_layout.setContentsMargins(12, 8, 12, 8)
        rows_layout.setSpacing(2)
        items = info.get("items") if isinstance(info.get("items"), dict) else {}
        if items:
            for key in sorted(items):
                label = FIELD_LABELS.get(key, key)
                check = QCheckBox("%s：%s" % (label, _value_text(items[key])))
                check.setChecked(True)
                self._checks[key] = check
                rows_layout.addWidget(check)
        else:
            empty = QLabel("旧配置中没有可识别项目，将使用默认配置。")
            empty.setStyleSheet("color: #94A3B8; font-size: 15px; padding: 12px; border: none;")
            rows_layout.addWidget(empty)
        rows_layout.addStretch()
        scroll.setWidget(rows)
        selection_layout.addWidget(scroll)
        layout.addWidget(self.selection_panel)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消并退出")
        cancel.setStyleSheet(self._button_style("#475569"))
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        confirm = QPushButton("保存选择并继续")
        confirm.setStyleSheet(self._button_style("#6D28D9"))
        confirm.clicked.connect(self._confirm)
        actions.addWidget(confirm)
        layout.addLayout(actions)
        self.resize(820, 700)
        self._update_selection_visibility()

    def _update_selection_visibility(self):
        self.selection_panel.setVisible(self.radio_selective.isChecked())

    def _confirm(self):
        if self.radio_rebuild.isChecked():
            self.choice = "rebuild"
        elif self.radio_selective.isChecked():
            self.choice = "selective"
            self.selected_keys = [key for key, check in self._checks.items() if check.isChecked()]
        else:
            self.choice = "auto"
        self.accept()
