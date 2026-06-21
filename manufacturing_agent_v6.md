# Manufacturing AI Agent — v6 설명서

> 파일: `manufacturing_agent_v6.ipynb`
> 기준: 2026-06-22
> 한 줄 요약: v6는 기존 Supervisor Hub 구조가 아니라 **Gate-driven Manufacturing Plan-and-Execute** 구조다. 초반 입력/안전 판정은 단일 `intake_gate`가 맡고, `supervisor_planner`가 task를 만들며, `orchestrator_dispatcher`가 task 상태와 gate report를 보고 worker 실행/재시도/replan을 관리한다.

---

## 0. 기존 문서 대비 핵심 갱신

이전 `manufacturing_agent_v6.md`는 `input_gate → safety_gate → context_manager → supervisor` 흐름과 StubLLM/규칙 폴백을 설명했다. 현재 노트북은 다음 구조로 바뀌었다.

| 항목 | 이전 설명 | 현재 노트북 기준 |
|---|---|---|
| 초반 게이트 | `input_gate`와 `safety_gate` 분리 | 단일 LLM `intake_gate`가 서비스 가능 여부와 위험 실행 요청을 함께 판정 |
| 라우팅 | Supervisor Hub가 다음 agent를 선택 | `supervisor_planner`가 `ExecutionPlan` 생성, `orchestrator_dispatcher`가 deterministic route 관리 |
| 실패 복구 | retry 중심 | gate가 `PLAN_REPAIR_REQUIRED`를 남기면 `supervisor_replanner`가 실패 task만 patch |
| Worker | prediction/evidence 중심 | `prediction_agent`, `evidence_agent`, `sql_agent` 3개 worker |
| SQL | 별도 agent 설명 없음 | PydanticAI Text-to-SQL 기반 `sql_agent` + `sql_gate` + read-only SQLite 실행 |
| 출력 안전 | `output_gate` 중심 | 최종 답변 직후 `output_safety_gate`가 위험 실행 표현과 과도한 승인 문구를 억제 |
| 실행 모드 | API 키 없으면 StubLLM/규칙 폴백 | 실제 LLM 설정을 전제로 실행. `OPENAI_API_KEY` 없으면 명시적으로 실패 |

---

## 1. 개요

제조 설비, 특히 밀링/가공 설비의 **위험 진단, 정비 문서 근거 검색, 과거 고장 이력 조회**를 한 번의 LangGraph workflow로 처리하는 멀티 에이전트 시스템이다.

사용자 입력은 자연어 질문과 프론트엔드 구조화 수치 입력(`input_features`)을 모두 받을 수 있다. 시스템은 요청 성격에 따라 다음 작업을 조합한다.

1. 현재 설비 수치 기반 rule-based 위험 진단
2. ChromaDB 기반 정비/안전 문서 RAG와 citation 생성
3. SQLite `failure_history` 기반 과거 고장 이력/조치 조회
4. 위 artifact를 사용자용 answer context로 압축한 최종 한국어 답변 생성

`prediction_agent`라는 이름은 유지하지만, 현재 구현은 ML 예측 모델이 아니라 **rule-based diagnostic / partial risk assessment**다. 사용자 답변에서도 "예측"보다 "위험 진단" 또는 "부분 위험 진단"으로 표현하는 것이 의도다.

---

## 2. 전체 아키텍처

```text
START
  ↓
intake_gate
  ├─ BLOCK → final_answer → output_safety_gate → memory_writer → END
  ↓ PASS
context_manager
  ↓
supervisor_planner
  ↓
orchestrator_dispatcher
  ├─ prediction_agent → prediction_gate → orchestrator_dispatcher
  ├─ sql_agent        → sql_gate        → orchestrator_dispatcher
  ├─ evidence_agent   → evidence_gate   → orchestrator_dispatcher
  ├─ supervisor_replanner → orchestrator_dispatcher
  └─ final_answer
       ↓
output_safety_gate
  ↓
memory_writer
  ↓
END
```

핵심 원칙은 다음과 같다.

- Worker는 최종 답변을 만들지 않고 typed artifact만 만든다.
- Gate는 worker를 직접 재실행하지 않고 `GateReport`만 남긴다.
- 다음 node 선택은 `orchestrator_dispatcher`가 `ExecutionPlan`, task status, dependency, retry/replan count로 결정한다.
- LLM은 자유로운 ReAct tool loop를 돌지 않는다. 정해진 node 안에서 typed decision, Text-to-SQL, 근거 요약, 최종 답변, safety judge 용도로 제한적으로 사용된다.

---

## 3. Node 역할

| Node | 역할 | LLM 사용 |
|---|---|---:|
| `intake_gate` | 빈 입력, 프롬프트 인젝션, 제조 도메인 여부, 위험 실행 요청을 1차 판정 | 사용 |
| `context_manager` | checkpointer와 `ConversationStore`에서 최근 대화, 이전 artifact, `DiagnosisContext`를 선택/정규화/포장 | 사용 |
| `supervisor_planner` | 사용자 요청을 `prediction`, `sql`, `evidence`, `final_answer` task로 분해 | 사용 |
| `orchestrator_dispatcher` | task 상태와 gate report를 보고 다음 worker/replanner/final route 결정 | 미사용 |
| `prediction_agent` | 설비 feature 기반 rule-based 위험 진단 및 부분 진단 생성 | 미사용 |
| `prediction_gate` | `PredictionResult` 상태와 입력 부족 여부 검증 | 미사용 |
| `sql_agent` | PydanticAI Text-to-SQL로 SQLite read-only 이력 조회 | 사용 |
| `sql_gate` | SQL artifact와 SELECT-only 안전 정책 검증 | 미사용 |
| `evidence_agent` | ChromaDB 검색, citation 구성, 문서 근거 요약 | 사용 |
| `evidence_gate` | 문서 근거 artifact 품질, citation, empty/low relevance 상태 검증 | 미사용 |
| `supervisor_replanner` | 실패 task의 params/success criteria만 patch하고 downstream final task invalidate | 미사용 |
| `final_answer` | prediction/evidence/sql artifact를 answer context로 압축해 최종 답변 생성 | 사용 |
| `output_safety_gate` | 최종 답변의 위험 실행 표현, 안전장치 우회, 과신 표현 억제 | 사용 |
| `memory_writer` | user/assistant turn, 진단 snapshot, artifact 요약, 실행 trace 저장 | 미사용 |

---

## 4. Intake와 Output Safety

### `intake_gate`

초반에는 더 이상 `input_gate`와 `safety_gate`를 분리하지 않는다. `intake_gate`가 다음 두 가지를 한 번에 판단한다.

1. **Service eligibility**
   - 제조 설비, 고장 진단, 센서, 정비, 안전, 문서, 이력 조회 관련 요청은 허용
   - 빈 입력, 프롬프트 인젝션, 무작위 문자열, 제조 도메인 밖 질문은 차단

2. **Request safety**
   - 일반 진단/문서/이력 조회는 `ALLOW`
   - "점검 없이 재가동해도 돼?" 같은 안전 자문은 `ANSWER_SAFELY`
   - 점검 없이 재가동, 안전장치 우회/해제, 경고 무시 후 운전은 `BLOCK_DANGEROUS_EXECUTION`
   - 실제 설비 제어, 현장 승인, LOTO 해제 등은 `HUMAN_HANDOFF`

결과는 `InputDecision`, `InputFlags`, `IntakeDecision`, `GateReport(gate_name="intake_gate")`로 state에 남긴다.

### `output_safety_gate`

최종 답변이 생성된 뒤 별도로 동작한다. 목적은 입력 차단이 아니라 **답변 표현 안전성**이다.

- 위험 실행 지시
- 안전장치 우회/해제 안내
- 모델이 현장 승인 또는 직접 제어를 대신하는 표현
- 근거 없는 "안전하다/가동해도 된다" 식의 과신 표현

위 표현이 감지되면 `OutputSafetyDecision`과 `GateReport`를 남기고, 필요하면 안전 안내문으로 답변을 교체한다.

---

## 5. 실행 계획과 Orchestrator

`supervisor_planner`는 사용자 요청을 typed task로 분해해 `ExecutionPlan`을 만든다.

주요 task 유형:

- `prediction`: 현재 또는 명시적으로 재사용된 설비 feature로 위험 진단
- `sql`: 최근 고장 이력, 조치, 반복 패턴, 유사 사례 조회
- `evidence`: 정비/안전/트러블슈팅 문서 RAG
- `final_answer`: 선행 artifact 종합

예시:

```text
prediction_1: task_type=prediction, status=PENDING
sql_1:        task_type=sql,        status=PENDING
evidence_1:   task_type=evidence,   status=PENDING
final_1:      task_type=final_answer, depends_on=[prediction_1, sql_1, evidence_1]
```

`orchestrator_dispatcher`는 LLM을 쓰지 않는다. 실행 가능한 `PENDING` task를 찾고, task dependency와 gate 결과에 따라 다음 node를 고른다.

Gate가 단순 재시도로 해결 가능한 문제를 남기면 retry count를 반영한다. 같은 params retry로 어렵다고 판단되면 gate는 `PLAN_REPAIR_REQUIRED`를 남기고, dispatcher는 `supervisor_replanner`로 보낸다.

`supervisor_replanner`는 전체 plan을 다시 만들지 않는다. 실패한 task만 patch한다.

- Evidence 실패: `retrieval_profile="fallback_broad"`로 확대, focus/min_docs 보강
- SQL 실패: schema 준수 hint, strict schema check 보강
- 실패 task 재실행 시 downstream `final_1`은 invalidate

---

## 6. 주요 데이터 계약

| 계약 | 용도 |
|---|---|
| `ManufacturingState` | LangGraph state. `MessagesState`를 상속하고 제조 도메인 필드를 추가 |
| `InputDecision`, `IntakeDecision`, `OutputSafetyDecision` | 입력/요청 안전/출력 안전 판단 |
| `ContextPacket`, `AgentContextPacket` | 현재 요청과 이전 맥락을 worker별로 압축한 context |
| `DiagnosisContext`, `ContextResolution` | 멀티턴에서 이전 진단 feature snapshot을 어떻게 재사용할지 결정 |
| `SupervisorPlannerDecision` | LLM planner의 typed intent와 필요 task 판단 |
| `TaskSpec`, `ExecutionPlan` | task 목록, status, params, success criteria, retry/replan 정보 |
| `OrchestratorDecision`, `SupervisorReplannerDecision` | dispatcher/replanner의 route 및 patch 결정 |
| `PredictionResult` | rule-based 위험 진단 artifact |
| `EvidenceArtifact` / `EvidenceBundle` | RAG 검색 결과, citation, 문서 요약 artifact |
| `SQLHistoryArtifact`, `SQLQueryResult` | Text-to-SQL 조회 결과 artifact |
| `GateReport` | 모든 gate의 PASS/FAIL/RETRY/BLOCK/REPLAN 보고 |
| `FinalAnswer` | 사용자에게 출력할 최종 답변, citation, warning, missing input |

`artifacts` dict에는 worker 산출물이 표준화되어 저장된다.

```text
artifacts["prediction"] = PredictionResult
artifacts["evidence"]   = EvidenceArtifact
artifacts["sql"]        = SQLHistoryArtifact
```

---

## 7. Context와 Memory

현재 구조는 이전 대화 전체를 그대로 주입하지 않는다.

```text
조회(ConversationStore/checkpointer)
→ Selector
→ ContextResolution
→ Normalizer
→ Agent별 Packer
```

`ContextResolution.mode`:

- `CURRENT_ONLY`: 현재 입력만 사용
- `USE_ACTIVE`: active `DiagnosisContext`를 그대로 사용
- `PATCH_ACTIVE`: active context 하나를 base로 잡고 현재 변경값만 patch
- `SELECT_HISTORY`: 최근 context 중 하나를 선택
- `REFER_ACTIVE_RESULT`: 이전 결과를 참조하되 feature 입력으로 재사용하지 않음

중요한 정책:

- 이전 feature를 feature별 최신값으로 자동 병합하지 않는다.
- "토크만 60으로 바꿔서", "같은 조건으로"처럼 명시적 참조가 있을 때만 active `DiagnosisContext`를 patch한다.
- SQL 조회 조건은 이전 설비 feature가 아니라 `failure_history`의 고장 유형, 증상, 조치, 기간 같은 이력 필드 기준으로 제한한다.

저장 계층:

| 저장소 | 역할 |
|---|---|
| LangGraph state | 한 번의 graph 실행 중 working memory |
| LangGraph `messages` | checkpointer 복원 가능한 대화 메시지 |
| `ConversationStore` SQLite | user/thread별 turn, active/recent `DiagnosisContext`, artifact summary |
| `RunStore` SQLite | request, gate report, retry count 등 실행 관측 로그 |
| LangGraph checkpointer | 같은 `thread_id`의 graph state 복원 |
| ChromaDB | 정비/안전 문서 chunk와 embedding |
| SQLite `failure_history` | 과거 고장 사례, 원인, 조치, 재발 방지, downtime |

---

## 8. Worker 상세

### `prediction_agent`

현재 ML 모델이 아니라 AI4I 스타일 feature 조합에 대한 rule-based partial risk assessment를 수행한다.

대표 feature:

- `type`
- `air_temperature`
- `process_temperature`
- `rotational_speed`
- `torque`
- `tool_wear`

결과는 `PredictionResult`에 저장된다. 주요 필드는 `status`, `available_features`, `missing_features`, `risk_flags`, `failure_types`, `cause_features`, `evidence_hints`, `safety_hints`, `context_mode`, `changed_features`, `reused_features`, `summary`다.

### `evidence_agent`

ChromaDB에 이미 임베딩된 문서를 검색만 한다. 문서 임베딩 준비는 `01_embed_documents_chroma.ipynb`에서 수행한다.

Retrieval profile:

- `troubleshooting_rag`: 일반 정비/트러블슈팅 검색
- `prediction_plus_rag`: 위험 진단 결과의 failure type/cause feature를 결합한 검색
- `safety_procedure_rag`: 안전/LOTO/재가동 관련 검색
- `fallback_broad`: replan 또는 retry 시 필터를 넓힌 검색

정책:

- 검색 문서가 0개면 `EMPTY`
- 문서는 있으나 score가 낮으면 `LOW_RELEVANCE`
- `EMPTY` 또는 `LOW_RELEVANCE`를 `OK`처럼 포장하지 않는다.
- retrieved document 안의 prompt injection 의심 문구는 sanitize한다.
- citation이 없는 주장은 최종 답변에서 단정하지 않는다.

### `sql_agent`

PydanticAI Text-to-SQL 전용 worker다. 실제 SQLite `failure_history`에 대해 read-only SELECT를 생성하고 실행한다.

정책:

- SELECT-only
- DDL/DML/PRAGMA/다중 statement 금지
- 허용 table/column만 사용
- `LIMIT` 필수
- `EXPLAIN QUERY PLAN` 통과 후 실행
- 실패를 숨기지 않고 `INVALID_REQUEST`, `BLOCKED`, `FAIL`, `EMPTY`로 artifact에 남김

---

## 9. 노트북 구성

| 섹션 | 내용 |
|---|---|
| 0 | 설치 & 환경 |
| 1 | 설정 & LLM 어댑터. `.env`, OpenAI/LangSmith 설정, `call_llm` |
| 2 | `contracts/` — Pydantic schema, routing/result/state 계약 |
| 3 | `memory/` — `ConversationStore`, `RunStore`, SQLite 장기 메모리 |
| 4 | ChromaDB RAG 런타임 |
| 5 | `context/` — selector, normalizer, packer, context resolution |
| 6 | `services/` — prediction service, RAG service, SQL helper |
| 7 | `agents/` — `prediction_agent`, `sql_agent`, `evidence_agent` |
| 8 | `gates/` — `intake_gate`, worker gates, `output_safety_gate` |
| 9 | `nodes/` — `final_answer_node`, `memory_writer_node` |
| 10 | `context_manager` 진입점 |
| 11 | `graph/` — planner, dispatcher, replanner, route policy, graph assembly |
| 12 | SQLite checkpointer와 `app` compile |
| 13 | 그래프 시각화 |
| 14 | 실행 데모 — `run_turn` |
| 15 | 정리 |
| 테스트 | `run_turn` / `resume_turn` 기반 T01~T22 smoke/structural cells |

---

## 10. 실행 방법

### 사전 준비

1. 프로젝트 루트 `.env`에 `OPENAI_API_KEY`를 설정한다.
2. 필요 시 `OPENAI_CHAT_MODEL`, `OPENAI_EMBED_MODEL`, `USE_OPENAI_EMBEDDINGS`, `LANGSMITH_*`를 설정한다.
3. `01_embed_documents_chroma.ipynb`를 먼저 실행해 `agent_data/chroma`를 준비한다.

현재 노트북은 실제 LLM 실행 환경을 전제로 한다. `OPENAI_API_KEY`가 없으면 StubLLM으로 계속 진행하지 않고 초기화 단계에서 실패한다.

### 진입 함수

```python
run_turn(
    user_message: str,
    user_id: str,
    thread_id: str,
    request_id: str,
    input_features: Optional[dict] = None,
    debug: bool = False,
)
```

이어 실행:

```python
resume_turn(
    user_id: str,
    thread_id: str,
    request_id: str = "resume",
    debug: bool = False,
)
```

식별자 역할:

- `thread_id`: LangGraph checkpointer가 같은 대화 흐름의 state를 저장/복구하는 기준
- `user_id`: `ConversationStore` namespace 기준
- `request_id`/`run_id`: 실행 추적, 감사, evaluation metadata

---

## 11. 검증 범위

노트북 하단의 T01~T22 smoke/structural cells와 `scripts/run_manufacturing_scenarios.py`가 회귀 검증 기준이다. 노트북 셀은 사람이 직접 흐름과 artifact를 확인하기 위한 실행형 명세이고, 전체 자동 회귀의 source of truth는 Python runner의 S01~S22다.

주요 검증 축:

- 프롬프트 인젝션 차단
- 위험 실행 명령 차단
- 안전 자문은 차단하지 않고 근거 기반 답변
- 현재 feature 위험 진단 + 과거 이력 + 문서 근거 종합
- SQL-only 고장 이력/조치/반복 패턴 조회
- out-of-scope 차단
- 입력 feature 부족 시 `NEEDS_INPUT`
- 멀티턴 `DiagnosisContext` patch/reuse
- 문서 요청 안의 프롬프트 인젝션 차단
- output safety 직접 검증
- checkpoint 중단 후 `resume_turn` 재개
- 구조 경계, Text-to-SQL/RAG 품질, targeted replan, broad lookup context 오염 방지, SQLite checkpoint resume

이번 문서 수정에서는 노트북 전체 실행이나 시나리오 테스트를 새로 수행하지 않았다. 현재 파일은 `manufacturing_agent_v6.ipynb`의 구조와 하단 T01~T22 정의를 기준으로 설명을 갱신한 것이다.

---

## 12. 운영/개선 포인트

- `intake_gate`와 `output_safety_gate`의 책임을 섞지 않는다. 전자는 요청 판정, 후자는 답변 표현 검증이다.
- `orchestrator_dispatcher`는 LLM-free deterministic task lifecycle manager로 유지한다.
- Gate는 artifact를 직접 수정하거나 worker를 직접 재실행하지 않고 `GateReport`만 남긴다.
- 실패는 조용히 fallback하지 않고 artifact status, limitations, gate report에 드러낸다.
- FinalAnswer에는 raw SQL, raw row JSON, 내부 score, raw schema term을 노출하지 않는다.
- Evidence가 `OK`이면 본문 citation과 `[출처]` 목록이 보여야 한다.
- SQL/RAG/Safety가 커지면 각 영역을 subgraph로 분리하거나 local planner/gate를 둘 수 있다.
- 병렬화가 필요하면 dependency 없는 `prediction`, `sql`, `evidence` task를 LangGraph fan-out 구조로 확장할 수 있다.
