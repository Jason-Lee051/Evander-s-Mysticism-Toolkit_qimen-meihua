"""
core/meihua/render.py - 将卦盘数据格式化为文本（用于显示和LLM）
"""
from .bagua import TRIGRAM_SYMBOLS

def format_meihua_result(gua_data: dict) -> str:
    """格式化卦盘为易读文本"""
    lines = []
    ben = gua_data["ben_gua"]
    bian = gua_data["bian_gua"]
    hu = gua_data["hu_gua"]

    lines.append(f"本卦：{ben['name']}（上{ben['upper_name']}下{ben['lower_name']}）")
    if ben.get("gua_ci"):
        lines.append(f"本卦卦辞：{ben['gua_ci']}")
    lines.append(f"变卦：{bian['name']}（上{bian['upper_name']}下{bian['lower_name']}）")
    if bian.get("gua_ci"):
        lines.append(f"变卦卦辞：{bian['gua_ci']}")
    lines.append(f"互卦：{hu['name']}（上{hu['upper_name']}下{hu['lower_name']}）")
    lines.append(f"动爻：第{ben['moving_line']}爻")
    lines.append(f"体卦：{gua_data['ti_name']}（{gua_data['ti_wuxing']}）")
    lines.append(f"用卦：{gua_data['yong_name']}（{gua_data['yong_wuxing']}）")
    lines.append(f"体用关系：{gua_data['relation']}")
    if gua_data.get("ti_shi"):
        lines.append(f"卦气旺衰（月令）：体{gua_data['ti_shi']}，用{gua_data['yong_shi']}")

    # 互变参断：互卦/变卦与体卦的生克
    hu_rel = gua_data.get("hu_ti_relations") or {}
    bian_rel = gua_data.get("bian_ti_relations") or {}
    if hu_rel or bian_rel:
        parts = []
        for k, v in hu_rel.items():
            parts.append(f"{k}{v}")
        for k, v in bian_rel.items():
            parts.append(f"{k}{v}")
        lines.append(f"互变与体卦生克：" + "，".join(parts))

    # 显示六爻
    lines.append("\n六爻（从下往上）:")
    for i, val in enumerate(gua_data["ben_lines"]):
        yao = "⚊" if val == 1 else "⚋"
        yao_type = "阳" if val == 1 else "阴"
        moving = " *" if (i+1) == ben["moving_line"] else ""
        lines.append(f"  第{i+1}爻：{yao} {yao_type}{moving}")

    return "\n".join(lines)

def format_meihua_for_llm(gua_data: dict, question: str = "") -> str:
    """专门为LLM提示词准备的格式化文本"""
    base = format_meihua_result(gua_data)
    if question:
        return f"所问事项：{question}\n\n{base}"
    return base