# Manufacturing Agent v6

LangGraph 기반 제조업 AI Agent 노트북 프로젝트다. 현재 구조는 ReAct가 아니라 **Gate-driven Manufacturing Plan-and-Execute**다.

```text
intake_gate
→ context_manager
→ supervisor_planner
→ orchestrator_dispatcher
→ prediction_agent / sql_agent / evidence_agent
→ worker gates
→ optional supervisor_replanner
→ final_answer
→ output_safety_gate
→ memory_writer
```

주요 기능:

- 설비 feature 기반 rule-based 위험 진단
- `failure_history` SQLite DB 기반 과거 고장 이력 / 조치 / 반복 패턴 조회
- ChromaDB 기반 정비/안전 문서 RAG와 citation 생성
- 멀티턴 `DiagnosisContext` 관리
- SQLite checkpointer 기반 실패 후 resume
- output safety deterministic backstop

## 1. 처음 클론 후 실행 순서

### 1. 저장소 클론

```bash
git clone <repo-url>
cd jupyter_2-sumup
```

### 2. Python / uv 준비

Python 3.12 이상을 권장한다.

`uv`가 없다면 먼저 설치한다.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

의존성 설치:

```bash
uv sync --all-extras
```

이미 `.venv`를 직접 쓰는 환경이면 다음처럼 실행해도 된다.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[llm,notebook,viz]"
```

### 3. 환경 변수 설정

`.env.example`을 복사해서 `.env`를 만든다.

```bash
cp .env.example .env
```

`.env`에 최소한 OpenAI 키를 넣는다.

```text
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-4o
OPENAI_EMBED_MODEL=text-embedding-3-small

LANGSMITH_TRACING=false
LANGCHAIN_TRACING_V2=false
```

현재 v6는 실제 LLM 실행을 전제로 한다. `OPENAI_API_KEY`가 없으면 주요 노트북/시나리오 실행이 정상 완료되지 않을 수 있다.

### 4. 런타임 데이터 폴더 생성

```bash
mkdir -p agent_data
```

### 5. Failure history SQLite DB 생성

```bash
sqlite3 agent_data/failure_history.sqlite < sql/failure_history_schema.sql
```

`sqlite3` CLI가 없다면 Python으로 생성할 수 있다.

```bash
uv run python - <<'PY'
import sqlite3
from pathlib import Path

Path("agent_data").mkdir(exist_ok=True)
sql = Path("sql/failure_history_schema.sql").read_text(encoding="utf-8")
conn = sqlite3.connect("agent_data/failure_history.sqlite")
conn.executescript(sql)
conn.close()
PY
```

### 6. 문서 임베딩 / ChromaDB 준비

RAG 문서 원본은 `document/` 아래에 있다. 먼저 임베딩 노트북을 실행해 `agent_data/chroma`를 준비한다.

권장: Jupyter에서 직접 실행

```bash
uv run jupyter lab
```

그리고 다음 노트북을 위에서 아래로 실행한다.

```text
01_embed_documents_chroma.ipynb
```

CLI로 실행하려면:

```bash
uv run jupyter nbconvert \
  --to notebook \
  --execute 01_embed_documents_chroma.ipynb \
  --output _exec_embed.ipynb
```

### 7. 메인 노트북 실행

Jupyter에서 다음 파일을 연다.

```text
manufacturing_agent_v6.ipynb
```

위에서 아래로 실행한다. 하단에는 `run_turn(...)` / `resume_turn(...)` 기반 T01~T22 smoke/structural cells가 있다.

## 2. 빠른 검증

전체 Python 회귀 검증:

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
uv run python scripts/run_manufacturing_scenarios.py --json
```

답변까지 자세히 보고 싶으면:

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
uv run python scripts/run_manufacturing_scenarios.py --json --full-answer
```

특정 시나리오만 실행:

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
uv run python scripts/run_manufacturing_scenarios.py \
  --scenario S04_combined_feature_history_solution \
  --json --full-answer
```

결과 dump:

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
uv run python scripts/run_manufacturing_scenarios.py \
  --json --full-answer \
  --dump-dir /private/tmp/manufacturing_scenario_dump
```

## 3. 주요 파일

| 파일 | 역할 |
|---|---|
| `manufacturing_agent_v6.ipynb` | 메인 LangGraph Agent 노트북 |
| `01_embed_documents_chroma.ipynb` | `document/` 문서를 ChromaDB에 임베딩 |
| `scripts/run_manufacturing_scenarios.py` | S01~S22 회귀 테스트 runner |
| `sql/failure_history_schema.sql` | `failure_history` schema와 seed data |
| `.env.example` | 환경 변수 템플릿 |
| `manufacturing_agent_v6.md` | v6 전체 설명서 |
| `manufacturing_agent_v6_flow.md` | graph 흐름, state, node 역할 정리 |
| `manufacturing_agent_v6_troubleshooting.md` | 문제 상황별 진단/수정 가이드 |
| `NOTEBOOK_GUIDE.md` | 노트북 실행 가이드 |
| `memory_context_engineering_notes.md` | checkpointer/store/context 관리 기준 |

## 4. 아키텍처 요약

### SupervisorPlanner

사용자 요청을 보고 `ExecutionPlan`을 만든다.

```text
prediction
sql
evidence
final_answer
```

각 task는 `TaskSpec.params`와 `success_criteria`를 가진다.

### OrchestratorDispatcher

LLM을 쓰지 않는 deterministic state machine이다.

- 마지막 `GateReport` 반영
- task status 업데이트
- retry count 관리
- dependency 확인
- 다음 worker 또는 `supervisor_replanner` 또는 `final_answer`로 route

### SupervisorReplanner

전체 plan을 다시 만들지 않는다. gate가 `PLAN_REPAIR_REQUIRED`를 남긴 경우 실패 task만 patch하고 targeted rerun을 유도한다.

### SQLAgent

PydanticAI Text-to-SQL 전용 worker다.

- 대상 DB: `agent_data/failure_history.sqlite`
- 대상 table: `failure_history`
- SELECT-only
- DDL/DML/PRAGMA/다중 statement 금지
- `LIMIT` 필수
- `EXPLAIN QUERY PLAN` 검증 후 readonly 실행

### EvidenceAgent

ChromaDB 기반 문서 RAG를 수행한다.

- `OK`, `EMPTY`, `LOW_RELEVANCE`, `FAIL` 상태를 구분
- docs=0이면 summary LLM 호출 금지
- citation metadata 포함
- retrieved document prompt injection sanitize

### ContextManager

이전 feature 값을 자동 병합하지 않는다.

```text
CURRENT_ONLY
USE_ACTIVE
PATCH_ACTIVE
SELECT_HISTORY
REFER_ACTIVE_RESULT
```

사용자가 명시적으로 이전 조건을 참조할 때만 active/recent `DiagnosisContext`를 사용한다.

## 5. RunnableConfig 기준

매턴 실행 config는 다음 구조를 따른다.

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

역할:

- `thread_id`: LangGraph checkpointer의 GraphState 복구 기준
- `user_id`: `ConversationStore` namespace 기준
- `request_id` / `run_id`: trace, audit, evaluation metadata

`session_id`는 사용하지 않는다.

## 6. 테스트 구성

노트북:

```text
T01~T17: 사용자 흐름과 멀티턴 smoke test
T18: 구조 경계 검증
T19: Text-to-SQL / RAG 품질 검증
T20: Gate-driven targeted replan 검증
T21: broad problem lookup context 오염 방지
T22: SQLite checkpoint resume 검증
```

Python runner:

```text
S01~S22: 전체 자동 회귀 테스트
```

전체 검증의 source of truth는 `scripts/run_manufacturing_scenarios.py`다. 노트북 Txx 셀은 사람이 직접 답변과 artifact를 확인하기 위한 실행형 명세다.

## 7. 자주 생기는 문제

### `OPENAI_API_KEY` 오류

`.env`가 없거나 키가 비어 있는지 확인한다.

```bash
cat .env
```

### RAG citation이 안 나옴

`01_embed_documents_chroma.ipynb`를 먼저 실행했는지 확인한다.

```bash
ls agent_data/chroma
```

### SQL 결과가 FAIL 또는 INVALID_REQUEST

DB가 생성되었는지 확인한다.

```bash
sqlite3 agent_data/failure_history.sqlite '.tables'
```

`failure_history`가 보여야 한다.

### LangSmith 관련 경고가 많음

로컬 검증에서는 tracing을 끄는 것이 편하다.

```bash
export LANGSMITH_TRACING=false
export LANGCHAIN_TRACING_V2=false
```

## 8. 개발 원칙

- 특정 시나리오 문장을 하드코딩하지 않는다.
- `orchestrator_dispatcher`에 LLM 호출을 넣지 않는다.
- Worker가 final answer를 직접 만들지 않는다.
- Gate가 worker를 직접 재실행하지 않는다.
- SQL 실패를 template fallback으로 숨기지 않는다.
- Evidence가 부족하면 부족하다고 표시한다.
- FinalAnswer에 raw SQL row, JSON, 내부 state, debug trace를 그대로 출력하지 않는다.
- 위험 실행, 안전장치 우회, 점검 없는 재가동 승인 표현은 `output_safety_gate`에서 차단한다.

