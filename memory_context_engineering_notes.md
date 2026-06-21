# LangGraph Memory / Context Engineering Notes

> 기준 파일: `manufacturing_agent_v6.ipynb`
> 기준일: 2026-06-22
> 핵심 결론: Checkpointer는 GraphState 복구용이고, Store는 재사용 가능한 도메인 컨텍스트 저장용이다. 이전 feature 값은 자동 병합하지 않는다.

## 1. 현재 구조의 원칙

현재 제조업 Agent의 context 관리는 다음 원칙을 따른다.

1. `thread_id`는 LangGraph checkpointer가 같은 대화 흐름의 state를 복구하는 기준이다.
2. `user_id`는 `ConversationStore`에서 사용자/스레드 namespace를 구성하는 기준이다.
3. `run_id` 또는 `request_id`는 trace, audit, evaluation metadata다.
4. `session_id`는 사용하지 않는다.
5. 이전 feature 값은 현재 입력에 자동 병합하지 않는다.
6. 사용자가 명시적으로 “같은 조건”, “방금 값”, “토크만 바꿔서”처럼 참조할 때만 이전 `DiagnosisContext`를 재사용한다.
7. 여러 과거 턴의 feature를 섞어 하나의 prediction input으로 만들지 않는다.

## 2. 저장 계층

| 계층 | 기준 | 역할 |
|---|---|---|
| LangGraph checkpointer | `thread_id` | GraphState, messages, active task, artifacts, interrupt/resume 상태 저장 |
| `ConversationStore` | `user_id + thread_id` | turn, active/recent `DiagnosisContext`, artifact summary 저장 |
| `RunStore` | `request_id`, `thread_id`, `user_id` | gate report, retry/replan, 실행 추적 저장 |
| ChromaDB | query / metadata | 제조 문서 RAG |
| SQLite history DB | SQL policy | `failure_history` read-only 조회 |

Checkpointer와 Store는 모두 필요하지만 책임이 다르다.

```text
Checkpointer
= 실행 중인 LangGraph state를 이어가기 위한 장치
= 실패 후 resume, 멀티턴 graph state 복구에 필요

Store
= 재사용 가능한 도메인 컨텍스트를 정리해 저장하는 장치
= active/recent DiagnosisContext, artifact summary, turn 기록에 필요
```

## 3. RunnableConfig

매턴 graph 실행은 다음 형태를 기준으로 한다.

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

금지:

- `configurable`에 feature, prediction result, SQL rows, RAG documents를 넣지 않는다.
- `run_id`를 checkpointer 복구 키로 쓰지 않는다.
- `run_id`를 Store namespace로 쓰지 않는다.
- `session_id`를 새로 만들지 않는다.

## 4. DiagnosisContext

이전에는 feature별 최신값을 저장하고, 현재 입력에 없는 값을 자동으로 보완하는 구조가 문제였다.

현재는 “진단에 실제 사용한 입력값 묶음”을 snapshot으로 저장한다.

```python
class DiagnosisContext(BaseModel):
    id: str
    turn_id: str
    user_id: str
    thread_id: str
    features: dict[str, Any]
    failure_types: list[str] = []
    prediction_summary: str = ""
    created_at: str
    is_safe_to_reuse: bool = True
```

저장 조건:

- `PredictionResult.status`가 `OK` 또는 `PARTIAL`
- 실제 used/resolved features가 존재
- intake/output safety에서 block되지 않음
- prompt injection 의심 요청이 아님

저장하지 않는 경우:

- 입력 차단
- 위험 실행 요청
- 예측에 사용할 수 없는 부분 입력
- 단순 SQL/RAG 질문만 수행한 turn

## 5. ContextResolution

`ContextManager`는 현재 질문에 대해 먼저 `ContextMode`를 결정한다.

```text
CURRENT_ONLY
  현재 입력만 사용.
  예: "토크 60만 있는데 위험해?"

USE_ACTIVE
  active DiagnosisContext를 그대로 사용.
  예: "방금 값 기준으로 다시 봐줘."

PATCH_ACTIVE
  active DiagnosisContext 하나를 base로 잡고 현재 변경값만 덮어쓴다.
  예: "토크만 60으로 바꿔서 다시 봐줘."

SELECT_HISTORY
  recent contexts 중 하나를 선택한다.
  예: "아까 온도 높았던 조건으로 다시 봐줘."

REFER_ACTIVE_RESULT
  prediction을 재실행하지 않고 이전 artifact만 참고한다.
  예: "방금 나온 고장 유형에 맞는 문서 찾아줘."
```

핵심은 “이전 맥락 전달”과 “이전 feature를 현재 입력으로 적용”을 분리하는 것이다.

## 6. ContextManager 처리 순서

```text
1. 현재 user_message와 input_features 읽기
2. 현재 턴에서 직접 제공된 feature 추출
3. checkpointer로 복원된 직전 messages/artifacts 확인
4. ConversationStore에서 active_context 조회
5. recent_contexts 3~5개 조회
6. ContextCarryoverDecision으로 이전 artifact 참조 여부 판단
7. ContextResolution으로 prediction input 사용 방식을 결정
8. ContextPacket과 worker별 agent_contexts 생성
```

`ContextManager`가 하지 않는 일:

- task planning
- SQL query type 최종 결정
- evidence focus 최종 결정
- prediction 실행
- final answer 작성
- feature별 최신값 자동 병합

## 7. ContextPacket 의미

`ContextPacket`에는 현재 입력과 선택된 context를 분리해서 둔다.

```text
current_values
= 이번 턴에서 사용자가 직접 제공한 값

context_resolution
= 이전 context를 어떻게 사용할지에 대한 결정

selected_machine_values
= ContextMode에 따라 안전하게 만든 최종 prediction 입력

previous_prediction_summary / previous_sql_summary / previous_evidence_summary
= 현재 질문 해석에 참고 가능한 이전 artifact 요약
```

`selected_machine_values`는 항상 하나의 base context에서만 온다. 여러 과거 turn에서 feature를 조합하지 않는다.

## 8. PredictionAgent와 MemoryWriter

`PredictionAgent`는 `selected_machine_values`와 `context_resolution.mode`를 함께 본다.

`PredictionResult`에는 다음 정보를 남긴다.

```text
context_mode
base_context_id
changed_features
reused_features
```

FinalAnswer는 이를 사용자에게 자연스럽게 설명한다.

예:

```text
이번 질문에서 제공된 값만 기준으로 부분 진단했습니다.
이전 입력 조건을 기준으로 torque만 변경해 다시 판단했습니다.
```

`MemoryWriter`는 prediction 결과가 재사용 가능할 때만 새로운 `DiagnosisContext`를 저장하고 active context를 갱신한다.

## 9. Checkpoint Resume

중간 실패 후 같은 thread를 이어 실행할 때는 새 state를 넣지 않는다.

```python
app.invoke(None, config=same_config)
```

새 state를 넣으면 checkpointer가 가진 이전 실행 상태를 덮어쓸 수 있다.

노트북 helper:

```text
run_turn(..., resume_on_error=True)
resume_turn(user_id, thread_id, request_id="resume")
checkpoint_status(thread_id, user_id, request_id)
```

`S22_sqlite_checkpoint_resume`와 노트북 `T22`는 다음을 검증한다.

- SQL 직전 interrupt
- SQLite checkpointer DB close/reopen
- 새 graph app compile
- 같은 `thread_id/user_id`로 `invoke(None, config)`
- SQL artifact와 final answer 생성

## 10. SQL/RAG Context 전달

SQL은 현재 feature를 직접 예측하는 역할이 아니다. SQL은 과거 고장 사례, 조치, 반복 패턴을 조회한다.

따라서 ContextManager가 이전 feature를 SQL 조건으로 밀어 넣지 않는다. 현재 prediction 결과의 failure type, 사용자 질문의 고장 유형/증상/부품/기간, 이전 SQL artifact 요약만 참고 맥락으로 제공한다.

EvidenceAgent도 이전 citation을 그대로 재사용하지 않는다. 이전 prediction/evidence/sql 요약은 query planning의 참고 맥락으로 쓰되, 현재 질문에 대해 새로 검색하고 새 citation을 만든다.

## 11. 품질 체크 포인트

다음 증상이 보이면 context 구조를 먼저 의심한다.

| 증상 | 확인할 곳 |
|---|---|
| “토크 60만” 질문에 이전 rpm/온도/tool_wear가 섞임 | `ContextResolution.mode`, `selected_machine_values` |
| SQL-only 질문인데 prediction task가 생김 | `supervisor_planner_decision`, `TaskSpec.params` |
| “방금 나온 고장 유형” 질문에서 prediction이 재실행됨 | `REFER_ACTIVE_RESULT` 판단 |
| 중간 실패 후 resume이 새 요청처럼 시작됨 | `app.invoke(None, config)` 사용 여부 |
| 다른 thread의 맥락이 섞임 | `thread_id`, `user_id`, Store namespace |

## 12. 최종 요약

```text
thread_id = checkpointer의 대화 흐름 키
user_id   = Store namespace 키
run_id    = trace/audit/evaluation 메타데이터

Checkpointer = GraphState 복구
ConversationStore = DiagnosisContext와 artifact summary 보관
RunStore = 실행 관측

이전 feature 자동 병합 금지
명시 참조 시 active context 하나만 선택
현재 변경값만 patch
여러 과거 context 혼합 금지
```
