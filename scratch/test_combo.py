"""测试不同方式让 QComboBox 下拉项变高"""
import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QComboBox, QLabel,
    QStyledItemDelegate, QListView
)
from PyQt5.QtCore import QSize

class BigDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        s.setHeight(48)
        return s

app = QApplication(sys.argv)
w = QWidget()
w.setWindowTitle("ComboBox Height Test")
w.resize(500, 400)
layout = QVBoxLayout(w)

items = ["选项一: Official", "选项二: COM串口", "选项三: 测试"]

# ── 方式1: queue_widget 原始写法 (QStyledItemDelegate + 自身stylesheet) ──
layout.addWidget(QLabel("方式1: QStyledItemDelegate + combo自身stylesheet"))
c1 = QComboBox()
c1.setItemDelegate(QStyledItemDelegate())
c1.addItems(items)
c1.setStyleSheet("""
    QComboBox { 
        font-size: 15px; padding: 10px 18px; 
        background: #0F172A; color: #F8FAFC; border: 1px solid #334155;
        border-radius: 8px;
    }
    QComboBox::drop-down { border: none; width: 30px; }
    QComboBox QAbstractItemView {
        background-color: #0F172A; color: #F8FAFC;
        selection-background-color: #EA580C;
        font-size: 15px; border: 1px solid #334155;
        outline: none;
    }
    QComboBox QAbstractItemView::item {
        min-height: 46px;
        padding: 8px 14px;
    }
""")
layout.addWidget(c1)

# ── 方式2: combobox-popup: 0 ──
layout.addWidget(QLabel("方式2: combobox-popup: 0"))
c2 = QComboBox()
c2.setItemDelegate(QStyledItemDelegate())
c2.addItems(items)
c2.setStyleSheet("""
    QComboBox { 
        combobox-popup: 0;
        font-size: 15px; padding: 10px 18px;
        background: #0F172A; color: #F8FAFC; border: 1px solid #334155;
        border-radius: 8px;
    }
    QComboBox::drop-down { border: none; width: 30px; }
    QComboBox QAbstractItemView {
        background-color: #0F172A; color: #F8FAFC;
        selection-background-color: #EA580C;
        font-size: 15px; border: 1px solid #334155;
        outline: none;
    }
    QComboBox QAbstractItemView::item {
        min-height: 46px;
        padding: 8px 14px;
    }
""")
layout.addWidget(c2)

# ── 方式3: BigDelegate 自定义 sizeHint ──
layout.addWidget(QLabel("方式3: 自定义sizeHint delegate"))
c3 = QComboBox()
c3.setItemDelegate(BigDelegate())
c3.addItems(items)
c3.setStyleSheet("""
    QComboBox { 
        font-size: 15px; padding: 10px 18px;
        background: #0F172A; color: #F8FAFC; border: 1px solid #334155;
    }
    QComboBox::drop-down { border: none; width: 30px; }
    QComboBox QAbstractItemView {
        background-color: #0F172A; color: #F8FAFC;
        selection-background-color: #EA580C;
        outline: none;
    }
""")
layout.addWidget(c3)

# ── 方式4: QListView + BigDelegate ──
layout.addWidget(QLabel("方式4: setView(QListView) + BigDelegate"))
c4 = QComboBox()
view4 = QListView()
c4.setView(view4)
c4.setItemDelegate(BigDelegate())
c4.addItems(items)
c4.setStyleSheet("""
    QComboBox { 
        font-size: 15px; padding: 10px 18px;
        background: #0F172A; color: #F8FAFC; border: 1px solid #334155;
    }
    QComboBox::drop-down { border: none; width: 30px; }
""")
layout.addWidget(c4)

w.show()
print("请逐个点击每个下拉框，看哪种方式的下拉选项变高了")
print("关闭窗口即退出")
sys.exit(app.exec_())
