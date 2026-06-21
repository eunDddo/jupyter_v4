# Manufacturing Agent v6 Notebook Guide

> 대상 파일: `manufacturing_agent_v6.ipynb`
> 기준: 2026-06-22
> 목적: 노트북을 위에서 아래로 실행하면서 현재 LangGraph 제조업 Agent 구조를 이해하고 검증하기 위한 가이드.

## 1. 현재 노트북의 한 줄 정의

`manufacturing_agent_v6.ipynb`는 ReAct Agent가 아니라 **Gate-driven Manufacturing Plan-and-Execute** 구조의 실행 가능한 노트북이다.

LLM이 자유롭게 tool을 반복 선택하지 않는다. `SupervisorPlanner`가 typed `ExecutionPlan`을 만들고, `OrchestratorDispatcher`가 task 상태와 gate report를 보고 다음 node를 결정한다.

```text
START
→ intake_gate
→ context_manager
→ supervisor_planner
→ orchestrator_dispatcher
   ├─ prediction_agent → prediction_gate → orchestrator_dispatcher
   ├─ sql_agent        → sql_gate        → orchestrator_dispatcher
   ├─ evidence_agent   → evidence_gate   → orchestrator_dispatcher
   ├─ supervisor_replanner → orchestrator_dispatcher
   └─ final_answer
→ output_safety_gate
→ memory_writer
→ END
```

## 2. 핵심 역할

| 컴포넌트 | 책임 | LLM 사용 |
|---|---|---:|
| `intake_gate` | 입력 가능성, 프롬프트 인젝션, 위험 실행 요청 1차 판정 | 사용 |
| `context_manager` | 현재 입력, checkpointer state, Store의 `DiagnosisContext`를 정리 | 사용 |
| `supervisor_planner` | 필요한 task와 `TaskSpec.params/success_criteria` 생성 | 사용 |
| `orchestrator_dispatcher` | task status, dependency, retry/replan route 관리 | 미사용 |
| `prediction_agent` | 현재 feature 또는 명시 재사용 context 기반 rule-based 위험 진단 | 미사용 |
| `sql_agent` | PydanticAI Text-to-SQL로 `failure_history` read-only 조회 | 사용 |
| `evidence_agent` | Chroma RAG, citation, 문서 근거 요약 | 사용 |
| worker gates | artifact 품질 검증과 `GateReport` 생성 | 미사용 |
| `supervisor_replanner` | gate가 요구한 실패 task만 patch하고 targeted rerun 유도 | 미사용 |
| `final_answer` | raw artifact를 사용자용 answer context로 압축해 최종 답변 작성 | 사용 |
| `output_safety_gate` | 최종 답변의 위험 실행 표현 deterministic/LLM 이중 검증 | 사용 |
| `memory_writer` | turn, artifact summary, reusable `DiagnosisContext`, run trace 저장 | 미사용 |

## 3. 예전 가이드와 달라진 점

| 이전 설명 | 현재 기준 |
|---|---|
| `InputGate`와 `SafetyGate` 분리 | 단일 `intake_gate`로 통합 |
| `Supervisor`가 다음 agent 선택 | `SupervisorPlanner`는 계획만 만들고 `OrchestratorDispatcher`가 실행 관리 |
| `SafetyAgent` worker 존재 | 별도 SafetyAgent 없음. 앞단 intake와 뒤단 output safety로 분리 |
| `session_id` 중심 | `thread_id`는 checkpointer, `user_id`는 Store namespace |
| 이전 feature 자동 병합 | 금지. `ContextMode`로 명시 재사용 여부 결정 |
| StubLLM/offline fallback | 실제 LLM 실행을 전제로 함. 키가 없으면 명시 실패 |
| 설비별 로그 SQL 조회 | 현재 SQL은 `failure_history` 기반 고장 사례 조회 |

## 4. 메모리와 컨텍스트

현재 구조는 Checkpointer와 Store를 분리한다.

| 계층 | 기준 ID | 역할 |
|---|---|---|
| LangGraph checkpointer | `thread_id` | 같은 대화 흐름의 GraphState 저장/복구 |
| `ConversationStore` | `user_id + thread_id` | turn, active/recent `DiagnosisContext`, artifact summary 저장 |
| `RunStore` | `request_id`, `thread_id`, `user_id` | gate report, retry/replan 등 실행 관측 저장 |
| ChromaDB | query / metadata | 문서 RAG 검색 |
| SQLite history DB | SQL policy | `failure_history` read-only 조회 |

`ContextManager`는 이전 feature 값을 현재 입력에 자동 보완하지 않는다.

```text
CURRENT_ONLY      현재 입력만 사용
USE_ACTIVE        active DiagnosisContext 그대로 사용
PATCH_ACTIVE      active context 하나를 base로 잡고 현재 변경값만 patch
SELECT_HISTORY    최근 context 중 하나만 선택
REFER_ACTIVE_RESULT 이전 artifact를 참고하되 prediction input으로 재사용하지 않음
```

예를 들어 “토크 60만 있는데 위험해?”는 `CURRENT_ONLY`가 맞다. 이전 rpm, 온도, 공구마모를 몰래 섞지 않는다. “토크만 60으로 바꿔서 다시 봐줘”처럼 명시적으로 이전 조건을 참조할 때만 `PATCH_ACTIVE`를 쓴다.

## 5. SQL Agent

`sql_agent`는 PydanticAI Text-to-SQL 전용 worker다.

- SQL 전체 생성은 PydanticAI structured output으로 수행한다.
- 실행 전 `validate_sql_query()`와 `EXPLAIN QUERY PLAN`으로 검증한다.
- 쓰기 SQL, DDL, PRAGMA, 다중 statement는 금지한다.
- 실행은 SQLite read-only로 제한한다.
- 실패는 template fallback으로 숨기지 않고 `SQLHistoryArtifact.status`에 남긴다.

주요 query type:

```text
failure_history
similar_incidents
corrective_actions
repeated_patterns
```

## 6. RAG와 Citation

`evidence_agent`는 검색 결과 품질을 상태로 구분한다.

| 상태 | 의미 |
|---|---|
| `OK` | 관련 문서와 citation을 확보 |
| `EMPTY` | 검색 결과 없음 |
| `LOW_RELEVANCE` | 결과는 있으나 score가 낮아 근거로 단정하기 어려움 |
| `FAIL` | 검색/요약 처리 실패 |

문서가 0건이면 summary LLM을 호출하지 않는다. retrieved document 안에 prompt injection성 문구가 있으면 summary LLM에 지시문처럼 전달하지 않도록 sanitize한다.

citation에는 최소한 다음 metadata가 포함된다.

```text
source_id, source, type, chunk_index, snippet, score, security_flags
```

## 7. 노트북 섹션 맵

| 섹션 | 내용 |
|---|---|
| 0 | 설치와 환경 |
| 1 | 설정, LLM adapter, 모델/경로 상수 |
| 2 | Pydantic contracts와 `ManufacturingState` |
| 3 | `ConversationStore`, `RunStore`, SQLite history schema |
| 4 | ChromaDB RAG runtime |
| 5 | Context extraction, carryover, `ContextResolution` |
| 6 | Prediction/RAG/SQL helper service |
| 7 | Worker agents |
| 8 | Gates |
| 9 | FinalAnswer와 MemoryWriter |
| 10 | `context_manager` node |
| 11 | SupervisorPlanner, OrchestratorDispatcher, SupervisorReplanner, graph assembly |
| 12 | SQLite checkpointer와 app compile |
| 13 | 그래프 시각화 |
| 14 | `run_turn`, `resume_turn`, debug helper |
| 15 이후 | 노트북 smoke/구조 검증 T01~T22 |

## 8. 실행 함수

새 요청:

```python
run_turn(
    user_message,
    user_id,
    thread_id,
    request_id,
    input_features=None,
    debug=False,
)
```

중단된 같은 thread 이어 실행:

```python
resume_turn(
    user_id,
    thread_id,
    request_id="resume",
    debug=False,
)
```

표준 config:

```python
config = {
    "configurable": {
        "thread_id": thread_id,
        "user_id": user_id,
    },
    "metadata": {
        "run_id": request_id,
        "source": "notebook",
    },
    "tags": ["manufacturing-agent"],
}
```

`RunnableConfig.configurable`에는 feature 값, SQL 결과, RAG 결과, prediction artifact를 넣지 않는다. 도메인 데이터는 GraphState 또는 Store에 둔다.

## 9. 검증 셀

노트북 하단은 scenario abstraction 없이 `run_turn(...)` / `resume_turn(...)` 기반으로 직접 확인한다.

```text
T01~T22: 노트북에서 직접 실행 가능한 smoke/structural cells

T01~T17: 사용자 흐름과 멀티턴 동작 확인
T18: 구조 경계 검증
T19: Text-to-SQL / RAG 품질 검증
T20: Gate-driven targeted replan 검증
T21: broad problem lookup context 오염 방지 검증
T22: SQLite checkpoint resume 검증
```

전체 자동 회귀 검증은 Python runner가 담당한다.

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py --json --full-answer
```

## 10. 운영상 주의

- `orchestrator_dispatcher`에 LLM 호출을 넣지 않는다.
- Worker가 최종 답변을 직접 만들지 않는다.
- Gate가 worker를 직접 재실행하지 않는다.
- 이전 feature를 feature별 최신값으로 자동 병합하지 않는다.
- SQL 실패를 deterministic template fallback으로 조용히 숨기지 않는다.
- Evidence가 부족하면 부족하다고 말한다.
- FinalAnswer에는 raw SQL row, JSON, 내부 state, debug trace를 그대로 출력하지 않는다.
- 안전장치 우회, 경고 무시, 점검 없는 재가동 승인 표현은 최종 출력에서 차단한다.
