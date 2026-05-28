import json

from quart import Blueprint, current_app, request
import structlog

from ..database import get_order, mark_order_paid_if_unpaid
from ..schemas import AfdianWebhookPayload

logger = structlog.get_logger()
bp = Blueprint("webhook", __name__)


def _ok() -> tuple[str, int, dict]:
    """爱发电要求无论什么情况都返回 ec:200，否则会重试"""
    return json.dumps({"ec": 200, "em": ""}, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@bp.route("/afdian", methods=["POST"])
async def afdian_webhook():
    db = current_app.config["DB"]
    afdian_client = current_app.config["AFDIAN_CLIENT"]
    http = current_app.config["HTTP_CLIENT"]

    # 解析 payload
    try:
        raw = await request.get_data(as_text=True)
        payload = AfdianWebhookPayload.model_validate_json(raw)
    except Exception:
        logger.warning("webhook_parse_error")
        return _ok()

    order_data = payload.data.order
    if not order_data.remark:
        logger.info("webhook_no_remark", out_trade_no=order_data.out_trade_no)
        return _ok()

    order_no = order_data.remark
    logger.info("webhook_received", order_no=order_no, out_trade_no=order_data.out_trade_no)

    # 查库
    order = await get_order(db, order_no)
    if order is None:
        logger.warning("webhook_order_not_found", order_no=order_no)
        # 返回 ec:200 防止爱发电无意义重试（订单由 Cloudreve 创建，爱发电重试也找不到）
        return _ok()

    # 已支付则幂等返回成功
    if order["is_paid"]:
        logger.info("webhook_already_paid", order_no=order_no)
        return _ok()

    # ── 关键安全步骤：调用 Afdian API 二次确认订单真实性 ──
    verified = await afdian_client.query_order(order_data.out_trade_no, http)
    if verified == "error":
        # API 调用失败，标记待重试，由 notifier worker 稍后通过 API 查询确认
        logger.warning("webhook_api_call_failed", order_no=order_no,
                        out_trade_no=order_data.out_trade_no)
        return _ok()
    if verified is None:
        # API 返回无结果，订单确实不存在
        logger.warning("webhook_verification_failed", order_no=order_no,
                        out_trade_no=order_data.out_trade_no)
        return _ok()

    # 确认 API 返回的状态为已支付（status=2）
    if verified.get("status") != 2:
        logger.warning("webhook_order_not_paid", order_no=order_no,
                        status=verified.get("status"))
        return _ok()

    # 用 API 返回的数据做金额校验（比 Webhook 推送的数据更可信）
    try:
        api_amount_fen = int(round(float(verified.get("total_amount", "0")) * 100))
    except (ValueError, TypeError):
        logger.warning("webhook_api_bad_amount", order_no=order_no)
        return _ok()

    if api_amount_fen != order["amount"]:
        logger.warning(
            "webhook_api_amount_mismatch",
            order_no=order_no,
            expected=order["amount"],
            got=api_amount_fen,
        )
        return _ok()

    # 原子标记已支付（CAS，防止竞态）
    changed = await mark_order_paid_if_unpaid(db, order_no)
    if changed:
        logger.info("order_marked_paid", order_no=order_no)
    else:
        logger.info("webhook_already_paid_race", order_no=order_no)

    return _ok()
