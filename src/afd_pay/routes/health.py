from quart import Blueprint, current_app

from ..schemas import HealthResponse

bp = Blueprint("health", __name__)


@bp.route("/health", methods=["GET"])
async def health():
    db = current_app.config["DB"]
    db_status = "connected"
    try:
        await db.execute("SELECT 1")
    except Exception:
        db_status = "error"
    resp = HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        version="1.0.0",
        db=db_status,
    )
    return resp.model_dump(), 200
