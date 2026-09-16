"""
core/tarot/draw.py — 洗牌与抽卡逻辑

采用 Fisher-Yates 算法洗牌，随机源为 SystemRandom（os.urandom，密码学强度），
保证同一时刻连续抽牌也不会重复；每张牌 50% 概率正位、50% 概率逆位；
三牌阵从 78 张全牌库中抽取且互不重复。
"""
import random
from typing import List, Dict, Any

from .cards import build_all_cards

# 真随机源：普通 random 的梅森旋转对占卜场景已足够，但 SystemRandom（os.urandom）
# 更符合"抽牌"语义，且开销可忽略（仅 78 次调用）。
_RNG = random.SystemRandom()

# 三牌阵位置及其含义（供展示与 AI 解读使用）
SPREAD_POSITIONS = [
    ("过去", "事情的起因、根源与已形成的影响"),
    ("现在", "当前处境、核心矛盾与自身状态"),
    ("未来", "发展趋势、可能结果与提示"),
]


def shuffle_deck() -> List[Dict[str, Any]]:
    """
    洗牌：使用 Fisher-Yates 算法随机排列 78 张牌。
    每张牌额外标记 is_reversed（True = 逆位）。
    """
    deck = build_all_cards()
    # Fisher-Yates 洗牌
    n = len(deck)
    for i in range(n - 1, 0, -1):
        j = _RNG.randint(0, i)
        deck[i], deck[j] = deck[j], deck[i]
    # 随机正逆位（50/50）
    for card in deck:
        card["is_reversed"] = _RNG.random() < 0.5
    return deck


def draw_three_cards() -> List[Dict[str, Any]]:
    """
    抽出三张牌（用于三牌阵：过去 / 现在 / 未来），互不重复。
    返回有序列表，每张含 draw_index（0=过去, 1=现在, 2=未来）与位置说明。
    """
    deck = shuffle_deck()
    drawn = []
    for i in range(3):
        card = deck.pop(0)
        card["draw_index"] = i  # 0=过去, 1=现在, 2=未来
        card["position"] = SPREAD_POSITIONS[i][0]
        card["position_meaning"] = SPREAD_POSITIONS[i][1]
        drawn.append(card)
    return drawn


def format_drawn_cards(drawn: List[Dict]) -> str:
    """格式化抽卡结果，供渲染与 AI 提示词使用"""
    lines = []
    lines.append("**三牌阵抽牌结果**（韦特系 78 张全牌库随机抽取）")
    lines.append("")
    for card in drawn:
        idx = card.get("draw_index", 0)
        if card.get("position"):
            pos = card["position"]
        elif 0 <= idx < len(SPREAD_POSITIONS):
            pos = SPREAD_POSITIONS[idx][0]
        else:
            pos = f"第{idx + 1}张"
        pos_meaning = card.get("position_meaning", "")
        ori = "逆位" if card.get("is_reversed") else "正位"
        kw = card.get("keywords_r") if card.get("is_reversed") else card.get("keywords_u")
        meaning = card.get("meaning_r") if card.get("is_reversed") else card.get("meaning_u")
        head = f"- **{card.get('symbol', '')} {card.get('name_cn', '')}（{ori}）** — 位置：{pos}"
        if pos_meaning:
            head += f"（{pos_meaning}）"
        lines.append(head)
        lines.append(f"  关键词：{kw}")
        lines.append(f"  含义：{meaning}")
        if card.get("is_major"):
            lines.append("  备注：大阿卡纳，多指关键的命运课题或重要阶段")
    return "\n".join(lines)
