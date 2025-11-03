# app/parser/admin_index.py

from functools import lru_cache
from typing import Dict, Tuple, Any, List
from .division_loader import load_divisions


# 常见行政区后缀。用户写地址时往往会省略这些后缀，
# 比如 "昌平区" -> "昌平", "高唐县" -> "高唐", "滨江区" -> "滨江"。
_SUFFIXES = [
    "特别行政区",
    "自治区",
    "自治州",
    "地区",
    "盟",
    "新区",
    "省",
    "市",
    "区",
    "县",
    "镇",
    "乡",
    "街道",
    "办事处",
]


def _variants(name: str) -> List[str]:
    """
    给一个正式行政区名生成一组可用于匹配的别名：
    - 原名本身
    - 去掉常见后缀的短名
    我们会把这些别名都放进索引里，后面做子串包含判断。

    这种“正名 + 常用简称/口语称呼”匹配策略
    就是中文地址标准化里常说的模糊匹配 / 地址别名归一化。:contentReference[oaicite:4]{index=4}
    """
    cands = {name}
    for suf in _SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf):
            cands.add(name[: -len(suf)])
    # 倒序按长度排一下，长的优先（更具体）
    return sorted(cands, key=len, reverse=True)


@lru_cache()
def get_indexes() -> Dict[str, Any]:
    """
    构建全局索引并缓存:
    - province_index[alias] = province_name
    - city_index[alias] = (province_name, city_name)
    - district_index[alias] = (province_name, city_name, district_name, district_meta)

    district_meta 就是该区/县在 divisions 里的字典：
    {
      "_pinyin": "BinJiang",
      "postal_code": "310052",
      "center": [120.146505, 30.16245]
    }

    我们会优先用 district_index 去匹配整段地址字符串，
    命中后可立刻反推出市和省（行政层级向上回填）。
    这种“以区县为锚点逐级回填省市”的做法在中文地址归一化研究里是标准手段，
    因为用户往往写的是最具体的区县/镇名称，而不是完整省市全称。:contentReference[oaicite:5]{index=5}
    """
    divisions = load_divisions()

    province_index: Dict[str, str] = {}
    city_index: Dict[str, Tuple[str, str]] = {}
    district_index: Dict[str, Tuple[str, str, str, Dict[str, Any]]] = {}

    for prov_name, prov_obj in divisions.items():
        if not isinstance(prov_obj, dict):
            continue
        if prov_name.startswith("_"):
            continue

        # 省的别名
        for alias in _variants(prov_name):
            province_index[alias] = prov_name

        for city_name, city_obj in prov_obj.items():
            if city_name.startswith("_"):
                continue
            if not isinstance(city_obj, dict):
                continue

            # 市的别名
            for alias in _variants(city_name):
                city_index[alias] = (prov_name, city_name)

            for dist_name, dist_meta in city_obj.items():
                if dist_name.startswith("_"):
                    continue
                if not isinstance(dist_meta, dict):
                    continue

                # 区/县/市辖区 的别名
                for alias in _variants(dist_name):
                    district_index[alias] = (prov_name, city_name, dist_name, dist_meta)

    return {
        "province_index": province_index,
        "city_index": city_index,
        "district_index": district_index,
        "divisions": divisions,
    }
