import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Tuple


# 常见行政后缀，用来生成简称 / 去冗余
_COMMON_SUFFIXES = [
    "特别行政区",
    "自治区",
    "自治州",
    "地区",
    "盟",
    "省",
    "市",
    "区",
    "县",
    "旗",
    "新区",
    "开发区",
    "高新区",
    "州",
]

_MANUAL_ALIAS_OVERRIDES = [
    {
        "alias": "北京沙河",
        "info": {
            "level": "district",
            "province": "北京市",
            "city": "北京市",
            "district": "昌平区",
            "postal_code": "102200",
            "lat": 40.22066,
            "lng": 116.231204,
        },
    },
]

_MANUAL_POSTAL_OVERRIDES = {
    "102206": {
        "province": "北京市",
        "city": "北京市",
        "district": "昌平区",
        "postal_code": "102206",
        "lat": 40.22066,
        "lng": 116.231204,
    },
}


def _generate_aliases(name: str) -> List[str]:
    """
    根据正式行政区名生成口语简称:
    - '北京市' -> ['北京市', '北京']
    - '昌平区' -> ['昌平区', '昌平']
    - '高唐县' -> ['高唐县', '高唐']

    这个做法类似常用的 cpca: 它会同时识别“杭州市滨江区”和“杭州滨江”并映射回标准省/市/区，
    方便后续清洗 street 部分时把省市区从地址主体里剥掉。:contentReference[oaicite:6]{index=6}
    """
    aliases = {name}
    for suf in sorted(_COMMON_SUFFIXES, key=len, reverse=True):
        if name.endswith(suf) and len(name) > len(suf):
            aliases.add(name[: -len(suf)])
    # 过滤太短（如单字“市”、“区”）
    aliases = {a for a in aliases if len(a) >= 2}
    return list(aliases)


@lru_cache()
def load_divisions_tree() -> Dict[str, Any]:
    """
    divisions_cn.json 结构示例:
    {
      "北京市": {
        "_pinyin": "BeiJing",
        "北京市": {
          "_pinyin": "BeiJing",
          "昌平区": {
            "_pinyin": "ChangPing",
            "postal_code": "102200",
            "center": [116.231204, 40.22066]
          },
          ...
        }
      },
      "山东省": {
        "_pinyin": "ShanDong",
        "聊城市": {
          "_pinyin": "LiaoCheng",
          "高唐县": {
            "_pinyin": "GaoTang",
            "postal_code": "252800",
            "center": [116.230158, 36.846755]
          }
        }
      },
      ...
    }
    """
    data_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "divisions_cn.json"
    )
    data_path = os.path.abspath(data_path)
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_indexes_from_tree(
    tree: Dict[str, Any]
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]]]:
    """
    alias_index:
        口语简称 -> 多个候选行政区 {level, province, city, district, postal_code, lat, lng}

    postal_index:
        邮编 -> {province, city, district, postal_code, lat, lng}

    postal_index 让我们可以像公开邮编库那样：
    - 102206 ↦ 北京市 / 昌平区 / 沙河镇白各庄一带（昌平区辖内，区级常见主邮编 102200，
      但片区精细邮编确实是 102206）:contentReference[oaicite:7]{index=7}
    - 310052 ↦ 浙江省 / 杭州市 / 滨江区 / 长河街道（滨江区的精细派送邮编段，不只是“310000”）:contentReference[oaicite:8]{index=8}
    - 450052 ↦ 河南省 / 郑州市 / 二七区（兴华北街、大学路、嵩山南路 71+ 号等路段实际使用 450052 投递，
      而不是只写 450000）:contentReference[oaicite:9]{index=9}
    """
    alias_index: Dict[str, List[Dict[str, Any]]] = {}
    postal_index: Dict[str, Dict[str, Any]] = {}

    for prov_name, prov_obj in tree.items():
        if not isinstance(prov_obj, dict):
            continue

        prov_aliases = _generate_aliases(prov_name)
        for alias in prov_aliases:
            alias_index.setdefault(alias, []).append(
                {
                    "level": "province",
                    "province": prov_name,
                    "city": None,
                    "district": None,
                    "postal_code": None,
                    "lat": None,
                    "lng": None,
                }
            )

        # city 层
        for city_name, city_obj in prov_obj.items():
            if city_name == "_pinyin":
                continue
            if not isinstance(city_obj, dict):
                continue

            city_aliases = _generate_aliases(city_name)
            for alias in city_aliases:
                alias_index.setdefault(alias, []).append(
                    {
                        "level": "city",
                        "province": prov_name,
                        "city": city_name,
                        "district": None,
                        "postal_code": None,
                        "lat": None,
                        "lng": None,
                    }
                )

            # district 层
            for dist_name, dist_obj in city_obj.items():
                if dist_name == "_pinyin":
                    continue
                if not isinstance(dist_obj, dict):
                    continue

                postal_code = dist_obj.get("postal_code")
                center = dist_obj.get("center", [None, None])
                lng = center[0] if len(center) >= 1 else None
                lat = center[1] if len(center) >= 2 else None

                dist_aliases = _generate_aliases(dist_name)
                for alias in dist_aliases:
                    alias_index.setdefault(alias, []).append(
                        {
                            "level": "district",
                            "province": prov_name,
                            "city": city_name,
                            "district": dist_name,
                            "postal_code": postal_code,
                            "lat": lat,
                            "lng": lng,
                        }
                    )

                if postal_code and postal_code not in postal_index:
                    postal_index[postal_code] = {
                        "province": prov_name,
                        "city": city_name,
                        "district": dist_name,
                        "postal_code": postal_code,
                        "lat": lat,
                        "lng": lng,
                    }

    return alias_index, postal_index


@lru_cache()
def get_indexes() -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]]]:
    tree = load_divisions_tree()
    alias_index, postal_index = _build_indexes_from_tree(tree)

    for override in _MANUAL_ALIAS_OVERRIDES:
        alias = override["alias"]
        info = override["info"]
        alias_index.setdefault(alias, []).append(info)

    for postal_code, info in _MANUAL_POSTAL_OVERRIDES.items():
        postal_index.setdefault(postal_code, info)

    return alias_index, postal_index


def build_aliases_for_names(
    province: str = None,
    city: str = None,
    district: str = None,
) -> List[str]:
    """
    给定识别出来的省/市/区，生成所有可能简称，用来从 street 里剔除冗余地名。
    例如:
      省=浙江省, 市=杭州市, 区=滨江区
    输出里会包含 ["浙江省","浙江","杭州市","杭州","滨江区","滨江"]
    这样 "浙江杭州滨江长河街道..." 会被清洗成 "长河街道..." ，
    同类思路在 cpca 场景下常用于把“省市区”跟“剩余详细地址”分离。:contentReference[oaicite:10]{index=10}
    """
    names = []
    if province:
        names.append(province)
    if city:
        names.append(city)
    if district:
        names.append(district)

    alias_set = set()
    for n in names:
        alias_set.add(n)
        for suf in sorted(_COMMON_SUFFIXES, key=len, reverse=True):
            if n.endswith(suf) and len(n) > len(suf):
                alias_set.add(n[: -len(suf)])

    # 去掉太短的别名
    alias_list = [a for a in alias_set if len(a) >= 2]
    alias_list.sort(key=len, reverse=True)  # 先剔除长的，后剔除短的
    return alias_list
