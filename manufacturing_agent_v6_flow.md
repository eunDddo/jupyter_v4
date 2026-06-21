# Manufacturing Agent v6 전체 흐름 정리

이 문서는 `manufacturing_agent_v6.ipynb` 기준의 현재 LangGraph 제조업 Agent 구조를 설명한다. 핵심은 ReAct가 아니라 `TaskPlan` 기반의 Graph-based Orchestrator-Worker 구조다. LLM은 자유롭게 tool을 반복 선택하지 않고, 정해진 graph node 안에서 typed decision, 근거 요약, safety 판단 등에 제한적으로 사용된다. 테스트 통과를 위해 특정 시나리오를 고정 문구로 덮어쓰는 방식은 사용하지 않는다. gate가 실패하면 실패 상태와 reason을 남기는 것을 우선한다.

## 1. 전체 실행 흐름

```text
START
→ intake_gate
→ context_manager
→ task_planner
→ orchestrator_dispatcher
   ├─ prediction_agent → prediction_gate → orchestrator_dispatcher
   ├─ sql_agent        → sql_gate        → orchestrator_dispatcher
   ├─ evidence_agent   → evidence_gate   → orchestrator_dispatcher
   └─ final_answer
→ output_safety_gate
→ memory_writer
→ END
```

예외 흐름:

- `intake_gate`가 입력을 차단하면 `context_manager`로 가지 않고 바로 `final_answer`로 이동한다.
- 각 worker는 직접 최종 답변을 만들지 않고 typed artifact만 생성한다.
- 각 gate는 worker를 직접 재실행하지 않고 `GateReport`만 남긴다.
- 재실행 여부와 다음 node 선택은 `orchestrator_dispatcher`가 `ExecutionPlan`, task status, `GateReport`, retry count를 보고 결정한다.

## 2. 현재 구조 판정: 오케스트레이터인가?

결론부터 말하면, 현재 `manufacturing_agent_v6.ipynb`는 단순 Router가 아니라 **단일 계층 Graph-based Orchestrator-Worker 구조**로 보는 것이 맞다.

다만 아직 **Hierarchical Supervisor**나 **LLM Compiler 기반 병렬 fan-out 구조**까지 구현된 것은 아니다. 현재 구조는 `task_planner`가 task를 만들고, `orchestrator_dispatcher`가 graph route를 순차적으로 결정하며, 각 worker와 gate가 artifact/report를 주고받는 단일 orchestrator 구조다.

### 2.1 Orchestrator로 볼 수 있는 이유

현재 구조가 Router가 아니라 Orchestrator인 이유는 다음과 같다.

| 판정 기준 | 현재 구현 여부 | 근거 |
|---|---:|---|
| 요청을 task로 분해한다 | 예 | `task_planner`가 `prediction`, `sql`, `evidence`, `final_answer` task를 만든다 |
| task 상태를 가진다 | 예 | `ExecutionPlan.tasks[*].status`가 `PENDING`, `PASS`, `FAIL`, `NEEDS_USER_INPUT` 등을 가진다 |
| worker artifact를 수집한다 | 예 | `prediction_result`, `evidence_bundle`, `sql_result`, `artifacts`에 typed artifact 저장 |
| gate 결과를 반영한다 | 예 | `prediction_gate`, `sql_gate`, `evidence_gate`, `output_safety_gate`가 `GateReport`를 남긴다 |
| retry/recovery를 graph 레벨에서 판단한다 | 예 | gate가 직접 재실행하지 않고 `orchestrator_dispatcher`가 retry 여부와 다음 route를 결정한다 |
| worker가 최종 답변을 직접 만들지 않는다 | 예 | worker는 artifact만 만들고, `final_answer`가 조합한다 |
| LLM이 매번 자유롭게 다음 tool을 고르지 않는다 | 예 | `orchestrator_dispatcher`는 LLM을 쓰지 않는 deterministic state manager다 |

따라서 현재 구조는 다음으로 분류하는 것이 가장 정확하다.

```text
Custom LangGraph Workflow
+ TaskPlan-based Orchestrator
+ Worker Subgraphs/Nodes
+ Evaluator Gates
+ Typed Artifacts
+ SQL/RAG/Prediction specialized workers
```

### 2.2 단순 Router가 아닌 이유

단순 Router라면 `supervisor` 또는 `router`가 매번 `next_node` 하나만 고르고 끝난다.

현재 구조는 다르다.

- `next_node`를 직접 고르는 것이 아니라 `ExecutionPlan`의 task 상태를 기준으로 다음 실행을 결정한다.
- `prediction`, `sql`, `evidence`가 모두 필요한 복합 질문이면 여러 worker를 순차 실행한다.
- worker 완료 여부는 artifact 존재 여부가 아니라 gate report와 task status로 판단한다.
- 실패한 worker는 gate가 아니라 dispatcher가 retry/recovery 대상으로 본다.
- 최종 답변 진입은 “어떤 artifact가 생겼는가”가 아니라 “필수 task가 완료/차단/입력요청 상태로 수렴했는가”에 의해 결정된다.

즉 현재 `orchestrator_dispatcher`는 단순 routing 함수가 아니라 **task lifecycle manager**에 가깝다.

### 2.3 God Supervisor가 아닌 이유

현재 구조는 God Supervisor도 아니다.

God Supervisor라면 supervisor가 다음을 모두 직접 판단하거나 생성한다.

- 위험 진단
- 문서 검색
- SQL 생성/실행
- safety 판단
- 최종 답변 생성
- retry 판단

현재는 책임이 분리되어 있다.

| 책임 | 담당 |
|---|---|
| 요청 intake와 1차 안전 판단 | `intake_gate` |
| task 생성 | `task_planner` |
| route와 task 상태 전이 | `orchestrator_dispatcher` |
| rule-based 위험 진단 | `prediction_agent` |
| 정형 이력 조회 | `sql_agent` |
| 문서 RAG와 citation | `evidence_agent` |
| artifact 품질 검증 | 각 worker별 gate |
| 최종 답변 조합 | `final_answer` |
| 답변 표현 안전성 검사 | `output_safety_gate` |
| 장기 저장 | `memory_writer` |

따라서 중앙 orchestrator는 “모든 판단을 직접 수행하는 agent”가 아니라 “task 상태와 route를 관리하는 graph controller”로 제한되어 있다.

### 2.4 ReAct 구조가 아닌 이유

현재 구조는 ReAct Agent가 아니다.

- LLM이 `thought → action → observation` 루프를 돌지 않는다.
- LLM이 임의의 tool을 반복 선택하지 않는다.
- tool 결과를 보고 같은 LLM agent가 계속 다음 tool을 고르는 구조가 아니다.
- 실행 가능한 node는 LangGraph edge와 `TASK_TO_NODE` mapping 안에 제한된다.
- task retry도 LLM tool loop가 아니라 gate report와 retry count로 제어된다.

LLM은 다음 위치에서만 typed decision 또는 요약에 사용된다.

- `intake_gate`: 요청 처리 가능 여부와 위험 요청 판단
- `context_manager`: 멀티턴 context carryover 판단
- `task_planner`: 필요한 task 목록 판단
- `sql_agent`: SQL intent 및 Pydantic AI SQL agent 실행
- `evidence_agent`: 검색 문서 요약
- `output_safety_gate`: 최종 답변 안전성 판단

### 2.5 아직 부족한 점

현재 구조는 오케스트레이터 구조로 볼 수 있지만, 다음 한계가 남아 있다.

| 항목 | 현재 상태 | 개선 방향 |
|---|---|---|
| 병렬 실행 | 아직 순차 dispatcher 중심 | `prediction`, `sql`, `evidence` dependency가 없을 때 LangGraph fan-out 병렬화 가능 |
| Hierarchical Supervisor | 아님 | SQL/RAG/Safety가 더 커지면 각 subgraph 내부에 local planner/gate 추가 |
| LLM Compiler | 전체 구조에는 미적용 | evidence query expansion, SQL multi-query planning 같은 제한 영역에만 적용 가능 |
| state 직렬화 | Pydantic 객체가 checkpointer warning 유발 | state에는 dict 저장, node 진입 시 Pydantic 재검증 |
| quality evaluation | gate 중심 | 답변 품질용 `quality_gate`를 별도 추가 가능 |
| recovery 정책 | 기본 retry 중심 | retry 실패 시 제한 답변, 추가 입력 요청, escalation policy를 더 명확히 분리 |

정리하면, 현재 구조는 **Router Pattern을 넘어선 Orchestrator-Worker 구조**가 맞다. 다만 “고도화된 계층형 멀티 에이전트 시스템”이라기보다는, 현 시점에서는 **명시적 LangGraph workflow 위에 TaskPlan 기반 orchestrator를 얹은 1단계 실무형 구조**로 보는 것이 가장 정확하다.

## 3. 주요 저장 계층

| 저장 위치 | 용도 | 대표 데이터 |
|---|---|---|
| LangGraph `state` | 한 번의 graph 실행 중 노드 간 공유되는 working memory | `context_packet`, `execution_plan`, `prediction_result`, `evidence_bundle`, `sql_result`, `gate_reports`, `final_answer` |
| `artifacts` dict in state | 장기적으로 worker 산출물을 통합 관리하기 위한 표준 artifact map | `artifacts["prediction"]`, `artifacts["evidence"]`, `artifacts["sql"]` |
| LangGraph `messages` | checkpointer가 복원할 수 있는 대화 메시지 히스토리 | `HumanMessage`, `AIMessage` |
| `ConversationStore` SQLite | 도메인 장기 메모리 | user/assistant turn, thread별 설비 feature, prediction/evidence/sql 요약 |
| `RunStore` SQLite | 실행 관측/감사 로그 | `request_id`, `user_id`, `thread_id`, gate report, retry count |
| LangGraph checkpointer | 동일 `thread_id` 세션의 working state 복원 | graph state snapshot |
| Chroma Vector DB | 문서 RAG 검색 인덱스 | Haas/OSHA/KOSHA 문서 chunk, embedding |
| SQLite history DB | 제조 이력 조회용 정형 DB | `maintenance_history`, `alarm_logs`, `sensor_readings`, `failure_incidents` |

현재 SQLite mock 데이터 건수:

```text
maintenance_history: 24
alarm_logs: 24
sensor_readings: 30
failure_incidents: 17
```

## 4. State 구조

`ManufacturingState`는 `MessagesState`를 상속한다. 즉, LangGraph의 `messages` 누적 기능을 그대로 사용하면서 제조 도메인 필드를 추가한다.

주요 필드:

| State 필드 | 의미 |
|---|---|
| `request_id`, `thread_id`, `user_id` | 실행/세션/사용자 식별자 |
| `user_message` | 현재 사용자 질문 |
| `input_features` | 프론트나 테스트에서 들어온 구조화 설비 feature |
| `input_decision`, `input_flags`, `intake_decision` | intake 단계의 입력/안전 판단 결과 |
| `context_packet` | 현재 요청에 사용할 압축 context |
| `agent_contexts` | worker별로 포장된 context |
| `execution_plan` | task 목록과 상태를 담은 실행 계획 |
| `task_planner_decision` | LLM task planner의 typed decision |
| `sql_intent_decision` | SQL Agent 실행 전 LLM SQL intent 판단 |
| `orchestrator_decision`, `active_task_id`, `route` | dispatcher의 다음 실행 판단 |
| `prediction_result` | prediction worker의 rule-based 위험 진단 artifact |
| `evidence_bundle` | RAG 문서 근거 artifact |
| `sql_result` | SQL 이력 조회 artifact |
| `artifacts` | worker artifact 통합 저장소 |
| `gate_reports` | 각 gate의 PASS/FAIL/RETRY 판단 |
| `retry_counts` | worker별 실행 횟수 |
| `final_answer` | 최종 답변 artifact |
| `run_trace` | 실행 추적 확장용 필드 |

## 5. Node별 역할, LLM 사용, 저장 위치

| Node | 역할 | LLM 사용 | State 저장 | Store/DB 저장 |
|---|---|---:|---|---|
| `intake_gate` | 입력 공백, 프롬프트 인젝션, 제조 도메인 여부, 위험 실행 요청을 1차 판정 | 사용함. `_llm_intake()`가 `IntakeDecision` 생성. 단, injection/위험 실행 backstop은 deterministic guardrail도 사용 | `input_decision`, `input_flags`, `intake_decision`, `gate_reports`, 통과 시 `messages`에 user message | 없음 |
| `context_manager` | 장기 메모리와 checkpointer message를 읽어 현재 요청용 context 구성 | 사용함. `_llm_context_carryover()`가 멀티턴 후속 질문과 이전 artifact 참조 여부 판단 | `context_packet`, `agent_contexts` | `ConversationStore`에서 최근 turn, feature, summary 조회 |
| `task_planner` | 사용자 요청을 `prediction`, `sql`, `evidence`, `final_answer` task로 분해 | 사용함. `_llm_task_planner_decision()`와 validator LLM이 `TaskPlannerDecision` 생성/검증 | `execution_plan`, `task_planner_decision`, `active_task_id`, `artifacts`, `intent` | 없음 |
| `orchestrator_dispatcher` | task 상태, dependency, gate report, retry count를 보고 다음 worker route 결정 | 사용하지 않음. deterministic state manager | `execution_plan`, `orchestrator_decision`, `active_task_id`, `route`, `agent_feedback` | 없음 |
| `prediction_agent` | ML이 아니라 rule-based diagnostic / partial risk assessment 수행 | 사용하지 않음. summary도 deterministic 문장 생성 | `prediction_result`, `artifacts["prediction"]` | 없음 |
| `prediction_gate` | `PredictionResult` 존재 여부, status, 입력 부족 여부 검증 | 사용하지 않음 | `gate_reports` | 없음 |
| `sql_agent` | Pydantic AI 기반 SQL Agent adapter를 통해 정형 이력 조회 | 사용함. `_llm_sql_intent_decision()`이 query type/machine/time/filter 판단. Pydantic AI SQL agent도 LLM 기반 | `sql_result`, `sql_intent_decision`, `artifacts["sql"]` | SQLite history DB 조회 |
| `sql_gate` | SQL artifact와 SQL 안전 정책 검증 | 사용하지 않음 | `gate_reports` | 없음 |
| `evidence_agent` | Chroma RAG 검색, citation 생성, 문서 근거 요약 | 사용함. 검색 자체는 deterministic RAG, 요약은 LLM | `evidence_bundle`, `artifacts["evidence"]` | Chroma Vector DB 조회 |
| `evidence_gate` | 문서 근거 artifact 품질 검증. 명시적 근거 요청인데 EMPTY면 retry 유도 | 사용하지 않음 | `gate_reports` | 없음 |
| `final_answer` | prediction/evidence/sql artifact를 조합해 최종 답변 생성. SQL은 `summary`가 아니라 `rows/results`를 직접 읽어 query type별 판단을 작성 | 사용하지 않음. 현재는 artifact 기반 deterministic synthesis | `final_answer`, final task status update | 없음 |
| `output_safety_gate` | 최종 답변 직후 위험 실행 표현, 안전장치 우회, 과신 표현을 검사하고 차단 여부를 기록 | 사용함. `_llm_output_safety()`가 `OutputSafetyDecision` 생성 | `final_answer` 갱신 가능, `gate_reports` | 없음 |
| `memory_writer` | 대화, 현재 feature, artifact 요약, 실행 trace 저장 | 사용하지 않음 | `messages`에 assistant answer 추가 | `ConversationStore`, `RunStore`에 저장 |

## 6. Intake와 Output Safety의 분리

현재 구조는 초반 `input_gate`와 `safety_gate`를 하나의 `intake_gate`로 합쳤다.

`intake_gate` 책임:

- 빈 입력 차단
- 프롬프트 인젝션 차단
- 제조 도메인 여부 판단
- 위험 실행 요청인지 판단
- 안전 자문으로 답변 가능한 질문인지 판단
- 통과/차단 결과를 `InputDecision`, `IntakeDecision`, `GateReport`로 남김

`output_safety_gate` 책임:

- 이미 생성된 `final_answer.answer`만 검사
- 점검 없는 재가동 승인, 안전장치 우회, 알람 무시 운전 같은 위험 표현 억제
- 차단 시 `GateReport`에 `BLOCK`과 reason을 남김
- LLM이 안전한 대체 답변을 제공한 경우에만 답변 교체를 시도하며, 테스트 통과 목적의 시나리오별 고정 치환은 하지 않음

즉, 앞단은 “요청을 처리해도 되는가”를 보고, 뒷단은 “생성된 답변 표현이 안전한가”를 본다.

## 7. Context 전달 방식

`context_manager`는 세 출처를 합쳐 `ContextPacket`과 `agent_contexts`를 만든다.

1. 현재 입력
   - `user_message`
   - `input_features`
   - 자연어에서 추출한 설비 feature

2. 장기 메모리
   - `ConversationStore.recent_turns()`
   - `ConversationStore.latest_machine_values()`
   - `ConversationStore.latest_summary(kind="prediction"|"evidence"|"sql")`

3. checkpointer message
   - `state["messages"]`에서 최근 `HumanMessage`/`AIMessage`를 추출
   - 장기 store의 recent turns에 보조적으로 합침

LLM은 여기서 `ContextCarryoverDecision`을 만든다. 예를 들어 “그 알람”, “방금 근거”, “같은 설비” 같은 후속 질문이 이전 SQL/evidence/prediction artifact를 참조하는지 판단한다.

## 8. TaskPlan과 Orchestrator

`task_planner`는 LLM으로 `TaskPlannerDecision`을 생성한다.

예시:

```json
{
  "intent": "combined_analysis",
  "needs_prediction": true,
  "needs_evidence": true,
  "needs_sql": true,
  "evidence_required": true,
  "sql_query_intents": ["similar_incidents", "maintenance_history"],
  "evidence_focus": ["점검 문서 근거", "해결 방법"]
}
```

이 decision은 `ExecutionPlan`으로 변환된다.

```text
prediction_1: PENDING
sql_1: PENDING
evidence_1: PENDING
final_1: PENDING, depends_on=[prediction_1, sql_1, evidence_1]
```

`orchestrator_dispatcher`는 LLM을 쓰지 않는다. 다음만 수행한다.

- 마지막 `GateReport`를 `ExecutionPlan.tasks[*].status`에 반영
- `RETRYABLE_FAIL`이면 retry count를 올리고 task를 `PENDING`으로 되돌림
- dependency가 충족된 다음 `PENDING` task를 선택
- `TASK_TO_NODE` mapping으로 route 결정
- 실행 가능한 worker가 없으면 `final_answer`로 보냄

## 9. Worker Artifact

### 9.1 PredictionResult

생성 node: `prediction_agent`

저장 위치:

- `state["prediction_result"]`
- `state["artifacts"]["prediction"]`

주요 내용:

- `status`: `OK`, `PARTIAL`, `NEEDS_INPUT`, `SKIPPED`, `FAIL`
- `available_features`, `missing_features`
- `risk_flags`
- `failure_types`
- `cause_features`
- `evidence_hints`
- `safety_hints`
- `used_stale_features`
- `summary`

주의:

- 이름은 `prediction`을 유지하지만 ML 예측이 아니다.
- 현재는 rule-based diagnostic / partial risk assessment다.

### 9.2 EvidenceArtifact

생성 node: `evidence_agent`

저장 위치:

- `state["evidence_bundle"]`
- `state["artifacts"]["evidence"]`

주요 내용:

- `status`: `OK`, `EMPTY`, `LOW_RELEVANCE`, `FAIL`
- `retrieval_profile`
- `queries`
- `documents`
- `citations`
- `evidence_summary`
- `limitations`

RAG source:

- Chroma Vector DB
- 문서 원천: Haas, OSHA, KOSHA 등

### 9.3 SQLHistoryArtifact

생성 node: `sql_agent`

저장 위치:

- `state["sql_result"]`
- `state["artifacts"]["sql"]`

주요 내용:

- `status`: `OK`, `EMPTY`, `INVALID_REQUEST`, `BLOCKED`, `FAIL`
- `query_type`
- `sql`
- `rows`
- `results`: 복합 SQL 조회 결과 목록
- `summary`: artifact/log/memory용 짧은 상태 요약. 사용자-facing 판단 근거는 아님
- `limitations`
- `error_message`

SQL source:

- SQLite DB: `agent_data/maintenance_history.sqlite`
- Schema seed file: `sql/maintenance_history_schema.sql`

## 10. Gate와 Recovery 정책

| Gate | PASS 기준 | Retry 기준 | 최종 답변으로 가는 경우 |
|---|---|---|---|
| `prediction_gate` | `PredictionResult.status in {"OK", "PARTIAL"}` | artifact 없음 또는 `FAIL` | `NEEDS_INPUT`이면 `final_answer`에서 입력 부족 안내 |
| `sql_gate` | `SQLHistoryArtifact.status == "OK"` | 실행 실패 등 retry 가능한 실패 | `EMPTY`, `INVALID_REQUEST`, `BLOCKED`는 제한 답변 또는 추가 입력 요청 |
| `evidence_gate` | 문서와 citation이 있는 `OK` | 명시적 근거 요청인데 `EMPTY`/`LOW_RELEVANCE`이고 아직 retry가 아닌 경우 | retry 후에도 부족하면 경고 포함 답변 |
| `output_safety_gate` | 위험 실행 표현이 없는 최종 답변 | 해당 없음 | block 시 `GateReport`에 실패를 남기고, 안전한 대체 답변이 있을 때만 교체 |

Gate는 직접 worker를 호출하지 않는다. `GateReport`만 추가하고, dispatcher가 재실행 또는 다음 route를 결정한다.

## 11. Final Answer 조립 규칙

`final_answer_node`는 LLM을 쓰지 않고 artifact를 deterministic하게 조합한다.

조립 규칙:

- `prediction_result`가 있으면 `[위험 진단]`, `[부분 위험 진단]`, `[입력 부족]` 중 하나를 생성
- `evidence_bundle`이 있으면 `[문서 근거]` 생성
- `sql_result`가 있으면 `[과거 이력]` 생성
- SQL은 `SQLHistoryArtifact.summary`를 최종 판단 근거로 쓰지 않고, `SQLQueryResult.rows` 또는 `SQLHistoryArtifact.rows`를 직접 읽어 알람/정비/센서/유사사례별로 필요한 row만 답변에 반영
- citation이 있으면 `[출처]` 섹션 생성
- SQL이 `EMPTY`면 “조건에 맞는 과거 이력은 조회되지 않았습니다”라고 명시
- SQL이 `INVALID_REQUEST`면 필요한 조회 조건을 안내
- 근거가 부족하면 단정하지 않음

## 12. Memory Writer 저장 내용

`memory_writer_node`는 마지막에 다음을 저장한다.

`ConversationStore`:

- `turns`
  - 현재 user message
  - 최종 assistant answer
- `machine_values`
  - 현재 입력에서 추출/전달된 feature만 저장
  - stale로 보완된 이전 값은 다시 저장하지 않음
- `summaries`
  - `prediction`: `PredictionResult.summary`
  - `evidence`: citation/source/query/summary를 압축한 문자열
  - `sql`: query type/table/row count/sample rows를 압축한 문자열. 멀티턴 context 회수용이며 최종 판단은 새 실행의 SQL rows를 우선 사용

`RunStore`:

- `request_id`
- `user_id`
- `thread_id`
- `gate_reports`
- `retry_counts`

LangGraph `messages`:

- 최종 assistant answer를 `AIMessage`로 추가
- 같은 `thread_id`로 invoke할 때 checkpointer 기반 대화 복원에 사용

## 13. LLM 사용 위치 요약

| 위치 | LLM 사용 목적 | 자유로운 tool loop 여부 |
|---|---|---:|
| `intake_gate` | 입력/안전 intake 판단 | 없음 |
| `context_manager` | 후속 질문과 이전 artifact 참조 판단 | 없음 |
| `task_planner` | 필요한 task 목록 typed planning | 없음 |
| `sql_agent` | SQL intent 판단 및 Pydantic AI SQL agent | 없음. graph node 안에서만 실행 |
| `evidence_agent` | 검색 문서 요약 | 없음 |
| `output_safety_gate` | 최종 답변 안전성 판단 | 없음 |
| `prediction_agent` | 사용하지 않음 | 없음 |
| `orchestrator_dispatcher` | 사용하지 않음 | 없음 |
| `final_answer` | 사용하지 않음 | 없음 |
| `memory_writer` | 사용하지 않음 | 없음 |

## 14. 현재 검증 시나리오

`scripts/run_manufacturing_scenarios.py`와 노트북 하단 시나리오 셀은 17개 케이스를 실행한다.

커버 범위:

- prompt injection 방어
- 위험 실행 요청 차단
- 안전 자문 처리
- 현재 위험 진단 + 과거 이력 + 문서 근거 복합 질문
- SQL-only 이력 조회
- 모호한 SQL 조회 추가 입력 요청
- out-of-scope 차단
- 입력 feature 부족
- 멀티턴 stale context
- output safety 직접 검증
- 센서 추이 + 위험 진단 + 문서 근거
- CNC-02 서보 알람 이력/절차 근거
- unknown machine empty result
- 정비 문서 요청 안의 prompt injection
- 멀티턴 combined follow-up
- SQL artifact follow-up
- Evidence artifact follow-up

최근 검증 결과:

```text
Scenario result: 17/17 passed
```

## 15. 주의할 기술부채

현재 LangGraph checkpointer 실행 중 커스텀 Pydantic 객체 역직렬화 warning이 발생할 수 있다.

의미:

- 지금 실행 실패는 아니다.
- 향후 `LANGGRAPH_STRICT_MSGPACK=true` 같은 strict 환경에서는 문제가 될 수 있다.

개선 방향:

- checkpointer에 저장되는 Pydantic 객체를 `model_dump()` 기반 dict로 직렬화
- 복원 시 필요한 노드에서 다시 Pydantic model로 validate
- 특히 `ExecutionPlan`, `ContextPacket`, `PredictionResult`, `EvidenceArtifact`, `SQLHistoryArtifact`, `FinalAnswer`를 우선 검토
