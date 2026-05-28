from urllib.parse import unquote, urlparse

from quart import Blueprint, current_app, request
import structlog

from ..database import get_order, get_order_status, insert_order
from ..schemas import CreateOrderRequest, OrderResponse, StatusResponse
from ..services.cloudreve import (
    parse_authorization,
    parse_sign_param,
    verify_get,
    verify_post,
)

logger = structlog.get_logger()
bp = Blueprint("order", __name__)


@bp.route("/order", methods=["POST", "GET"])
async def order():
    settings = current_app.config["SETTINGS"]
    db = current_app.config["DB"]

    # ─── 站点 URL 校验 ───────────────────────────────────
    site_url = request.headers.get("X-Cr-Site-Url", "")
    if site_url.rstrip("/") != settings.site_url.rstrip("/"):
        logger.warning("order_request_failed", reason="site_url_mismatch", got=site_url)
        return OrderResponse(code=500, error="站点地址不匹配").to_json(), 200

    if request.method == "POST":
        return await _create_order(settings, db)
    else:
        return await _query_status(settings, db)


async def _create_order(settings, db):
    # 解析签名
    auth = request.headers.get("Authorization", "")
    parsed = parse_authorization(auth)
    if parsed is None:
        logger.warning("order_create_failed", reason="invalid_authorization")
        return OrderResponse(code=500, error="无效的 Authorization 头格式").to_json(), 200
    signature, timestamp = parsed

    body = await request.get_data(as_text=True)
    ok, msg = verify_post(
        headers={k: v for k, v in request.headers},
        body=body,
        path=request.path or "/",
        signature=signature,
        timestamp=timestamp,
        communication_key=settings.communication_key,
    )
    if not ok:
        logger.warning("order_create_failed", reason="signature_invalid", detail=msg)
        return OrderResponse(code=500, error=msg).to_json(), 200

    # 解析请求体
    try:
        data = CreateOrderRequest.model_validate_json(body)
    except Exception:
        logger.warning("order_create_failed", reason="bad_request_body")
        return OrderResponse(code=500, error="请求体格式错误").to_json(), 200

    # 仅支持 CNY
    if data.currency != "CNY":
        logger.warning("order_create_failed", reason="unsupported_currency", currency=data.currency)
        return OrderResponse(code=500, error=f"不支持的货币: {data.currency}").to_json(), 200

    # 最低金额
    if data.amount < settings.min_amount_fen:
        logger.warning("order_create_failed", reason="amount_too_low", amount=data.amount)
        return OrderResponse(code=500, error=f"金额需大于等于 {settings.min_amount_fen / 100} 元").to_json(), 200

    # SSRF 防护：校验 notify_url 与 site_url 同域
    notify_host = urlparse(data.notify_url).hostname
    site_host = urlparse(settings.site_url).hostname
    if notify_host != site_host:
        logger.warning("order_create_failed", reason="notify_url_mismatch",
                        notify_url=data.notify_url, site_host=site_host)
        return OrderResponse(code=500, error="回调地址与站点不匹配").to_json(), 200

    # 存库
    await insert_order(db, data.order_no, data.amount, data.notify_url)

    # 生成爱发电付款链接
    afdian = current_app.config["AFDIAN_CLIENT"]
    payment_url = afdian.build_payment_url(data.order_no, data.amount)
    logger.info("order_created", order_no=data.order_no, amount=data.amount)

    return OrderResponse(code=0, data=payment_url).to_json(), 200


async def _query_status(settings, db):
    # 解析签名
    sign_param = request.args.get("sign", "")
    if not sign_param:
        logger.warning("query_status_failed", reason="missing_sign")
        return StatusResponse(code=500, error="缺少 sign 参数").to_json(), 200
    parsed = parse_sign_param(unquote(sign_param))
    if parsed is None:
        logger.warning("query_status_failed", reason="invalid_sign_format")
        return StatusResponse(code=500, error="无效的签名格式").to_json(), 200
    signature, timestamp = parsed

    ok, msg = verify_get(
        path=request.path or "/",
        signature=signature,
        timestamp=timestamp,
        communication_key=settings.communication_key,
    )
    if not ok:
        logger.warning("query_status_failed", reason="signature_invalid", detail=msg)
        return StatusResponse(code=500, error=msg).to_json(), 200

    order_no = request.args.get("order_no", "")
    if not order_no:
        logger.warning("query_status_failed", reason="missing_order_no")
        return StatusResponse(code=500, error="缺少 order_no 参数").to_json(), 200

    status = await get_order_status(db, order_no)
    if status is None:
        logger.warning("query_status_failed", reason="order_not_found", order_no=order_no)
        return StatusResponse(code=500, error="订单不存在").to_json(), 200

    return StatusResponse(code=0, data=status).to_json(), 200
