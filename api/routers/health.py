"""Liveness and readiness probes."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz():
    """Check that core resources (graph/Chroma/SQLite) are importable/ready."""
    try:
        from manufacturing_agent.runtime import app as _graph_app  # noqa: F401

        if _graph_app is None:
            raise RuntimeError("graph app is None")
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(status_code=503, content={"ready": False, "error": str(exc)})
    return {"ready": True}
