"""爱发电 API 客户端

- API 签名：MD5(token + "params" + params_json + "ts" + ts + "user_id" + user_id)
- 双域名回退：ifdian.net 优先，afdian.com 兜底
- 生成用户付款链接
"""

from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import quote

import httpx
import structlog

from ..schemas import AfdianApiResponse

# sentinel：区分"订单不存在"和"API调用失败"
_ERROR = "error"

logger = structlog.get_logger("afdian_client")


class AfdianClient:
    def __init__(
        self,
        user_id: str,
        token: str,
        api_base: str = "https://ifdian.net",
        api_fallback: str = "https://afdian.com",
        payment_base: str = "https://afdian.com",
        user_agent: str = "AfdPay",
    ):
        self.user_id = user_id
        self.token = token
        self.api_base = api_base
        self.api_fallback = api_fallback
        self.payment_base = payment_base
        self.user_agent = user_agent
        self.working_domain: str | None = None

    def _sign(self, params_json: str, ts: str) -> str:
        raw = f"{self.token}params{params_json}ts{ts}user_id{self.user_id}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def build_payment_url(self, order_no: str, amount_fen: int) -> str:
        base = self.working_domain or self.payment_base
        price = f"{amount_fen / 100:.2f}"
        return (
            f"{base}/order/create"
            f"?user_id={self.user_id}"
            f"&remark={quote(order_no, safe='')}"
            f"&custom_price={quote(price, safe='')}"
        )

    async def query_order(self, out_trade_no: str, http: httpx.AsyncClient) -> dict | None | str:
        """查询爱发电订单。
        返回:
          dict   - 找到订单
          None   - 订单不存在（API 返回 ec!=200 或 total_count=0）
          "error" - 所有域名都调用失败
        """
        params_json = json.dumps({"out_trade_no": out_trade_no}, ensure_ascii=False)
        ts = str(int(time.time()))
        sign = self._sign(params_json, ts)

        post_data = {
            "user_id": self.user_id,
            "params": params_json,
            "ts": ts,
            "sign": sign,
        }
        headers = {"User-Agent": self.user_agent}

        for base in (self.api_base, self.api_fallback):
            try:
                resp = await http.post(
                    f"{base}/api/open/query-order",
                    data=post_data,
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                parsed = AfdianApiResponse.model_validate_json(resp.text)
                if parsed.ec != 200 or parsed.data.total_count == 0:
                    return None
                self.working_domain = base
                return parsed.data.items[0].model_dump()
            except Exception as e:
                logger.warning("query_order_failed", base=base, error=str(e))
                continue
        return _ERROR
