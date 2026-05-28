from __future__ import annotations

from pydantic import BaseModel, Field


# ─── Cloudreve 请求体 ───────────────────────────────────────


class CreateOrderRequest(BaseModel):
    name: str
    order_no: str = Field(min_length=1, max_length=128)
    notify_url: str = Field(min_length=1, max_length=2048)
    amount: int = Field(gt=0, le=10_000_000)
    currency: str = Field(min_length=1, max_length=16)


# ─── 统一响应 ───────────────────────────────────────────────


class OrderResponse(BaseModel):
    code: int
    data: str | None = None
    error: str | None = None

    def to_json(self) -> dict:
        """只输出有值的字段，避免多余的 null"""
        d: dict = {"code": self.code}
        if self.data is not None:
            d["data"] = self.data
        if self.error is not None:
            d["error"] = self.error
        return d


class StatusResponse(BaseModel):
    code: int
    data: str | None = None
    error: str | None = None

    def to_json(self) -> dict:
        d: dict = {"code": self.code}
        if self.data is not None:
            d["data"] = self.data
        if self.error is not None:
            d["error"] = self.error
        return d


# ─── 爱发电 Webhook ─────────────────────────────────────────


class AfdianWebhookSku(BaseModel):
    sku_id: str = ""
    count: int = 0
    name: str = ""
    album_id: str = ""
    pic: str = ""


class AfdianWebhookOrder(BaseModel):
    out_trade_no: str = ""
    custom_order_id: str = ""
    user_id: str = ""
    user_private_id: str = ""
    plan_id: str = ""
    month: int = 0
    total_amount: str = "0.00"
    show_amount: str = "0.00"
    status: int = 0
    remark: str = ""
    redeem_id: str = ""
    product_type: int = 0
    discount: str = "0.00"
    sku_detail: list[AfdianWebhookSku] = []
    address_person: str = ""
    address_phone: str = ""
    address_address: str = ""


class AfdianWebhookData(BaseModel):
    type: str = ""
    order: AfdianWebhookOrder


class AfdianWebhookPayload(BaseModel):
    ec: int = 0
    em: str = ""
    data: AfdianWebhookData


# ─── 爱发电 API 查询订单响应 ─────────────────────────────────


class AfdianApiOrder(BaseModel):
    out_trade_no: str = ""
    custom_order_id: str = ""
    remark: str = ""
    total_amount: str = "0.00"
    status: int = 0
    plan_id: str = ""
    month: int = 0


class AfdianApiData(BaseModel):
    total_count: int = 0
    total_page: int = 0
    items: list[AfdianApiOrder] = Field(default=[], alias="list")


class AfdianApiResponse(BaseModel):
    ec: int = 0
    em: str = ""
    data: AfdianApiData


# ─── 健康检查 ───────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
