"""
ui/tarot_view.py — 塔罗牌阵可视化控件（Unicode 符号 + 正逆位标注）
布局风格与奇门遁甲/梅花易数保持一致：仅设 minimumSize，paintEvent 按比例布局
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont

from .common import BG_COLOR


class TarotView(QWidget):
    """三牌阵可视化：过去 / 现在 / 未来，展示牌的符号与正逆位"""

    def __init__(self, drawn_cards: list, parent=None):
        super().__init__(parent)
        self.drawn_cards = drawn_cards
        self.setMinimumSize(400, 260)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()

        if w < 100 or h < 100 or not self.drawn_cards:
            return

        painter.fillRect(self.rect(), QColor(BG_COLOR))

        positions = ["过去", "现在", "未来"]
        n = max(len(self.drawn_cards), 1)

        # 整体布局比例（与 QimenView / MeihuaView 保持一致的风格）
        margin = int(w * 0.05)           # 左右边距 5%
        usable_w = w - 2 * margin
        slot_w = usable_w / n            # 每张牌占等宽 slot
        card_w = slot_w - 12             # 牌宽，留间距
        card_h = int(h * 0.55)           # 牌高 55%
        card_y = int(h * 0.18)           # 牌顶部位置（垂直居中偏上）

        for i, card in enumerate(self.drawn_cards):
            x0 = margin + slot_w * i + 6
            is_rev = card.get("is_reversed", False)
            symbol = card.get("symbol", "?")
            name_cn = card.get("name_cn", "")
            kw = card.get("keywords_r", "") if is_rev else card.get("keywords_u", "")

            # 卡牌背景
            bg = QColor("#1a2a3a" if not is_rev else "#2a1a1a")
            painter.fillRect(QRectF(x0, card_y, card_w, card_h), bg)
            # 卡牌边框
            border = QColor("#ffd479" if not is_rev else "#e06c75")
            painter.setPen(QPen(border, 2))
            painter.drawRect(int(x0 + 1), int(card_y + 1), int(card_w) - 2, int(card_h) - 2)

            # 牌符号（大 emoji）
            painter.setPen(QColor("#e8e8e8"))
            font = QFont("Segoe UI Emoji", 32)
            painter.setFont(font)
            sym_rect = QRectF(x0 + 4, card_y + 6, card_w - 8, int(card_h * 0.24))
            painter.drawText(sym_rect, Qt.AlignCenter, symbol)

            # 牌名（中文）
            painter.setPen(QColor("#ffd479" if not is_rev else "#e06c75"))
            font = QFont("Microsoft YaHei", 13, QFont.Bold)
            painter.setFont(font)
            name_rect = QRectF(x0 + 4, card_y + card_h * 0.26, card_w - 8, int(card_h * 0.08))
            painter.drawText(name_rect, Qt.AlignCenter, name_cn)

            # 正/逆位标注
            label = "逆" if is_rev else "正"
            label_color = "#e06c75" if is_rev else "#98c379"
            painter.setPen(QColor(label_color))
            font = QFont("Microsoft YaHei", 11)
            painter.setFont(font)
            label_rect = QRectF(x0 + 4, card_y + card_h * 0.36, card_w - 8, int(card_h * 0.07))
            painter.drawText(label_rect, Qt.AlignCenter, label)

            # 关键词
            painter.setPen(QColor("#a9b4c0"))
            font = QFont("Microsoft YaHei", 10)
            painter.setFont(font)
            kw_rect = QRectF(x0 + 6, card_y + card_h * 0.45, card_w - 12, int(card_h * 0.35))
            painter.drawText(kw_rect, Qt.AlignLeft | Qt.TextWordWrap, kw)

            # 位置标签（卡牌下方）：优先用抽卡数据里的 position，缺失时按序回退
            pos_name = card.get("position") or (
                positions[i] if i < len(positions) else f"第{i + 1}张")
            pos_y = int(card_y + card_h + 4)
            painter.setPen(QColor("#7fd1ff"))
            font = QFont("Microsoft YaHei", 11, QFont.Bold)
            painter.setFont(font)
            pos_rect = QRectF(x0, pos_y, card_w, 22)
            painter.drawText(pos_rect, Qt.AlignCenter, f"【{pos_name}】")

        # 顶部标题
        painter.setPen(QColor("#7fd1ff"))
        font = QFont("Microsoft YaHei", 14, QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(0, 4, w, 28), Qt.AlignCenter, "塔罗牌 · 三牌阵")
