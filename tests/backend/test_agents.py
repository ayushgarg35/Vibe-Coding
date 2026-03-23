"""
Agent unit tests — validate agent contracts and output schemas.
Run: pytest tests/backend/test_agents.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.intake import IntakeAgent
from agents.gap_detector import GapDetectorAgent
from agents.brd_generator import BRDGeneratorAgent
from agents.po_review_agent import POReviewAgent
from adapters.base import ModelResponse


def make_mock_adapter(structured_output: dict) -> MagicMock:
    adapter = MagicMock()
    adapter.complete = AsyncMock(return_value=ModelResponse(
        content="{}",
        model_used="claude-sonnet-4-6",
        provider="anthropic",
        input_tokens=100,
        output_tokens=200,
        cost_usd=0.001,
        task_type="test",
        structured=structured_output,
    ))
    return adapter


@pytest.mark.asyncio
async def test_intake_agent_returns_structured_output():
    mock_output = {
        "product_name": "Test Product",
        "problem_statement": "Users can't do X efficiently",
        "goals": ["Reduce time by 50%"],
        "personas": [{"name": "Alice", "role": "PM"}],
        "constraints": [],
        "open_questions": [
            {"question": "What integrations are needed?", "why_it_matters": "Affects scope", "priority": "must_have"}
        ],
        "assumptions": [],
        "non_goals": [],
        "kpis": [],
    }
    adapter = make_mock_adapter(mock_output)
    agent = IntakeAgent(adapter=adapter)

    result = await agent.run(
        context={"user_input": "I want to build a test product"},
        session_id="test-session-1",
    )

    assert result["agent"] == "intake_conversation"
    assert result["output"]["product_name"] == "Test Product"
    assert len(result["output"]["open_questions"]) > 0


@pytest.mark.asyncio
async def test_gap_detector_returns_can_proceed():
    mock_output = {
        "can_proceed": True,
        "gaps": [],
        "blocking_gaps": [],
        "recommended_questions": [],
        "risk_summary": "No critical gaps found",
    }
    adapter = make_mock_adapter(mock_output)
    agent = GapDetectorAgent(adapter=adapter)

    result = await agent.run(
        context={
            "current_stage": "discovery",
            "confirmed_facts": {"product_name": "Test"},
            "assumptions": [],
            "decisions": [],
        },
        session_id="test-session-1",
    )

    assert result["output"]["can_proceed"] is True
    assert result["output"]["blocking_gaps"] == []


@pytest.mark.asyncio
async def test_brd_generator_requires_structured_output():
    mock_brd = {
        "executive_summary": "A system to manage X",
        "business_problem": "Users struggle with X",
        "business_objectives": [{"id": "BO-1", "objective": "Reduce X by 50%", "metric": "Time", "target": "50%"}],
        "success_metrics": [],
        "stakeholders": [],
        "scope": {"in_scope": ["Feature A"], "out_of_scope": ["Feature B"]},
        "assumptions": [],
        "constraints": [],
        "risks": [],
        "traceability": [],
        "open_items": [],
    }
    adapter = make_mock_adapter(mock_brd)
    agent = BRDGeneratorAgent(adapter=adapter)

    result = await agent.run(
        context={"intake_output": {"product_name": "Test"}, "approved_decisions": [], "assumptions": []},
        session_id="test-session-1",
    )

    assert result["artifact_type"] == "BRD"
    assert "executive_summary" in result["output"]
    assert "business_objectives" in result["output"]


@pytest.mark.asyncio
async def test_po_review_returns_verdict():
    mock_review = {
        "artifact_type": "BRD",
        "readiness_score": 85,
        "verdict": "GO",
        "confidence": "high",
        "summary": "BRD is well-structured",
        "issues": [],
        "blockers": [],
        "recommendations": ["Add more detail to stakeholder section"],
    }
    adapter = make_mock_adapter(mock_review)
    agent = POReviewAgent(adapter=adapter)

    result = await agent.run(
        context={"artifact_type": "BRD", "artifact_content": {"executive_summary": "..."}, "prior_artifacts": {}},
        session_id="test-session-1",
    )

    assert result["output"]["verdict"] in ["GO", "REVISE", "HOLD"]
    assert 0 <= result["output"]["readiness_score"] <= 100


@pytest.mark.asyncio
async def test_po_review_hold_when_blockers():
    mock_review = {
        "artifact_type": "PRD",
        "readiness_score": 45,
        "verdict": "HOLD",
        "confidence": "high",
        "summary": "Multiple blocking issues found",
        "issues": [
            {"id": "I-1", "category": "ambiguity", "severity": "blocker",
             "location": "FR-3", "description": "Requirement is untestable",
             "recommendation": "Rewrite with measurable criteria"}
        ],
        "blockers": ["I-1"],
        "recommendations": [],
    }
    adapter = make_mock_adapter(mock_review)
    agent = POReviewAgent(adapter=adapter)

    result = await agent.run(
        context={"artifact_type": "PRD", "artifact_content": {}, "prior_artifacts": {}},
        session_id="test-session-2",
    )

    assert result["output"]["verdict"] == "HOLD"
    assert len(result["output"]["blockers"]) > 0
