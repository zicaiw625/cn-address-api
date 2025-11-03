import re
from typing import Optional, Tuple, Dict, Any, List, Set

from pypinyin import lazy_pinyin

from .division_loader import (
    get_indexes,
    build_aliases_for_names,
)
from app.models import ParseResponse

_DIRECT_MUNICIPALITIES = {"北京市", "上海市", "天津市", "重庆市"}

_MOBILE_RE = re.compile(r"(1[3-9]\d{9})")
# Postal code often sticks to Chinese chars, so use digit lookarounds instead of \b
_POSTAL_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_POSTAL_WITH_LABEL_RE = re.compile(
    r"(?:邮编|邮政编码|邮编号码|邮政代号)[:：]?\s*(\d{6})",
    re.IGNORECASE,
)
_NAME_MARKER_RE = re.compile(
    r"(?:收货?人|收件人|联系人|联络人|寄件人|取件人|收)\s*[:：]?\s*([\u4e00-\u9fa5]{2,4})(?:先生|女士|小姐|老师)?\s*$"
)
_NAME_SUFFIX_MARKER_RE = re.compile(
    r"([\u4e00-\u9fa5]{2,4})(?:先生|女士|小姐|老师)?\s*(?:收货?人|收件人|收)\s*$"
)
_TRAILING_NAME_RE = re.compile(
    r"(?:^|[\s,，;；/|])([\u4e00-\u9fa5]{2,4})(?:先生|女士|小姐|老师)?(?=\s*(?:$|1[3-9]\d{7,10}|\d{7,}|$))"
)
_NAME_TOKEN_RE = re.compile(r"^[\u4e00-\u9fa5]{2,4}$")
_DIGIT_TOKEN_RE = re.compile(r"^\d{7,}$")
_ADDRESS_SUFFIXES = (
    "省",
    "市",
    "区",
    "县",
    "旗",
    "州",
    "盟",
    "镇",
    "乡",
    "村",
    "街",
    "街道",
    "路",
    "大道",
    "道",
    "巷",
    "弄",
    "里",
    "号",
    "院",
    "幢",
    "栋",
    "楼",
    "单元",
    "室",
    "庄",
    "湾",
    "山",
    "岭",
    "社区",
    "小区",
    "花园",
    "大厦",
    "中心",
    "广场",
    "市场",
    "商场",
    "公寓",
    "公司",
    "学校",
    "学院",
    "大学",
    "中学",
    "小学",
    "幼儿园",
    "公园",
    "工业园",
    "产业园",
    "科技园",
    "园区",
    "软件园",
    "基地",
    "厂",
    "仓",
    "景区",
)

_BUILDING_LEVEL_RE = re.compile(r"(号楼|幢|栋|楼)")
_UNIT_LEVEL_RE = re.compile(r"(单元|室|(?<!号)号(?!楼))")
_NAME_BLACKLIST = {"邮编", "邮政编码", "邮政代号", "邮编号码"}

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
    labeled = list(_POSTAL_WITH_LABEL_RE.finditer(addr))
    if labeled:
        match = labeled[-1]
        postal_code = match.group(1)
        start, end = match.span()
        addr_wo = (addr[:start] + " " + addr[end:]).strip()
        return addr_wo, postal_code

    matches = list(_POSTAL_RE.finditer(addr))
    if not matches:
        return addr, None
    match = matches[-1]
    postal_code = match.group(1)
    start, end = match.span(1)
    addr_wo = (addr[:start] + " " + addr[end:]).strip()
    return addr_wo, postal_code


def _looks_like_place(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in _ADDRESS_SUFFIXES)


def _extract_name(addr: str) -> Tuple[str, Optional[str]]:
    for pattern in (_NAME_MARKER_RE, _NAME_SUFFIX_MARKER_RE):
        match = pattern.search(addr)
        if match:
            candidate = match.group(1)
            if _looks_like_place(candidate):
                continue
            start, end = match.span()
            cleaned = (addr[:start] + " " + addr[end:]).strip()
            if candidate in _NAME_BLACKLIST:
                return _extract_name(cleaned)
            return cleaned, candidate

    match = _TRAILING_NAME_RE.search(addr)
    if match:
        candidate = match.group(1)
        if not _looks_like_place(candidate):
            start, end = match.span(1)
            cleaned = (addr[:start] + " " + addr[end:]).strip()
            if candidate in _NAME_BLACKLIST:
                return _extract_name(cleaned)
            return cleaned, candidate

    tokens = [t for t in re.split(r"[\s,，;；/|]+", addr) if t]
    if len(tokens) >= 2:
        maybe_tail = tokens[-1]
        maybe_name = tokens[-2]
        if (
            _DIGIT_TOKEN_RE.match(maybe_tail)
            and _NAME_TOKEN_RE.match(maybe_name)
            and not _looks_like_place(maybe_name)
        ):
            idx = addr.rfind(maybe_name)
            if idx != -1:
                cleaned = (addr[:idx] + " " + addr[idx + len(maybe_name):]).strip()
                if maybe_name in _NAME_BLACKLIST:
                    return _extract_name(cleaned)
                return cleaned, maybe_name

    return addr, None


def _is_mainland_province_name(name: Optional[str]) -> bool:
    if not name:
        return False
    return any(name.startswith(p) for p in _MAINLAND_WHITELIST_PREFIX)


def _collect_alias_hits(
    address_core: str,
    alias_index: Dict[str, List[Dict[str, Any]]]
) -> Tuple[List[Dict[str, Any]], Set[str], Set[str]]:
    alias_hits: List[Dict[str, Any]] = []
    provinces_in_addr: Set[str] = set()
    cities_in_addr: Set[str] = set()

    for alias, infos in alias_index.items():
        if not alias or alias not in address_core:
            continue
        for info in infos:
            level = info.get("level")
            alias_hits.append({
                "alias": alias,
                "info": info,
                "level": level,
            })
            if level == "province" and info.get("province"):
                provinces_in_addr.add(info["province"])
            elif level == "city" and info.get("city"):
                cities_in_addr.add(info["city"])

    return alias_hits, provinces_in_addr, cities_in_addr


def _pick_best_hit(
    alias_hits: List[Dict[str, Any]],
    level: str,
    provinces_in_addr: Set[str],
    cities_in_addr: Set[str],
    required_province: Optional[str] = None,
    required_city: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_score: Optional[Tuple[int, int]] = None

    for hit in alias_hits:
        if hit["level"] != level:
            continue

        info = hit["info"]
        province = info.get("province")
        city = info.get("city")

        if required_province and province and province != required_province:
            continue
        if required_city and city and city != required_city:
            continue
        if provinces_in_addr and province and province not in provinces_in_addr:
            continue

        mainland_priority = 1 if _is_mainland_province_name(province) else 0
        city_match = 1
        if cities_in_addr:
            if city and city in cities_in_addr:
                city_match = 1
            else:
                city_match = 0
        score = (
            mainland_priority,
            city_match,
            len(hit["alias"]),
        )

        if (best is None) or (score > (best_score or (-1, -1))):
            best = info
            best_score = score

    return best


def _pick_postal_prefix_candidate(
    candidates: List[Dict[str, Any]],
    province: Optional[str],
    city: Optional[str],
) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_score: Optional[Tuple[int, int, int, int]] = None

    for info in candidates:
        prov = info.get("province")
        city_name = info.get("city")
        district = info.get("district")

        score = (
            1 if province and prov and prov == province else 0,
            1 if city and city_name and city_name == city else 0,
            1 if district else 0,
            1 if _is_mainland_province_name(prov) else 0,
        )

        if (best is None) or (score > (best_score or (-1, -1, -1, -1))):
            best = info
            best_score = score

    return best


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


def _strip_leading_tokens(text: str, tokens: List[str]) -> str:
    """
    Remove known行政区别名，仅当它们位于字符串开头时才剥离，
    避免把“浙江大学”这类合法地名中的“浙江”误删。
    """
    if not text:
        return text
    if not tokens:
        return text

    sorted_tokens = sorted({t for t in tokens if t}, key=len, reverse=True)
    work = text
    stripped = True
    while stripped and work:
        stripped = False
        for token in sorted_tokens:
            if work.startswith(token):
                work = work[len(token):]
                stripped = True
                break
    return work


def parse_address(raw_address: str) -> ParseResponse:
    (
        alias_index,
        postal_index,
        postal_prefix_index,
        province_postal_index,
    ) = get_indexes()

    work_str = raw_address.strip()

    # 1. 手机号
    work_str, phone = _extract_phone(work_str)

    # 2. 用户邮编
    work_str, input_postal = _extract_postal(work_str)
    if input_postal:
        for marker in ("邮编", "邮政编码", "邮政代号", "邮编号码"):
            if marker in work_str:
                work_str = work_str.replace(marker, " ")

    # 3. 收件人
    work_str, recipient = _extract_name(work_str)

    # 4. 去空白
    work_str = _strip_spaces(work_str)

    # 5. 行政区命中（先收集全部别名，再按层级择优）
    alias_hits, provinces_in_addr, cities_in_addr = _collect_alias_hits(
        work_str, alias_index
    )

    province = None
    city = None
    district = None
    lat = None
    lng = None
    admin_postal = None  # 行政区主邮编(区级默认)

    district_hit = _pick_best_hit(
        alias_hits=alias_hits,
        level="district",
        provinces_in_addr=provinces_in_addr,
        cities_in_addr=cities_in_addr,
    )
    if district_hit:
        province = district_hit.get("province") or province
        city = district_hit.get("city") or city
        district = district_hit.get("district") or district
        lat = district_hit.get("lat") or lat
        lng = district_hit.get("lng") or lng
        admin_postal = district_hit.get("postal_code") or admin_postal

    city_hit = _pick_best_hit(
        alias_hits=alias_hits,
        level="city",
        provinces_in_addr=provinces_in_addr,
        cities_in_addr=cities_in_addr,
        required_province=province,
    )
    if city_hit:
        province = city_hit.get("province") or province
        city = city_hit.get("city") or city

    if district is None and city:
        district_from_city = _pick_best_hit(
            alias_hits=alias_hits,
            level="district",
            provinces_in_addr=provinces_in_addr,
            cities_in_addr=cities_in_addr,
            required_province=province,
            required_city=city,
        )
        if district_from_city:
            district = district_from_city.get("district") or district
            lat = lat or district_from_city.get("lat")
            lng = lng or district_from_city.get("lng")
            admin_postal = admin_postal or district_from_city.get("postal_code")

    if province is None:
        province_hit = _pick_best_hit(
            alias_hits=alias_hits,
            level="province",
            provinces_in_addr=provinces_in_addr,
            cities_in_addr=cities_in_addr,
        )
        if province_hit:
            province = province_hit.get("province") or province

    # 6. 邮编反查（不管前面有没有 district，我们都要拿它做 same_area 判断）
    via_postal = _lookup_postal_info(input_postal, postal_index)
    postal_conflict = False
    if via_postal:
        postal_province = via_postal.get("province")
        postal_city = _fix_municipality_city(
            postal_province, via_postal.get("city")
        )
        postal_district = via_postal.get("district")

        conflict = False
        if province and postal_province and province != postal_province:
            conflict = True
        if city and postal_city and city != postal_city:
            conflict = True
        if district and postal_district and district != postal_district:
            conflict = True

        if not conflict:
            province = province or postal_province
            city = city or postal_city
            district = district or postal_district
            lat = lat or via_postal.get("lat")
            lng = lng or via_postal.get("lng")
            admin_postal = admin_postal or via_postal.get("postal_code")
        else:
            postal_conflict = True

    # 6.1 邮编前三位兜底（当邮编不在索引里时，用前三位判断省份是否冲突）
    prefix_info = None
    prefix_candidates: List[Dict[str, Any]] = []
    if input_postal:
        prefix_candidates = postal_prefix_index.get(input_postal[:3], [])
        if prefix_candidates:
            prefix_info = _pick_postal_prefix_candidate(
                prefix_candidates,
                province=province,
                city=city,
            )

            if not any([province, city, district]) and prefix_info:
                province = prefix_info.get("province") or province
                city = prefix_info.get("city") or city
                district = prefix_info.get("district") or district
                lat = lat or prefix_info.get("lat")
                lng = lng or prefix_info.get("lng")
                admin_postal = admin_postal or prefix_info.get("postal_code")
            elif prefix_info:
                conflict = False
                pref_province = prefix_info.get("province")
                pref_city = prefix_info.get("city")
                pref_district = prefix_info.get("district")
                if province and pref_province and province != pref_province:
                    conflict = True
                if city and pref_city and city != pref_city:
                    conflict = True
                if district and pref_district and district != pref_district:
                    conflict = True
                if conflict:
                    postal_conflict = True
                elif not admin_postal:
                    admin_postal = prefix_info.get("postal_code") or admin_postal

            if not postal_conflict and prefix_candidates and prefix_info is None:
                candidate_provinces = {
                    info.get("province")
                    for info in prefix_candidates
                    if info.get("province")
                }
                if province and candidate_provinces and province not in candidate_provinces:
                    postal_conflict = True

    province_postal_entry = province_postal_index.get(province) if province else None
    if province_postal_entry and not admin_postal:
        admin_postal = province_postal_entry.get("postal_code") or admin_postal
        if not lat:
            lat = province_postal_entry.get("lat") or lat
        if not lng:
            lng = province_postal_entry.get("lng") or lng

    # 7. 直辖市修正
    city = _fix_municipality_city(province, city)

    # 8. street 清洗：去掉省/市/区 + 它们的简称
    street_candidate = work_str
    aliases_for_strip = build_aliases_for_names(
        province=province,
        city=city,
        district=district,
    )
    tokens_for_strip = list(filter(None, [province, city, district])) + aliases_for_strip
    street = _strip_leading_tokens(street_candidate, tokens_for_strip).strip()

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
        if postal_conflict:
            if province_postal_entry:
                postal_code_final = province_postal_entry.get("postal_code")
            else:
                postal_code_final = None
            postal_mismatch = True
        else:
            postal_code_final = input_postal
            if province and not _is_mainland_province_name(province):
                postal_mismatch = True
            else:
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
