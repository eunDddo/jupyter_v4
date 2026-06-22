"""Conversation history endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from api.deps import require_user_thread
from manufacturing_agent.memory.store import conversation_store

router = APIRouter(tags=["history"])


@router.get("/users/{user_id}/threads/{thread_id}/history")
def get_history(user_id: str, thread_id: str):
    require_user_thread(user_id, thread_id)
    turns = conversation_store.recent_turns(user_id, limit=20, thread_id=thread_id)
    return {"turns": turns}
