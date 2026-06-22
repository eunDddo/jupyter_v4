"""OpenTelemetry 기반 LLM API 사용량 계측.

- OTel MeterProvider + InMemoryMetricReader 로 LLM 호출/토큰을 Counter 로 기록한다.
- `/usage` API는 reader.get_metrics_data() 를 읽어 모델별로 집계하고 비용을 추정한다.
- 외부 수집기(OTLP/Prometheus)로 내보내려면 reader를 추가하면 된다(코드 변경 최소).
"""
from __future__ import annotations

import os
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

# 인메모리 리더: 프로세스 안에서 현재 누적값을 그대로 읽을 수 있다.
_reader = InMemoryMetricReader()
_provider = MeterProvider(metric_readers=[_reader])
try:
    metrics.set_meter_provider(_provider)
except Exception:
    pass  # 이미 설정된 경우 무시
_meter = metrics.get_meter("manufacturing_agent.llm")

# 계측기(Counter): 호출 수 / 토큰 수(입력·출력)
_calls = _meter.create_counter("llm.calls", unit="1", description="LLM 호출 횟수")
_tokens = _meter.create_counter("llm.tokens", unit="token", description="LLM 토큰 수(type=input|output)")

# 모델별 단가 (USD per 1M tokens) — 대략값. .env LLM_PRICE_JSON 으로 덮어쓰기 가능.
_DEFAULT_PRICE = {
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}
def _load_prices() -> dict:
    import json
    raw = os.environ.get("LLM_PRICE_JSON")
    if raw:
        try:
            return {**_DEFAULT_PRICE, **json.loads(raw)}
        except Exception:
            pass
    return dict(_DEFAULT_PRICE)
PRICES = _load_prices()


def record_llm_usage(model: str, tier: str, input_tokens: int = 0,
                     output_tokens: int = 0, error: bool = False) -> None:
    """LLM 한 번 호출의 사용량을 OTel Counter에 기록한다."""
    attrs = {"model": model or "unknown", "tier": tier or "default", "error": bool(error)}
    _calls.add(1, attrs)
    if input_tokens:
        _tokens.add(int(input_tokens), {**attrs, "type": "input"})
    if output_tokens:
        _tokens.add(int(output_tokens), {**attrs, "type": "output"})


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICES.get(model)
    if not p:
        return 0.0
    return round(input_tokens / 1_000_000 * p["input"] + output_tokens / 1_000_000 * p["output"], 6)


def usage_snapshot() -> dict:
    """OTel reader에서 현재 누적 메트릭을 읽어 모델별로 집계 + 비용 추정."""
    data = _reader.get_metrics_data()
    by_model: dict[str, dict] = {}
    totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0}

    def slot(model: str) -> dict:
        return by_model.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0})

    for rm in getattr(data, "resource_metrics", []) or []:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                for dp in metric.data.data_points:
                    attrs = dict(dp.attributes or {})
                    model = attrs.get("model", "unknown")
                    val = dp.value
                    if metric.name == "llm.calls":
                        slot(model)["calls"] += val
                        totals["calls"] += val
                        if attrs.get("error"):
                            slot(model)["errors"] += val
                            totals["errors"] += val
                    elif metric.name == "llm.tokens":
                        ttype = attrs.get("type", "input")
                        key = "input_tokens" if ttype == "input" else "output_tokens"
                        slot(model)[key] += val
                        totals[key] += val

    models_out = {}
    total_cost = 0.0
    for model, s in by_model.items():
        c = _cost(model, s["input_tokens"], s["output_tokens"])
        total_cost += c
        models_out[model] = {**s, "total_tokens": s["input_tokens"] + s["output_tokens"],
                             "est_cost_usd": c}
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    totals["est_cost_usd"] = round(total_cost, 6)
    return {"totals": totals, "by_model": models_out}
