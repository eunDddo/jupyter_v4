"""OpenTelemetry 기반 LLM API 사용량 조회."""
from __future__ import annotations

from fastapi import APIRouter

from manufacturing_agent.observability import usage_snapshot, PRICES

router = APIRouter(tags=["usage"])


@router.get("/usage")
def get_usage():
    """현재 프로세스 누적 LLM 사용량(호출 수·토큰·모델별)과 추정 비용(USD).

    OTel InMemoryMetricReader에 누적된 `llm.calls`/`llm.tokens` 카운터를 읽어 집계한다.
    값은 서버 프로세스 시작 이후 누적이며, 재시작하면 0부터 다시 센다.
    """
    snap = usage_snapshot()
    snap["pricing_usd_per_1m_tokens"] = PRICES
    snap["note"] = "프로세스 시작 이후 누적. call_llm 경유 호출만 집계(pydantic_ai SQL 에이전트 호출은 제외)."
    return snap
