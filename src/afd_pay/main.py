"""Quart 应用工厂 + 生命周期管理"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import structlog
from quart import Quart

from .config import Settings
from .database import close_db, init_db
from .routes import health, order, webhook
from .services.afdian import AfdianClient
from .services.notifier import NotifyWorker


def create_app() -> Quart:
    app = Quart(__name__)
    settings = Settings()

    # 请求体大小限制 1MB，防止 DoS
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

    missing = settings.validate_required()
    if missing:
        raise RuntimeError(f"缺少必填配置项: {', '.join(missing)}")

    # 存入 app.config 供路由访问
    app.config["SETTINGS"] = settings

    # 注册蓝图
    app.register_blueprint(health.bp)
    app.register_blueprint(order.bp)
    app.register_blueprint(webhook.bp)

    @app.after_request
    async def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response

    @app.errorhandler(Exception)
    async def handle_unexpected_error(error):
        logger = structlog.get_logger()
        logger.error("unhandled_exception", error=str(error), type=type(error).__name__)
        return (
            json.dumps({"code": 500, "error": "服务器内部错误"}, ensure_ascii=False),
            500,
            {"Content-Type": "application/json"},
        )

    # 爱发电客户端（生命周期与 app 一致）
    afdian_client = AfdianClient(
        user_id=settings.afdian_user_id,
        token=settings.afdian_token,
        api_base=settings.afdian_api_base,
        api_fallback=settings.afdian_api_fallback,
        payment_base=settings.afdian_payment_base,
        user_agent=settings.user_agent_afdian,
    )
    app.config["AFDIAN_CLIENT"] = afdian_client

    notify_task: asyncio.Task | None = None
    http_client: httpx.AsyncClient | None = None

    @app.before_serving
    async def startup():
        nonlocal notify_task, http_client

        structlog.configure(
            processors=[
                structlog.dev.ConsoleRenderer() if settings.log_level == "DEBUG" else structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, settings.log_level.upper(), logging.INFO)
            ),
        )

        db = await init_db(settings.db_path)
        app.config["DB"] = db

        # 为 notifier worker 创建独立连接，避免写操作串行阻塞事件循环
        db_worker = await init_db(settings.db_path)
        app.config["DB_WORKER"] = db_worker

        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        app.config["HTTP_CLIENT"] = http_client

        worker = NotifyWorker(
            db=db_worker,
            http=http_client,
            max_attempts=settings.notify_max_attempts,
            base_delay=settings.notify_base_delay,
            max_delay=settings.notify_max_delay,
            user_agent=settings.user_agent_cloudreve,
        )
        notify_task = asyncio.create_task(worker.run())

        logger = structlog.get_logger()
        logger.info("server_started", port=settings.port)

    @app.after_serving
    async def shutdown():
        nonlocal notify_task, http_client
        logger = structlog.get_logger()
        logger.info("server_shutting_down")

        if notify_task:
            notify_task.cancel()
            try:
                await asyncio.wait_for(notify_task, timeout=10.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if http_client:
            await http_client.aclose()

        for key in ("DB", "DB_WORKER"):
            db = app.config.get(key)
            if db:
                await close_db(db)

    return app


def main():
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    settings = Settings()
    config = Config()
    config.bind = [f"0.0.0.0:{settings.port}"]
    config.accesslog = "-"

    app = create_app()
    try:
        asyncio.run(serve(app, config))
    except OSError as e:
        if "address already in use" in str(e).lower() or e.errno == 98:
            print(f"错误：端口 {settings.port} 已被占用")
        else:
            raise


if __name__ == "__main__":
    main()
