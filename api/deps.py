"""FastAPI dependencies / shared validation helpers."""
from __future__ import annotations

from fastapi import HTTPException

from manufacturing_agent.memory.registry import registry


def require_user_thread(user_id: str, thread_id: str) -> None:
    """Validate that the user and thread exist.

    Raises HTTPException(404) if either is missing. Plain function so it can be
    reused directly inside route handlers as well as via Depends.
    """
    if not registry.user_exists(user_id):
        raise HTTPException(status_code=404, detail="user_not_found")
    if not registry.thread_exists(user_id, thread_id):
        raise HTTPException(status_code=404, detail="thread_not_found")
