# Manufacturing Agent v6 Troubleshooting

이 문서는 `manufacturing_agent_v6.ipynb`를 운영/개선할 때 반복적으로 확인해야 하는 트러블슈팅 기준을 정리한다.

현재 구조의 핵심은 ReAct가 아니라 **Gate-driven Manufacturing Plan-and-Execute**다.

```text
InputGate
→ ContextManager
→ SupervisorPlanner
→ OrchestratorDispatcher
→ PredictionAgent / SQLAgent / EvidenceAgent
→ Gate
→ OrchestratorDispatcher
→ SupervisorReplanner, if needed
→ FinalAnswerNode
→ OutputSafetyGate
→ MemoryWriter
```

중요한 운영 원칙:

- 특정 시나리오 문장을 하드코딩해서 통과시키지 않는다.
- 실패는 숨기지 않고 artifact status, gate report, limitations, warnings에 남긴다.
- Orchestrator는 LLM 없이 task 상태와 gate report만 보고 route를 결정한다.
- Worker는 자기 artifact만 만들고, Gate는 검증만 한다.
- FinalAnswerNode는 raw artifact를 출력하지 않고 사용자용 `answer_context`를 조립해 답변한다.
- 문서 근거가 있으면 citation을 본문과 `[출처]`에 보여준다.
- 출처 원문은 임의 번역하지 않고, 본문만 사용자 친화적으로 정리한다.

## 1. 검증 기준: Notebook vs Python Scenario Runner

### 핵심 정리

현재 `manufacturing_agent_v6.ipynb` 하단에는 사람이 직접 실행하기 쉬운 `run_turn(...)` / `resume_turn(...)` 기반 smoke/structural cells가 있다. 노트북 셀은 `T01`부터 `T22`까지 있다.

반면, 전체 회귀 검증 기준은 `scripts/run_manufacturing_scenarios.py`다. 이 파일에는 `S01`부터 `S22`까지 있다.

따라서 다음 표현은 구분해야 한다.

```text
노트북에서 직접 확인한 시나리오
= ipynb 하단 T01~T22

전체 회귀 테스트 통과
= scripts/run_manufacturing_scenarios.py 기준 S01~S22
```

최근 확인한 전체 회귀 결과는 Python scenario runner 기준이다.

```text
Scenario result: 22/22 passed
Trace index: /private/tmp/manufacturing_scenario_full_final/index.json
```

### 노트북 T18~T22의 의미

노트북 하단은 데모와 수동 smoke test 용도다. 사용자가 직접 셀을 하나씩 실행하면서 답변 품질, trace, artifact를 확인하기 위한 형태다.

`T18~T22`는 Python runner의 구조 회귀 성격을 노트북에서도 직접 확인할 수 있게 붙인 셀이다.

| 노트북 셀 | 성격 |
|---|---|
| `T18` | Orchestrator / Context / SQL schema 경계 검증 |
| `T19` | Text-to-SQL / RAG 품질과 citation metadata 검증 |
| `T20` | Gate-driven targeted replan 검증 |
| `T21` | broad 문제 조회에서 이전 feature context 오염 방지 |
| `T22` | SQLite checkpointer를 새 graph app으로 재생성한 뒤 resume 검증 |

`T17`은 기본 `resume_turn(...)` smoke test이고, `T22`는 SQLite checkpointer DB를 닫았다가 다시 열어 같은 `thread_id/user_id`로 `invoke(None, config)` 경로를 검증한다.

### 혼동 방지 문구

보고할 때는 다음처럼 말하는 것이 정확하다.

```text
노트북 smoke/structural cells는 T01~T22 구조로 정리되어 있다.
전체 자동 회귀 테스트는 scripts/run_manufacturing_scenarios.py의 S01~S22로 검증했다.
```

## 2. 빠른 진단 체크리스트

문제가 생기면 아래 순서로 본다.

### 2.1 답변이 이상할 때

확인할 것:

- `final_answer.answer`
- `answer_context`
- `answer_mode`
- `gate_reports`
- `prediction_result`
- `sql_result`
- `evidence_bundle`

대표 원인:

- artifact는 정상인데 final answer prompt가 raw artifact를 과하게 반영함
- SQL-only 질문인데 final answer가 `현재 판단`이나 `문서 근거` 섹션을 생성함
- Evidence citation은 있는데 최종 답변에 `[C1]`이나 `[출처]`가 빠짐
- 출처 원문까지 한국어 후처리가 적용되어 원문이 왜곡됨

### 2.2 EvidenceAgent가 약할 때

확인할 것:

- `USE_OPENAI_EMBEDDINGS`
- Chroma collection 이름과 chunk 수
- `rag_search(...)` 결과의 `status`
- `documents`, `citations`, `score`
- `evidence_gate` diagnostics

대표 원인:

- local hash embedding collection을 사용해 문서 검색 품질이 낮음
- source policy와 type filter가 충돌함
- `safety_procedure_rag`인데 safety 문서가 필터에서 제외됨
- docs는 있는데 score가 낮아 `LOW_RELEVANCE`
- docs가 0인데 summary LLM을 호출해 hallucinated summary가 생김

### 2.3 SQLAgent가 이상할 때

확인할 것:

- `sql_result.status`
- `sql_result.results[*].status`
- 생성 SQL
- `sql_gate` diagnostics
- `validate_sql_query(...)`
- `EXPLAIN QUERY PLAN` 통과 여부

대표 원인:

- PydanticAI Text-to-SQL이 schema에 없는 column을 생성함
- LIMIT이 빠짐
- allowed table이 아닌 table을 사용함
- 복합 요청 중 일부 query만 EMPTY/FAIL인데 전체 OK처럼 보임

### 2.4 멀티턴 context가 이상할 때

확인할 것:

- `thread_id`
- `user_id`
- `ContextResolution.mode`
- `ContextPacket.current_values`
- `ContextPacket.selected_machine_values`
- `context_carryover`
- Store의 active/recent `DiagnosisContext`

대표 원인:

- 이전 feature를 자동 병합함
- broad lookup 질문을 이전 feature context로 좁힘
- 여러 과거 turn의 feature를 섞음
- `thread_id`를 잘못 전달해 checkpoint 흐름이 분리됨

### 2.5 중간 실패 후 재개가 안 될 때

확인할 것:

- 같은 `thread_id`를 사용했는가
- 같은 checkpointer DB를 다시 열었는가
- `app.invoke(None, config=same_config)`로 resume했는가
- 새 input state로 checkpoint를 덮어쓰지 않았는가
- `snapshot.next`에 남은 node가 있는가

## 3. FinalAnswer 품질 관리

### 문제

최종 답변이 artifact를 단순히 이어 붙이면 사용자 경험이 나빠진다.

대표 증상:

- SQL-only 질문인데 `현재 판단`, `문서 근거`, `우선 점검 순서`를 억지로 생성
- 내부 `score`, raw SQL row, raw schema term 노출
- 문서 citation이 있는데 답변 본문이나 출처 목록에 보이지 않음
- 근거 없는 내용을 진단처럼 단정
- 출처 원문이 후처리 과정에서 번역/치환되어 원문성이 깨짐

### 현재 해결 방식

`final_answer_node`는 먼저 artifact 조합으로 `answer_mode`를 정한다.

```text
SQL_ONLY
COMBINED
HISTORY_WITH_EVIDENCE
PREDICTION_ONLY
PREDICTION_WITH_EVIDENCE
EVIDENCE_ONLY
GENERAL
```

그 다음 `answer_context`를 만들고, LLM 최종 답변을 생성한 뒤 품질 피드백을 적용한다.

```text
artifact 수집
→ answer_mode 결정
→ answer_context 생성
→ final answer 1차 생성
→ 품질 피드백 생성
→ 필요 시 1회 재작성
→ 본문 raw schema 용어 한국어 치환
→ mode 정책 위반 시 fallback
→ citation 출처 목록 보강
→ 최종 포맷 정리
```

중요한 점은 본문과 출처 블록을 분리해 다룬다는 것이다.

```text
본문
= 사용자가 읽기 쉬운 한국어 현장 용어로 정리

[출처] 블록
= EvidenceArtifact.citations에서 deterministic하게 렌더링
= 원문 snippet은 임의 번역하지 않음
```

### 출처 출력 정책

출처는 짧게 숨기지 않고, 길어도 깔끔하게 보이도록 다음 형식으로 출력한다.

```text
[출처]
- [C1] 문서: Mill Spindle - Troubleshooting Guide - TG0101
  - 원본: haas/Mill Spindle - Troubleshooting Guide - TG0101.html
  - 위치: chunk=11
  - 원문 근거: ...
```

이 방식의 목적:

- 사용자가 citation을 실제로 추적할 수 있게 함
- 출처가 길어도 항목별로 스캔 가능하게 함
- LLM이 임의로 출처를 꾸미지 않게 함
- EvidenceArtifact의 metadata를 그대로 사용자에게 투명하게 보여줌

### 유지해야 할 품질 기준

- `SQL_ONLY` 답변은 조회 결과 중심이어야 한다.
- `SQL_ONLY` 답변에 `현재 판단`, `우선 점검 순서`, `문서 근거` 섹션을 만들지 않는다.
- `COMBINED` 답변은 현재 위험 진단, 과거 이력, 문서 근거를 모두 다룬다.
- `EvidenceArtifact.status == OK`이면 본문에 `[C1]` 형식 citation이 있어야 한다.
- `EvidenceArtifact.status == OK`이면 하단 `[출처]` 목록이 있어야 한다.
- `score`, `query_type`, SQL, raw schema term은 본문에 노출하지 않는다.
- 출처 원문 snippet은 원문성을 유지한다.

### 관련 테스트

```text
S03_safe_advisory
S04_combined_feature_history_solution
S05_failure_history_actions
S06_failure_patterns
S11_feature_history_docs
S12_twf_history_procedure
S16_multiturn_sql_history_followup
S17_multiturn_evidence_followup
S21_broad_problem_lookup_feature_context
```

## 4. Evidence RAG / Citation 문제

### 문제

EvidenceAgent가 제대로 작동하지 않으면 최종 답변은 근거 없는 일반론처럼 보인다.

대표 증상:

- `evidence_gate`는 PASS인데 답변에 citation이 없음
- `EvidenceArtifact.status == LOW_RELEVANCE`인데 최종 답변이 단정적임
- 안전 절차 질문인데 Haas troubleshooting 문서만 검색됨
- 공구/스핀들 질문인데 HTML menu chunk 같은 무관 chunk가 검색됨
- 출처가 너무 짧아 어떤 문서 근거인지 알 수 없음

### 주요 원인

#### 4.1 Local hash embedding collection 사용

local hash embedding은 빠르지만 의미 검색 품질이 낮다. 특히 문서 chunk 수가 적거나 HTML boilerplate가 많은 경우 검색 결과가 엉뚱해질 수 있다.

현재는 기본값을 OpenAI embedding collection으로 둔다.

```python
USE_OPENAI_EMBEDDINGS = os.environ.get("USE_OPENAI_EMBEDDINGS", "true").lower() in {"1", "true", "yes", "on"}
```

정상 로그 예:

```text
Use OpenAI embeddings: YES
Evidence RAG ChromaDB 연결 완료: collection=manufacturing_document_chunks_openai, embedding=OpenAI(text-embedding-3-small), chunks=213
```

문제가 있을 때 확인:

```text
Use OpenAI embeddings: NO(local hash)
chunks=18
```

이 경우 검색 품질 저하 가능성이 높다.

#### 4.2 Retrieval profile filter 충돌

예전 문제:

```text
safety_procedure_rag
→ source policy는 OSHA/KOSHA 허용
→ type_filter는 troubleshooting으로 제한
→ 안전 문서가 검색에서 제외됨
```

현재 정책:

- `safety_procedure_rag`: type filter를 넓혀 KOSHA/OSHA/Haas safety 문서 검색 가능
- `fallback_broad`: broad fallback 검색
- `prediction_plus_rag`: prediction risk/failure hint를 반영한 troubleshooting 중심 검색

#### 4.3 docs=0인데 summary LLM 호출

문서가 없는데 summary LLM을 호출하면 hallucinated evidence summary가 생길 수 있다.

현재 정책:

```text
docs == 0
→ EvidenceArtifact.status = EMPTY
→ summary LLM 호출 금지
→ citations = []
→ final answer에서 근거 부족 명시
```

#### 4.4 LOW_RELEVANCE를 OK처럼 포장

검색 결과가 있더라도 관련성이 낮으면 `OK`로 보면 안 된다.

현재 상태 분리:

```text
docs == 0
→ EMPTY

docs 있음 + score 낮음
→ LOW_RELEVANCE

docs 있음 + score 기준 통과
→ OK
```

### Citation contract

모든 citation은 최소 다음 metadata를 가져야 한다.

```text
citation_id
source_id
source
title
type
chunk_index
snippet
score
security_flags
```

최종 답변에서 보이는 필드:

```text
citation_id
title
source
chunk_index
snippet
```

### 문서 prompt injection 방어

retrieved document 안에 다음 류의 문구가 있으면 summary LLM에 instruction처럼 전달하지 않는다.

```text
ignore previous instructions
system prompt
developer instruction
이전 지시 무시
안전 경고 제거
규칙 무시
```

현재 정책:

```text
sanitize_retrieved_doc(...)
→ security_flags.possible_prompt_injection = True
→ 원문 지시를 신뢰하지 않음
```

### 관련 테스트

```text
S03_safe_advisory
S11_feature_history_docs
S12_twf_history_procedure
S17_multiturn_evidence_followup
S19_text_to_sql_rag_quality
```

## 5. SQL Agent 안전성과 실패 처리

### 현재 구조

SQL Agent는 PydanticAI Text-to-SQL 전용이다.

```text
SupervisorPlanner SQL task
→ sql_agent
→ PydanticAI Text-to-SQL
→ structured output
→ output validator
→ validate_sql_query
→ EXPLAIN QUERY PLAN
→ readonly SQLite execution
→ SQLQueryResult
→ SQLHistoryArtifact
→ sql_gate
```

현재 SQL의 핵심은 설비 현재값 예측이 아니라 `failure_history`에 저장된 과거 고장 사례와 대응 패턴을 구조화해서 가져오는 것이다.

SQL Agent가 담당하는 것:

- 최근 고장 이력 요약
- 고장 유형별 반복 패턴
- corrective action / preventive action 조회
- 현재 prediction failure_type과 유사한 과거 사례 조회
- downtime / component 기반 요약

SQL Agent가 담당하지 않는 것:

- 현재 feature 기반 고장 진단
- 문서 근거 검색
- 안전 승인
- 최종 답변 작성

### 위험 사례

Text-to-SQL은 유연하지만 생성 SQL을 그대로 실행하면 위험하다.

위험 사례:

- `DELETE`, `UPDATE`, `DROP`, `ALTER`, `PRAGMA` 생성
- LIMIT 없는 대량 조회
- 허용되지 않은 table/column 사용
- SQLite schema와 맞지 않는 SQL 생성
- 복합 SQL 중 일부 실패가 전체 OK로 숨겨짐

### 방어 레이어

```text
1. PydanticAI structured output
2. SQLSuccess | SQLInvalidRequest
3. output validator
4. validate_sql_query
5. allowed table 검사
6. LIMIT 검사
7. forbidden keyword 검사
8. SQLite EXPLAIN QUERY PLAN
9. readonly execution
10. sql_gate
```

### SQL status 해석

`SQLQueryResult.status`:

```text
OK
EMPTY
INVALID_REQUEST
BLOCKED
FAIL
```

`SQLHistoryArtifact.status`:

```text
모든 query OK
→ OK

일부 OK + 일부 EMPTY
→ OK 또는 PASS_WITH_WARNINGS 성격

모든 query EMPTY
→ EMPTY

policy 위반
→ BLOCKED

실행 실패
→ FAIL

요청 필드 부족
→ INVALID_REQUEST
```

### 운영상 중요한 원칙

- PydanticAI가 실패했다고 deterministic SQL template으로 조용히 fallback하지 않는다.
- 실패는 `SQLHistoryArtifact.status`, `SQLQueryResult.error_message`, `limitations`에 남긴다.
- `sql_gate`는 전체 artifact status뿐 아니라 `results[*].status`도 본다.
- 최종 답변에서는 SQL row 원문을 그대로 나열하지 않고 요약한다.

### 관련 테스트

```text
S05_failure_history_actions
S06_failure_patterns
S12_twf_history_procedure
S13_empty_unknown_failure
S16_multiturn_sql_history_followup
S19_text_to_sql_rag_quality
S21_broad_problem_lookup_feature_context
S22_sqlite_checkpoint_resume
```

## 6. Context Carryover / DiagnosisContext

### 문제

멀티턴에서 이전 context를 항상 가져오면 새 질문의 범위가 오염된다.

문제 예:

```text
1턴: Type M, 온도 298/309, rpm 1320, torque 62, tool_wear 215로 위험 진단해줘
2턴: 최근에 문제 있었던 곳 조회해줘
```

2턴은 전체 고장 이력 조회일 수 있다. 그런데 이전 feature context를 SQL scope로 쓰면 사용자는 넓게 물었는데 시스템이 특정 feature/failure_type에 묶인 답변을 할 수 있다.

### 현재 해결 방식

ContextManager는 task planning을 하지 않는다.

ContextManager의 책임:

- 현재 질문에서 직접 제공한 feature 추출
- 이전 artifact 참조 여부 판단
- Store의 active/recent `DiagnosisContext` 조회
- `ContextResolution.mode` 결정
- `selected_machine_values` 구성

ContextManager가 하지 않는 것:

- SQL task 생성
- Evidence task 생성
- query_type 확정
- 최종 답변 작성

### ContextMode 의미

```text
CURRENT_ONLY
= 이번 질문에서 사용자가 직접 제공한 값만 사용

USE_ACTIVE
= 사용자가 "방금 값 기준", "아까 입력값"처럼 명시적으로 active context를 참조

PATCH_ACTIVE
= "토크만 60으로 바꿔서"처럼 active context 하나를 base로 두고 current value만 patch

SELECT_HISTORY
= recent contexts 중 특정 과거 조건 하나 선택

REFER_ACTIVE_RESULT
= 재예측하지 않고 이전 artifact만 참고
```

### 절대 금지

- 현재 입력에 없는 feature를 이전값으로 자동 보완하지 않는다.
- 여러 과거 turn의 feature를 섞지 않는다.
- Checkpointer state의 이전 feature를 무조건 현재 prediction input에 넣지 않는다.
- broad SQL lookup 질문을 이전 prediction context로 좁히지 않는다.

### 관련 테스트

```text
S08_missing_features
S09_multiturn_stale_context
S15_multiturn_combined_followup
S16_multiturn_sql_history_followup
S17_multiturn_evidence_followup
S21_broad_problem_lookup_feature_context
```

## 7. RunnableConfig / Checkpointer / Store

### RunnableConfig 원칙

매턴 graph 실행 시 config는 다음 구조를 따른다.

```python
config = {
    "configurable": {
        "thread_id": thread_id,
        "user_id": user_id,
        "request_id": request_id,
    },
    "metadata": {
        "run_id": request_id,
        "source": "notebook",
    },
    "tags": ["manufacturing-agent"],
    "recursion_limit": 50,
}
```

역할:

```text
thread_id
= Checkpointer가 같은 대화 흐름의 GraphState를 저장/복구하는 기준

user_id
= Store/ConversationStore namespace 기준

request_id
= 요청 단위 trace/audit 식별자

run_id
= metadata 성격. routing/context reuse 판단 기준으로 쓰면 안 됨
```

금지:

- `RunnableConfig`에 feature 값, prediction 결과, SQL row, RAG 문서를 넣지 않는다.
- `session_id`를 쓰지 않는다.
- `run_id`를 checkpointer key나 store namespace로 쓰지 않는다.

### Checkpointer와 Store 역할 분리

```text
Checkpointer
= LangGraph 실행 state 복구
= thread_id 기준
= messages, execution_plan, active_task_id, artifacts, gate_reports 등 runtime state

Store / ConversationStore
= 사용자/스레드 기준 도메인 context 저장
= recent turns
= active/recent DiagnosisContext
= 장기적으로 재사용 가능한 요약 context
```

### 중간 실패 후 resume

중간 노드에서 실패한 뒤 다시 이어 실행할 때는 새 input state를 넣지 않는다.

```python
app.invoke(None, config=same_config)
```

새 state를 넣으면 checkpoint state를 덮어쓸 수 있다.

### SQLite checkpointer serializer

Pydantic 객체를 checkpoint에 저장하기 때문에 allowlist serializer를 사용한다.

```python
def make_checkpoint_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_SAFE_TYPES)

def make_sqlite_saver(path: str = CHECKPOINT_DB) -> SqliteSaver:
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn, serde=make_checkpoint_serde())
```

### 현재 검증한 resume 경로

`S22_sqlite_checkpoint_resume`:

```text
build_graph(SqliteSaver)
→ invoke(..., interrupt_before=["sql_agent"])
→ SQL 직전 checkpoint 생성 확인
→ SQLite checkpoint DB close
→ 같은 DB로 새 graph app 생성
→ invoke(None, same_config)
→ SQL 실행과 final_answer 생성 확인
```

검증 기준:

- SQL 직전 `snapshot.next`에 `sql_agent` 존재
- interrupt 시점에는 `sql_result` 없음
- resume 후 `sql_result.status == OK`
- resume 후 `sql_gate == PASS/PASS_WITH_WARNINGS`
- resume 후 `final_answer` 존재
- resume 후 남은 node 없음
- unregistered type warning 없음

## 8. Gate-driven Replan / Recovery

### 문제

같은 params로 retry해도 해결되지 않는 실패가 있다.

예:

- Evidence가 계속 `EMPTY` 또는 `LOW_RELEVANCE`
- SQL이 schema/policy 검증에 반복 실패
- 특정 task artifact가 바뀌었는데 final answer가 이전 artifact 기준으로 남음

### 현재 해결 방식

Gate는 직접 재실행하지 않고 `GateReport`만 남긴다.

같은 params retry로 해결되기 어렵다고 판단하면:

```text
GateReport.status = PLAN_REPAIR_REQUIRED
```

흐름:

```text
worker
→ gate
→ orchestrator_dispatcher
→ supervisor_replanner
→ failed task params patch
→ final task invalidation
→ orchestrator_dispatcher
→ patched task rerun
```

Replanner는 전체 plan을 새로 만들지 않는다. 실패한 task만 patch한다.

예:

```text
SQL task:
- repair_hint 추가
- strict_schema_check=True

Evidence task:
- retrieval_profile=fallback_broad
- focus에 feedback 반영
- min_docs 완화
```

무한 루프 방지:

```text
retry_count / max_retries
rerun_count / max_reruns
consumed_replan_report_index
plan_revision
invalidated_by
```

### 유지해야 할 경계

- OrchestratorDispatcher는 replan 내용을 만들지 않는다.
- SupervisorReplanner는 worker를 직접 실행하지 않는다.
- Gate는 worker를 직접 재실행하지 않는다.
- Prediction `NEEDS_INPUT`은 replan 대상이 아니라 사용자 추가 입력 대상으로 본다.

### 관련 테스트

```text
S20_plan_and_execute_replan
```

## 9. Output Safety

### 문제

LLM final answer가 다음처럼 위험한 표현을 생성할 수 있다.

```text
점검 없이 재가동해도 됩니다.
안전장치를 우회하고 운전하세요.
경고를 무시하고 계속 가동하세요.
```

### 현재 해결 방식

`output_safety_gate`는 LLM judge만 믿지 않고 deterministic backstop을 적용한다.

```text
final_answer empty
→ BLOCK

unsafe execution instruction detected
→ BLOCK

else
→ LLM output safety judge
→ post-LLM deterministic backstop
```

차단 시 safe answer로 대체한다.

### 관련 테스트

```text
S02_dangerous_execution
S03_safe_advisory
S10_output_safety_direct
```

## 10. 하드코딩 여부 판단 기준

사용자가 자주 우려한 지점이다.

### 하드코딩으로 보면 안 되는 것

다음은 특정 시나리오 답변을 박아 넣는 것이 아니라 시스템 공통 정책이다.

- EvidenceArtifact.citations를 `[출처]` 블록으로 deterministic 렌더링
- 본문에서 raw schema term을 한국어 현장 용어로 정리
- SQL-only 답변에서 prediction/evidence 섹션을 막는 mode policy
- unsafe output phrase를 deterministic backstop으로 차단
- docs=0이면 summary LLM 호출 금지
- SQL SELECT-only / LIMIT / allowed table 검증

### 하드코딩에 가까운 위험한 변경

다음은 피해야 한다.

- 특정 사용자 문장에만 맞춘 if문 추가
- 특정 scenario id에 따라 답변 변경
- 특정 failure만 숨기는 checker 수정
- 특정 테스트 통과를 위해 artifact status를 강제로 PASS로 변경
- LLM 실패 시 조용히 가짜 결과를 넣는 fallback

### 현재 문서화된 기준

```text
특정 시나리오 문장을 맞추지 않는다.
대신 artifact contract, gate policy, final answer mode policy, safety policy를 강화한다.
```

## 11. 검증 명령

### 정적 검증

```bash
.venv/bin/python -m py_compile scripts/run_manufacturing_scenarios.py
```

노트북 코드 셀 파싱 검증:

```bash
.venv/bin/python - <<'PY'
import ast, json
nb = json.load(open("manufacturing_agent_v6.ipynb"))
for i, c in enumerate(nb["cells"]):
    if c.get("cell_type") != "code":
        continue
    src = "".join(c.get("source", []))
    if not src.strip():
        continue
    ast.parse(src)
print("notebook_compile_ok")
PY
```

diff whitespace 검증:

```bash
git diff --check
```

### 전체 회귀 테스트

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py \
  --json \
  --dump-dir /private/tmp/manufacturing_scenario_full_final
```

기대 결과:

```text
Scenario result: 22/22 passed
Trace index: /private/tmp/manufacturing_scenario_full_final/index.json
```

### Evidence / Citation 집중 검증

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py \
  --scenario S03_safe_advisory \
  --scenario S04_combined_feature_history_solution \
  --scenario S09_multiturn_stale_context \
  --scenario S11_feature_history_docs \
  --scenario S12_twf_history_procedure \
  --scenario S17_multiturn_evidence_followup \
  --json \
  --dump-dir /private/tmp/manufacturing_scenario_evidence_final
```

확인할 것:

- `evidence_status == OK`
- `evidence_gate == PASS`
- `final_answer.answer`에 `[C1]`
- `final_answer.answer`에 `[출처]`
- 출처 항목에 `문서`, `원본`, `위치`, `원문 근거`

### SQL 집중 검증

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py \
  --scenario S05_failure_history_actions \
  --scenario S06_failure_patterns \
  --scenario S12_twf_history_procedure \
  --scenario S13_empty_unknown_failure \
  --scenario S16_multiturn_sql_history_followup \
  --scenario S21_broad_problem_lookup_feature_context \
  --json
```

확인할 것:

- SQL이 `failure_history`의 고장 사례, 원인, 조치, 반복 패턴을 조회하는지
- 현재 feature 값이나 이전 context가 SQL 조건으로 과도하게 주입되지 않는지
- EMPTY 결과가 제한 답변으로 남는지
- `sql_gate`가 부분 경고를 숨기지 않는지

### 구조 / Replan / Resume 검증

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py \
  --scenario S18_structural_boundaries \
  --scenario S19_text_to_sql_rag_quality \
  --scenario S20_plan_and_execute_replan \
  --scenario S22_sqlite_checkpoint_resume \
  --json
```

## 12. 자주 보는 증상별 조치

### 증상: Evidence OK인데 최종 답변에 출처가 없다

확인:

```text
evidence_bundle.status
evidence_bundle.citations
final_answer.citations
final_answer.answer
```

조치:

- `_ensure_citations_visible(...)`가 호출되는지 확인
- `build_answer_context(...)`에서 citations가 `OK` 또는 허용된 status일 때 전달되는지 확인
- LLM이 만든 `[출처]`를 신뢰하지 말고 deterministic 출처 블록을 붙이는지 확인

### 증상: 안전 질문인데 Haas 문서만 나온다

확인:

```text
execution_plan.intent
evidence task params.retrieval_profile
rag_search profile
type_filter
SOURCE_PREFIX_POLICY
```

조치:

- `safety_procedure_rag`가 선택되는지 확인
- KOSHA/OSHA source가 허용되는지 확인
- type filter가 safety docs를 제외하지 않는지 확인

### 증상: SQL-only 답변이 위험 진단처럼 보인다

확인:

```text
answer_mode
prediction_result 존재 여부
sql_result 존재 여부
final_answer_quality_feedback
```

조치:

- `answer_mode == SQL_ONLY`인지 확인
- SQL-only mode에서 `현재 판단`, `우선 점검 순서`, `문서 근거` 섹션을 금지하는지 확인
- scenario checker의 `_check_answer_quality(..., mode="sql_only")` 확인

### 증상: "최근에 문제 있었던 곳 조회"가 이전 feature에 묶인다

확인:

```text
ContextResolution.mode
context_carryover
sql task params
SQL WHERE clause
```

조치:

- broad lookup은 `CURRENT_ONLY` 또는 SQL-only scope여야 한다.
- 이전 prediction failure_type을 SQL filter로 자동 사용하지 않는다.
- `S21_broad_problem_lookup_feature_context`를 실행한다.

### 증상: 토크만 줬는데 전체 feature가 채워진다

확인:

```text
ContextPacket.current_values
ContextPacket.selected_machine_values
ContextResolution.mode
PredictionResult.missing_features
```

조치:

- `CURRENT_ONLY`에서는 current values만 prediction input으로 사용해야 한다.
- Store의 active context를 자동 병합하지 않는다.
- `S08_missing_features`를 실행한다.

### 증상: checkpoint resume이 처음부터 다시 돈다

확인:

```text
thread_id
checkpoint DB path
app.invoke(None, same_config)
snapshot.next
```

조치:

- resume 시 새 input state를 넣지 않는다.
- 같은 checkpointer DB와 같은 `thread_id`를 사용한다.
- `S22_sqlite_checkpoint_resume`를 실행한다.

## 13. 남은 기술부채

### 13.1 별도 QualityGate

현재 답변 품질 검사는 `final_answer_node` 내부와 scenario test에 있다.

현업 구조로 확장하려면 다음처럼 분리할 수 있다.

```text
final_answer
→ quality_gate
→ output_safety_gate
→ memory_writer
```

QualityGate 후보 기준:

- 요청한 산출물을 모두 다뤘는가
- artifact 없는 내용을 단정하지 않았는가
- citation이 필요한 주장에 citation이 있는가
- SQL-only 답변에서 불필요한 진단 섹션을 만들지 않았는가
- 출처 원문과 본문 요약이 서로 어긋나지 않는가

### 13.2 Dict 기반 checkpoint state

현재는 `JsonPlusSerializer` allowlist로 Pydantic 객체 checkpoint warning을 제거했다.

더 강한 운영 구조는 다음이다.

```text
state에는 dict만 저장
node 진입 시 Pydantic model_validate()
node 반환 시 model_dump()
```

다만 이 방식은 전체 node의 artifact 접근부를 hydrate-safe하게 바꿔야 하므로 별도 리팩토링으로 분리하는 것이 맞다.

### 13.3 병렬 실행

현재 dispatcher는 순차 실행 중심이다.

`prediction`, `sql`, `evidence`가 독립적으로 실행 가능한 경우 LangGraph fan-out으로 병렬화할 수 있다.

다만 지금은 다음을 우선한다.

- debugging 용이성
- checkpoint resume 안정성
- gate-driven replan 안정성
- artifact/gate trace 가독성

### 13.4 RAG 평가 고도화

현재는 score threshold, source policy, citation contract 중심이다.

추가할 수 있는 평가:

- citation support claim check
- duplicate source/chunk penalty
- section/header metadata
- 문서 type별 minimum evidence criteria
- safety 질문에서 KOSHA/OSHA 우선 ranking

## 14. 최근 검증 결과 기록

최근 검증은 Python scenario runner 기준으로 수행했다.

```text
실행 파일:
scripts/run_manufacturing_scenarios.py

검증 범위:
S01 ~ S22

결과:
22/22 passed

trace:
/private/tmp/manufacturing_scenario_full_final/index.json
```

추가로 S12는 마지막 본문/출처 분리 및 한국어 레이블 정리 후 단독 재검증했다.

```text
S12_twf_history_procedure
→ 1/1 passed

trace:
/private/tmp/manufacturing_scenario_s12_final3/index.json
```

노트북 하단 테스트는 `T01~T22`까지 있으며, 전체 자동 회귀의 source of truth는 `scripts/run_manufacturing_scenarios.py`다.
