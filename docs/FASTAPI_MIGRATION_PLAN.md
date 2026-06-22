# 노트북 → 모듈 패키지 → FastAPI 마이그레이션 계획

> 대상: `manufacturing_agent_v6.ipynb`
> 목표: 검증 끝난 노트북 로직을 **재사용 가능한 .py 패키지**로 분리하고, 그 위에 **FastAPI 서비스**를 올린다.
> 원칙: **동작(답변 틀·게이트·plan-and-execute)은 그대로**, 구조만 분리. 셀에 이미 박혀 있는 `# ---------- xxx.py ----------` 모듈 마커를 그대로 패키지 경로로 쓴다.

---

## 0. 현재 사실 (분리 전 점검)
- 노트북은 99→107셀 규모, 셀마다 모듈 마커(`contracts/`, `memory/`, `context/`, `services/`, `agents/`, `gates/`, `nodes/`, `graph/`)가 있음 → 거의 그대로 파일로 떨어진다.
- 진입점: `run_turn` / `resume_turn`(데모 헬퍼 셀), 그래프 `app = build_graph(checkpointer=sql_saver)`.
- 런타임 자원: ChromaDB(PersistentClient, `agent_data/chroma`), SQLite 3종(`longterm_memory`/`checkpoints`/`failure_history`), OpenAI(`call_llm` tier 어댑터).
- 상태/멀티턴: LangGraph **SqliteSaver 체크포인터 + thread_id** 기반. `input_features`(데이터 입력란)는 선택, 기본은 자연어 질의.
- 테스트: 노트북 하단 T01~T22 (게이트/태스크/SQL 회귀 + 구조 T18/T20/T22).

---

## 1. 목표 패키지 구조

```
manufacturing_agent/                # 설치 가능한 파이썬 패키지
  __init__.py
  config.py                         # 환경설정·경로·모델 tier (.env 로드, 셀5)
  llm.py                            # call_llm(tier=...) + 재시도/백오프 (셀5)
  contracts/
    __init__.py
    context.py                      # MachineValue, DiagnosisContext, ContextPacket ... (셀7)
    results.py                      # PredictionResult, EvidenceArtifact, SQLHistoryArtifact, FinalAnswer (셀7)
    routing.py                      # TaskSpec, ExecutionPlan, GateReport, *Decision (셀7)
    state.py                        # ManufacturingState + reducers (셀9)
  memory/
    store.py                        # ConversationStore, RunStore (셀11)
    registry.py                     # UserStore/ThreadStore (users·threads 테이블, cascade 삭제) [신규]
  rag/
    chroma.py                       # 임베딩 함수 + vector_search (셀13)
  context/
    policy.py                       # FEATURE_ALIASES, extract_machine_values, detect_injection (셀15)
    selector.py  normalizer.py  packer.py   # (셀16/17/18)
    manager.py                      # context_manager 노드 (셀35)
  services/
    prediction_service.py           # compute_partial_risks(규칙/계산식) (셀20)
    rag_service.py                  # rag_search, 소스 정책 (셀21)
  agents/
    prediction_agent.py             # (셀23)
    evidence_agent.py               # (셀24 전반)
    sql_agent.py                    # Text-to-SQL 어댑터 (셀24 후반)
  gates/
    intake_gate.py  prediction_gate.py  evidence_gate.py  sql_gate.py  output_safety_gate.py  (셀29/30)
  nodes/
    final_answer_node.py            # 결정적 조립형 답변 틀 (셀32)
    memory_writer_node.py           # (셀33)
  graph/
    plan_ops.py                     # PlanOps 상태머신 (셀37 분리분)
    planner.py  replanner.py  dispatcher.py  route_policy.py
    build.py                        # build_graph + checkpointer + serde (셀38/40)
  runtime.py                        # make_initial_state / run_turn / resume_turn (셀44, FastAPI가 호출)

api/                                # FastAPI 레이어 (패키지와 분리)
  main.py                           # FastAPI app, lifespan(자원 초기화), 라우터 등록
  deps.py                           # 그래프/스토어 싱글톤 의존성
  schemas.py                        # 요청/응답 Pydantic 모델 (API 경계 전용)
  routers/
    users.py                        # POST/DELETE /users, POST/GET/DELETE threads [신규]
    chat.py                         # POST /chat, POST /chat/resume ((user,thread) 존재 검증)
    health.py                       # GET /healthz, GET /readyz
    history.py                      # GET /users/{uid}/threads/{tid}/history (장기 메모리 조회)

scripts/
  build_chroma.py                   # 01_embed_documents_chroma.ipynb 대체(문서 임베딩)
tests/
  test_regression.py               # T01~T22 → pytest 이식
pyproject.toml                      # 패키지 + fastapi/uvicorn 의존성 추가
.env(.example)
```

> 의존 방향(단방향): `contracts ← (llm, memory, rag) ← context/services ← agents/gates/nodes ← graph ← runtime ← api`. 순환 금지.

---

## 2. 셀 → 모듈 매핑 (기계적 추출)
노트북은 `# ---------- path ----------` 마커로 나뉘므로, **마커 기준으로 셀 소스를 해당 파일로 떼어내는 추출 스크립트**를 한 번 돌린다(수작업 복붙 금지, 오타 방지).
- 추출 후 각 파일 상단에 필요한 import만 정리(현재는 셀3에서 전부 전역 import).
- 전역 import(셀3)는 각 모듈의 명시적 import로 분해 — 가장 손이 많이 가는 단계.
- `print("... 정의 완료")` 류 로그는 제거하거나 logging으로 대체.

---

## 3. 설정·자원 수명주기 (FastAPI 핵심)
- **config.py**: `.env` 로드, `DATA_DIR`, 모델(`DEFAULT_MODEL`, tier 스펙), `SQL_REFERENCE_DATE`, `MIN_EVIDENCE_SCORE` 등 환경변수로. 시크릿은 코드에 두지 않음.
- **싱글톤 자원은 startup(lifespan)에서 1회 생성** 후 app.state에 보관:
  - ChromaDB client/collection (로딩 비용 큼)
  - `conversation_store`, `run_store` (SQLite)
  - `failure_history` 부트스트랩(없으면 생성)
  - **compiled graph** `app = build_graph(checkpointer=SqliteSaver(...))` — 1회 컴파일
- SqliteSaver는 `check_same_thread=False`로 이미 생성. 동시 요청은 **서로 다른 thread_id면 안전**(채널 충돌 없음). 같은 thread_id 동시 요청은 드물지만 직렬화 권장(요청 큐/락).
- 부재 시 빠른 실패: chroma 컬렉션 없음 → 명확한 startup 에러(“먼저 build_chroma 실행”).

---

## 4. FastAPI 계약 (초안)

> 확정된 정책: **인증 없음**(사내/게이트웨이 뒤). **user_id는 쉽게 생성·삭제**. **(user_id, thread_id)가 모두 존재해야만 `/chat` 응답** — thread_id는 클라이언트가 보내되, 해당 user 아래 사전 생성돼 있어야 한다.

### 4.1 user/thread 라이프사이클 (선결 — 이게 있어야 chat이 동작)
경량 레지스트리를 SQLite에 추가(`users`, `threads` 테이블; 기존 `agent_data` SQLite 인프라 재사용).
- `users(user_id PK, created_at)`
- `threads(thread_id PK, user_id FK, created_at, title)`

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/users` | 사용자 생성 → `{user_id, created_at}` 반환 (id는 서버 발급(uuid) 또는 body로 받기) |
| DELETE | `/users/{user_id}` | 사용자 + 그 사용자의 **모든 thread/대화메모리/체크포인트 정리(cascade)** |
| GET | `/users/{user_id}/threads` | 사용자의 thread 목록 |
| POST | `/users/{user_id}/threads` | thread 생성 → `{thread_id, created_at}` (멀티턴 키 발급) |
| DELETE | `/users/{user_id}/threads/{thread_id}` | thread + 해당 대화메모리/체크포인트 정리 |

- **삭제 cascade 주의**: user/thread 삭제 시 ① `threads`/`users` 행 ② ConversationStore 대화·요약·diagnosis_context ③ LangGraph `checkpoints.sqlite`의 해당 thread_id 체크포인트 까지 함께 제거. (정리 유틸을 store/runtime에 추가)

### 4.2 POST `/chat`
요청:
```json
{ "user_id": "u1", "thread_id": "t1", "message": "토크 60에 공구마모 215인데 위험 진단해줘",
  "input_features": { "type":"M", "torque":60 }   // optional, 자연어가 1순위
}
```
- **검증**: `user_id` 존재 + `thread_id`가 그 user 소유로 존재해야 함. 아니면 **404**(`user_not_found` / `thread_not_found`). → "user_id별 thread_id가 꼭 있어야 응답" 요구 충족.

응답:
```json
{ "user_id": "u1", "thread_id": "t1",
  "answer": "🔴 종합 판단: ...\n현재 위험 진단\n...",
  "citations": [{ "citation_id":"C1","title":"...","source":"..." }],
  "warnings": ["..."], "missing_inputs": [], "blocked": false,
  "trace": { "gates":[["intake_gate","PASS"]], "tasks":["prediction","final_answer"] }  // debug=true일 때만
}
```
- 내부 디버그(gate/task)는 기본 숨김, `?debug=true`일 때만.

### 4.3 POST `/chat/resume`
`{user_id, thread_id}` → 중단(HITL/interrupt)된 그래프 이어 실행 (`resume_turn`). 동일하게 (user, thread) 존재 검증.

### 4.4 GET `/users/{user_id}/threads/{thread_id}/history`
장기 메모리(ConversationStore) 기반 대화/요약 조회.

### 4.5 GET `/healthz`, `/readyz`
프로세스 살아있음 / 자원(chroma·db·LLM 키) 준비 여부.

### 동작 방식
- 엔드포인트는 동기 함수(`def`)로 두고 FastAPI 스레드풀에서 실행(LLM 호출이 blocking).
- 에러 매핑: user/thread 없음 → **404**. intake 차단 → 200 + `blocked:true`(거절 메시지). LLM 쿼터 소진(`insufficient_quota`) → **503**. 검증 실패 → 422.
- **테스트 흐름(요구사항)**: `POST /users` → `POST /users/{id}/threads` → `POST /chat`(user_id+thread_id) 로 응답 확인. thread 없이 chat 호출 시 404 확인.

---

## 5. 테스트 이식
- T01~T22를 `tests/test_regression.py`로 옮김(서비스 함수 직접 호출, FastAPI 불필요).
- 결정적 테스트(T18/T20/PlanOps, 구문)는 LLM 없이 CI에서 상시 실행.
- LLM 의존 시나리오(S1~S12)는 별도 마크(`@pytest.mark.llm`)로 분리 — 키 있을 때만.
- API 레이어는 `TestClient`로 `/chat`, `/resume`, `/healthz` 스모크.

---

## 6. 단계별 진행(작게 자주 검증)
1. **추출**: 마커 기준 셀→파일 스크립트로 패키지 골격 생성(동작 변경 0). 각 모듈 import 정리.
2. **import-only 검증**: `python -c "import manufacturing_agent.runtime"` 가 LLM 없이 통과(자원 lazy/startup 분리).
3. **runtime 동등성**: `run_turn`을 패키지에서 호출 → 노트북과 동일 결과(키 있을 때 스모크 1~2건).
4. **FastAPI 골격**: lifespan 자원 초기화 + `/healthz` + `/chat`(동기).
5. **테스트 이식**: 결정적 회귀부터 CI 연결.
6. **정리**: 노트북은 “설계/탐색용”으로 남기고 진실의 원천은 패키지로 이동.

---

## 7. 결정 사항 (확정 / 보류)
- ✅ **패키지 구조**: `manufacturing_agent/` 패키지.
- ✅ **인증**: 없음(사내/게이트웨이 뒤).
- ✅ **user_id**: 쉽게 생성/삭제(POST/DELETE /users). 삭제는 thread·메모리·체크포인트 cascade.
- ✅ **thread_id**: 클라이언트 필수 + 해당 user 아래 **사전 생성 필수**. (user,thread) 없으면 chat 404.
- ✅ **엔드포인트**: 동기(스레드풀).
- (보류) 스트리밍 응답(SSE) — 추후. 현재 결정적 조립이라 비스트리밍.
- (보류) notebook 동기화/동결 — 패키지 안정화 후 동결 권장.

---

## 8. 리스크 & 비범위
- **리스크**: 전역 import(셀3) 분해 시 누락 import, ChromaDB/SQLite 경로 상대→절대 정리, 자원 startup 비용, 동일 thread 동시요청 직렬화.
- **이번 범위 아님(추후)**: 에이전트 병렬(Send fan-out, 보류 결정됨), 답변 eval 하니스, 인증/RBAC, 멀티 테넌시, 스트리밍.

---

## 부록 — 마이그레이션 후에도 보존할 핵심 동작
- 결정적 조립형 답변 틀(배너→진단 계산식→이력→문서근거→체크리스트→출처→footer)
- Gate-driven plan-and-execute(PlanOps/planner/replanner/dispatcher) + targeted replan
- intake/output_safety 안전 게이트, 구조화 입력 우선, SQL reference_date 내장
- 모델 전부 gpt-4o(final tier만 2048 토큰)
```
