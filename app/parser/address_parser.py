import re
from typing import Optional, Tuple, Dict, Any, List

from pypinyin import lazy_pinyin

from .division_loader import (
    get_indexes,
    build_aliases_for_names,
)
from app.models import ParseResponse

_DIRECT_MUNICIPALITIES = {"北京市", "上海市", "天津市", "重庆市"}

_MOBILE_RE = re.compile(r"(1[3-9]\d{9})")
_POSTAL_RE = re.compile(r"\b(\d{6})\b")
_NAME_RE = re.compile(r"([\u4e00-\u9fa5]{2,4})")

_BUILDING_LEVEL_RE = re.compile(r"(号楼|幢|栋|楼)")
_UNIT_LEVEL_RE = re.compile(r"(单元|室|(?<!号)号(?!楼))")

_MAINLAND_PROVINCE_KEYWORDS = [
    "省", "市", "自治区", "维吾尔自治区", "壮族自治区", "回族自治区", "内蒙古自治区", "特别行政区",
]
_MAINLAND_WHITELIST_PREFIX = [
    "北京", "上海", "天津", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "广西", "海南",
    "四川", "贵州", "云南", "西藏", "陕西", "甘肃",
    "青海", "宁夏", "新疆", "内蒙古",
    # 不含台湾/香港/澳门，避免“云林县 西螺镇”压过“河南 郑州 二七区”
]


def _strip_spaces(s: str) -> str:
    return re.sub(r"\s+", "", s).strip()


def _extract_phone(addr: str) -> Tuple[str, Optional[str]]:
    m = _MOBILE_RE.search(addr)
    if not m:
        return addr, None
    phone = m.group(1)
    addr_wo = addr.replace(phone, " ")
    return addr_wo, phone


def _extract_postal(addr: str) -> Tuple[str, Optional[str]]:
    matches = list(_POSTAL_RE.finditer(addr))
    if not matches:
        return addr, None
    postal_code = matches[-1].group(1)
    addr_wo = addr.replace(postal_code, " ")
    return addr_wo, postal_code


_NAME_PRECEDING_DELIMS = set(" ,，;；。:：/|\\-()[]{}<>")
_NAME_FOLLOWING_DELIMS = _NAME_PRECEDING_DELIMS.union({"#", "+", "&"})


def _is_potential_name_context(addr: str, start: int, end: int) -> bool:
    """Only treat the match as a name when surrounded by explicit separators."""
    if start == 0:
        before_ok = True
    else:
        before_char = addr[start - 1]
        before_ok = before_char.isspace() or before_char in _NAME_PRECEDING_DELIMS

    if end >= len(addr):
        after_ok = True
    else:
        after_char = addr[end]
        after_ok = (
            after_char.isspace()
            or after_char.isdigit()
            or after_char in _NAME_FOLLOWING_DELIMS
        )
    return before_ok and after_ok


def _extract_name(addr: str) -> Tuple[str, Optional[str]]:
    matches = list(_NAME_RE.finditer(addr))
    if not matches:
        return addr, None

    for match in reversed(matches):
        name_guess = match.group(1)
        if name_guess.endswith(("省", "市", "区", "县", "镇", "乡", "村")):
            continue
        start, end = match.span(1)
        if not _is_potential_name_context(addr, start, end):
            continue
        addr_wo = addr[:start] + " " + addr[end:]
        return addr_wo, name_guess

    return addr, None


def _is_mainland_province_name(name: Optional[str]) -> bool:
    if not name:
        return False
    if any(name.startswith(p) for p in _MAINLAND_WHITELIST_PREFIX):
        return True
    if any(k in name for k in _MAINLAND_PROVINCE_KEYWORDS):
        if "澳门" in name or "香港" in name or "台湾" in name:
            return False
        return True
    return False


def _best_alias_hit(address_core: str,
                    alias_index: Dict[str, List[Dict[str, Any]]]
                    ) -> Optional[Dict[str, Any]]:
    """
    优先大陆行政区：
    1. mainland_priority (大陆=1, 其他=0)
    2. 匹配别名长度(越长越好)
    3. 行政级别优先 district > city > province

    这样“河南郑州二七…450052”会解析为
    河南省/郑州市/二七区（区划代码410103，公开邮编常见为450052），
    而不会被台湾云林县西螺镇一类的候选盖掉。:contentReference[oaicite:11]{index=11}
    """
    candidates: List[Tuple[int, int, int, Dict[str, Any]]] = []
    for alias, infos in alias_index.items():
        if alias and alias in address_core:
            for info in infos:
                level_priority = {"district": 3, "city": 2, "province": 1}.get(
                    info["level"], 0
                )
                mainland_priority = 1 if _is_mainland_province_name(
                    info.get("province")
                ) else 0
                candidates.append((
                    mainland_priority,
                    len(alias),
                    level_priority,
                    info,
                ))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return candidates[0][3]


def _lookup_postal_info(postal_code: Optional[str],
                        postal_index: Dict[str, Dict[str, Any]]
                        ) -> Optional[Dict[str, Any]]:
    """
    邮编反查行政区 + 坐标：
    - 102206 -> 北京市 昌平区 沙河/白各庄片区，属于北京市昌平区（区级邮编常见为102200段）。:contentReference[oaicite:12]{index=12}
    - 252800 -> 山东省 聊城市 高唐县，广泛用于高唐县地址。:contentReference[oaicite:13]{index=13}
    - 450052 -> 河南省 郑州市 二七区（区划代码410103，政府驻淮河路街道），这是郑州市核心城区之一的常见邮编段。:contentReference[oaicite:14]{index=14}
    """
    if not postal_code:
        return None
    return postal_index.get(postal_code)


def _fix_municipality_city(province: Optional[str],
                           city: Optional[str]) -> Optional[str]:
    if not province:
        return city
    if province in _DIRECT_MUNICIPALITIES:
        if (city is None) or (city in ["市辖区", "市辖县", "县", "区"]):
            return province
    return city


def _same_admin_area(current_province: Optional[str],
                     current_city: Optional[str],
                     current_district: Optional[str],
                     target: Optional[Dict[str, Any]]) -> bool:
    if not target:
        return False

    tgt_province = target.get("province")
    tgt_city = _fix_municipality_city(tgt_province, target.get("city"))
    tgt_district = target.get("district")

    cur_city = _fix_municipality_city(current_province, current_city)

    province_match = (
        bool(current_province and tgt_province)
        and current_province == tgt_province
    )
    city_match = (
        bool(cur_city and tgt_city)
        and cur_city == tgt_city
    )
    district_match = (
        bool(current_district and tgt_district)
        and current_district == tgt_district
    )

    return province_match and city_match and district_match


def _detail_level(street: str) -> str:
    if _UNIT_LEVEL_RE.search(street):
        return "unit"
    if _BUILDING_LEVEL_RE.search(street):
        return "building"
    return "none"


def _calc_delivery_flags(district: Optional[str],
                         street: str,
                         phone: Optional[str],
                         base_conf: float = 0.6) -> Tuple[bool, float, bool]:
    """
    我们把配送可达性和成本风险捆在一起考虑：
    行业公开资料：失败派送可以占到5%~20%的订单，单次失败会多烧十几美元（客服回拨、重派、仓储、补偿），还会显著打击复购。:contentReference[oaicite:15]{index=15}
    """
    lvl = _detail_level(street)

    confidence = base_conf
    if district:
        confidence += 0.2
    if lvl == "unit":
        confidence += 0.15
    elif lvl == "building":
        confidence += 0.05
    if phone is None:
        confidence -= 0.1
    if confidence < 0:
        confidence = 0.0
    if confidence > 0.99:
        confidence = 0.99

    needs_detail = True
    if lvl == "unit":
        needs_detail = False

    deliverable = bool(
        district and (lvl == "unit") and (phone is not None) and (confidence >= 0.8)
    )

    return deliverable, round(confidence, 2), needs_detail


def _to_pinyin(text: str) -> str:
    if not text:
        return ""
    return " ".join(lazy_pinyin(text))


def _build_normalized_cn(province: Optional[str],
                         city: Optional[str],
                         district: Optional[str],
                         street: str) -> str:
    parts = []
    if province:
        parts.append(province)
    if city and city != province:
        parts.append(city)
    if district:
        parts.append(district)
    if street:
        parts.append(street)
    return "".join(parts) if parts else street


def _build_normalized_en(street: str,
                         district: Optional[str],
                         city: Optional[str],
                         province: Optional[str],
                         final_postal: Optional[str]) -> str:
    parts = []
    if street:
        parts.append(_to_pinyin(street))
    if district:
        parts.append(_to_pinyin(district))
    if city and (city != province):
        parts.append(_to_pinyin(city))
    if province:
        parts.append(_to_pinyin(province))
    if final_postal:
        parts.append(final_postal)
    parts.append("China")
    return " , ".join([p for p in parts if p])


def parse_address(raw_address: str) -> ParseResponse:
    alias_index, postal_index = get_indexes()

    work_str = raw_address.strip()

    # 1. 手机号
    work_str, phone = _extract_phone(work_str)

    # 2. 用户邮编
    work_str, input_postal = _extract_postal(work_str)

    # 3. 收件人
    work_str, recipient = _extract_name(work_str)

    # 4. 去空白
    work_str = _strip_spaces(work_str)

    # 5. 行政区命中（别名匹配，带大陆优先）
    hit = _best_alias_hit(work_str, alias_index)
    province = None
    city = None
    district = None
    lat = None
    lng = None
    admin_postal = None  # 行政区主邮编(区级默认)

    if hit:
        province = hit.get("province") or province
        city = hit.get("city") or city
        district = hit.get("district") or district
        lat = hit.get("lat") or lat
        lng = hit.get("lng") or lng
        admin_postal = hit.get("postal_code") or admin_postal

    # 6. 邮编反查（不管前面有没有 district，我们都要拿它做 same_area 判断）
    via_postal = _lookup_postal_info(input_postal, postal_index)
    if via_postal:
        if district is None:
            # 如果我们还没识别到区县，用邮编兜底
            province = province or via_postal.get("province")
            city = city or via_postal.get("city")
            district = district or via_postal.get("district")
            lat = lat or via_postal.get("lat")
            lng = lng or via_postal.get("lng")
            admin_postal = admin_postal or via_postal.get("postal_code")
        elif not _same_admin_area(province, city, district, via_postal):
            # 如果别名命中了其他同名区域，但邮编指向更精确的行政区，则以邮编为准
            province = via_postal.get("province") or province
            city = via_postal.get("city") or city
            district = via_postal.get("district") or district
            lat = via_postal.get("lat") or lat
            lng = via_postal.get("lng") or lng
            admin_postal = via_postal.get("postal_code") or admin_postal

    # 7. 直辖市修正
    city = _fix_municipality_city(province, city)

    # 8. street 清洗：去掉省/市/区 + 它们的简称
    street_candidate = work_str
    for token in [province, city, district]:
        if token and token in street_candidate:
            street_candidate = street_candidate.replace(token, "")
    aliases_for_strip = build_aliases_for_names(
        province=province,
        city=city,
        district=district,
    )
    for alias in aliases_for_strip:
        if alias and alias in street_candidate:
            street_candidate = street_candidate.replace(alias, "")
    street = street_candidate.strip()

    # 9. 邮编决策（在 divisions_cn.json 没细分邮编的情况下，尽量别误报 mismatch）
    #
    # 我们有：
    #   admin_postal    -> 区/县主邮编（比如 310000 / 102200 / 450000 / 252800）
    #   input_postal    -> 用户提供的邮编（可能是 310052 / 102206 / 450052 这种街道级真实邮编）
    #   via_postal      -> 如果 postal_index 里正好有 input_postal 则能反查到行政区
    #
    # 我们要判断 same_area：
    #   1. 如果 via_postal 存在，且它的 province/city/district == 我们识别的 province/city/district
    #      -> same_area = True
    #   2. 否则，如果 admin_postal 和 input_postal 都存在，且它们前三位(市级邮区)一致
    #      -> same_area = True
    #
    # 依据公开资料，中国邮政编码前两位标识省（含直辖市），前三位一般标识地级市/邮区。
    # 杭州：310000 vs 310052 都以 "310" 开头，对应杭州市滨江区等地段。:contentReference[oaicite:11]{index=11}
    # 北京昌平：102200 vs 102206 都以 "102" 开头，都是北京昌平片区的投递段。:contentReference[oaicite:12]{index=12}
    # 郑州二七：450000 vs 450052/450063 都以 "450" 开头，都是郑州市二七区/主城区各街道使用。:contentReference[oaicite:13]{index=13}
    #
    # 这样即使 divisions_cn.json 没细分邮编，我们也不会误把真实邮编当错的。

    def _same_city_family(p1: Optional[str], p2: Optional[str]) -> bool:
        if not p1 or not p2:
            return False
        # 需要至少3位才比较
        if len(p1) < 3 or len(p2) < 3:
            return False
        return p1[:3] == p2[:3]

    same_area = False
    if via_postal:
        via_city_fixed = _fix_municipality_city(
            via_postal.get("province"), via_postal.get("city")
        )
        same_area = (
            via_postal.get("province") == province
            and via_city_fixed == city
            and via_postal.get("district") == district
        )

    # 如果还没判同区，但 admin_postal 跟 input_postal 的前三位一致，
    # 我们也认为是【同一个地级市 / 邮区】，这在中国大陆的寄递流程里
    # 通常视为“同城/同区段的细分投递网点”，应算安全，不该裁为 mismatch。
    if (not same_area) and admin_postal and input_postal:
        if _same_city_family(admin_postal, input_postal):
            same_area = True

    if input_postal and same_area:
        # 用户邮编匹配我们识别的区域或至少同邮区前缀
        postal_code_final = input_postal
        postal_mismatch = False
    elif admin_postal and not same_area and input_postal:
        # 用户邮编看起来不是同区同邮区 → 高风险
        postal_code_final = admin_postal
        postal_mismatch = True
    elif admin_postal and not input_postal:
        postal_code_final = admin_postal
        postal_mismatch = False
    elif input_postal and not admin_postal:
        postal_code_final = input_postal
        postal_mismatch = False
    else:
        postal_code_final = None
        postal_mismatch = False


    # 10. 可投递性/置信度/是否缺细节
    deliverable, confidence, needs_detail = _calc_delivery_flags(
        district=district,
        street=street,
        phone=phone,
        base_conf=0.6,
    )

    # 11. 规范化地址
    normalized_cn = _build_normalized_cn(
        province=province,
        city=city,
        district=district,
        street=street,
    )
    normalized_en = _build_normalized_en(
        street=street,
        district=district,
        city=city,
        province=province,
        final_postal=postal_code_final,
    )

    return ParseResponse(
        province=province,
        city=city,
        district=district,
        street=street,
        input_postal=input_postal,
        postal_code=postal_code_final,
        postal_mismatch=postal_mismatch,
        lat=lat,
        lng=lng,
        recipient=recipient,
        phone=phone,
        normalized_cn=normalized_cn,
        normalized_en=normalized_en,
        deliverable=deliverable,
        confidence=confidence,
        needs_detail=needs_detail,
    )
