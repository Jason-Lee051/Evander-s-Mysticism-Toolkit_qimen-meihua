"""
core/meihua/paipan.py - 排卦：构建本卦、变卦、互卦，计算体用
"""
from typing import Dict, List, Tuple
from .bagua import TRIGRAM_MAP, TRIGRAM_WUXING, get_gua_name, get_gua_ci
import datetime

# 八卦的二进制（阳=1，阴=0，从下往上三位：低三位为下卦，高三位为上卦）
# 乾111, 兑110, 离101, 震100, 巽011, 坎010, 艮001, 坤000
_BIN_MAP = {
    1: [1, 1, 1],
    2: [1, 1, 0],
    3: [1, 0, 1],
    4: [1, 0, 0],
    5: [0, 1, 1],
    6: [0, 1, 0],
    7: [0, 0, 1],
    8: [0, 0, 0],
}

def _bin_to_trigram(bin_list):
    for num, b in _BIN_MAP.items():
        if b == bin_list:
            return num
    return None


def build_full_gua(upper_num: int, lower_num: int, moving_line: int,
                   dt: datetime.datetime = None) -> Dict:
    """
    输入上卦数、下卦数、动爻位置（1-6，从下往上），返回完整卦盘
    返回字典包含本卦、变卦、互卦、体用关系等
    dt: 起卦时间（用于月令卦气旺衰），默认当前时间
    """
    if dt is None:
        dt = datetime.datetime.now()

    # 本卦：上卦、下卦
    upper_info = TRIGRAM_MAP[upper_num]
    lower_info = TRIGRAM_MAP[lower_num]
    ben_gua = {
        "upper": upper_num,
        "upper_name": upper_info["name"],
        "upper_symbol": upper_info["symbol"],
        "upper_wuxing": upper_info["wuxing"],
        "lower": lower_num,
        "lower_name": lower_info["name"],
        "lower_symbol": lower_info["symbol"],
        "lower_wuxing": lower_info["wuxing"],
        "name": get_gua_name(upper_info["name"], lower_info["name"]),
        "moving_line": moving_line,
        "gua_ci": get_gua_ci(get_gua_name(upper_info["name"], lower_info["name"])),
    }

    # 本卦六爻（从下往上）
    ben_lines = _BIN_MAP[lower_num] + _BIN_MAP[upper_num]
    # 变卦六爻：动爻阴阳互变
    bian_lines = ben_lines.copy()
    idx = moving_line - 1  # 转为0索引
    bian_lines[idx] = 1 - bian_lines[idx]  # 取反

    # 分离变卦上下卦
    bian_lower_num = _bin_to_trigram(bian_lines[0:3])
    bian_upper_num = _bin_to_trigram(bian_lines[3:6])
    if bian_lower_num is None or bian_upper_num is None:
        # 容错
        bian_lower_num = lower_num
        bian_upper_num = upper_num

    bian_upper_info = TRIGRAM_MAP[bian_upper_num]
    bian_lower_info = TRIGRAM_MAP[bian_lower_num]
    bian_gua = {
        "upper": bian_upper_num,
        "upper_name": bian_upper_info["name"],
        "lower": bian_lower_num,
        "lower_name": bian_lower_info["name"],
        "name": get_gua_name(bian_upper_info["name"], bian_lower_info["name"]),
        "gua_ci": get_gua_ci(get_gua_name(bian_upper_info["name"], bian_lower_info["name"])),
    }

    # 互卦：本卦 2、3、4 爻为下互，3、4、5 爻为上互（索引1-3、2-4）
    hu_lower_num = _bin_to_trigram(ben_lines[1:4])
    hu_upper_num = _bin_to_trigram(ben_lines[2:5])
    if hu_lower_num is None or hu_upper_num is None:
        # 容错
        hu_lower_num = lower_num
        hu_upper_num = upper_num
    hu_upper_info = TRIGRAM_MAP[hu_upper_num]
    hu_lower_info = TRIGRAM_MAP[hu_lower_num]
    hu_gua = {
        "upper": hu_upper_num,
        "upper_name": hu_upper_info["name"],
        "lower": hu_lower_num,
        "lower_name": hu_lower_info["name"],
        "name": get_gua_name(hu_upper_info["name"], hu_lower_info["name"]),
        "gua_ci": get_gua_ci(get_gua_name(hu_upper_info["name"], hu_lower_info["name"])),
    }

    # 体用：动爻所在之卦为用卦，另一卦为体卦
    # 动爻位置1-3在下卦，4-6在上卦
    if moving_line <= 3:
        ti_num = upper_num
        yong_num = lower_num
    else:
        ti_num = lower_num
        yong_num = upper_num

    ti_info = TRIGRAM_MAP[ti_num]
    yong_info = TRIGRAM_MAP[yong_num]
    ti_wuxing = ti_info["wuxing"]
    yong_wuxing = yong_info["wuxing"]
    # 五行相生: 金生水, 水生木, 木生火, 火生土, 土生金
    wuxing_sheng = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
    # 五行相克: 木克土, 土克水, 水克火, 火克金, 金克木
    wuxing_ke = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

    ti_sheng_yong = (wuxing_sheng.get(ti_wuxing) == yong_wuxing)
    yong_sheng_ti = (wuxing_sheng.get(yong_wuxing) == ti_wuxing)
    ti_ke_yong = (wuxing_ke.get(ti_wuxing) == yong_wuxing)
    yong_ke_ti = (wuxing_ke.get(yong_wuxing) == ti_wuxing)

    relation = ""
    if yong_sheng_ti:
        relation = "用生体（吉）"
    elif ti_sheng_yong:
        relation = "体生用（泄气，凶）"
    elif yong_ke_ti:
        relation = "用克体（凶）"
    elif ti_ke_yong:
        relation = "体克用（吉）"
    else:
        relation = "体用比和（吉）"

    # 月令五行旺衰（以起卦时刻的月建/节气月为准）
    ti_shi, yong_shi = _wuxing_wangshuai(ti_wuxing, yong_wuxing, dt)

    # 互卦、变卦与体卦的生克（互变参断：生体之卦多则吉、克体之卦多则凶）
    ti_sheng = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
    ti_ke = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

    def _relation_with_ti(wx: str) -> str:
        if wx == ti_wuxing:
            return "比和"
        if ti_sheng.get(ti_wuxing) == wx:
            return "体生之（泄体）"
        if ti_sheng.get(wx) == ti_wuxing:
            return "生体（吉）"
        if ti_ke.get(ti_wuxing) == wx:
            return "体克之"
        return "克体（凶）"

    hu_ti_relations = {
        "上互": _relation_with_ti(hu_upper_info["wuxing"]),
        "下互": _relation_with_ti(hu_lower_info["wuxing"]),
    }
    bian_ti_relations = {
        "变上": _relation_with_ti(bian_upper_info["wuxing"]),
        "变下": _relation_with_ti(bian_lower_info["wuxing"]),
    }

    return {
        "ben_gua": ben_gua,
        "bian_gua": bian_gua,
        "hu_gua": hu_gua,
        "ti_num": ti_num,
        "ti_name": ti_info["name"],
        "ti_wuxing": ti_wuxing,
        "yong_num": yong_num,
        "yong_name": yong_info["name"],
        "yong_wuxing": yong_wuxing,
        "relation": relation,
        "ti_shi": ti_shi,
        "yong_shi": yong_shi,
        "month": dt.month,
        "ben_lines": ben_lines,   # 六爻列表0-5
        "bian_lines": bian_lines,
        "hu_ti_relations": hu_ti_relations,
        "bian_ti_relations": bian_ti_relations,
    }


# 月建五行（节气月）：寅卯=木、巳午=火、申酉=金、亥子=水、辰戌丑未=土
_DIZHI_WUXING = {'寅': '木', '卯': '木', '巳': '火', '午': '火',
                 '申': '金', '酉': '金', '亥': '水', '子': '水',
                 '辰': '土', '戌': '土', '丑': '土', '未': '土'}
# 公历月近似月令（降级用）：以月建为主的近似（1月丑土、2月寅木……12月子水）
_MONTH_WUXING_APPROX = {1: '土', 2: '木', 3: '木', 4: '土', 5: '火', 6: '火',
                        7: '土', 8: '金', 9: '金', 10: '土', 11: '水', 12: '水'}
# 五行相生（用于判断得生）
WUXING_SHENG = {'金': '水', '水': '木', '木': '火', '火': '土', '土': '金'}


def _month_wuxing(dt: datetime.datetime) -> str:
    """当前月令五行：优先节气月（月建，lunar_python），缺失时用公历近似"""
    try:
        from lunar_python import Lunar  # type: ignore
        lunar = Lunar.fromDate(dt)
        month_zhi = lunar.getMonthInGanZhiExact()[-1]  # 如 "丁卯" -> 卯
        wx = _DIZHI_WUXING.get(month_zhi)
        if wx:
            return wx
    except Exception:
        pass
    return _MONTH_WUXING_APPROX.get(dt.month, '土')


def _wuxing_wangshuai(ti_wx: str, yong_wx: str, dt: datetime.datetime):
    """依据月令返回 (体卦旺衰说明, 用卦旺衰说明)"""
    owner = _month_wuxing(dt)
    ti = _single_wangshuai(ti_wx, owner)
    yo = _single_wangshuai(yong_wx, owner)
    return f"{ti_wx}卦{ti}", f"{yong_wx}卦{yo}"


def _single_wangshuai(wx: str, owner: str) -> str:
    """
    单五行的旺相休囚死判定（以月令 owner 为基准）：
    旺=当令，相=令生我，休=我生令，囚=我克令，死=令克我
    """
    if wx == owner:
        return "当令（旺）"
    if WUXING_SHENG.get(owner) == wx:   # 月令生我 -> 相
        return "受月令生（相）"
    if WUXING_SHENG.get(wx) == owner:   # 我生月令 -> 休
        return "生月令（休）"
    ke_map = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    if ke_map.get(wx) == owner:         # 我克月令 -> 囚
        return "克月令（囚）"
    return "受月令克（死）"               # 月令克我 -> 死