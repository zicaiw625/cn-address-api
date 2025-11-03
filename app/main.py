import os
from typing import Optional

from fastapi import FastAPI, Depends, Header, HTTPException, status

from app.models import ParseRequest, ParseResponse
from app.parser.address_parser import parse_address

# 多个 key 用逗号分隔:
# export API_KEYS="test123,anotherKey987"
ALLOWED_API_KEYS = {
    key.strip()
    for key in os.getenv("API_KEYS", "").split(",")
    if key.strip()
}


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    最小可商用 API Key 校验：
    - 本地开发：如果没设 API_KEYS，就放行
    - 线上：必须带上在 API_KEYS 里的 key，否则 401

    这种“Header 里放 key -> FastAPI 依赖里验证 -> 未授权直接 401”的模式，
    就是很多 API 市场和物流SaaS的常规做法，用来按 key 计费、限流、统计使用量。:contentReference[oaicite:8]{index=8}
    """
    if not ALLOWED_API_KEYS:
        return
    if (x_api_key is None) or (x_api_key not in ALLOWED_API_KEYS):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key. Send header 'X-API-Key'.",
        )
    return x_api_key


app = FastAPI(
    title="CN Address Deliverability API",
    description=(
        "实时清洗中文地址，输出：\n"
        "- 省/市/区标准化 (支持口语简称如“北京昌平沙河…”，“山东高唐…”)；\n"
        "- 干净 street (剥掉省/市/区及别名，只留街道/小区/楼栋/单元/门牌)；\n"
        "- 收件人 / 手机号；\n"
        "- 经纬度(区县中心点)；\n"
        "- input_postal vs postal_code + postal_mismatch(跨区域高风险单自动打红灯)；\n"
        "- deliverable / needs_detail / confidence；\n"
        "- normalized_cn / normalized_en (跨境面单用)。\n\n"
        "电商&仓配买这个不是为了好玩，而是为了省钱：行业公开数据提到，"
        "一次失败派送平均可能要多烧 ~$17 的人力和补偿成本，"
        "而且首次派送失败会严重伤害复购（很多顾客经历一次烂派送就不回来了）。"
        "把高风险地址在下单时拦下来，就能直接降这笔冤枉钱。:contentReference[oaicite:9]{index=9}"
    ),
    version="0.6.0",
)


@app.get("/health")
def healthcheck():
    return {"ok": True}


@app.post(
    "/parse",
    response_model=ParseResponse,
    dependencies=[Depends(verify_api_key)],
)
def parse_endpoint(req: ParseRequest) -> ParseResponse:
    return parse_address(req.raw_address)
