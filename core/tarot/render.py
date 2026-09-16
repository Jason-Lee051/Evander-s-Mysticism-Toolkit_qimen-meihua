"""
core/tarot/render.py — 将抽卡结果格式化为文本（供显示与 LLM 使用）
"""
from .draw import format_drawn_cards as _fmt_drawn


def format_tarot_result(drawn: list) -> str:
    """
    格式化抽卡结果。
    drawn: draw_three_cards() 返回的列表，每项含 card 数据 + draw_index
    """
    return _fmt_drawn(drawn)


def format_tarot_for_llm(drawn: list, question: str = "", background: str = "") -> str:
    """专门为 LLM 提示词准备的格式化文本"""
    base = format_tarot_result(drawn)
    lines = [
        f"【问卜者信息】",
        f"所问事项：{question}",
        f"背景：{background if background else '无额外信息'}",
        f"",
        f"【牌阵数据】",
        base,
    ]
    return "\n".join(lines)
