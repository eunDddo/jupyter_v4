from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from manufacturing_agent.memory.registry import registry

router = APIRouter()


class CreateUserBody(BaseModel):
    user_id: str | None = None


class CreateThreadBody(BaseModel):
    thread_id: str | None = None
    title: str | None = None


@router.post("/users")
def create_user(body: CreateUserBody | None = None) -> dict:
    user_id = body.user_id if body is not None else None
    result = registry.create_user(user_id)
    return {"user_id": result["user_id"], "created_at": result["created_at"]}


@router.delete("/users/{user_id}")
def delete_user(user_id: str) -> dict:
    if not registry.user_exists(user_id):
        raise HTTPException(status_code=404, detail="user_not_found")
    deleted = registry.delete_user(user_id)
    return {"deleted": deleted}


@router.get("/users/{user_id}/threads")
def list_threads(user_id: str) -> dict:
    if not registry.user_exists(user_id):
        raise HTTPException(status_code=404, detail="user_not_found")
    return {"threads": registry.list_threads(user_id)}


@router.post("/users/{user_id}/threads")
def create_thread(user_id: str, body: CreateThreadBody | None = None) -> dict:
    if not registry.user_exists(user_id):
        raise HTTPException(status_code=404, detail="user_not_found")
    thread_id = body.thread_id if body is not None else None
    title = (body.title if body is not None else None) or ""
    result = registry.create_thread(user_id, thread_id=thread_id, title=title)
    return result


@router.delete("/users/{user_id}/threads/{thread_id}")
def delete_thread(user_id: str, thread_id: str) -> dict:
    if not registry.thread_exists(user_id, thread_id):
        raise HTTPException(status_code=404, detail="thread_not_found")
    deleted = registry.delete_thread(user_id, thread_id)
    return {"deleted": deleted}
