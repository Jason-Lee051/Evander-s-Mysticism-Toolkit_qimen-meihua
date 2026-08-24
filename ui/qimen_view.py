"""
ui/qimen_view.py - 奇门遁甲九宫格绘制控件（QPainter）
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from .common import (BG_COLOR, LINE_COLOR, LINE_WIDTH,
                     JI_SHEN, XIONG_SHEN, JI_MEN, XIONG_MEN,
                     STAR_COLOR, get_gan_color, GONG_NUMBER_COLOR)

class QimenView(QWidget):
    def __init__(self, pan_result: dict, parent=None):
        super().__init__(parent)
        self.result = pan_result
        self.setMinimumSize(600, 600)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景黑色
        painter.fillRect(self.rect(), QColor(BG_COLOR))

        # 计算格子尺寸
        w = self.width()
        h = self.height()
        side = min(w, h) * 0.9
        cell = side / 3
        start_x = (w - side) / 2
        start_y = (h - side) / 2

        # 绘制金色网格
        pen = QPen(QColor(LINE_COLOR), LINE_WIDTH)
        painter.setPen(pen)
        for i in range(4):
            # 竖线
            painter.drawLine(int(start_x + i * cell), int(start_y),
                             int(start_x + i * cell), int(start_y + side))
            # 横线
            painter.drawLine(int(start_x), int(start_y + i * cell),
                             int(start_x + side), int(start_y + i * cell))

        # 九宫坐标映射 (宫数 -> 列,行)
        # 布局：4 9 2 (上)
        #        3 5 7 (中)
        #        8 1 6 (下)
        grid_pos = {
            4: (0, 2), 9: (1, 2), 2: (2, 2),
            3: (0, 1), 5: (1, 1), 7: (2, 1),
            8: (0, 0), 1: (1, 0), 6: (2, 0)
        }

        # 遍历九宫信息绘制
        for info in self.result.get('pan_info', []):
            gong = info['gong']
            if gong not in grid_pos:
                continue
            c, r = grid_pos[gong]
            x0 = start_x + c * cell
            y0 = start_y + r * cell

            # 中宫只写“中五”
            if gong == 5:
                font = QFont("SimHei", 18)
                painter.setFont(font)
                painter.setPen(QColor("dimgray"))
                painter.drawText(QRectF(x0, y0, cell, cell),
                                 Qt.AlignCenter, "中\n五")
                continue

            # 1. 左上：八神
            shen = info.get('shen', '')
            if shen:
                color = 'lime' if shen in JI_SHEN else ('red' if shen in XIONG_SHEN else 'white')
                painter.setPen(QColor(color))
                font = QFont("SimHei", 11, QFont.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(x0 + 4, y0 + 4, cell/2 - 8, cell/2 - 8),
                                 Qt.AlignLeft | Qt.AlignTop, shen)

            # 2. 右上：九星
            star = info.get('star', '')
            if star:
                painter.setPen(QColor(STAR_COLOR))
                font = QFont("SimHei", 11, QFont.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(x0 + cell/2, y0 + 4, cell/2 - 8, cell/2 - 8),
                                 Qt.AlignRight | Qt.AlignTop, star)

            # 3. 左下：八门
            door = info.get('door', '')
            if door:
                color = 'lime' if door in JI_MEN else ('red' if door in XIONG_MEN else 'white')
                painter.setPen(QColor(color))
                font = QFont("SimHei", 11, QFont.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(x0 + 4, y0 + cell/2, cell/2 - 8, cell/2 - 8),
                                 Qt.AlignLeft | Qt.AlignBottom, door)

            # 4. 右下：天盘干
            tian = info.get('tian_pan', '')
            if tian:
                color = get_gan_color(tian)
                painter.setPen(QColor(color))
                font = QFont("SimHei", 12, QFont.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(x0 + cell/2, y0 + cell/2, cell/2 - 8, cell/2 - 8),
                                 Qt.AlignRight | Qt.AlignBottom, f"天{tian}")

            # 5. 正下方靠中间：地盘干
            di = info.get('di_pan', '')
            if di:
                color = get_gan_color(di)
                painter.setPen(QColor(color))
                font = QFont("SimHei", 11, QFont.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(x0 + cell/4, y0 + cell - 20, cell/2, 18),
                                 Qt.AlignHCenter | Qt.AlignBottom, f"地{di}")

            # 6. 宫号小字（可选）
            painter.setPen(QColor(GONG_NUMBER_COLOR))
            font = QFont("SimHei", 14)
            painter.setFont(font)
            painter.drawText(QRectF(x0 + cell/2 - 10, y0 + cell/2 - 12, 20, 20),
                             Qt.AlignCenter, str(gong))

            # 7. 四害/马星标记（宫号下方小字）
            tags = []
            if info.get('kongwang'):
                tags.append('空')
            if info.get('jixing'):
                tags.append('刑')
            if info.get('rumu'):
                tags.append('墓')
            if info.get('menpo'):
                tags.append('迫')
            if info.get('maxing'):
                tags.append('马')
            if tags:
                painter.setPen(QColor('#ff6b6b'))
                font = QFont("SimHei", 9, QFont.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(x0 + cell/2 - 10, y0 + cell - 40, cell, 16),
                                 Qt.AlignHCenter, "·".join(tags))