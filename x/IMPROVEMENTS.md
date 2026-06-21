# Manufacturing Agent v6 개선 과제

> 대상: `manufacturing_agent_v6.ipynb`
> 기준: Gate-driven Manufacturing Plan-and-Execute 구조, notebook T01~T22, Python runner S01~S22.

이 문서는 예전 skeleton 기준의 TODO가 아니라, 현재 v6 구조에서 남은 개선 과제를 정리한다.

## 0. 현재 구현 상태

| 영역 | 현재 상태 | 남은 핵심 과제 |
|---|---|---|
| Graph 구조 | `SupervisorPlanner → OrchestratorDispatcher → Worker → Gate → optional SupervisorReplanner` | dependency 없는 task의 병렬 fan-out 검토 |
| Orchestration | LLM-free deterministic dispatcher | replan 정책의 실제 운영 실패 유형 축적 |
| Context | `DiagnosisContext`, `ContextResolution`, no auto-merge | context 선택 이유를 더 잘 노출하는 UX |
| SQL | PydanticAI Text-to-SQL + read-only SQLite `failure_history` | claim-level SQL 근거 요약, schema evolution 관리 |
| RAG | citation metadata, `EMPTY/LOW_RELEVANCE`, prompt-injection sanitize | rerank, claim-support checking, section metadata |
| Safety | `intake_gate` + deterministic `output_safety_gate` backstop | 안전 표현 회귀 corpus 확장 |
| Checkpoint | `thread_id` 기반 SQLite resume, T22/S22 검증 | 운영용 Postgres checkpointer 검토 |
| 검증 | Notebook T01~T22, script S01~S22 | 품질 점수형 evaluator와 golden answer set |

## 1. Prediction / Diagnostic

현재 `prediction_agent`는 ML 모델이 아니라 rule-based diagnostic / partial risk assessment다. 이름은 기존 호환을 위해 유지한다.

개선 방향:

- AI4I feature 기준 rule을 더 명확히 문서화한다.
- `PredictionResult.summary`는 계속 deterministic하게 유지한다.
- ML 모델을 붙일 경우 `PredictionResult` 계약은 유지하고, 사용자-facing 표현은 “위험 진단”으로 둔다.
- 누락 feature가 있을 때 평균 대치로 몰래 채우지 않는다.

우선순위:

| 우선순위 | 작업 |
|---|---|
| P0 | 부분 진단 / 입력 부족 / context reuse 설명 품질 개선 |
| P1 | risk flag 산출 근거를 테스트 가능한 rule table로 분리 |
| P2 | 실제 ML 모델 실험. 단, notebook 기본 흐름에는 바로 넣지 않음 |

## 2. SQL / Failure History

현재 SQLAgent는 PydanticAI Text-to-SQL이 실제 SELECT를 생성하고, output validator와 SQLGate가 검증한다.

보완할 점:

- `failure_history` schema 변경 시 few-shot, validator, scenario를 함께 갱신하는 절차 필요
- SQL 결과를 final answer에 raw row가 아니라 “패턴/예시/한계”로 압축하는 품질 기준 강화
- 일부 query result가 `EMPTY/FAIL`일 때 사용자에게 어떤 결과가 비어 있었는지 더 명확히 표시
- Text-to-SQL runner mock과 실제 PydanticAI 실행 결과의 차이 추적

하지 말아야 할 것:

- SQL 실패 시 deterministic template fallback으로 조용히 대체
- SQLAgent가 prediction을 대신 판단
- raw SQL row JSON을 final answer에 그대로 출력

## 3. RAG / Evidence

현재 EvidenceAgent는 citation metadata와 RAG 상태를 명시한다.

이미 반영된 것:

- `EMPTY`, `LOW_RELEVANCE`, `OK` 분리
- docs=0이면 summary LLM 호출 금지
- citation에 `source`, `chunk_index`, `score`, `security_flags` 포함
- retrieved document prompt injection sanitize
- final answer에 `[출처]` 목록 표시

남은 개선:

- reranker 또는 lexical+semantic hybrid score
- 동일 source 중복 citation penalty
- claim-support 검증: 답변 문장별 citation 연결
- 문서 section/title/page metadata 보강
- 안전 문서와 장비 troubleshooting 문서의 ranking policy 분리

## 4. Safety

현재 safety는 독립 SafetyAgent가 아니라 두 단계다.

```text
intake_gate
= 요청을 처리해도 되는지 판단

output_safety_gate
= 생성된 답변 표현이 안전한지 최종 검증
```

개선 방향:

- 위험 실행 승인 표현 corpus 확장
- “안전 자문”과 “위험 실행 명령” 구분 사례 추가
- output replacement 후에도 backstop을 재검사하는 테스트 유지
- S02, S03, S10을 safety 핵심 회귀로 유지

## 5. Context / Memory

현재는 `session_id`를 쓰지 않고 `thread_id`, `user_id`, `run_id` 책임을 분리한다.

남은 개선:

- `ContextResolution.reason`을 사용자 debug view에 보기 좋게 노출
- “이전 조건 사용” 여부를 final answer에서 더 자연스럽게 설명
- active/recent `DiagnosisContext` 만료 정책
- Store compaction: 최근 context 3~5개 유지와 오래된 summary 압축

금지:

- feature별 최신값 자동 병합 부활
- 여러 과거 context를 섞어 prediction input 생성
- SQL query scope에 이전 feature를 암묵적으로 주입

## 6. Orchestration / Recovery

현재 구조는 Gate-driven Plan-and-Execute다.

```text
SupervisorPlanner
→ OrchestratorDispatcher
→ Worker
→ Gate
→ OrchestratorDispatcher
→ SupervisorReplanner
→ Targeted rerun
```

남은 개선:

- task dependency가 없는 경우 병렬 실행으로 확장 가능성 검토
- `PLAN_REPAIR_REQUIRED` 유형을 실제 실패 사례 기반으로 세분화
- replan 후 final task invalidation이 모든 upstream 변경에 대해 유지되는지 테스트 확대
- 운영 환경에서는 checkpoint DB를 비신뢰 입력으로 보지 않도록 보안 경계 명확화

## 7. 품질 평가

이미 존재하는 검증:

- Notebook T01~T22
- Python runner S01~S22
- S18 구조 경계
- S19 Text-to-SQL/RAG 품질
- S20 targeted replan
- S21 broad lookup context contamination 방지
- S22 SQLite checkpoint resume

추가하면 좋은 것:

- final answer readability score
- citation coverage score
- unsafe phrase false negative corpus
- SQL result partial failure visibility score
- multi-turn context reuse precision/recall

원칙:

새 평가 체계를 따로 만들기보다 기존 notebook Txx와 script Sxx에 추가한다.

## 8. 운영화 과제

| 우선순위 | 작업 | 이유 |
|---|---|---|
| P0 | LLM/API key/config validation 명확화 | 실행 실패 원인 파악 |
| P0 | final answer 품질 회귀 추가 | 사용자가 보는 UX 품질 |
| P1 | RAG corpus 확장과 metadata 개선 | citation 신뢰도 |
| P1 | SQL schema migration 절차 | Text-to-SQL 안정성 |
| P2 | Postgres checkpointer/store 검토 | 동시성/운영 |
| P2 | LangSmith/OTel 관측성 | 비용/지연/실패 분석 |

## 9. 최종 판단

현재 가장 중요한 개선 축은 기능 추가가 아니라 다음 세 가지다.

```text
1. 답변 품질과 citation 신뢰성
2. context reuse의 사용자 경험
3. 실패/replan/resume 경로의 관측 가능성
```

Graph 구조 자체는 이미 단순 Router를 넘어선 상태다. 앞으로는 구조를 더 크게 늘리기보다, artifact 품질과 사용자-facing 답변 품질을 반복적으로 검증하는 쪽이 더 중요하다.
