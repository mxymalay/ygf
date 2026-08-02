# -*- coding: utf-8 -*-
import sys
import os
from PyQt5.QtWidgets import QApplication, QSpinBox, QWidget, QVBoxLayout, QLabel

app = QApplication(sys.argv)
w = QWidget()
lay = QVBoxLayout(w)

lbl = QLabel(u"👨‍🍳 制作联份数:")
lay.addWidget(lbl)

sb = QSpinBox()
sb.setRange(0, 10)
lay.addWidget(sb)

# 创建并保存标准的箭头图片数据或生成图标
icon_dir = os.path.join(os.path.dirname(__file__), "..", "data", "icons")
os.makedirs(icon_dir, exist_ok=True)

up_path = os.path.join(icon_dir, "arrow_up.png").replace("\\", "/")
down_path = os.path.join(icon_dir, "arrow_down.png").replace("\\", "/")

from PyQt5.QtGui import QPixmap, QPainter, QColor, QPolygon, QPen
from PyQt5.QtCore import QPoint, Qt

def create_arrow_icon(direction="up", color="#F8FAFC", filename=""):
    pix = QPixmap(16, 16)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    if direction == "up":
        poly = QPolygon([QPoint(8, 3), QPoint(2, 12), QPoint(14, 12)])
    else:
        poly = QPolygon([QPoint(2, 4), QPoint(14, 4), QPoint(8, 13)])
    painter.drawPolygon(poly)
    painter.end()
    pix.save(filename, "PNG")

create_arrow_icon("up", "#F8FAFC", up_path)
create_arrow_icon("down", "#F8FAFC", down_path)

print("Icons created successfully:", up_path, down_path)
