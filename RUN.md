# 실행 가이드 (임베딩 · 백엔드 · 프론트엔드)

제조 설비 진단 AI 에이전트를 **처음부터 끝까지 실행**하는 방법입니다. Windows PowerShell 기준.

---

## 0. 구성 한눈에

```
manufacturing_agent/   ← 코어 로직 패키지 (노트북에서 추출: 진단/RAG/SQL/게이트/그래프)
api/                   ← FastAPI 서버 (REST API)
frontend/              ← React(Vite) 화면
document/              ← 임베딩할 원본 문서(KOSHA/OSHA/Haas)
agent_data/            ← 런타임 데이터(ChromaDB 벡터·SQLite). 자동 생성, git 제외
```

흐름: **문서 임베딩(1회) → 백엔드 실행 → 프론트 실행 → 브라우저에서 사용**

---

## 1. 사전 준비 (최초 1회)

### 1-1. 필수 도구
- **Python + uv**: 의존성은 `uv`가 가상환경으로 관리합니다. (`uv --version`으로 확인)
- **Node.js 18+ / npm**: 프론트엔드용. (`node -v`, `npm -v`)

> 모든 파이썬 명령은 `uv run ...` 으로 실행합니다. (가상환경 자동 사용 — `python`/`uvicorn`을 직접 부르면 "인식되지 않습니다" 에러가 납니다.)

### 1-2. 의존성 설치
프로젝트 폴더(`jupyter_v4`)에서:
```powershell
uv sync --all-extras
```

### 1-3. `.env` 설정
프로젝트 루트에 `.env` 파일을 만들고 OpenAI 키를 넣습니다:
```env
OPENAI_API_KEY=sk-...your-key...
OPENAI_CHAT_MODEL=gpt-4o
OPENAI_EMBED_MODEL=text-embedding-3-small

# (선택) LangSmith 추적
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=manufacturing-agent
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```
> ⚠️ 키는 코드에 적지 말고 `.env`에만. `.env`는 git에 커밋되지 않습니다.

---

## 2. 문서 임베딩 (최초 1회, 문서가 바뀔 때만)

`document/` 폴더의 문서를 ChromaDB 벡터로 임베딩합니다. **OpenAI 임베딩 API를 사용하므로 크레딧이 필요**합니다.

```powershell
# 실제 임베딩 (agent_data/chroma 생성)
uv run python scripts/build_chroma.py

# 무엇을 임베딩할지 미리보기만 (API 호출/비용 없음)
uv run python scripts/build_chroma.py --dry-run

# 컬렉션을 지우고 처음부터 다시 빌드
uv run python scripts/build_chroma.py --reset

# OpenAI 키 없이 오프라인(로컬 해시 임베딩)으로 빌드 — 테스트용, 검색 품질은 낮음
uv run python scripts/build_chroma.py --local
```

성공하면 `agent_data/chroma/`에 213개 안팎의 청크가 저장됩니다. (코사인 거리 공간)
> 이미 임베딩돼 있으면 새로 추가된 청크만 처리하므로 다시 돌려도 안전합니다.

---

## 3. 백엔드 실행 (FastAPI)

프로젝트 폴더에서:
```powershell
uv run uvicorn api.main:app --reload --port 8000
```
- 처음 기동 시 ChromaDB·그래프 로딩으로 **몇 초** 걸립니다(정상).
- 확인: 브라우저에서 `http://localhost:8000/healthz` → `{"status":"ok"}`
- 대화형 API 문서: `http://localhost:8000/docs` (Swagger UI)

> `uvicorn`이 "인식되지 않습니다"로 뜨면 → 반드시 `uv run uvicorn ...` 으로 실행하세요.

---

## 4. 프론트엔드 실행 (React / Vite)

**새 터미널**을 열고:
```powershell
cd frontend
npm install        # 최초 1회
npm run dev        # 개발 서버: http://localhost:5173
```
- 브라우저에서 `http://localhost:5173` 접속.
- 백엔드 주소가 다르면 `frontend/.env` 에 `VITE_API_BASE=http://localhost:8000` 지정.
- CORS는 `5173`, `3000` dev origin을 허용하도록 설정돼 있습니다.

배포용 정적 빌드가 필요하면:
```powershell
npm run build      # frontend/dist 생성
```

---

## 5. 사용 흐름

화면(또는 API)에서 **사용자 → 대화(thread) → 질문** 순서입니다. (대화가 있어야 답변합니다.)

1. **사용자 생성** — 사이드바에서 "새 사용자 생성". (브라우저에 user_id 저장됨)
2. **대화 생성** — "새 대화(thread) 생성" 후 선택.
3. **질문** — 두 칸을 제공합니다:
   - **질의입력란(자연어, 1순위)**: 예) `토크 62, 공구마모 215, 공기온도 298, 공정온도 309, 회전속도 1320, 타입 M인데 고장 위험 진단해줘`
   - **데이터 입력란(선택)**: 수치를 칸으로 따로 넣어도 됩니다(자연어가 우선이라 비워도 OK).
4. 답변에는 **종합 판단 / 고장 종류별 근거(계산식) / 과거 고장 이력 / 문서 근거 / 지금 점검할 일 / 출처**가 표시됩니다. "debug" 토글을 켜면 내부 게이트·태스크도 볼 수 있습니다.

---

## 6. 주요 API 요약

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/users` | 사용자 생성 → `{user_id}` |
| DELETE | `/users/{user_id}` | 사용자 + 대화/메모리/체크포인트 전체 삭제 |
| POST | `/users/{user_id}/threads` | 대화 생성 → `{thread_id}` |
| GET | `/users/{user_id}/threads` | 대화 목록 |
| DELETE | `/users/{user_id}/threads/{thread_id}` | 대화 삭제 |
| POST | `/chat` | `{user_id, thread_id, message, input_features?}` → 진단 답변 (둘 다 존재해야 함, 없으면 404) |
| POST | `/chat/resume` | 중단된 대화 이어 실행 |
| GET | `/users/{uid}/threads/{tid}/history` | 대화 기록 |
| GET | `/usage` | **LLM API 사용량**(OpenTelemetry 계측) — 호출 수·토큰(입력/출력)·모델별 집계·추정 비용(USD) |
| GET | `/healthz`, `/readyz` | 헬스 체크 |

cURL 예시:
```powershell
# 1) 사용자
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d "{}"
# 2) 대화 (위에서 받은 user_id 사용)
curl -X POST http://localhost:8000/users/<USER_ID>/threads -H "Content-Type: application/json" -d "{}"
# 3) 질문 (user_id + thread_id)
curl -X POST "http://localhost:8000/chat?debug=true" -H "Content-Type: application/json" -d "{\"user_id\":\"<USER_ID>\",\"thread_id\":\"<THREAD_ID>\",\"message\":\"토크 62 공구마모 215 타입 M 진단해줘\"}"
```

---

## 6-1. API 사용량 모니터링 (OpenTelemetry)

`call_llm` 호출마다 OpenTelemetry Counter(`llm.calls`, `llm.tokens`)에 토큰 사용량이 기록됩니다.

```powershell
curl http://localhost:8000/usage
```
응답 예:
```json
{
  "totals": { "calls": 12, "input_tokens": 8400, "output_tokens": 3100,
              "total_tokens": 11500, "errors": 0, "est_cost_usd": 0.052 },
  "by_model": { "gpt-4o": { "calls": 9, "input_tokens": ..., "est_cost_usd": ... },
                "gpt-4o-mini": { ... } },
  "pricing_usd_per_1m_tokens": { "gpt-4o": {"input":2.5,"output":10.0}, ... }
}
```
- 값은 **서버 프로세스 시작 이후 누적**(재시작 시 0). `call_llm` 경유 호출만 집계됩니다(별도 pydantic_ai SQL 에이전트 호출은 제외).
- 단가는 대략값이며 `.env`의 `LLM_PRICE_JSON`(예: `{"gpt-4o":{"input":2.5,"output":10}}`)으로 덮어쓸 수 있습니다.
- OTLP/Prometheus 등 외부 수집기로 보내려면 `manufacturing_agent/observability.py`의 MeterProvider에 reader/exporter만 추가하면 됩니다.

---

## 7. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `uvicorn ... 인식되지 않습니다` | 전역에 없음. `uv run uvicorn api.main:app --reload` 로 실행. |
| `/chat`이 **503 llm_quota_exhausted** | OpenAI **크레딧 잔액/프로젝트 예산** 소진. "사용량(Usage)"이 아니라 **Billing → Credit balance**와 해당 **프로젝트 예산 한도**를 확인(프로젝트 키는 예산이 프로젝트별로 분리됨). 사용자/대화 생성·조회는 크레딧 없이도 동작. |
| 시작 시 `ChromaDB 컬렉션을 찾을 수 없습니다` | 먼저 `uv run python scripts/build_chroma.py` 로 임베딩. |
| 프론트에서 호출 시 CORS 에러 | 백엔드가 떠 있는지, 프론트가 `5173`/`3000`인지 확인. 다른 포트면 `CORS_ORIGINS` 환경변수에 추가. |
| 첫 응답이 느림 | 정상. 기동 시 Chroma/그래프 로딩 + LLM 호출(수 초). |
| 모듈 import 에러(`manufacturing_agent` 없음) | 프로젝트 루트 폴더에서 `uv run ...` 으로 실행. |

---

## 8. 참고
- 결정적(LLM 불필요) 회귀 테스트: `uv run python -m pytest tests/ -q`
- 설계/탐색 노트북: `manufacturing_agent_v6.ipynb` (현재 진실의 원천은 `manufacturing_agent/` 패키지)
- 마이그레이션 설계 문서: `FASTAPI_MIGRATION_PLAN.md`
