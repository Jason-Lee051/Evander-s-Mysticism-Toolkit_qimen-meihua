"""
ui/meihua_view.py - 梅花易数卦象绘制（六爻）
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont

from .common import BG_COLOR, LINE_COLOR

class MeihuaView(QWidget):
    def __init__(self, gua_data: dict, parent=None):
        super().__init__(parent)
        self.gua_data = gua_data
        self.setMinimumSize(300, 400)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG_COLOR))

        # 绘制卦象：六爻从下往上垂直排列
        w = self.width()
        h = self.height()
        margin = 40
        y_spacing = (h - 2*margin) / 6
        x_center = w // 2
        line_len = min(w * 0.6, 150)

        ben_lines = self.gua_data["ben_lines"]  # 从下往上索引0-5
        moving_line = self.gua_data["ben_gua"]["moving_line"]

        # 画标题
        painter.setPen(QColor("white"))
        font = QFont("SimHei", 14)
        painter.setFont(font)
        title = self.gua_data["ben_gua"]["name"]
        painter.drawText(QRectF(0, 10, w, 30), Qt.AlignHCenter, title)

        # 绘制爻
        for i in range(5, -1, -1):  # 从最上面（上爻）开始绘制
            y = margin + (5 - i) * y_spacing + y_spacing/2
            val = ben_lines[i]
            is_moving = (i+1) == moving_line
            # 阳爻：实线长条，阴爻：中间断开的双线
            painter.setPen(QPen(QColor(LINE_COLOR), 4))
            if val == 1:  # 阳
                painter.drawLine(int(x_center - line_len/2), int(y), int(x_center + line_len/2), int(y))
            else:  # 阴
                gap = 10
                painter.drawLine(int(x_center - line_len/2), int(y), int(x_center - gap/2), int(y))
                painter.drawLine(int(x_center + gap/2), int(y), int(x_center + line_len/2), int(y))
            # 动爻标记
            if is_moving:
                painter.setPen(QColor("red"))
                font2 = QFont("SimHei", 10)
                painter.setFont(font2)
                painter.drawText(QRectF(x_center + line_len/2 + 10, y-8, 30, 16), "动")

        # 显示卦名和体用、旺衰
        painter.setPen(QColor("gray"))
        font = QFont("SimHei", 10)
        painter.setFont(font)
        painter.drawText(QRectF(10, h-30, w-20, 20), Qt.AlignLeft, f"体:{self.gua_data['ti_name']}({self.gua_data['ti_wuxing']}) 用:{self.gua_data['yong_name']}({self.gua_data['yong_wuxing']})")
        painter.drawText(QRectF(10, h-50, w-20, 20), Qt.AlignLeft, f"旺衰:体{self.gua_data.get('ti_shi','')} 用{self.gua_data.get('yong_shi','')}")
        painter.drawText(QRectF(10, h-70, w-20, 20), Qt.AlignLeft, f"关系: {self.gua_data['relation']}")
        # 卦辞（本卦）
        if self.gua_data.get("ben_gua", {}).get("gua_ci"):
            painter.drawText(QRectF(10, 46, w-20, h-90), Qt.AlignLeft | Qt.TextWordWrap,
                             f"卦辞：{self.gua_data['ben_gua']['gua_ci']}")