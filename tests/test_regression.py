"""Deterministic (no-LLM) regression tests ported from the notebook.

These reproduce the notebook's deterministic Plan-and-Execute checks so they can
run in CI without any OpenAI quota / API key.

Run:
    uv run python -m pytest tests/test_regression.py -q
(with PYTHONPATH set to the project root so `manufacturing_agent` is importable)
"""
from __future__ import annotations

from manufacturing_agent.graph.plan_ops import PlanOps, TASK_TO_NODE
from manufacturing_agent.graph.dispatcher import orchestrator_dispatcher
from manufacturing_agent.graph.replanner import supervisor_replanner_node
from manufacturing_agent.contracts.context import (
    TaskSpec,
    ExecutionPlan,
    GateReport,
    EvidenceArtifact,
)


def test_task_to_node():
    """TASK_TO_NODE mapping + the allowed-node routing set are stable."""
    assert TASK_TO_NODE["sql"] == "sql_agent"
    allowed = set(TASK_TO_NODE.values()) | {"supervisor_replanner"}
    assert "supervisor_replanner" in allowed


def test_planops_next_runnable():
    """next_runnable respects dependency gating and advances after a PASS."""
    evidence = TaskSpec(task_id="evidence_1", task_type="evidence", status="PENDING")
    final = TaskSpec(
        task_id="final_1",
        task_type="final_answer",
        status="PENDING",
        depends_on=["evidence_1"],
    )
    plan = ExecutionPlan(intent="document_qa", tasks=[evidence, final])

    # final_1 depends on evidence_1 (PENDING) -> evidence_1 is the only runnable task.
    nxt = PlanOps.next_runnable(plan)
    assert nxt is not None
    assert nxt.task_id == "evidence_1"

    # Mark evidence_1 PASS -> final_1 (now dependency-satisfied) becomes runnable.
    plan = PlanOps.with_task(plan, "evidence_1", status="PASS")
    nxt = PlanOps.next_runnable(plan)
    assert nxt is not None
    assert nxt.task_id == "final_1"


def test_t20_replan():
    """T20: EvidenceGate PLAN_REPAIR_REQUIRED -> dispatcher REPLAN ->
    replanner PATCH_AND_RERUN -> dispatcher RETRY_TASK on evidence_agent."""
    evidence = TaskSpec(
        task_id="evidence_1",
        task_type="evidence",
        status="RUNNING",
        params={
            "retrieval_profile": "troubleshooting_rag",
            "evidence_required": True,
            "focus": ["설비 고장 원인"],
            "min_docs": 2,
            "require_citation": True,
        },
        success_criteria={"allow_empty": False, "require_citation": True},
    )
    final = TaskSpec(task_id="final_1", task_type="final_answer", depends_on=["evidence_1"])
    plan = ExecutionPlan(
        intent="document_qa",
        tasks=[evidence, final],
        reason_summary="notebook replan regression fixture",
    )
    evidence_bundle = EvidenceArtifact(
        status="EMPTY",
        documents=[],
        citations=[],
        evidence_summary="관련 문서 근거를 찾지 못했습니다.",
        is_retry=True,
    )
    report = GateReport(
        task_id="evidence_1",
        gate_name="evidence_gate",
        status="PLAN_REPAIR_REQUIRED",
        route_hint="supervisor_replanner",
        reason="retry 후에도 문서 근거 부족",
        feedback="검색 질의를 보강해 focus를 강화하세요.",
    ).model_dump()

    state = {
        "execution_plan": plan,
        "gate_reports": [report],
        "active_task_id": "evidence_1",
        "evidence_bundle": evidence_bundle,
    }

    # (1) dispatcher routes the PLAN_REPAIR_REQUIRED gate report to the replanner.
    routed = orchestrator_dispatcher(state)
    decision = routed.get("orchestrator_decision")
    route = routed.get("route")
    assert decision.action == "REPLAN", decision
    assert route.next_node == "supervisor_replanner", route

    # (2) replanner produces a targeted PATCH_AND_RERUN for evidence_1.
    replan_state = dict(state)
    replan_state.update(routed)
    replanned = supervisor_replanner_node(replan_state)
    new_plan = replanned.get("execution_plan")
    replanner_decision = replanned.get("supervisor_replanner_decision")
    new_evidence = next(t for t in new_plan.tasks if t.task_id == "evidence_1")
    new_final = next(t for t in new_plan.tasks if t.task_id == "final_1")

    assert replanner_decision.action == "PATCH_AND_RERUN", replanner_decision
    assert new_plan.replan_count == 1, new_plan
    assert new_evidence.rerun_count == 1, new_evidence
    assert new_evidence.params.get("retrieval_profile") == "fallback_broad", new_evidence.params
    assert new_final.invalidated_by == "evidence_1", new_final

    # (3) dispatcher now dispatches the patched evidence task as a retry.
    next_state = dict(replan_state)
    next_state.update(replanned)
    dispatched = orchestrator_dispatcher(next_state)
    dispatch_decision = dispatched.get("orchestrator_decision")
    assert dispatch_decision.next_node == "evidence_agent", dispatch_decision
    assert dispatch_decision.action == "RETRY_TASK", dispatch_decision
