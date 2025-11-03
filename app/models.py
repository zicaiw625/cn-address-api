from pydantic import BaseModel, Field
from typing import Optional


class ParseRequest(BaseModel):
    raw_address: str = Field(
        ...,
        description="原始整段地址字符串，可能包含省市区/小区/门牌/收件人/手机/邮编全部糊在一起"
    )


class ParseResponse(BaseModel):
    province: Optional[str] = Field(
        None, description="识别/推断出的省级行政区，例如 浙江省 / 北京市"
    )
    city: Optional[str] = Field(
        None, description="识别/推断出的地级市或直辖市名称；北京这种直辖市会复制为 北京市"
    )
    district: Optional[str] = Field(
        None, description="识别/推断出的区/县，例如 滨江区 / 昌平区 / 二七区 / 高唐县"
    )

    street: str = Field(
        ..., description="去掉省市区及其简称后剩下的详细街道、小区、楼栋、单元、门牌等"
    )

    # 用户原始看到的邮编（可能是“更细网格”的真实投递邮编，也可能是错的）
    input_postal: Optional[str] = Field(
        None,
        description="用户原始地址里提取到的邮编（可能跨区/写错，也可能是非常精细的派送邮编）"
    )

    # 我们最终认可/推荐的邮编
    # 逻辑：
    #   1. 如果用户邮编和解析出来的省/市/区是同一片区，我们直接信用户的邮编（更细）。
    #   2. 如果冲突，我们用行政区主邮编兜底并把 postal_mismatch = True。
    postal_code: Optional[str] = Field(
        None,
        description="推荐使用的邮编；若用户邮编与解析省市区一致，则直接使用用户邮编；否则降级为该区/县主邮编"
    )

    # 用户邮编是否和解析出的省/市/区冲突
    postal_mismatch: bool = Field(
        ...,
        description="True = 用户邮编跟解析行政区不匹配（高风险单，需要人工确认）"
    )

    lat: Optional[float] = Field(
        None,
        description="区/县级中心点纬度（从行政区或邮编映射得到）"
    )
    lng: Optional[float] = Field(
        None,
        description="区/县级中心点经度（从行政区或邮编映射得到）"
    )

    recipient: Optional[str] = Field(
        None, description="推测的收件人姓名（通常是末尾2~4个中文人名）"
    )
    phone: Optional[str] = Field(
        None, description="推测的大陆手机号 (1[3-9]XXXXXXXXX)"
    )

    normalized_cn: str = Field(
        ..., description="标准化中文整串地址，适合打印在面单"
    )
    normalized_en: str = Field(
        ..., description="拼音/英文化地址，适合跨境清关、海外仓"
    )

    deliverable: bool = Field(
        ..., description="是否看起来可直接投递（区/县明确 + 有到户门牌/单元/室号 + 有手机号）"
    )
    confidence: float = Field(
        ..., description="0~1置信度，越高越像真实可送达地址"
    )
    needs_detail: bool = Field(
        ..., description="True=缺单元/室/门牌等户级信息，建议在下单时提示用户补充"
    )
