"""异步回调重试 Worker

- 指数退避：5s → 10s → 20s → 40s ... 最大 30min
- 最多重试 20 次，之后放弃（notify_status=3）
- 批量取出最多 10 条待处理任务
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import httpx
import structlog

from ..database import (
    fetch_due_notify_jobs,
    mark_notify_failure,
    mark_notify_success,
)

if TYPE_CHECKING:
    import aiosqlite

logger = structlog.get_logger()


class NotifyWorker:
    def __init__(
        self,
        db: aiosqlite.Connection,
        http: httpx.AsyncClient,
        max_attempts: int = 20,
        base_delay: float = 5.0,
        max_delay: float = 1800.0,
        user_agent: str = "AfdPay",
    ):
        self.db = db
        self.http = http
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.user_agent = user_agent

    def backoff_seconds(self, attempts: int) -> float:
        """指数退避：base_delay * 2^(attempts-1)，上限 max_delay"""
        return min(self.base_delay * (2 ** (attempts - 1)), self.max_delay)

    async def notify_once(self, url: str) -> tuple[bool, str]:
        """向 Cloudreve 发送一次回调通知，返回 (成功?, 错误信息)"""
        try:
            resp = await self.http.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=(3, 5),
            )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            body = resp.json()
            if body.get("code") == 0:
                return True, ""
            return False, f"code={body.get('code')}, body={resp.text[:200]}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    async def run(self) -> None:
        """主循环：持续轮询待处理任务"""
        logger.info("notify_worker_started")
        consecutive_errors = 0
        while True:
            try:
                now = int(time.time())
                jobs = await fetch_due_notify_jobs(self.db, now)
                consecutive_errors = 0  # 成功则重置
                if not jobs:
                    await asyncio.sleep(1.0)
                    continue

                for job in jobs:
                    order_no = job["order_no"]
                    url = job["notify_url"]
                    attempts = int(job["notify_attempts"] or 0)

                    ok, err = await self.notify_once(url)
                    if ok:
                        logger.info("notify_success", order_no=order_no)
                        await mark_notify_success(self.db, order_no)
                    else:
                        attempts += 1
                        next_at = int(time.time()) + int(self.backoff_seconds(attempts))
                        logger.warning(
                            "notify_failed",
                            order_no=order_no,
                            attempts=attempts,
                            err=err,
                        )
                        await mark_notify_failure(
                            self.db, order_no, attempts, err, next_at
                        )
                    # 让出控制权，避免饿死其他协程
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                logger.info("notify_worker_cancelled")
                raise
            except Exception as e:
                consecutive_errors += 1
                delay = min(2.0 * (2 ** (consecutive_errors - 1)), 60.0)
                logger.error("notify_worker_exception",
                             error=str(e), consecutive=consecutive_errors,
                             next_retry_in=delay)
                await asyncio.sleep(delay)
