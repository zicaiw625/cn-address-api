from pydantic import BaseModel, Field
from typing import Optional


class ParseRequest(BaseModel):
    raw_address: str = Field(
        ...,
        description=(
            "Raw free-form address text, may include province/city/district + "
            "street + recipient + phone + postal code / "
            "原始整段地址字符串，可能包含省市区、小区、门牌、收件人、手机、邮编等混合信息"
        ),
    )


class ParseResponse(BaseModel):
    province: Optional[str] = Field(
        None,
        description=(
            "Recognized province-level division (e.g. 浙江省, 北京市) / "
            "识别或推断出的省级行政区"
        ),
    )
    city: Optional[str] = Field(
        None,
        description=(
            "Recognized prefecture-level city or direct-controlled municipality "
            "(e.g. 杭州市, 北京市) / "
            "识别或推断出的地级市或直辖市名称（直辖市复制为 xx市）"
        ),
    )
    district: Optional[str] = Field(
        None,
        description=(
            "Recognized district/county (e.g. 滨江区, 昌平区, 高唐县) / "
            "识别或推断出的区、县"
        ),
    )

    street: str = Field(
        ...,
        description=(
            "Detailed street + building info with province/city/district stripped / "
            "去掉省市区及其简称后剩下的街道、小区、楼栋、单元、门牌等"
        ),
    )

    # 用户原始看到的邮编（可能是“更细网格”的真实投递邮编，也可能是错的）
    input_postal: Optional[str] = Field(
        None,
        description=(
            "Postal code extracted from the user input (may be mismatched or very granular) / "
            "用户原始地址里提取到的邮编（可能跨区或非常精细）"
        ),
    )

    # 我们最终认可/推荐的邮编
    # 逻辑：
    #   1. 如果用户邮编和解析出来的省/市/区是同一片区，我们直接信用户的邮编（更细）。
    #   2. 如果冲突，我们用行政区主邮编兜底并把 postal_mismatch = True。
    postal_code: Optional[str] = Field(
        None,
        description=(
            "Recommended postal code after validation / "
            "推荐使用的邮编：一致则沿用用户邮编，否则回退到区县主邮编"
        ),
    )

    # 用户邮编是否和解析出的省/市/区冲突
    postal_mismatch: bool = Field(
        ...,
        description=(
            "True if the input postal code conflicts with the parsed province/city/district / "
            "True 表示用户邮编与解析出的省市区不匹配，需要人工确认"
        ),
    )

    lat: Optional[float] = Field(
        None,
        description=(
            "Latitude (district/county centroid or postal-code derived) / "
            "区县级中心点纬度（来自行政区或邮编映射）"
        ),
    )
    lng: Optional[float] = Field(
        None,
        description=(
            "Longitude (district/county centroid or postal-code derived) / "
            "区县级中心点经度（来自行政区或邮编映射）"
        ),
    )

    recipient: Optional[str] = Field(
        None,
        description=(
            "Guessed recipient name (typically 2-4 Chinese characters) / "
            "推测的收件人姓名（通常为2~4个中文字符）"
        ),
    )
    phone: Optional[str] = Field(
        None,
        description=(
            "Guessed Mainland China mobile number (1[3-9]XXXXXXXXX) / "
            "推测的大陆手机号 (1[3-9]XXXXXXXXX)"
        ),
    )

    normalized_cn: str = Field(
        ...,
        description=(
            "Normalized Chinese full address suitable for shipping labels / "
            "标准化中文整串地址，适合打印面单"
        ),
    )
    normalized_en: str = Field(
        ...,
        description=(
            "Pinyin/English-style address for customs forms / "
            "拼音或英文化地址，适合跨境清关、海外仓"
        ),
    )

    deliverable: bool = Field(
        ...,
        description=(
            "True if the heuristics consider the address deliverable / "
            "True 表示启发式判断为可投递"
        ),
    )
    confidence: float = Field(
        ...,
        description=(
            "Confidence score from 0-1 / "
            "0~1 置信度，越高越接近真实可送达地址"
        ),
    )
    needs_detail: bool = Field(
        ...,
        description=(
            "True when the parser believes unit/room details are missing / "
            "True 表示缺少单元、室、门牌等户级信息"
        ),
    )


class ErrorResponse(BaseModel):
    error: str = Field(
        ...,
        description="Machine readable error code / 机器可读错误码",
    )
    message: str = Field(
        ...,
        description="Human readable error message / 人类可读错误说明",
    )
    request_id: Optional[str] = Field(
        None,
        description=(
            "Optional correlation identifier for tracing / 可选的调用追踪 ID"
        ),
    )
    details: Optional[dict] = Field(
        None,
        description="Optional structured error payload / 可选的结构化错误详情",
    )
