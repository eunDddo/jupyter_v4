# Manufacturing Agent v6 Troubleshooting

이 문서는 `manufacturing_agent_v6.ipynb`의 현재 구조에서 계속 중요하게 봐야 하는 트러블슈팅 포인트만 정리한다. 과거 설계 변경 이력은 제외하고, 현재 운영/개선 판단에 직접 영향을 주는 항목만 남긴다.

핵심 원칙:

- 특정 시나리오 문장을 하드코딩해서 통과시키지 않는다.
- 실패는 숨기지 않고 artifact status, gate report, limitations에 남긴다.
- Orchestrator는 LLM 없이 task 상태와 gate report만 보고 route를 결정한다.
- Worker는 자기 artifact만 만들고, Gate는 검증만 한다.
- 최종 답변은 raw artifact가 아니라 사용자용 answer_context를 기반으로 작성한다.

## 1. FinalAnswer 품질 관리

### 문제

최종 답변이 artifact를 단순히 이어 붙이면 사용자 경험이 나빠진다.

대표 증상:

- SQL-only 질문인데 `현재 판단`, `문서 근거`, `우선 점검 순서`를 억지로 생성
- 내부 `score`, raw SQL row, raw schema term 노출
- 문서 citation이 있는데 답변 본문이나 출처 목록에 보이지 않음
- 근거 없는 내용을 진단처럼 단정

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

그 다음 `answer_context`를 만들고, LLM 최종 답변을 생성한 뒤 품질 피드백을 한 번 더 적용한다.

```text
artifact 수집
→ answer_mode 결정
→ answer_context 생성
→ final answer 1차 생성
→ 품질 피드백 생성
→ 필요 시 1회 재작성
→ raw schema 용어 한국어 치환
→ mode 정책 위반 시 fallback
→ citation 출처 목록 보강
```

### 유지해야 할 품질 기준

- `SQL_ONLY` 답변은 조회 결과 중심이어야 한다.
- `SQL_ONLY` 답변에 `현재 판단`, `우선 점검 순서`, `문서 근거` 섹션을 만들지 않는다.
- `COMBINED` 답변은 현재 위험 진단, 과거 이력, 문서 근거를 모두 다룬다.
- `EvidenceArtifact.status == OK`이면 본문에 `[C1]`과 하단 `[출처]`가 있어야 한다.
- `score`, `query_type`, SQL, raw schema term은 사용자 답변에 노출하지 않는다.

### 관련 테스트

```text
S04_combined_feature_history_solution
S05_failure_history_actions
S06_failure_patterns
S16_multiturn_sql_history_followup
S21_broad_problem_lookup_feature_context
```

## 2. SQL Agent 안전성과 실패 처리

### 문제

Text-to-SQL은 유연하지만, 생성 SQL을 그대로 실행하면 위험하다.

위험 사례:

- 쓰기/DDL SQL 생성
- LIMIT 없는 대량 조회
- 허용되지 않은 table/column 사용
- schema와 맞지 않는 SQL 생성
- 복합 SQL 중 일부만 성공했는데 전체 OK처럼 보이는 문제

### 현재 해결 방식

SQL Agent는 PydanticAI Text-to-SQL 전용이다. 단, 생성된 SQL은 여러 층에서 검증한다.

```text
PydanticAI structured output
→ SQLSuccess | SQLInvalidRequest
→ _validate_text_to_sql_query
→ validate_sql_query
→ EXPLAIN QUERY PLAN
→ readonly SQLite execution
→ SQLQueryResult
→ SQLHistoryArtifact
→ sql_gate
```

SQL 실행 결과는 query별로 `SQLQueryResult`에 남긴다.

```text
status
sql
rows
summary
limitations
error_message
```

복합 조회에서 일부 실패/EMPTY가 있으면 `SQLHistoryArtifact.limitations`에 남긴다.

### 유지해야 할 정책

- SELECT-only
- DDL/DML/PRAGMA/다중 statement 금지
- allowed table만 사용
- LIMIT 필수
- SQLite `EXPLAIN QUERY PLAN` 통과 필수
- 실패 시 조용히 fallback하지 않고 `FAIL`, `BLOCKED`, `INVALID_REQUEST`, `EMPTY`로 남김

### 관련 테스트

```text
S19_text_to_sql_rag_quality
```

## 3. RAG 근거 품질 관리

### 문제

문서 검색 결과가 없거나 낮은 관련성인데 summary LLM을 호출하면 근거 없는 문서 요약이 생길 수 있다.

또한 retrieved document 안에 prompt injection 문구가 들어 있으면 summary LLM에 악성 지시가 전달될 수 있다.

### 현재 해결 방식

Evidence RAG는 검색 품질을 먼저 상태로 분리한다.

```text
docs == 0
→ EMPTY

docs 있음 + score 낮음
→ LOW_RELEVANCE

docs 있음 + score 기준 통과
→ OK
```

정책:

- `EMPTY`이면 summary LLM 호출 금지
- `LOW_RELEVANCE`이면 OK로 포장하지 않음
- retrieved document prompt injection 의심 문구 sanitize
- citation metadata 유지

필수 citation metadata:

```text
source_id
source
type
chunk_index
snippet
score
```

### 유지해야 할 정책

- 문서 근거가 부족하면 답변에서 단정하지 않는다.
- Evidence OK인데 citation이 없으면 실패로 본다.
- retrieved doc의 지시문은 시스템 지시처럼 취급하지 않는다.

### 관련 테스트

```text
S19_text_to_sql_rag_quality
```

## 4. Gate-driven Replan / Recovery

### 문제

같은 params로 retry해도 해결되지 않는 실패가 있다.

예:

- Evidence가 계속 `EMPTY` 또는 `LOW_RELEVANCE`
- SQL이 schema/policy 검증에 반복 실패
- 특정 task 결과가 바뀌었는데 final answer가 이전 artifact 기준으로 남는 문제

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

## 5. Checkpointer / Resume

### 문제

중간 노드에서 실패했을 때 새 입력으로 다시 시작하면 checkpoint state를 덮어쓸 수 있다.

또한 Pydantic 객체를 checkpoint에 그대로 저장하면 LangGraph msgpack deserializer에서 unregistered type warning이 발생할 수 있다.

### 현재 해결 방식

실패한 동일 요청을 이어 실행할 때는 새 state를 넣지 않는다.

```python
app.invoke(None, config=same_config)
```

`thread_id`는 checkpoint 세션 key다.

```python
config = {
    "configurable": {
        "thread_id": thread_id,
        "user_id": user_id,
        "request_id": request_id,
    },
    "recursion_limit": 50,
}
```

SQLite checkpointer는 명시 allowlist serializer로 생성한다.

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

### 관련 테스트

```text
S22_sqlite_checkpoint_resume
```

## 6. Context Carryover

### 문제

멀티턴에서 이전 artifact를 항상 가져오면 새 질문의 범위를 오염시킬 수 있다.

예:

```text
1턴: feature 기반 위험 진단
2턴: 최근에 문제 있었던 곳 조회해줘
```

2턴은 전체 고장 이력 조회일 수 있는데, 이전 feature context 때문에 특정 진단 결과에 과도하게 묶이면 사용자 경험이 나빠진다.

### 현재 해결 방식

ContextManager는 task planning을 하지 않는다. 현재 질문이 이전 artifact를 참조하는지만 판단한다.

`ContextCarryoverDecision`은 다음 정도만 담당한다.

```text
is_followup
uses_previous_prediction
uses_previous_sql
uses_previous_evidence
referenced_artifacts
reason_summary
```

SQL task 생성, evidence task 생성, query type 결정은 SupervisorPlanner/SQLAgent의 책임이다.

### 유지해야 할 정책

- 이전 context는 참고 자료이지 task planning의 최종 근거가 아니다.
- broad lookup 질문은 이전 feature context로 SQL scope를 좁히지 않는다.
- 최종 답변은 구체 대상이 없으면 빈 대상 표현을 쓰지 않는다.

### 관련 테스트

```text
S16_multiturn_sql_history_followup
S17_multiturn_evidence_followup
S21_broad_problem_lookup_feature_context
```

## 7. 검증 명령

정적 검증:

```bash
.venv/bin/python -m py_compile scripts/run_manufacturing_scenarios.py
.venv/bin/jupyter nbconvert --to script manufacturing_agent_v6.ipynb --stdout
git diff --check
```

답변 품질 검증:

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py \
  --scenario S04_combined_feature_history_solution \
  --scenario S05_failure_history_actions \
  --scenario S06_failure_patterns \
  --scenario S16_multiturn_sql_history_followup \
  --scenario S21_broad_problem_lookup_feature_context \
  --json --full-answer
```

구조 / SQL / RAG / Replan / Resume 검증:

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py \
  --scenario S18_structural_boundaries \
  --scenario S19_text_to_sql_rag_quality \
  --scenario S20_plan_and_execute_replan \
  --scenario S22_sqlite_checkpoint_resume \
  --json
```

## 8. 남은 기술부채

### 8.1 별도 QualityGate

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

### 8.2 Dict 기반 checkpoint state

현재는 `JsonPlusSerializer` allowlist로 Pydantic 객체 checkpoint warning을 제거했다.

더 강한 운영 구조는 다음이다.

```text
state에는 dict만 저장
node 진입 시 Pydantic model_validate()
node 반환 시 model_dump()
```

다만 이 방식은 전체 node의 artifact 접근부를 hydrate-safe하게 바꿔야 하므로 별도 리팩토링으로 분리하는 것이 맞다.

### 8.3 병렬 실행

현재 dispatcher는 순차 실행 중심이다.

`prediction`, `sql`, `evidence`가 독립적으로 실행 가능한 경우 LangGraph fan-out으로 병렬화할 수 있다.

다만 지금은 debugging, checkpoint resume, gate-driven replan 안정성을 우선해 순차 dispatcher를 유지한다.

