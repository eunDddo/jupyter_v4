# ARCHIVE — v5 Input Guardrail Handoff

> 기준일: 2026-06-19
> 현재 상태: **보관용 문서**
> 주의: 이 문서는 `manufacturing_agent_v5.ipynb` 시대의 handoff 기록이다. 현재 `manufacturing_agent_v6.ipynb` 구현 지침으로 사용하지 않는다.

## 1. 현재 v6 기준 결론

현재 v6는 v5 handoff에서 제안했던 standalone `safety_gate` 구조를 사용하지 않는다.

현재 구조:

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

Safety 책임은 두 곳으로 나뉜다.

| 위치 | 책임 |
|---|---|
| `intake_gate` | 프롬프트 인젝션, out-of-scope, 위험 실행 요청, 안전 자문 가능 여부를 입력 단계에서 판정 |
| `output_safety_gate` | 생성된 최종 답변에 위험 실행 승인, 안전장치 우회, 점검 없는 재가동 허용 표현이 남지 않도록 deterministic backstop + LLM judge 적용 |

따라서 이 파일에 있던 과거 standalone safety gate 예시는 현재 v6에 그대로 추가하지 않는다.

## 2. v5 handoff의 역사적 의미

이 문서의 원래 목적은 v5에서 다음 문제를 추적하는 것이었다.

```text
입력 단에서 제어/승인성 요청을 너무 일찍 차단할 것인가,
아니면 하류 safety 계층에서 위험 실행 부분집합만 차단할 것인가.
```

v6에서는 이 논의를 다음처럼 정리했다.

```text
1. 초반 gate는 input/safety 분리 대신 intake_gate로 통합한다.
2. 위험 실행 요청은 intake에서 차단하거나 안전 자문으로 제한한다.
3. final_answer 이후 output_safety_gate가 최종 표현을 다시 검사한다.
4. SafetyAgent worker 또는 별도 safety_gate는 현재 graph에 두지 않는다.
```

## 3. 현재 v6에서 검증해야 할 항목

v5 문서의 checklist 대신 현재는 다음 경로로 검증한다.

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
.venv/bin/python scripts/run_manufacturing_scenarios.py --json
```

Safety 관련 핵심 시나리오:

| 시나리오 | 목적 |
|---|---|
| `S01_prompt_injection` | system/developer instruction override 차단 |
| `S02_dangerous_execution` | 점검 없는 재가동, 안전장치 우회 등 위험 실행 요청 차단 |
| `S03_safe_advisory` | 안전 자문 질문은 차단하지 않고 제한 답변 |
| `S10_output_safety_direct` | final answer에 위험 표현이 들어가도 output safety backstop이 차단 |
| `S14_injection_inside_maintenance_request` | 정비 문서 요청 내부의 prompt injection 방어 |

노트북에서는 T01~T22 하단 셀로 주요 흐름을 직접 확인한다.

## 4. v6 구현자가 지켜야 할 것

하지 말 것:

- v5의 `input_gate` / `safety_gate` / `SafetyAgent` 구조를 되살리지 않는다.
- `session_id` 기준 설계를 되돌리지 않는다.
- dangerous action을 단순 prompt 문구로만 처리하지 않는다.
- output safety 없이 final answer를 바로 사용자에게 내보내지 않는다.

해야 할 것:

- `intake_gate`와 `output_safety_gate`의 책임을 분리한다.
- 위험 실행 요청은 artifact와 `GateReport`에 reason을 남긴다.
- final answer 이후에도 deterministic unsafe-output backstop을 적용한다.
- 안전 자문은 무조건 차단하지 말고, 현장 책임자 확인/LOTO/점검 필요성을 포함해 제한 답변한다.

## 5. 현재 문서의 보존 이유

이 문서는 현재 구현 지침이 아니라 다음 배경을 보존하기 위해 남긴다.

- 왜 v6에서 input/safety를 `intake_gate`로 합쳤는지
- 왜 별도 SafetyAgent를 두지 않았는지
- 왜 output safety backstop이 필요한지
- 위험 실행 요청과 안전 자문을 분리해야 하는 이유

현재 구조를 설명하거나 수정하려면 다음 문서를 우선 본다.

```text
manufacturing_agent_v6.md
manufacturing_agent_v6_flow.md
manufacturing_agent_v6_troubleshooting.md
NOTEBOOK_GUIDE.md
memory_context_engineering_notes.md
```
