"""
PO Review Agent — reviews any artifact as a Product Owner / PM.
Detects: ambiguity, contradictions, missing flows, non-testable requirements,
hidden dependencies, scope gaps, missing edge cases, vague AC.
Outputs a structured review pack with severity-ranked issues and readiness score.
Automatically runs at every approval gate.
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()

REVIEW_PACK_SCHEMA = {
    "type": "object",
    "required": [
        "artifact_type",
        "readiness_score",
        "verdict",
        "issues",
        "blockers",
        "recommendations",
        "confidence",
        "summary",
    ],
    "properties": {
        "artifact_type": {"type": "string"},
        "readiness_score": {
            "type": "number",
            "description": "0-100 score. 80+ = Go. 60-79 = Revise. <60 = Hold.",
        },
        "verdict": {
            "type": "string",
            "enum": ["GO", "REVISE", "HOLD"],
            "description": "GO=ready, REVISE=fixable issues, HOLD=fundamental problems",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Reviewer confidence in the verdict",
        },
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "ambiguity",
                            "contradiction",
                            "missing_actor",
                            "missing_flow",
                            "missing_validation",
                            "non_testable_requirement",
                            "vague_acceptance_criteria",
                            "hidden_dependency",
                            "missing_permission",
                            "missing_edge_case",
                            "scope_gap",
                            "compliance_risk",
                            "change_impact",
                        ],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["blocker", "critical", "major", "minor", "suggestion"],
                    },
                    "location": {"type": "string", "description": "Section/field/requirement ID where issue was found"},
                    "description": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "example_fix": {"type": "string"},
                },
            },
        },
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Issue IDs that are blockers — must be resolved before approval",
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Non-blocking improvements worth addressing",
        },
        "consistency_with_prior_artifacts": {
            "type": "object",
            "properties": {
                "is_consistent": {"type": "boolean"},
                "inconsistencies": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}


class POReviewAgent(BaseAgent):
    task_type = "po_review"
    prompt_template_path = "review/po_review_v1.yaml"

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        """
        Reviews the target artifact against prior approved artifacts.
        Produces a structured review pack.
        """
        artifact_type = context.get("artifact_type", "Unknown")
        artifact_content = context.get("artifact_content", {})
        prior_artifacts = context.get("prior_artifacts", {})

        system_prompt = self._build_system_prompt(context)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert Product Owner and requirements quality reviewer. "
                    "Your reviews are precise, structured, and actionable. "
                    "You do not overlook missing edge cases, vague requirements, or untestable acceptance criteria. "
                    "You check consistency across all provided artifacts. "
                    "You are honest — if something is fundamentally broken, you say HOLD, not REVISE. "
                    "Never give inflated scores. A score of 80+ means truly production-ready."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Review this {artifact_type}:\n\n{artifact_content}\n\n"
                    f"Prior approved artifacts (check for consistency):\n{prior_artifacts}\n\n"
                    "Produce a complete review pack. "
                    "Score 0-100. Verdict: GO (80+), REVISE (60-79), HOLD (<60). "
                    "Every issue must have a severity, location, description, and recommendation. "
                    "Output must be valid JSON matching the review pack schema."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            response_schema=REVIEW_PACK_SCHEMA,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": response.structured or {},
            "artifact_type": "REVIEW_PACK",
            "reviewed_artifact_type": artifact_type,
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
