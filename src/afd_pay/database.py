import time as _time
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS afdian_pay (
    order_no          TEXT PRIMARY KEY,
    amount            INTEGER NOT NULL,
    notify_url        TEXT    NOT NULL,
    is_paid           INTEGER DEFAULT 0,
    notify_status     INTEGER DEFAULT 0,
    notify_attempts   INTEGER DEFAULT 0,
    notify_next_at    INTEGER DEFAULT 0,
    notify_last_at    INTEGER DEFAULT 0,
    notify_last_error TEXT    DEFAULT ''
);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    """初始化数据库连接，开启 WAL 模式，建表"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA wal_autocheckpoint=100;")
    await conn.execute(_SCHEMA)
    await conn.commit()
    return conn


async def ensure_db(app) -> aiosqlite.Connection:
    """获取数据库连接，如果已断开则自动重连"""
    db = app.config.get("DB")
    try:
        await db.execute("SELECT 1")
        return db
    except Exception:
        import structlog
        logger = structlog.get_logger()
        logger.warning("db_reconnecting")
        try:
            await db.close()
        except Exception:
            pass
        settings = app.config["SETTINGS"]
        new_db = await init_db(settings.db_path)
        app.config["DB"] = new_db
        return new_db


async def close_db(conn: aiosqlite.Connection) -> None:
    try:
        await conn.commit()
    except Exception:
        pass
    await conn.close()


# ─── 订单 CRUD ───────────────────────────────────────────────


async def insert_order(
    conn: aiosqlite.Connection,
    order_no: str,
    amount: int,
    notify_url: str,
) -> None:
    """创建订单（INSERT OR IGNORE，幂等，不覆盖已有记录）"""
    await conn.execute(
        """
        INSERT OR IGNORE INTO afdian_pay
            (order_no, amount, notify_url, is_paid, notify_status, notify_attempts,
             notify_next_at, notify_last_at, notify_last_error)
        VALUES (?, ?, ?, 0, 0, 0, ?, 0, '')
        """,
        (order_no, amount, notify_url, int(_time.time())),
    )
    await conn.commit()


async def get_order_status(conn: aiosqlite.Connection, order_no: str) -> str | None:
    """查询订单支付状态，返回 'PAID' / 'UNPAID' / None（不存在）"""
    async with conn.execute(
        "SELECT is_paid FROM afdian_pay WHERE order_no = ?",
        (order_no,),
    ) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        return "PAID" if row[0] else "UNPAID"


async def get_order(conn: aiosqlite.Connection, order_no: str) -> dict | None:
    """获取完整订单记录"""
    async with conn.execute(
        "SELECT * FROM afdian_pay WHERE order_no = ?",
        (order_no,),
    ) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        return dict(row)


async def mark_order_paid(conn: aiosqlite.Connection, order_no: str) -> None:
    """标记订单为已支付，加入回调队列"""
    now = int(_time.time())
    await conn.execute(
        """
        UPDATE afdian_pay
        SET is_paid = 1,
            notify_status = 0,
            notify_next_at = ?,
            notify_last_error = ''
        WHERE order_no = ?
        """,
        (now, order_no),
    )
    await conn.commit()


async def mark_order_paid_if_unpaid(conn: aiosqlite.Connection, order_no: str) -> bool:
    """原子地将未支付订单标记为已支付，返回是否成功（CAS 防竞态）"""
    now = int(_time.time())
    cursor = await conn.execute(
        """
        UPDATE afdian_pay
        SET is_paid = 1,
            notify_status = 0,
            notify_next_at = ?,
            notify_last_error = ''
        WHERE order_no = ? AND is_paid = 0
        """,
        (now, order_no),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def fetch_due_notify_jobs(
    conn: aiosqlite.Connection,
    now: int,
    limit: int = 10,
) -> list[dict]:
    """取出待回调的通知任务"""
    async with conn.execute(
        """
        SELECT order_no, notify_url, notify_attempts
        FROM afdian_pay
        WHERE is_paid = 1
          AND notify_url != ''
          AND notify_status NOT IN (1, 3)
          AND notify_next_at <= ?
        ORDER BY notify_next_at ASC
        LIMIT ?
        """,
        (now, limit),
    ) as cur:
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_notify_success(conn: aiosqlite.Connection, order_no: str) -> None:
    now = int(_time.time())
    await conn.execute(
        """
        UPDATE afdian_pay
        SET notify_status = 1,
            notify_last_at = ?,
            notify_last_error = ''
        WHERE order_no = ?
        """,
        (now, order_no),
    )
    await conn.commit()


async def mark_notify_failure(
    conn: aiosqlite.Connection,
    order_no: str,
    attempts: int,
    err: str,
    next_at: int,
) -> None:
    now = int(_time.time())
    status = 3 if attempts >= 20 else 2
    await conn.execute(
        """
        UPDATE afdian_pay
        SET notify_status = ?,
            notify_attempts = ?,
            notify_last_at = ?,
            notify_next_at = ?,
            notify_last_error = ?
        WHERE order_no = ?
        """,
        (status, attempts, now, next_at, err[:500], order_no),
    )
    await conn.commit()
