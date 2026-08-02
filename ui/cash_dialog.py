from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QGraphicsBlurEffect
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

class CashCalculatorDialog(QDialog):
    """
    现金结算计算器
    自动弹钱箱，收银员输入实收金额，显示找零，点击确认出票。
    """
    def __init__(self, sale_data, parent=None, on_confirm=None, printer=None):
        super().__init__(parent)
        self.sale_data = sale_data
        self.total_amount = sale_data.get("total_price", 0.0)
        self.on_confirm = on_confirm
        self.printer = printer
        self.received_amount_str = ""

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.resize(500, 650)
        
        self._build_ui()
        
        # 立即发送开钱箱指令
        if self.printer:
            QTimer.singleShot(100, self.printer.open_cash_drawer)

    def _build_ui(self):
        main_frame = QFrame(self)
        main_frame.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border-radius: 20px;
                border: 2px solid #3B82F6;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(main_frame)
        
        layout = QVBoxLayout(main_frame)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 标题栏
        header = QHBoxLayout()
        lbl_title = QLabel(u"💵 现金结算")
        lbl_title.setStyleSheet("font-size: 24px; font-weight: 900; color: #60A5FA; border: none;")
        header.addWidget(lbl_title)
        
        btn_close = QPushButton(u"✕")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton { background: transparent; color: #94A3B8; font-size: 24px; font-weight: bold; border: none; }
            QPushButton:hover { color: #F87171; }
        """)
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close, alignment=Qt.AlignRight)
        layout.addLayout(header)
        
        # 价格显示区
        display_frame = QFrame()
        display_frame.setStyleSheet("""
            QFrame { background: #0F172A; border-radius: 12px; border: 1px solid #334155; }
        """)
        disp_layout = QVBoxLayout(display_frame)
        disp_layout.setContentsMargins(20, 20, 20, 20)
        disp_layout.setSpacing(10)
        
        # 应收
        row_ys = QHBoxLayout()
        lbl_ys_t = QLabel(u"应收金额：")
        lbl_ys_t.setStyleSheet("font-size: 18px; color: #94A3B8; border: none;")
        int_ys, dec_ys = f"{self.total_amount:.2f}".split('.')
        self.lbl_ys = QLabel(f"￥{int_ys}.<span style='font-size:18px;'>{dec_ys}</span>")
        self.lbl_ys.setStyleSheet("font-size: 28px; font-weight: bold; color: #F1F5F9; border: none;")
        row_ys.addWidget(lbl_ys_t)
        row_ys.addStretch()
        row_ys.addWidget(self.lbl_ys)
        disp_layout.addLayout(row_ys)
        
        # 实收
        row_ss = QHBoxLayout()
        lbl_ss_t = QLabel(u"实收金额：")
        lbl_ss_t.setStyleSheet("font-size: 18px; color: #94A3B8; border: none;")
        self.lbl_ss = QLabel(u"￥0.<span style='font-size:24px;'>00</span>")
        self.lbl_ss.setStyleSheet("font-size: 36px; font-weight: 900; color: #34D399; border: none;")
        row_ss.addWidget(lbl_ss_t)
        row_ss.addStretch()
        row_ss.addWidget(self.lbl_ss)
        disp_layout.addLayout(row_ss)
        
        # 找零
        row_zl = QHBoxLayout()
        lbl_zl_t = QLabel(u"找零金额：")
        lbl_zl_t.setStyleSheet("font-size: 18px; color: #94A3B8; border: none;")
        self.lbl_zl = QLabel(u"￥0.<span style='font-size:36px;'>00</span>")
        self.lbl_zl.setStyleSheet("font-size: 56px; font-weight: 900; color: #F59E0B; border: none;")
        row_zl.addWidget(lbl_zl_t)
        row_zl.addStretch()
        row_zl.addWidget(self.lbl_zl)
        disp_layout.addLayout(row_zl)
        
        layout.addWidget(display_frame)

        # 键盘区域
        grid = QGridLayout()
        grid.setSpacing(10)
        
        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2), ('退格', 0, 3),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2), ('清空', 1, 3),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2), ('确认\n收款', 2, 3, 2, 1),
            ('0', 3, 0, 1, 2), ('.', 3, 2)
        ]
        
        for btn_data in buttons:
            text = btn_data[0]
            r = btn_data[1]
            c = btn_data[2]
            rs = btn_data[3] if len(btn_data) > 3 else 1
            cs = btn_data[4] if len(btn_data) > 4 else 1
            
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            
            if text == '确认\n收款':
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2563EB, stop:1 #1D4ED8);
                        color: white; font-size: 22px; font-weight: 900; border-radius: 12px; border: none;
                    }
                    QPushButton:hover { background: #3B82F6; }
                """)
                btn.clicked.connect(self._on_confirm)
            elif text in ('退格', '清空'):
                btn.setStyleSheet("""
                    QPushButton {
                        background: #334155; color: #F1F5F9; font-size: 20px; font-weight: bold; border-radius: 12px; border: none;
                    }
                    QPushButton:hover { background: #475569; }
                """)
                btn.clicked.connect(lambda checked, t=text: self._on_key(t))
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #1E293B; color: #F8FAFC; font-size: 26px; font-weight: 900; border-radius: 12px; border: 1px solid #334155;
                    }
                    QPushButton:hover { background: #334155; border: 1px solid #475569; }
                """)
                btn.clicked.connect(lambda checked, t=text: self._on_key(t))
                
            grid.addWidget(btn, r, c, rs, cs)
            # 让键盘占满空间
            btn.setSizePolicy(btn.sizePolicy().Expanding, btn.sizePolicy().Expanding)

        layout.addLayout(grid, stretch=1)

    def _on_key(self, key):
        if key == '清空':
            self.received_amount_str = ""
        elif key == '退格':
            self.received_amount_str = self.received_amount_str[:-1]
        elif key == '.':
            if '.' not in self.received_amount_str:
                self.received_amount_str += '.'
        else:
            if len(self.received_amount_str) < 10:
                self.received_amount_str += key
                
        self._update_display()
        
    def _update_display(self):
        val = 0.0
        try:
            if self.received_amount_str:
                val = float(self.received_amount_str)
        except ValueError:
            pass
            
        int_ss, dec_ss = f"{val:.2f}".split('.')
        self.lbl_ss.setText(f"￥{int_ss}.<span style='font-size:24px;'>{dec_ss}</span>")
        
        change = val - self.total_amount
        if change < 0:
            self.lbl_zl.setText(u"￥0.<span style='font-size:36px;'>00</span>")
            self.lbl_zl.setStyleSheet("font-size: 56px; font-weight: 900; color: #94A3B8; border: none;")
        else:
            int_zl, dec_zl = f"{change:.2f}".split('.')
            self.lbl_zl.setText(f"￥{int_zl}.<span style='font-size:36px;'>{dec_zl}</span>")
            self.lbl_zl.setStyleSheet("font-size: 56px; font-weight: 900; color: #F59E0B; border: none;")

    def _on_confirm(self):
        val = 0.0
        try:
            if self.received_amount_str:
                val = float(self.received_amount_str)
        except ValueError:
            pass
            
        if val < self.total_amount:
            from ui.custom_dialog import show_warning
            show_warning(self, u"提示", u"实收金额小于应收金额！")
            return
            
        if self.on_confirm:
            self.on_confirm("cash")
        self.accept()
