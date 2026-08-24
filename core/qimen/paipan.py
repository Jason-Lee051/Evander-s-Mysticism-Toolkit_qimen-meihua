"""
core/qimen/paipan.py - 奇门遁甲时家排盘核心算法
依赖：datetime, core.qimen.calendar
"""

import datetime
from typing import Dict, Any
from core.qimen.calendar import (
    day_ganzhi, hour_ganzhi, get_solar_terms, solar_terms_covering, find_ju_and_dun,
    TIAN_GAN, DI_ZHI, JIA_ZI
)

# 九宫顺序
GONG_ORDER = [1, 8, 3, 4, 9, 2, 7, 6]  # 八宫（不含5）
GONG_ORDER_FULL = [1, 8, 3, 4, 5, 9, 2, 7, 6]

# 地盘干顺序
DI_PAN_ORDER = ['戊', '己', '庚', '辛', '壬', '癸', '丁', '丙', '乙']
# 九星名称
STAR_NAMES = ['天蓬', '天芮', '天冲', '天辅', '天禽', '天心', '天柱', '天任', '天英']
# 八门名称
DOOR_NAMES = ['休门', '生门', '伤门', '杜门', '景门', '死门', '惊门', '开门']
# 八神名称
SHEN_NAMES = ['值符', '腾蛇', '太阴', '六合', '白虎', '玄武', '九地', '九天']

# 星、门、神对应旬首的起始
XUN_SHOU_MAP = {
    '甲子': ('天蓬', '休门'),
    '甲戌': ('天芮', '死门'),
    '甲申': ('天冲', '伤门'),
    '甲午': ('天辅', '杜门'),
    '甲辰': ('天禽', '死门'),  # 中五寄坤二，门随死门
    '甲寅': ('天心', '开门'),
}

# 星、门原宫位
STAR_BASE_GONG = {'天蓬':1, '天芮':2, '天冲':3, '天辅':4, '天禽':5, '天心':6, '天柱':7, '天任':8, '天英':9}
DOOR_BASE_GONG = {'休门':1, '死门':2, '伤门':3, '杜门':4, '景门':9, '惊门':7, '开门':6, '生门':8}

# ========== 断局要诀数据 ==========
# 九宫五行
GONG_WUXING = {1: '水', 2: '土', 3: '木', 4: '木', 5: '土', 6: '金', 7: '金', 8: '土', 9: '火'}
# 八门五行
DOOR_WUXING = {'休门': '水', '生门': '土', '伤门': '木', '杜门': '木',
               '景门': '火', '死门': '土', '惊门': '金', '开门': '金'}
# 地支 -> 后天九宫
DIZHI_GONG = {0: 1, 1: 8, 2: 8, 3: 3, 4: 4, 5: 4, 6: 9, 7: 2,
              8: 7, 9: 7, 10: 6, 11: 6}  # 子丑寅卯辰巳午未申酉戌亥

# 六甲旬空亡（时柱旬首）
XUN_KONG = {
    '甲子': ['戌', '亥'],  # 乾宫
    '甲戌': ['申', '酉'],  # 兑宫
    '甲申': ['午', '未'],  # 离/坤宫
    '甲午': ['辰', '巳'],  # 巽宫
    '甲辰': ['寅', '卯'],  # 艮/震宫
    '甲寅': ['子', '丑'],  # 坎/艮宫
}

# 驿马（按局内时支）：申子辰马在寅，寅午戌马在申，巳酉丑马在亥，亥卯未马在巳
MAXING_DIZHI = {
    (0, 3, 6): 2,   # 申子辰 -> 寅(8宫)
    (2, 6, 9): 8,   # 寅午戌 -> 申(7宫)
    (5, 8, 11): 11,  # 巳酉丑 -> 亥(6宫)
    (11, 3, 7): 5,  # 亥卯未 -> 巳(4宫)
}

# 天干入墓（六仪三奇入墓宫）
GAN_MU_GONG = {'乙': 6, '丙': 6, '戊': 6,   # 乾宫（戌）
               '丁': 8, '己': 8, '庚': 8,   # 艮宫（丑）
               '辛': 4, '壬': 4,            # 巽宫（辰）
               '癸': 2}                     # 坤宫（未）

# 六仪击刑（六仪落宫）
GAN_JIXING_GONG = {'戊': 3, '己': 2, '庚': 8, '辛': 9, '壬': 4, '癸': 4}

# 五行相克
WUXING_KE = {'水': '火', '火': '金', '金': '木', '木': '土', '土': '水'}


def _xun_key(hour_gz_idx: int) -> str:
    """返回时柱所属六甲旬首名"""
    for name, idx in [('甲子', 0), ('甲戌', 10), ('甲申', 20), ('甲午', 30), ('甲辰', 40), ('甲寅', 50)]:
        if idx <= hour_gz_idx < idx + 10:
            return name
    return '甲子'


def _maxing(hour_gz_idx: int):
    """返回时支的驿马地支"""
    hour_dz = hour_gz_idx % 12
    for keys, ma in MAXING_DIZHI.items():
        if hour_dz in keys:
            return DI_ZHI[ma]
    return ''


def analyze_harm(pan_info: list, hour_gz_idx: int, gong_wuxing: dict):
    """
    就地给 pan_info 中每一宫标注四害与马星：
      kongwang: 该宫是否为时柱空亡
      jixing  : 该宫天盘干/地盘干是否入击刑
      rumu    : 该宫地盘干是否入墓
      menpo   : 该宫之门是否门迫（门克宫）
      maxing  : 该宫是否为驿马所在
    """
    # 空亡
    xun = _xun_key(hour_gz_idx)
    kong_dizhis = XUN_KONG.get(xun, [])
    kong_gongs = set(DIZHI_GONG[DI_ZHI.index(d)] for d in kong_dizhis)

    # 驿马
    ma_dz = _maxing(hour_gz_idx)
    ma_gong = DIZHI_GONG[DI_ZHI.index(ma_dz)] if ma_dz else None

    for info in pan_info:
        gong = info['gong']
        info['kongwang'] = gong in kong_gongs
        info['maxing'] = (gong == ma_gong)

        # 击刑：看天盘干与地盘干（重点六仪）
        info['jixing'] = any(
            GAN_JIXING_GONG.get(gan) == gong
            for gan in (info.get('tian_pan'), info.get('di_pan')) if gan
        )
        # 入墓：看地盘干（也可看天盘干）
        info['rumu'] = GAN_MU_GONG.get(info.get('di_pan', '')) == gong

        # 门迫：门五行克宫五行
        door = info.get('door', '')
        if door and gong_wuxing.get(gong):
            door_wx = DOOR_WUXING.get(door)
            info['menpo'] = bool(door_wx) and (WUXING_KE.get(door_wx) == gong_wuxing.get(gong))
        else:
            info['menpo'] = False


def pai_pan(current_dt: datetime.datetime, matter: str = "", location: str = "") -> Dict[str, Any]:
    """
    执行奇门遁甲时家排盘，返回结果字典。
    current_dt: 当前时间（本地时间）
    matter, location: 用户输入的事项和位置
    """
    # 1. 节气与用局
    terms = solar_terms_covering(current_dt)
    dun_type, ju, jieqi, yuan = find_ju_and_dun(current_dt, terms)

    # 2. 日柱时柱
    day_gz_idx, day_gz = day_ganzhi(current_dt.date())
    hour = current_dt.hour
    hour_gz_idx, hour_gz = hour_ganzhi(day_gz_idx, hour)
    hour_tg = TIAN_GAN[hour_gz_idx % 10]
    hour_dz = DI_ZHI[hour_gz_idx % 12]

    # 3. 地盘干排布
    di_pan = {}   # {宫数: 天干}
    start_gong = ju  # 戊的起始宫
    # 九宫顺序（阳顺阴逆）
    order = list(range(1, 10))  # 1~9
    if dun_type == '阴遁':
        order = order[::-1]
    start_idx = order.index(start_gong)
    reordered = order[start_idx:] + order[:start_idx]
    for gong, gan in zip(reordered, DI_PAN_ORDER):
        di_pan[gong] = gan

    # 4. 确定旬首、值符星、值使门
    # 找出时柱所在的旬首
    xun_shou_name = None
    for name, idx in [('甲子',0), ('甲戌',10), ('甲申',20), ('甲午',30), ('甲辰',40), ('甲寅',50)]:
        if idx <= hour_gz_idx < idx+10:
            xun_shou_name = name
            break
    zhi_fu_star, zhi_shi_door = XUN_SHOU_MAP[xun_shou_name]

    # 5. 天盘干排布：时干落宫，将旬首对应的六仪加到时干宫
    shi_gan_gong = None
    for g, gan in di_pan.items():
        if gan == hour_tg:
            shi_gan_gong = g
            break
    # 旬首六仪
    xun_shou_gan = {'甲子':'戊','甲戌':'己','甲申':'庚','甲午':'辛','甲辰':'壬','甲寅':'癸'}[xun_shou_name]
    xun_shou_gong = None
    for g, gan in di_pan.items():
        if gan == xun_shou_gan:
            xun_shou_gong = g
            break

    tian_pan = {}
    seq = DI_PAN_ORDER  # 戊己庚辛壬癸丁丙乙
    if dun_type == '阴遁':
        seq = list(reversed(seq))
    xun_idx = seq.index(xun_shou_gan)
    fly_order = list(range(1, 10))  # 1-9
    if dun_type == '阴遁':
        fly_order = fly_order[::-1]
    start_fly_idx = fly_order.index(shi_gan_gong)
    reordered_fly = fly_order[start_fly_idx:] + fly_order[:start_fly_idx]
    reordered_seq = seq[xun_idx:] + seq[:xun_idx]
    for gong, gan in zip(reordered_fly, reordered_seq):
        tian_pan[gong] = gan

    # 6. 九星排布（值符落时干宫，其余星按顺时针填满九宫）
    star_pos = {}
    star_order = STAR_NAMES  # 天蓬1 ... 天英9
    star_idx = star_order.index(zhi_fu_star)
    # 星盘一律顺排（飞宫顺序1-9）
    fly_star = list(range(1, 10))
    start_idx_star = fly_star.index(shi_gan_gong)
    reordered_star_fly = fly_star[start_idx_star:] + fly_star[:start_idx_star]
    reordered_star = star_order[star_idx:] + star_order[:star_idx]
    for gong, star in zip(reordered_star_fly, reordered_star):
        star_pos[gong] = star

    # 7. 八门排布（值使门随时支，阳顺阴逆只布八宫，中5寄坤2）
    door_base_gong = DOOR_BASE_GONG[zhi_shi_door]
    xun_shou_dz = xun_shou_name[1]  # 子/戌/申/午/辰/寅
    xun_dz_idx = DI_ZHI.index(xun_shou_dz)
    hour_dz_idx = DI_ZHI.index(hour_dz)
    offset = (hour_dz_idx - xun_dz_idx) % 12

    # 只使用八宫序列
    gong_seq_for_door = [1, 8, 3, 4, 9, 2, 7, 6]
    if dun_type == '阴遁':
        gong_seq_for_door = gong_seq_for_door[::-1]
    base = 2 if door_base_gong == 5 else door_base_gong  # 中5寄坤2
    idx = gong_seq_for_door.index(base)
    zhi_shi_gong = gong_seq_for_door[(idx + offset) % 8]

    door_pos = {}
    door_order = DOOR_NAMES  # 休生伤杜景死惊开
    start_door_idx = door_order.index(zhi_shi_door)
    ordered_doors = door_order[start_door_idx:] + door_order[:start_door_idx]
    ordered_gongs = gong_seq_for_door[gong_seq_for_door.index(zhi_shi_gong):] + \
                    gong_seq_for_door[:gong_seq_for_door.index(zhi_shi_gong)]
    for gong, door in zip(ordered_gongs, ordered_doors):
        door_pos[gong] = door
    door_pos[5] = door_pos.get(2, '')  # 中宫寄坤2

    # 8. 八神排布（值符落时干宫，阳顺阴逆，只布八宫）
    shen_pos = {}
    zhi_fu_gong_for_shen = shi_gan_gong
    if zhi_fu_gong_for_shen == 5:
        zhi_fu_gong_for_shen = 2  # 中5寄坤2

    shen_order = SHEN_NAMES  # 值符,腾蛇,太阴,六合,白虎,玄武,九地,九天
    if dun_type == '阴遁':
        shen_order = [shen_order[0]] + list(reversed(shen_order[1:]))

    gong_list = [1, 8, 3, 4, 9, 2, 7, 6]
    if dun_type == '阴遁':
        gong_list = list(reversed(gong_list))

    start_idx_shen = gong_list.index(zhi_fu_gong_for_shen)
    ordered_gongs_shen = gong_list[start_idx_shen:] + gong_list[:start_idx_shen]
    for gong, shen in zip(ordered_gongs_shen, shen_order):
        shen_pos[gong] = shen
    shen_pos[5] = ''

    # 组装九宫信息
    pan_info = []
    for gong in GONG_ORDER_FULL:
        info = {
            'gong': gong,
            'di_pan': di_pan.get(gong, ''),
            'tian_pan': tian_pan.get(gong, ''),
            'star': star_pos.get(gong, ''),
            'door': door_pos.get(gong, ''),
            'shen': shen_pos.get(gong, ''),
        }
        pan_info.append(info)

    # 9. 断局要诀：四害（空亡、入墓、门迫、击刑）与马星
    analyze_harm(pan_info, hour_gz_idx, GONG_WUXING)

    return {
        'dun_type': dun_type,
        'ju': ju,
        'jieqi': jieqi,
        'yuan': yuan,
        'day_gz': day_gz,
        'hour_gz': hour_gz,
        'matter': matter,
        'location': location,
        'datetime': current_dt.strftime("%Y-%m-%d %H:%M"),
        'pan_info': pan_info,
        'kongwang_dizhi': XUN_KONG.get(_xun_key(hour_gz_idx), []),
        'maxing_dizhi': _maxing(hour_gz_idx),
        'jixing_gong': [i['gong'] for i in pan_info if i.get('jixing')],
        'rumu_gong': [i['gong'] for i in pan_info if i.get('rumu')],
        'menpo_gong': [i['gong'] for i in pan_info if i.get('menpo')],
        'kongwang_gong': [i['gong'] for i in pan_info if i.get('kongwang')],
        'maxing_gong': [i['gong'] for i in pan_info if i.get('maxing')],
    }