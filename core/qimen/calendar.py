"""
core/qimen/calendar.py - 干支历、节气计算（带缓存）
依赖：datetime, math, ephem（节气优先用 lunar_python，精度更高）
"""

import datetime
import math
import ephem
from collections import OrderedDict

# 天干、地支、六十甲子
TIAN_GAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
DI_ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
JIA_ZI = [TIAN_GAN[i % 10] + DI_ZHI[i % 12] for i in range(60)]

BASE_DATE = datetime.date(2020, 1, 1)
BASE_GANZHI_DAY = 39

# 节气缓存：key=年份, value=OrderedDict
_TERMS_CACHE = {}

# lunar_python 可选依赖（节气/农历精度更高）；缺失时降级用 ephem
try:
    from lunar_python import Lunar, LunarYear  # type: ignore
    _LUNAR_OK = True
except Exception:  # pragma: no cover
    _LUNAR_OK = False

# lunar_python getJieQiTable 返回的键名中，个别节气为拼音（如 DA_XUE）
_JIEQI_PINYIN = {
    'DA_XUE': '大雪', 'DONG_ZHI': '冬至', 'XIAO_HAN': '小寒', 'DA_HAN': '大寒',
    'LI_CHUN': '立春', 'YU_SHUI': '雨水', 'JING_ZHE': '惊蛰',
}

def year_ganzhi(year: int) -> tuple:
    """年份干支（旧历以立春换年，此处用公历年份近似：1984 为甲子）"""
    idx = (year - 1984) % 60
    return idx, JIA_ZI[idx]

def day_ganzhi(date: datetime.date) -> tuple:
    delta = (date - BASE_DATE).days
    idx = (BASE_GANZHI_DAY + delta) % 60
    return idx, JIA_ZI[idx]

def hour_ganzhi(day_gz_idx: int, hour: int) -> tuple:
    di = (hour + 1) // 2 % 12
    day_tg = day_gz_idx % 10
    idx = (day_tg % 5 * 12 + di) % 60
    return idx, JIA_ZI[idx]

def get_solar_terms(year: int) -> OrderedDict:
    """返回当年24个节气的datetime（带缓存）；优先 lunar_python 精确算法"""
    if year in _TERMS_CACHE:
        return _TERMS_CACHE[year]

    if _LUNAR_OK:
        terms = _solar_terms_lunar(year)
    else:
        terms = _solar_terms_ephem(year)

    _TERMS_CACHE[year] = terms
    return terms


def _solar_terms_lunar(year: int) -> OrderedDict:
    """
    基于 lunar_python（寿星天文历）的节气表。
    以农历 year-1 与 year 年的节气表为基底（覆盖公历 year-1-12 ~ year+1-03），
    合并去重后筛出公历 year 年内的 24 个节气，保证当年 1~12 月完整无缺。
    """
    terms = {}
    for y in (year - 1, year):
        try:
            lunar = Lunar.fromDate(datetime.datetime(y, 6, 1, 12, 0))
        except Exception:
            continue
        table = lunar.getJieQiTable() or {}
        for name, solar in table.items():
            name = _JIEQI_PINYIN.get(name, name)
            try:
                dt = datetime.datetime.strptime(solar.toYmdHms(), "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            key = (name, dt.date())
            # 跨年表重叠的同一节气（同名词同日期）保留时间较晚的一条
            if key not in terms or dt > terms[key][1]:
                terms[key] = (name, dt)
    merged = OrderedDict()
    for name, dt in sorted(terms.values(), key=lambda x: x[1]):
        if dt.year == year:  # 只保留公历 year 年内的节气
            merged[name] = dt
    return merged


def _solar_terms_ephem(year: int) -> OrderedDict:
    """ephem 天文库兜底实现（J2000 平黄经，存在约 8 小时岁差偏差，仅作降级）"""

    term_names = [
        "春分", "清明", "谷雨", "立夏", "小满", "芒种",
        "夏至", "小暑", "大暑", "立秋", "处暑", "白露",
        "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
        "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰"
    ]
    angles = [
        0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165,
        180, 195, 210, 225, 240, 255, 270, 285, 300, 315, 330, 345
    ]

    observer = ephem.Observer()
    observer.lon = '120'
    observer.lat = '35'
    observer.elevation = 0
    observer.pressure = 0
    observer.horizon = '0'

    sun = ephem.Sun()
    terms = OrderedDict()

    # 搜索区间：本列表覆盖当年春分(3月)至次年惊蛰(3月初)，
    # 故下界用当年1月1日、上界放宽到次年4月1日，避免次年1~3月的节气
    # （小寒~惊蛰）被 hi=次年1月1日 截断而全部算错。
    lo_base = ephem.Date(f"{year}-01-01")
    hi_base = ephem.Date(f"{year+1}-04-01")

    for name, angle in zip(term_names, angles):
        lo = lo_base
        hi = hi_base
        target = math.radians(angle)
        for _ in range(40):
            mid = ephem.Date((lo + hi) / 2)
            observer.date = mid
            sun.compute(observer)
            ecl = float(ephem.Ecliptic(sun).lon)
            # 黄经为 0~360° 循环值，二分比较前先映射到 target 附近，
            # 消除跨 0°（春分）时的 wrap-around，否则春分会收敛到 1月1日。
            while ecl - target > math.pi:
                ecl -= 2 * math.pi
            while ecl - target < -math.pi:
                ecl += 2 * math.pi
            if ecl < target:
                lo = mid
            else:
                hi = mid
        dt = ephem.Date(lo + 8 * ephem.hour).datetime()
        terms[name] = dt

    return terms

def solar_terms_covering(current_dt: datetime.datetime) -> list:
    """
    返回覆盖 current_dt 的按时间排序的节气列表 [(name, datetime), ...]。
    get_solar_terms(y) 只覆盖当年春分到次年惊蛰，冬季（1-2月）会缺失上一年冬至，
    故合并前一年与当年的节气后再排序去重，修复跨年取不到节气的问题。
    """
    seen = {}
    for y in (current_dt.year - 1, current_dt.year):
        for name, dt in get_solar_terms(y).items():
            # 同一节气名保留时间较晚的一条（关键日期去重）
            seen[(name, dt.date())] = (name, dt)
    items = sorted(seen.values(), key=lambda x: x[1])
    return items

def find_ju_and_dun(current_dt: datetime.datetime, terms: list) -> tuple:
    """
    根据当前时间和节气列表返回 (dun_type, ju, jieqi, yuan)
    current_dt: datetime
    terms: solar_terms_covering() 返回的 [(name, datetime), ...] 时间升序列表
    dun_type: '阳遁' 或 '阴遁'
    ju: 局数 1-9
    jieqi: 节气名
    yuan: '上元'/'中元'/'下元'
    """
    # 节气用局表
    JIE_QI_JU = {
        "冬至": (1, 7, 4), "小寒": (2, 8, 5), "大寒": (3, 9, 6),
        "立春": (8, 5, 2), "雨水": (9, 6, 3), "惊蛰": (1, 7, 4),
        "春分": (3, 9, 6), "清明": (4, 1, 7), "谷雨": (5, 2, 8),
        "立夏": (4, 1, 7), "小满": (5, 2, 8), "芒种": (6, 3, 9),
        "夏至": (9, 3, 6), "小暑": (8, 2, 5), "大暑": (7, 1, 4),
        "立秋": (2, 5, 8), "处暑": (1, 4, 7), "白露": (9, 3, 6),
        "秋分": (7, 1, 4), "寒露": (6, 9, 3), "霜降": (5, 8, 2),
        "立冬": (6, 9, 3), "小雪": (5, 8, 2), "大雪": (4, 7, 1),
    }

    # 查找当前时间所属的节气：取最近一个已到节气（terms 时间升序）
    current_jq = None
    for name, dt in terms:
        if dt <= current_dt:
            current_jq = name
        else:
            break
    if current_jq is None:  # 数据覆盖异常时的兜底
        current_jq = terms[-1][0]

    # 判断阴阳遁
    yang_dun_jq = ["冬至","小寒","大寒","立春","雨水","惊蛰","春分","清明","谷雨","立夏","小满","芒种"]
    dun_type = '阳遁' if current_jq in yang_dun_jq else '阴遁'

    # 三元判断（拆补法：符头定元）
    # 以甲、己日为符头，每 5 日为一元（一元管 60 时辰）：
    #   甲子~戊辰 上元，己巳~癸酉 中元，甲戌~戊寅 下元，己卯~癸未 上元……
    # 即 60 甲子按 5 日一组切分，上中下循环。按日柱所在 5 日组定元。
    # （"按日支子午卯酉定元"仅在符头日成立，非符头日会错，
    #   如乙丑日属甲子上元而非"丑→下元"。）
    day_idx, _ = day_ganzhi(current_dt.date())
    yuan = ('上元', '中元', '下元')[(day_idx // 5) % 3]

    ju_list = JIE_QI_JU[current_jq]
    if yuan == '上元':
        ju = ju_list[0]
    elif yuan == '中元':
        ju = ju_list[1]
    else:
        ju = ju_list[2]

    return dun_type, ju, current_jq, yuan