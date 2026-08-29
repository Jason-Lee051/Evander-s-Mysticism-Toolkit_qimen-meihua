"""
core/meihua/qigua.py - 起卦方法（数字、时间、汉字等）

说明：时间起卦传统需用农历（年支+农历月日+时支）。这里优先使用
lunar_python 库（pip install lunar_python）以获得准确农历；若未安装则降级
为近似算法（年支依公历年份换算、月日用公历），保证程序仍可运行。
"""
import datetime
from typing import Tuple

from .bagua import TRIGRAM_MAP

# 十二地支序数（子1...亥12）
DI_ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

# lunar_python 仅提供农历换算（Lunar）。农历与笔画分开检测：
# 农历可用即启用精确时间起卦；笔画法依赖 strokes 库。
_LUNAR_OK = False
_LUNAR_ERR = None
try:
    from lunar_python import Lunar  # type: ignore
    _LUNAR_OK = True
except Exception as _e:  # 未安装 lunar_python 时降级
    _LUNAR_ERR = _e
    Lunar = None

# 汉字笔画（可选）：lunar_python 无笔画能力，改用 strokes 库（基于 Unihan 数据）
_CHAR_OK = False
try:
    from strokes.strokes import strokes as _strokes_count  # type: ignore
    _CHAR_OK = True
except Exception:
    _strokes_count = None


def qigua_by_number(num1: int, num2: int, num3: int) -> Tuple[int, int, int]:
    """
    数字起卦：三个数字分别对应上卦数、下卦数、动爻数
    规则：上卦 = num1 % 8（余0为8），下卦 = num2 % 8，动爻 = num3 % 6（余0为6）
    返回 (上卦数, 下卦数, 动爻位置1-6)
    """
    upper = num1 % 8
    if upper == 0:
        upper = 8
    lower = num2 % 8
    if lower == 0:
        lower = 8
    moving = num3 % 6
    if moving == 0:
        moving = 6
    return upper, lower, moving


def _hour_zhi(hour: int) -> int:
    """将小时转换为时辰地支序数（子时23-1为1，丑时1-3为2 ... 亥时21-23为12）"""
    return (hour + 1) // 2 % 12 + 1


def _mod8(n: int) -> int:
    return n % 8 if n % 8 != 0 else 8


def _mod6(n: int) -> int:
    return n % 6 if n % 6 != 0 else 6


def qigua_by_time(dt: datetime.datetime) -> Tuple[int, int, int]:
    """
    时间起卦：上卦=(年支+月+日)%8，下卦=(年支+月+日+时支)%8，
    动爻=(年支+月+日+时支)%6。
    传统取年支序数、农历月日；末安装 lunar_python 时降级用公历。
    """
    hour_zhi = _hour_zhi(dt.hour)

    if _LUNAR_OK:
        # Lunar.fromDate 需要完整 datetime（含时分秒），不能只传 date
        lunar = Lunar.fromDate(dt)
        year_gz = lunar.getYearInGanZhiExact()      # 如 "甲辰"
        year_zhi = DI_ZHI.index(year_gz[-1]) + 1     # 年支序数
        month = abs(lunar.getMonth())                # 农历月（闰月取绝对值）
        day = lunar.getDay()                          # 农历日
    else:
        # 降级：年支序数按公历年份近似（1900 庚子=子=1）
        year_zhi = (dt.year - 1900) % 12 + 1
        month = dt.month
        day = dt.day

    upper_num = _mod8(year_zhi + month + day)
    lower_num = _mod8(year_zhi + month + day + hour_zhi)
    moving = _mod6(year_zhi + month + day + hour_zhi)
    return upper_num, lower_num, moving


# ---- 汉字笔画工具（依赖 strokes 库，缺失时优雅降级） ----
def _char_stroke(ch: str) -> int:
    if not _CHAR_OK:
        raise NotImplementedError(_stroke_missing_msg())
    return _strokes_count(ch)


def _stroke_missing_msg() -> str:
    return "汉字笔画起卦需要 strokes 库，请先运行：pip install strokes"


def _stroke_count(text: str) -> int:
    return sum(_char_stroke(c) for c in text if c.strip())


def _split_halves(seq):
    """把序列尽量平均分成前、后两份（前多后少）"""
    half = len(seq) // 2
    if len(seq) % 2 == 1:
        half = len(seq) // 2 + 1
    return seq[:half], seq[half:]


def qigua_by_characters(text: str, mode: str = "word") -> Tuple[int, int, int]:
    """
    汉字起卦（测字）：
      mode='word'  ：按字数法。多字按前后各半取上下卦，总字数取动爻。
      mode='stroke'：按笔画数法。前段总笔画为上卦，后段总笔画为下卦，
                     总笔画数取动爻。（需要 strokes 库提供笔画数）
    """
    text = text.strip()
    if not text:
        raise ValueError("请输入汉字")

    if mode == "word":
        upper_part, lower_part = _split_halves(text)
        upper = _mod8(len(upper_part))
        lower = _mod8(len(lower_part)) if lower_part else upper
        moving = _mod6(len(text))
        return upper, lower, moving

    elif mode == "stroke":
        upper_part, lower_part = _split_halves(text)
        upper = _mod8(sum(_char_stroke(c) for c in upper_part if c.strip()))
        lower = _mod8(sum(_char_stroke(c) for c in lower_part if c.strip())) if lower_part else upper
        moving = _mod6(sum(_char_stroke(c) for c in text if c.strip()))
        return upper, lower, moving

    raise ValueError(f"未知起卦模式：{mode}")