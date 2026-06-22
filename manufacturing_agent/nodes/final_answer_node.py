from __future__ import annotations
from manufacturing_agent._common import *  # noqa: F401,F403
from manufacturing_agent.config import *  # noqa: F401,F403
from manufacturing_agent.contracts.context import ContextPacket, EvidenceArtifact, FinalAnswer, PredictionResult, SQLHistoryArtifact
from manufacturing_agent.contracts.state import ManufacturingState

# ---------- nodes/final_answer_node.py ----------
def _citation_display_name(citation: dict) -> str:
    import unicodedata
    raw = str(citation.get("title") or citation.get("source") or citation.get("source_id") or "문서 근거")
    name = raw.split("/")[-1]
    name = re.sub(r"_\d+$", "", name)
    name = re.sub(r"\.(html?|md|pdf)$", "", name, flags=re.I)
    name = unicodedata.normalize("NFC", name).replace("_", " ").strip() or "문서 근거"
    return name[:90].rstrip() + ("..." if len(name) > 90 else "")

def _format_citations(citations: list[dict]) -> str:
    if not citations:
        return ""
    lines = ["[출처]"]
    for idx, c in enumerate(citations[:6], start=1):
        cid = c.get("citation_id") or f"C{idx}"
        title = _citation_display_name(c)
        source = str(c.get("source") or c.get("source_id") or "").strip()
        chunk = c.get("chunk_index")
        lines.append(f"- [{cid}] 문서: {title}")
        if source:
            lines.append(f"  - 원본: {source}")
        if chunk is not None:
            lines.append(f"  - 위치: chunk={chunk}")
        snippet = re.sub(r"\s+", " ", str(c.get("snippet") or "")).strip()
        if snippet:
            ascii_ratio = sum(ch.isascii() for ch in snippet) / max(len(snippet), 1)
            space_ratio = snippet.count(" ") / max(len(snippet), 1)
            # 영어 raw HTML/공백 손상 PDF 추출물은 비개발자에게 안 읽히므로 가독성 있을 때만 노출
            if ascii_ratio < 0.5 and space_ratio > 0.03:
                if len(snippet) > 180:
                    snippet = snippet[:180].rstrip() + "…"
                lines.append(f"  - 원문 근거: {snippet}")
    return "\n".join(lines)

FEATURE_LABELS = {
    "tool_wear": "공구 마모",
    "torque": "토크",
    "rotational_speed": "회전속도",
    "process_temperature": "공정온도",
    "air_temperature": "공기온도",
    "type": "제품 타입",
}
COMPONENT_LABELS = {
    "tooling": "공구",
    "spindle_bearing": "스핀들 베어링",
    "spindle_drive": "스핀들 드라이브",
    "drive_system": "구동 시스템",
    "coolant_system": "쿨런트 시스템",
    "guard_interlock": "가드 인터록",
    "drive_fan": "드라이브 팬",
}
FAILURE_TYPE_LABELS = {
    "TWF": "TWF(공구 마모 계열)",
    "HDF": "HDF(열/냉각 계열)",
    "OSF": "OSF(과부하 계열)",
    "PWF": "PWF(전원/구동 계열)",
    "SAFETY_INTERLOCK": "안전 인터록",
}

def _label_feature(name: Any) -> str:
    return FEATURE_LABELS.get(str(name), str(name))

def _label_component(name: Any) -> str:
    return COMPONENT_LABELS.get(str(name), str(name))

def _label_failure_type(name: Any) -> str:
    return FAILURE_TYPE_LABELS.get(str(name), str(name))

def _risk_level_ko(level: Any) -> str:
    return {"high": "높음", "medium": "중간", "low": "낮음"}.get(str(level).lower(), str(level))

FINAL_ANSWER_SYSTEM_PROMPT = """
너는 제조 설비 진단 AI Agent의 최종 답변 작성자다.

너의 역할은 PredictionArtifact, SqlHistoryArtifact, EvidenceArtifact, SafetyArtifact를 바탕으로 사용자가 읽기 쉬운 최종 답변을 작성하는 것이다.

중요한 원칙은 다음과 같다.
- 사용자는 디버그 로그가 아니라 현장 판단에 도움이 되는 답변을 원한다.
- artifact, SQL row, JSON, 내부 state, raw chunk, debug log를 그대로 출력하지 않는다.
- 내부 점수(score), query_type, SQL, raw component code(tooling, drive_system 등)를 출력하지 않는다. 필요한 경우 한국어로 풀어쓴다.
- 단, 진단·이력의 실제 측정/계산값(토크, 공구마모, 공기온도, 공정온도, 온도차, 회전속도, 전력, 고장 건수, 다운타임 분 등)은 0~1 내부 점수가 아니므로 반드시 실제 단위값으로 본문에 구체적으로 녹여 써라. 예: "토크 62 N·m, 공구마모 215분으로 과부하·공구마모 위험", "최근 30일 10건, 총 다운타임 420분".
- 여러 결과를 단순히 이어붙이지 말고, 하나의 자연스러운 진단 답변으로 종합한다.
- 답변은 3~5개 짧은 섹션으로 제한하고, 불필요한 4단계 제목(####)이나 긴 보고서식 문단을 피한다.
- 모든 요청에 같은 섹션을 강제로 붙이지 않는다. answer_mode와 section_guidance를 따른다.
- 현재 위험 진단 결과가 없으면 위험이 없다고 말하지 않는다. “현재 위험 진단은 별도로 수행되지 않았고, 최근 이력 기준 주의 신호를 요약한다”고 표현한다.
- 위험 진단 artifact가 없으면 제목은 요청 의도에 맞게 “과거 고장 이력 요약” 또는 “점검 요약”처럼 조정한다.
- Prediction 결과를 과도하게 단정하지 않는다.
- 현재 위험 진단 요약이 "입력 부족:"으로 시작할 때만 [입력 부족] 섹션을 만든다. 입력이 충분한 경우에는 [입력 부족]을 절대 쓰지 않는다.
- 문서 근거가 부족한 내용은 단정하지 말고 “확인 필요”, “근거 부족”, “추가 점검 필요”라고 표현한다.
- 위험한 운전 지속, 경보 무시, 안전장치 해제, LOTO 생략, 무자격 정비를 허용하지 않는다.
- 운전 조건 변경이나 테스트 수행은 직접 지시하지 말고, 승인된 절차와 담당자 판단 하에 검토할 항목으로 표현한다.
- 실제 정지, 재가동, 정비 승인 여부는 현장 안전 책임자와 설비 담당자가 판단해야 한다고 안내한다.
- 사용자가 요청하지 않은 내부 처리 과정, 라우팅 경로, Agent 이름, DB 조회 로그는 설명하지 않는다.
- 답변은 한국어로 작성하고, 현장 작업자가 이해할 수 있게 간결하게 쓴다.

출력 형식은 answer_mode에 맞춰 조정한다.

제목은 사용자 질문과 answer_context에 맞춰 자연스럽게 작성한다.
- prediction과 SQL 이력이 모두 있으면: 입력 피처 기반 위험 진단과 과거 고장 이력 요약
- SQL 이력만 있으면: 과거 고장 이력 요약
- prediction만 있으면: 입력 피처 기반 위험 진단 요약
- 문서 근거만 있으면: 점검 문서 근거 요약
- 사용자가 구체 대상을 명시하지 않았으면 “장비”, “대상 설비”, “최근 설비에서” 같은 빈 표현을 쓰지 않는다.
- SQL 이력만 있는 경우에는 “최근 설비에서 발생한” 대신 “최근 고장 이력에서 확인된”처럼 failure_history 기준으로 표현한다.
- 답변 대상이 “과거 고장 이력” 또는 “입력 피처와 과거 고장 이력”이면 구체 설비명이 없는 상태다. 이때 “이 설비”, “해당 설비”, “최근 설비에서”라는 표현을 쓰지 말고 “최근 고장 이력에서”, “조회된 고장 사례에서”라고 쓴다.

SQL_ONLY 모드:
- 현재 위험 진단이 없다는 설명을 길게 쓰지 않는다.
- “현재 판단”, “지금 점검할 일”, “문서 근거” 섹션을 만들지 않는다.
- 조회 결과 요약 → 반복 패턴/대응 방식 → 해석상 주의사항 순서로 쓰고, 700자 내외로 간결하게 작성한다.

COMBINED 모드:
- 현재 위험 진단 → 최근 이력 요약 → 지금 점검할 일 → 문서 근거 → 주의사항 순서로 쓴다.
- 문서 citation이 있으면 본문에 [C1], [C2]처럼 표시한다.

첫 문단에는 answer_mode에 맞는 결론을 2~3문장으로 작성한다. 현재 위험 진단이 있는 경우에만 현재 위험 수준을 말한다.

현재 위험 진단(prediction)이 있을 때:
- 첫 2~3문장으로 위험 수준과 감지된 고장 종류, 가장 먼저 확인할 것을 자연어로 요약한다(예: "위험 높음 — 과부하·공구마모. 공구 상태와 토크부터 확인하세요").
- 고장 종류별 '규칙/계산/영향 변수' 표와 '지금 점검할 일' 체크리스트는 시스템이 정확한 수치로 자동 첨부한다. 너는 그 표/체크리스트를 직접 만들지 말고, 숫자(계산식·임계값·비율)도 새로 만들지 마라.
- 문서 근거가 있으면 관련 문장에 [C1] 형식으로 인용해 해석을 덧붙인다.

최근 이력 요약
- failure_history에서 조회된 고장 유형, 원인, 대응 조치, 반복 패턴만 bullet로 정리한다.
- SQL row 원문을 그대로 나열하지 않는다.
- 개별 row가 필요하더라도 최대 2개 이하의 예시만 요약 형태로 언급한다.

지금 점검할 일
- 사용자가 바로 실행할 수 있는 점검 순서를 3~5개로 작성한다.
- 공구, 스핀들, 쿨런트, 절삭 조건, 안전 확인 항목을 필요한 경우 포함한다.
- 위험한 직접 조작이나 안전 절차 생략을 지시하지 않는다.

문서 근거
- 문서 근거가 있는 경우 citation id를 포함해 작성한다. 예: [C1], [C2]
- 문서 근거가 부족한 경우에는 억지로 citation을 만들지 말고 “현재 검색된 문서 근거만으로는 단정하기 어렵습니다”라고 작성한다.

주의사항
- 진단 보조 한계, 현장 확인 필요성, 정지/재가동/정비 승인 주체를 간단히 안내한다.

최종 출력에는 자기검토 과정은 포함하지 말고, 사용자에게 보여줄 답변만 작성한다.
""".strip()

FINAL_ANSWER_USER_PROMPT = """
사용자 질문:
{user_question}

답변 대상:
{equipment_id}
(답변 대상은 내부 요약 기준이다. 제목에 그대로 복사하지 말고 자연스러운 한국어 제목으로 바꿔라.)

아래는 최종 답변 생성을 위해 정리된 answer_context이다.
이 정보 안에서만 답변하라. 없는 정보는 추정하지 말고 “확인 필요”라고 표현하라.

[답변 모드]
{answer_mode}

[섹션 작성 지침]
{section_guidance}

[현재 위험 진단 요약]
{prediction_summary}

[최근 이력 요약]
{history_summary}

[문서 근거 요약]
{evidence_summary}

[안전 판단 요약]
{safety_summary}

[사용 가능한 Citation 목록]
{citations}

위 정보를 바탕으로 사용자에게 보여줄 최종 답변만 작성하라.
artifact 이름, SQL row, JSON, 내부 처리 과정은 출력하지 마라.
""".strip()

def _answer_equipment_id(state: ManufacturingState, sql: Optional[SQLHistoryArtifact], packet: Optional[ContextPacket]) -> str:
    pred = state.get("prediction_result")
    if pred and sql:
        return "입력 피처와 과거 고장 이력"
    if pred:
        return "입력 피처 샘플"
    if sql:
        return "과거 고장 이력"
    return "제조 설비 점검"

def _answer_title_from_context(ctx: dict) -> str:
    subject = ctx.get("equipment_id") or ""
    if subject == "입력 피처와 과거 고장 이력":
        return "입력 피처 기반 위험 진단과 과거 고장 이력 요약"
    if subject == "입력 피처 샘플":
        return "입력 피처 기반 위험 진단 요약"
    if subject == "과거 고장 이력":
        return "과거 고장 이력 요약"
    return "제조 점검 답변 요약"

def _format_measured_values(machine_values: Optional[dict]) -> str:
    """진단에 사용된 실제 입력 측정값을 '라벨 값단위' 형태로 푼다."""
    if not machine_values:
        return ""
    _units = {"air_temperature": "K", "process_temperature": "K",
              "rotational_speed": "rpm", "torque": "N·m", "tool_wear": "분"}
    parts = []
    for k, v in machine_values.items():
        unit = getattr(v, "unit", None) or _units.get(k, "")
        val = getattr(v, "value", v)
        parts.append(f"{_label_feature(k)} {val}{unit}".strip())
    return ", ".join(parts)

def _prediction_summary_for_answer(pred: Optional[PredictionResult], machine_values: Optional[dict] = None) -> str:
    if not pred:
        return "현재 위험 진단은 이번 요청에서 별도로 수행되지 않음. 이 문장은 위험이 없다는 의미가 아니며, 위험 없음으로 표현하지 말 것."
    if pred.status == "NEEDS_INPUT":
        return "입력 부족: " + ", ".join(pred.missing_features or [])
    levels = [str(r.get("level", "")).lower() for r in (pred.risk_flags or [])]
    if "high" in levels:
        risk_level = "높음"
    elif "medium" in levels:
        risk_level = "중간"
    elif pred.risk_flags:
        risk_level = "낮음"
    else:
        risk_level = "뚜렷한 고위험 신호 없음"
    lines = [f"진단 상태: 완료, 현재 위험 수준: {risk_level}, 신뢰도: {pred.confidence}"]
    measured = _format_measured_values(machine_values)
    if measured:
        lines.append("사용된 입력 측정값: " + measured)
    if pred.summary:
        lines.append(pred.summary)
    if pred.risk_flags:
        brief = [f"{_label_failure_type(r.get('failure_type'))} {_risk_level_ko(r.get('level'))}"
                 f"(영향: {', '.join(_label_feature(x) for x in (r.get('contributing_features') or [])) or '확인 필요'})"
                 for r in pred.risk_flags]
        lines.append("감지된 위험: " + ", ".join(brief))
        lines.append("(고장 종류별 계산식·점검 체크리스트는 시스템이 정확한 수치로 자동 첨부하므로 본문에서 표로 반복하지 말 것)")
    if pred.context_mode in {"PATCH_ACTIVE", "USE_ACTIVE", "SELECT_HISTORY"}:
        if pred.changed_features:
            lines.append("변경 입력: " + ", ".join(_label_feature(x) for x in pred.changed_features))
        if pred.reused_features:
            lines.append("재사용한 진단 context feature: " + ", ".join(_label_feature(x) for x in pred.reused_features[:6]))
    if pred.limitations:
        lines.append("한계: " + "; ".join(pred.limitations[:3]))
    return "\n".join(lines)

def _sample_failure_rows(rows: list[dict]) -> list[str]:
    out = []
    for r in rows[:3]:
        dt = r.get("downtime_min")
        dt_s = f" · {dt}분" if str(dt or "").strip() not in ("", "None") else ""
        date = str(r.get("event_date") or "")[5:] or str(r.get("event_date") or "")
        sym = str(r.get("symptom") or r.get("corrective_action") or "").strip()
        out.append(f"{date} {_short_failure(r.get('failure_type'))} {_label_component(r.get('component'))}{dt_s} — {sym}")
    return out

def _format_counter(counter: Counter, unit: str = "건", limit: int = 5) -> str:
    if not counter:
        return "확인 필요"
    return ", ".join(f"{name} {count}{unit}" for name, count in counter.most_common(limit))

def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def _history_result_summary(query_type: Optional[str], rows: list[dict], status: str) -> str:
    qtype = query_type or "history"
    if not rows:
        return "• 조건에 맞는 이력 없음"
    if qtype in {"similar_incidents", "failure_history"}:
        failure_types = Counter(_short_failure(r.get("failure_type")) for r in rows if r.get("failure_type"))
        components = Counter(_label_component(r.get("component")) for r in rows if r.get("component"))
        actions = []
        for row in rows:
            a = str(row.get("corrective_action") or "").strip()
            if a and a not in actions:
                actions.append(a)
            if len(actions) >= 3:
                break
        downtimes = [_to_int(r.get("downtime_min"), 0) for r in rows if str(r.get("downtime_min") or "").strip() not in ("", "None")]
        head = f"총 {len(rows)}건"
        if downtimes:
            head += f" · 다운타임 {sum(downtimes)}분(평균 {round(sum(downtimes) / len(downtimes))}분)"
        lines = [head,
                 f"• 유형: {_format_counter(failure_types)}",
                 f"• 영역: {_format_counter(components)}"]
        samples = _sample_failure_rows(rows[:3])
        if samples:
            lines.append("• 대표 사례:")
            lines.extend(f"   - {s}" for s in samples)
        if actions:
            lines.append("• 대표 조치: " + " · ".join(actions))
        preventions = []
        for row in rows:
            p = str(row.get("preventive_action") or "").strip()
            if p and p not in preventions:
                preventions.append(p)
            if len(preventions) >= 3:
                break
        if preventions:
            lines.append("• 재발 방지: " + " · ".join(preventions))
        return "\n".join(lines)
    if qtype == "corrective_actions":
        items = []
        for row in rows:
            it = f"{_short_failure(row.get('failure_type'))}: {row.get('corrective_action')} (예방: {row.get('preventive_action')})"
            if it not in items:
                items.append(it)
            if len(items) >= 4:
                break
        return "유형별 대응 방식\n" + "\n".join(f"• {it}" for it in items)
    if qtype == "repeated_patterns":
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            ft = _short_failure(row.get("failure_type"))
            slot = grouped.setdefault(ft, {"cases": 0, "downtime": 0, "components": Counter()})
            slot["cases"] += _to_int(row.get("case_count"), 1)
            slot["downtime"] += _to_int(row.get("total_downtime_min"), 0)
            if row.get("component"):
                slot["components"][_label_component(row.get("component"))] += _to_int(row.get("case_count"), 1)
        patterns = []
        for ft, data in sorted(grouped.items(), key=lambda kv: (-kv[1]["cases"], -kv[1]["downtime"], kv[0]))[:5]:
            patterns.append(f"{ft}: {data['cases']}건 · 다운타임 {data['downtime']}분 · 주요 영역 {_format_counter(data['components'], limit=2)}")
        return "반복 패턴\n" + "\n".join(f"• {p}" for p in patterns) if patterns else f"• {len(rows)}건 조회됨"
    return f"• {len(rows)}건 조회됨"

def _history_summary_for_answer(sql: Optional[SQLHistoryArtifact]) -> str:
    if not sql:
        return "확인된 최근 이력 없음"
    if sql.status == "INVALID_REQUEST":
        return sql.summary or "이력 조회 조건이 부족함"
    if sql.status == "EMPTY":
        return "조건에 맞는 과거 이력은 조회되지 않음"
    if sql.status in {"BLOCKED", "FAIL"}:
        return "이력 조회 실패 또는 정책 차단: " + (sql.error_message or sql.summary or "확인 필요")
    lines = []
    results = getattr(sql, "results", []) or []
    if results:
        by_type = {}
        for r in results:
            by_type.setdefault(r.query_type, r)
        primary = by_type.get("failure_history") or by_type.get("similar_incidents")
        if primary:
            lines.append(_history_result_summary(primary.query_type, primary.rows or [], primary.status))
        if "repeated_patterns" in by_type:
            rp = by_type["repeated_patterns"]
            lines.append(_history_result_summary("repeated_patterns", rp.rows or [], rp.status))
        if not primary and "corrective_actions" in by_type:
            ca = by_type["corrective_actions"]
            lines.append(_history_result_summary("corrective_actions", ca.rows or [], ca.status))
    elif sql.rows:
        lines.append(_history_result_summary(sql.query_type, sql.rows, sql.status))
    else:
        lines.append(sql.summary or "조건에 맞는 이력 없음")
    if sql.limitations:
        lines.append("조회 한계: " + "; ".join(sql.limitations[:3]))
    return "\n".join(lines)

def _citation_list_for_answer(citations: list[dict]) -> str:
    if not citations:
        return "사용 가능한 citation 없음"
    return "\n".join(f"[{c.get('citation_id') or f'C{idx}'}] {c.get('title') or _citation_display_name(c)}" for idx, c in enumerate(citations[:5], start=1))

def _evidence_summary_for_answer(ev: Optional[EvidenceArtifact]) -> str:
    if not ev:
        return "확인된 문서 근거 없음"
    if ev.status == "OK":
        return ev.evidence_summary or "문서 근거는 검색됐지만 요약이 비어 있음"
    if ev.status == "LOW_RELEVANCE":
        limited = ev.evidence_summary or "현재 검색된 문서 근거의 관련성이 낮아 단정하기 어려움"
        return limited + " citation은 참고용이며, 추가 문서 확인이 필요함."
    if ev.status == "EMPTY":
        return "현재 검색된 문서 근거만으로는 단정하기 어려움"
    return "문서 근거 조회 실패: " + ("; ".join(ev.limitations[:3]) or "문서 근거를 가져오지 못했습니다.")

def _answer_mode(pred: Optional[PredictionResult], sql: Optional[SQLHistoryArtifact], ev: Optional[EvidenceArtifact]) -> str:
    has_pred = pred is not None and pred.status not in {"SKIPPED"}
    has_sql = sql is not None
    has_evidence = ev is not None and ev.status in {"OK", "LOW_RELEVANCE", "EMPTY"}
    if has_pred and has_sql:
        return "COMBINED"
    if has_sql and has_evidence:
        return "HISTORY_WITH_EVIDENCE"
    if has_sql:
        return "SQL_ONLY"
    if has_pred and has_evidence:
        return "PREDICTION_WITH_EVIDENCE"
    if has_pred:
        return "PREDICTION_ONLY"
    if has_evidence:
        return "EVIDENCE_ONLY"
    return "GENERAL"

def _section_guidance_for_answer(mode: str, ev: Optional[EvidenceArtifact], citations: list[dict]) -> str:
    if mode == "SQL_ONLY":
        return (
            "최근 고장 이력 조회 답변이다. 섹션은 '조회 결과 요약', '반복 패턴/대응 방식', '해석상 주의사항'만 사용한다. "
            "현재 판단, 지금 점검할 일, 문서 근거 섹션은 만들지 않는다. "
            "점검 권고를 하더라도 SQL 이력에서 확인된 조치 패턴 수준으로만 표현한다."
        )
    if mode in {"COMBINED", "PREDICTION_WITH_EVIDENCE"}:
        return (
            "현재 위험 진단, 최근 이력 요약, 지금 점검할 일, 문서 근거, 주의사항 순서로 작성한다. "
            "문서 citation이 있으면 본문에 [C1] 형태로 표시하고, 없는 문서 근거를 새로 만들지 않는다."
        )
    if mode == "PREDICTION_ONLY":
        return "입력 피처 기반 위험 진단과 필요한 추가 입력/현장 확인만 작성한다. 과거 이력이나 문서 근거 섹션은 만들지 않는다."
    if mode == "EVIDENCE_ONLY":
        return "문서 근거와 점검 절차 중심으로 작성한다. 현재 위험 진단이나 과거 이력 섹션은 만들지 않는다."
    if mode == "HISTORY_WITH_EVIDENCE":
        return "고장 이력 요약과 문서 근거를 연결해 작성한다. 현재 위험 진단 섹션은 만들지 않는다."
    return "사용자 질문에 직접 답하되, 없는 artifact를 근거로 한 섹션은 만들지 않는다."

def _safety_summary_for_answer(state: ManufacturingState, pred: Optional[PredictionResult]) -> str:
    lines = []
    intake = state.get("intake_decision")
    if intake:
        lines.append(f"요청 안전 판정: {intake.safety_action}. {intake.safety_reason}")
    if pred and pred.safety_hints:
        for h in pred.safety_hints[:3]:
            required = ", ".join(h.required_checks or []) or "현장 확인 필요"
            avoid = ", ".join(h.avoid_actions or []) or "위험 작업 임의 진행 금지"
            lines.append(f"{h.risk_level}: {h.reason}; 필요 확인={required}; 회피={avoid}")
    lines.append("정지/재가동/정비 승인 여부는 현장 안전 책임자와 설비 담당자가 판단해야 함")
    return "\n".join(lines)

_RISK_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}

def _render_diagnosis_block(pred: Optional[PredictionResult]) -> str:
    """고장 종류별 근거(규칙/계산/영향 변수)를 결정적으로 렌더한다. 정상(낮음)은 한 줄로 접는다."""
    if not pred or not pred.risk_flags:
        return ""
    lines = ["고장 종류별 근거"]
    low = []
    for r in pred.risk_flags:
        lvl = str(r.get("level", "")).lower()
        if lvl == "low":
            low.append(_label_failure_type(r.get("failure_type")))
            continue
        emoji = _RISK_EMOJI.get(lvl, "•")
        drivers = " · ".join(_label_feature(x) for x in (r.get("contributing_features") or [])) or "확인 필요"
        lines.append(f"{emoji} {_label_failure_type(r.get('failure_type'))} — {_risk_level_ko(r.get('level'))}")
        if r.get("rule"):
            lines.append(f"   규칙 : {r['rule']}")
        if r.get("formula") or r.get("detail"):
            lines.append(f"   계산 : {r.get('formula') or r.get('detail')}")
        lines.append(f"   영향 변수 : {drivers}")
    if low:
        lines.append("🟢 정상(현재 위험 낮음): " + ", ".join(low))
    return "\n".join(lines)

def _render_checklist(pred: Optional[PredictionResult]) -> str:
    """위험 높은 순으로 권장 점검을 중복 없이 모아 체크리스트로 렌더한다."""
    if not pred or not pred.risk_flags:
        return ""
    seen, items = set(), []
    for r in pred.risk_flags:
        for chk in (r.get("recommended_checks") or []):
            if chk and chk not in seen:
                seen.add(chk)
                items.append(chk)
    if not items:
        return ""
    return "지금 점검할 일\n" + "\n".join(f"{i}. {it}" for i, it in enumerate(items[:4], 1))

def _ensure_diagnosis_block(answer: str, pred: Optional[PredictionResult]) -> str:
    """LLM 답변에 결정적 근거 블록/체크리스트가 없으면 정확한 수치로 덧붙인다(인용 [출처]보다 앞)."""
    if not pred or not pred.risk_flags:
        return answer
    out = (answer or "").rstrip()
    block = _render_diagnosis_block(pred)
    if block and "고장 종류별 근거" not in out:
        out += "\n\n" + block
    checklist = _render_checklist(pred)
    if checklist and "지금 점검할 일" not in out:
        out += "\n\n" + checklist
    return out

def build_answer_context(state: ManufacturingState) -> dict:
    pred = state.get("prediction_result")
    ev = state.get("evidence_bundle")
    sql = state.get("sql_result")
    packet = state.get("context_packet")
    citations = ev.citations if ev and ev.status in {"OK", "LOW_RELEVANCE"} else []
    mode = _answer_mode(pred, sql, ev)
    machine_values = packet.selected_machine_values if packet else None
    prediction_summary = _prediction_summary_for_answer(pred, machine_values) if pred else "이번 답변 모드에서는 현재 위험 진단 섹션을 만들지 않는다."
    evidence_summary = _evidence_summary_for_answer(ev) if ev else "이번 요청에서 문서 근거 artifact가 없으므로 문서 근거 섹션을 만들지 않는다."
    return {
        "user_question": state.get("user_message", ""),
        "equipment_id": _answer_equipment_id(state, sql, packet),
        "answer_mode": mode,
        "section_guidance": _section_guidance_for_answer(mode, ev, citations),
        "prediction_summary": prediction_summary,
        "history_summary": _history_summary_for_answer(sql),
        "evidence_summary": evidence_summary,
        "safety_summary": _safety_summary_for_answer(state, pred),
        "citations": _citation_list_for_answer(citations),
    }

def _fallback_final_answer(ctx: dict) -> str:
    title = _answer_title_from_context(ctx)
    if ctx.get("answer_mode") == "SQL_ONLY":
        return (
            f"{title}\n\n"
            f"조회 결과 요약\n- {ctx['history_summary']}\n\n"
            "해석상 주의사항\n- 이 요약은 저장된 failure_history 샘플 이력 기준입니다. 실제 정비 판단은 현장 점검과 담당자 승인 기준으로 확인해야 합니다."
        )
    return (
        f"{title}\n\n"
        f"현재 확인된 정보 기준으로 종합하면 다음과 같습니다. 단, 일부 판단은 추가 현장 확인이 필요합니다.\n\n"
        f"현재 판단\n- {ctx['prediction_summary']}\n\n"
        f"최근 이력 요약\n- {ctx['history_summary']}\n\n"
        "지금 점검할 일\n1. 공구 마모와 체결 상태를 확인합니다.\n2. 스핀들 진동, 온도, 런아웃을 확인합니다.\n3. 쿨런트 유량과 필터 상태를 확인합니다.\n4. 절삭 조건을 완화해 재현 여부를 확인합니다.\n5. 안전 절차와 담당자 승인 없이 재가동을 단정하지 않습니다.\n\n"
        f"문서 근거\n- {ctx['evidence_summary']}\n\n"
        f"주의사항\n- {ctx['safety_summary']}"
    )

def _localize_answer_terms(answer: str) -> str:
    out = answer
    feature_labels = {k: v for k, v in FEATURE_LABELS.items() if k != "type"}
    for raw, label in {**COMPONENT_LABELS, **feature_labels}.items():
        out = re.sub(rf"\b{re.escape(raw)}\b", label, out)
    phrase_replacements = {
        "Corrective Action": "시정 조치",
        "Preventive Action": "예방 조치",
        "Root Cause": "근본 원인",
        "Failure Type": "고장 유형",
        "Tooling": "공구",
        "tooling": "공구",
    }
    for raw, label in phrase_replacements.items():
        out = out.replace(raw, label)
    return out

def _clean_final_answer_format(answer: str) -> str:
    # Notebook 출력에서 보고서식 markdown heading marker가 과하게 보이지 않도록 정리한다.
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s+", "", answer or "")
    cleaned = cleaned.replace("시정 조치으로", "시정 조치로")
    cleaned = cleaned.replace("예방 조치으로", "예방 조치로")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _final_answer_quality_feedback(ctx: dict, answer: str) -> list[str]:
    issues: list[str] = []
    mode = ctx.get("answer_mode")
    if mode == "SQL_ONLY":
        banned_sections = ["현재 판단", "지금 점검할 일", "문서 근거"]
        leaked = [s for s in banned_sections if s in answer]
        if leaked:
            issues.append("SQL_ONLY 답변에는 다음 섹션을 만들지 마세요: " + ", ".join(leaked))
    if re.search(r"\bscore\b|점수\s*\(?\d", answer, re.I):
        issues.append("내부 score/점수 값을 노출하지 말고 높음/중간/낮음 정도로 표현하세요.")
    _leak_terms = list(COMPONENT_LABELS) + [t for t in FEATURE_LABELS if t != "type"]
    raw_terms = [t for t in _leak_terms if re.search(rf"\b{re.escape(t)}\b", answer)]
    if raw_terms:
        issues.append("raw schema 용어를 한국어 현장 용어로 풀어 쓰세요: " + ", ".join(sorted(set(raw_terms))[:6]))
    if ctx.get("citations") != "사용 가능한 citation 없음" and not re.search(r"\[C\d+\]", answer):
        issues.append("사용 가능한 citation이 있으면 관련 문장에 [C1] 형식으로 표시하세요.")
    if ctx.get("prediction_summary", "").startswith("입력 부족:") is False and "입력 부족" in answer:
        issues.append("입력 부족 상태가 아니므로 [입력 부족] 섹션이나 표현을 제거하세요.")
    if re.search(r"(?m)^\s*#{1,6}\s+", answer):
        issues.append("markdown # heading marker를 쓰지 말고 짧은 일반 섹션 제목으로 작성하세요.")
    if re.search(r"조정하여\s*테스트|바로\s*재가동|계속\s*운전", answer):
        issues.append("운전 조건 변경이나 테스트 수행을 직접 지시하지 말고 승인된 절차에서 검토할 항목으로 표현하세요.")
    return issues

def _ensure_citations_visible(answer: str, citations: list[dict]) -> str:
    if not citations:
        return answer
    if "[출처]" in answer:
        answer = re.split(r"\n\s*\[출처\]\s*", answer, maxsplit=1)[0].rstrip()
    return answer.rstrip() + "\n\n" + _format_citations(citations[:6])

def _ensure_missing_input_visible(answer: str, missing_inputs: list[str]) -> str:
    if not missing_inputs:
        return answer
    if "입력 부족" in answer or ("입력" in answer and any(term in answer for term in ["부족", "확인 필요", "추가 정보", "추가 입력"])):
        return answer
    missing_text = ", ".join(_label_feature(name) for name in missing_inputs)
    prefix = (
        "[입력 부족]\n"
        f"이번 질문에서 제공된 값만으로는 전체 위험 진단이 제한됩니다. 추가 입력이 필요합니다: {missing_text}.\n\n"
    )
    return prefix + answer.lstrip()

def _remove_false_missing_input_section(answer: str, missing_inputs: list[str]) -> str:
    if missing_inputs or "입력 부족" not in answer:
        return answer
    cleaned = re.sub(r"\n?\[입력 부족\]\s*\n.*?(?=\n(?:#{1,3}\s|[가-힣A-Za-z ]{2,20}\n)|\Z)", "\n", answer, flags=re.S).strip()
    return cleaned or answer

def _mark_final_task_pass(state: ManufacturingState) -> dict:
    plan = state.get("execution_plan")
    active = state.get("active_task_id")
    if not plan:
        return {}
    tasks = [t.model_copy(deep=True) for t in plan.tasks]
    changed = False
    for task in tasks:
        if task.task_type == "final_answer" and (task.task_id == active or task.status == "RUNNING"):
            task.status = "PASS"
            changed = True
    return {"execution_plan": plan.model_copy(update={"tasks": tasks})} if changed else {}

_SHORT_FT = {"OSF": "과부하", "TWF": "공구마모", "HDF": "열/냉각", "PWF": "전원/구동",
             "SAFETY_INTERLOCK": "안전 인터록"}

def _short_failure(code: Any) -> str:
    return _SHORT_FT.get(str(code), _label_failure_type(code))

def _verdict_banner(pred, sql, ev) -> str:
    """답변 맨 앞 한 줄 종합 판단(결정적)."""
    if pred and getattr(pred, "status", None) == "NEEDS_INPUT":
        return "ℹ️ 종합 판단: 입력 부족 — 정확한 진단을 위해 추가 데이터가 필요합니다."
    if pred and pred.risk_flags:
        levels = [str(r.get("level", "")).lower() for r in pred.risk_flags]
        lv, emo = ("높음", "🔴") if "high" in levels else ("중간", "🟡") if "medium" in levels else ("낮음", "🟢")
        types = [_short_failure(r.get("failure_type")) for r in pred.risk_flags
                 if str(r.get("level", "")).lower() in {"high", "medium"}]
        ts = " · ".join(dict.fromkeys(types)) or "주의 신호"
        return f"{emo} 종합 판단: 위험 {lv} — {ts}"
    if pred and getattr(pred, "status", None) in {"OK", "PARTIAL"}:
        return "🟢 종합 판단: 입력 기준 뚜렷한 고위험 신호 없음"
    if sql is not None:
        return "🗂 종합 판단: 과거 고장 이력 요약"
    if ev is not None:
        return "📄 종합 판단: 점검 문서 근거 요약"
    return "ℹ️ 종합 판단"

def _missing_block(pred) -> str:
    if not (pred and getattr(pred, "status", None) == "NEEDS_INPUT"):
        return ""
    miss = ", ".join(_label_feature(x) for x in (pred.missing_features or [])) or "추가 입력값"
    return ("추가로 필요한 입력\n"
            f"현재 입력만으로는 정확한 진단이 어렵습니다. 다음 값을 입력해 주세요: {miss}")

def _history_block(sql) -> str:
    if sql is None:
        return ""
    body = _history_summary_for_answer(sql)
    if not body:
        return ""
    return "과거 고장 이력\n" + body

def _evidence_block(ev) -> str:
    if not ev:
        return ""
    status = getattr(ev, "status", None)
    if status == "OK" and ev.evidence_summary:
        _parts = [p.strip() for p in ev.evidence_summary.split("\n") if p.strip()]
        _cited = [p for p in _parts if "[C" in p][:4]
        return "문서 근거\n" + ("\n".join(_cited) if _cited else ev.evidence_summary[:600])
    if status == "LOW_RELEVANCE":
        body = ev.evidence_summary or "검색된 문서의 관련성이 낮아 단정하기 어렵습니다."
        return "문서 근거\n" + body + "\n(관련성이 낮아 참고용입니다. 추가 문서 확인이 필요합니다.)"
    if status == "EMPTY":
        return "문서 근거\n현재 검색된 문서 근거만으로는 단정하기 어렵습니다."
    return ""  # FAIL → 섹션 생략

HEADLINE_SYS = (
    "너는 제조 진단 답변의 첫 요약 문장 작성자다. 주어진 진단/이력/문서 요지를 바탕으로, "
    "사용자가 가장 먼저 알아야 할 핵심과 가장 먼저 할 일을 1~2문장으로만 쓴다. "
    "표·수치 나열·체크리스트·섹션 제목은 쓰지 마라(뒤에 시스템이 정확한 수치로 붙인다). "
    "위험한 실행 지시(점검 없이 재가동 등)는 절대 하지 말고, 단정 대신 '확인 필요'·'점검 필요'로 표현한다. "
    "한국어 1~2문장만 출력하라."
)

def _headline(pred, sql, ev, user_q: str) -> str:
    facts = []
    if pred and pred.risk_flags:
        top = pred.risk_flags[0]
        facts.append(f"진단: {_short_failure(top.get('failure_type'))} 등 위험 {_risk_level_ko(top.get('level'))}")
    elif pred and getattr(pred, "status", None) == "NEEDS_INPUT":
        facts.append("진단: 입력 부족으로 추가 데이터 필요")
    if sql is not None:
        facts.append("과거 고장 이력 조회됨")
    if ev is not None and getattr(ev, "status", None) in {"OK", "LOW_RELEVANCE"}:
        facts.append("관련 문서 근거 있음")
    try:
        out = call_llm(HEADLINE_SYS, json.dumps({"질문": user_q, "요지": facts}, ensure_ascii=False), tier="default").strip()
        return out.split("\n")[0].strip() if out else ""
    except Exception:
        return ""

def final_answer_node(state: ManufacturingState) -> dict:
    # Intake Gate 차단 시: 차단 메시지를 그대로 최종 답변으로 반환
    dec = state.get("input_decision")
    if dec and dec.blocked:
        return {"final_answer": FinalAnswer(answer=dec.block_message or "요청을 처리할 수 없습니다.")}

    pred = state.get("prediction_result")
    ev = state.get("evidence_bundle")
    sql = state.get("sql_result")
    packet = state.get("context_packet")

    warnings: list[str] = list(packet.context_warnings) if packet else []
    intake = state.get("intake_decision")
    if intake and intake.output_constraints:
        warnings.extend(intake.output_constraints)
    for art in (pred, ev, sql):
        if art and getattr(art, "limitations", None):
            warnings.extend(art.limitations)
    missing = pred.missing_features if (pred and pred.status == "NEEDS_INPUT") else []
    citations = ev.citations if ev and ev.status in {"OK", "LOW_RELEVANCE"} else []

    # ===== 결정적 조립형 답변 틀 =====
    # 수치/판단은 코드가 고정 위치에 렌더하고, LLM은 헤드라인 1~2문장만 담당한다.
    sections = [_verdict_banner(pred, sql, ev)]
    headline = _headline(pred, sql, ev, state.get("user_message", ""))
    if headline:
        sections.append(headline)
    for block in (
        _missing_block(pred),
        _render_diagnosis_block(pred),   # 현재 위험 진단 (규칙/계산/영향 변수)
        _history_block(sql),             # 과거 고장 이력 (건수/유형/다운타임)
        _evidence_block(ev),             # 문서 근거 (citation-aware)
        _render_checklist(pred),         # 지금 점검할 일
        _format_citations(citations),    # [출처]
    ):
        if block:
            sections.append(block)
    _has_risk = bool(pred and pred.risk_flags and any(str(r.get("level", "")).lower() in {"high", "medium"} for r in pred.risk_flags))
    if _has_risk:
        sections.append("⚠ 규칙 기반 보조 진단이며, 정지·재가동·정비 승인 여부는 현장 안전 책임자와 설비 담당자가 판단해야 합니다.")
    else:
        sections.append("ℹ 보조 진단·조회 결과이며, 실제 조치는 현장 담당자 확인이 필요합니다.")

    answer = _clean_final_answer_format(_localize_answer_terms("\n\n".join(s for s in sections if s)))
    fa = FinalAnswer(answer=answer, citations=citations, warnings=warnings, missing_inputs=missing)
    updates = _mark_final_task_pass(state)
    updates["final_answer"] = fa
    return updates
print("final_answer_node artifact synthesis 정의 완료")
