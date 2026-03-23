"""
Gap Detector — analyses current session context to find:
- Missing decisions that block artifact generation
- Ambiguous requirements
- Risky assumptions that need human validation
- Conflicting inputs
Operates at every stage gate before advancing.
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()

GAP_REPORT_SCHEMA = {
    "type": "object",
    "required": ["gaps", "can_proceed", "blocking_gaps", "recommended_questions"],
    "properties": {
        "can_proceed": {
            "type": "boolean",
            "description": "True only if no blocking gaps remain",
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "missing_decision",
                            "ambiguity",
                            "risky_assumption",
                            "conflict",
                            "missing_actor",
                            "missing_flow",
                            "missing_edge_case",
                            "compliance_risk",
                        ],
                    },
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": ["blocker", "high", "medium", "low"]},
                    "affects": {"type": "array", "items": {"type": "string"}},
                    "recommendation": {"type": "string"},
                },
            },
        },
        "blocking_gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of gaps that must be resolved before proceeding",
        },
        "recommended_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "priority": {"type": "string", "enum": ["must_have", "nice_to_have"]},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "gap_id": {"type": "string"},
                },
            },
        },
        "risk_summary": {"type": "string"},
    },
}


class GapDetectorAgent(BaseAgent):
    task_type = "gap_detection"
    prompt_template_path = "intake/discovery_v1.yaml"  # shares context prompt

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        """
        Analyses context at current stage and returns a structured gap report.
        If can_proceed=False, orchestrator pauses and surfaces questions to user.
        """
        current_stage = context.get("current_stage", "discovery")
        confirmed_facts = context.get("confirmed_facts", {})
        assumptions = context.get("assumptions", [])
        prior_decisions = context.get("decisions", [])

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior product manager and requirements analyst. "
                    "Your job is to identify gaps, ambiguities, missing decisions, "
                    "and risks in the current product context before the team proceeds. "
                    "Be thorough but prioritized. Distinguish blockers from nice-to-haves. "
                    "Never silently assume — surface everything."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Current stage: {current_stage}\n\n"
                    f"Confirmed facts:\n{confirmed_facts}\n\n"
                    f"Current assumptions:\n{assumptions}\n\n"
                    f"Prior decisions:\n{prior_decisions}\n\n"
                    "Identify all gaps. Return structured JSON matching the schema. "
                    "Set can_proceed=true only if there are zero blocking gaps."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            response_schema=GAP_REPORT_SCHEMA,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": response.structured or {"can_proceed": False, "gaps": [], "blocking_gaps": [], "recommended_questions": []},
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
