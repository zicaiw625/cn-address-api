import logging
import os
from typing import Optional

from fastapi import FastAPI, Depends, Header, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.models import ErrorResponse, ParseRequest, ParseResponse
from app.parser.address_parser import parse_address

# 多个 key 用逗号分隔:
# export API_KEYS="test123,anotherKey987"
ALLOWED_API_KEYS = {
    key.strip()
    for key in os.getenv("API_KEYS", "").split(",")
    if key.strip()
}
RAPIDAPI_PROXY_SECRETS = {
    key.strip()
    for key in os.getenv("RAPIDAPI_PROXY_SECRET", "").split(",")
    if key.strip()
}
_TRUTHY = {"1", "true", "yes", "on"}
ALLOW_KEYLESS_ACCESS = (
    os.getenv("ALLOW_KEYLESS_ACCESS", "true").lower() in _TRUTHY
)


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        *,
        request_id: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.request_id = request_id
        self.details = details


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_rapidapi_proxy_secret: Optional[str] = Header(
        None, alias="X-RapidAPI-Proxy-Secret"
    ),
    x_rapidapi_user: Optional[str] = Header(
        None, alias="X-RapidAPI-User"
    ),
    x_rapidapi_subscription: Optional[str] = Header(
        None, alias="X-RapidAPI-Subscription"
    ),
):
    """
    Minimal API key validation that works for both direct calls and RapidAPI:
    - Direct clients: send `X-API-Key`, must exist in API_KEYS env var.
    - RapidAPI proxy: Rapid adds `X-RapidAPI-Proxy-Secret`; validate against RAPIDAPI_PROXY_SECRET.
    - Local dev: set ALLOW_KEYLESS_ACCESS=true to skip auth while hacking.

    最小可商用的 API Key 验证流程，既兼容直连也兼容 RapidAPI 代理：
    - 直连：客户端发送 `X-API-Key`，需要出现在 API_KEYS 环境变量里。
    - RapidAPI：Rapid 平台自动加 `X-RapidAPI-Proxy-Secret`，用 RAPIDAPI_PROXY_SECRET 校验。
    - 本地调试：设置 ALLOW_KEYLESS_ACCESS=true 后可跳过鉴权。
    """
    if not ALLOWED_API_KEYS and not RAPIDAPI_PROXY_SECRETS:
        if ALLOW_KEYLESS_ACCESS:
            return
        raise APIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="auth_not_configured",
            message=(
                "Authentication is not configured. Set API_KEYS or "
                "RAPIDAPI_PROXY_SECRET environment variables, or explicitly "
                "opt-in to keyless access with ALLOW_KEYLESS_ACCESS=true."
            ),
        )

    if x_api_key is not None and x_api_key in ALLOWED_API_KEYS:
        return {
            "source": "direct",
            "token": x_api_key,
        }

    if (
        x_rapidapi_proxy_secret is not None
        and x_rapidapi_proxy_secret in RAPIDAPI_PROXY_SECRETS
    ):
        return {
            "source": "rapidapi",
            "token": x_rapidapi_proxy_secret,
            "rapidapi_user": x_rapidapi_user,
            "rapidapi_subscription": x_rapidapi_subscription,
        }

    if not ALLOWED_API_KEYS and ALLOW_KEYLESS_ACCESS:
        return

    raise APIError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        error="unauthorized",
        message=(
            "Invalid or missing API credentials. Send header 'X-API-Key' or "
            "the RapidAPI-managed 'X-RapidAPI-Proxy-Secret'."
        ),
    )


app = FastAPI(
    title="CN Address Deliverability API",
    description=(
        "Clean messy Chinese shipping addresses and return normalized province/"
        "city/district, street-level details, contact info, postal validation, "
        "geo centroids, and deliverability heuristics.\n"
        "- Normalize province/city/district even with shorthand tokens.\n"
        "- Extract street/building/unit while stripping higher-level divisions.\n"
        "- Parse recipient, phone, latitude/longitude, postal code sanity checks.\n"
        "- Provide normalized Chinese + English strings and confidence flags.\n\n"
        "实时清洗中文地址，输出标准化的省/市/区、街道门牌、收件人、手机号、"
        "邮编校验、经纬度和可投递评分。\n"
        "- 支持口语简称自动匹配标准省市区。\n"
        "- 去掉上级行政区，仅保留街道/小区/楼栋/单元等详细信息。\n"
        "- 抽取收件人、手机号、经纬度、邮编一致性。\n"
        "- 返回 normalized_cn / normalized_en 以及 deliverable / confidence 标记。"
    ),
    version="0.6.0",
)


@app.exception_handler(APIError)
async def handle_api_error(_, exc: APIError):
    payload = ErrorResponse(
        error=exc.error,
        message=exc.message,
        request_id=exc.request_id,
        details=exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(payload),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_, exc: RequestValidationError):
    payload = ErrorResponse(
        error="validation_error",
        message="Request body failed validation",
        details={"errors": exc.errors()},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(payload),
    )


logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def handle_unexpected_error(_, exc: Exception):
    logger.exception("Unhandled application error: %s", exc)
    payload = ErrorResponse(
        error="internal_error",
        message="Internal server error",
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(payload),
    )


@app.get("/health")
def healthcheck():
    return {"ok": True}


@app.post(
    "/parse",
    response_model=ParseResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": (
                "Unauthorized — missing or invalid X-API-Key / RapidAPI proxy secret"
            ),
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorResponse,
            "description": (
                "Validation error — request body failed schema checks / "
                "请求体验证失败"
            ),
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error / 服务内部错误",
        },
    },
    dependencies=[Depends(verify_api_key)],
)
def parse_endpoint(req: ParseRequest) -> ParseResponse:
    return parse_address(req.raw_address)
