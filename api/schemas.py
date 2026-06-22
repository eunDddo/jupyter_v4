"""Pydantic request/response models for the Manufacturing Agent API."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str
    thread_id: str
    message: str
    input_features: Optional[dict] = None


class ChatResponse(BaseModel):
    user_id: str
    thread_id: str
    answer: str
    citations: list = Field(default_factory=list)
    warnings: list = Field(default_factory=list)
    missing_inputs: list = Field(default_factory=list)
    blocked: bool = False
    trace: Optional[dict] = None


class ResumeRequest(BaseModel):
    user_id: str
    thread_id: str
