"""
BRD Generator — produces a Business Requirements Document.
Only runs after Gate 1 (scope approval) is passed.
Inputs: structured intake context + approved decisions.
Output: full BRD with traceability to source decisions.
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()

BRD_SCHEMA = {
    "type": "object",
    "required": [
        "executive_summary",
        "business_problem",
        "business_objectives",
        "success_metrics",
        "stakeholders",
        "scope",
        "assumptions",
        "constraints",
        "risks",
        "traceability",
    ],
    "properties": {
        "executive_summary": {"type": "string"},
        "business_problem": {"type": "string"},
        "business_objectives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "objective": {"type": "string"},
                    "metric": {"type": "string"},
                    "target": {"type": "string"},
                },
            },
        },
        "success_metrics": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "kpi": {"type": "string"},
                "baseline": {"type": "string"},
                "target": {"type": "string"},
                "measurement_method": {"type": "string"},
            }},
        },
        "stakeholders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "interest": {"type": "string"},
                    "influence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        },
        "scope": {
            "type": "object",
            "properties": {
                "in_scope": {"type": "array", "items": {"type": "string"}},
                "out_of_scope": {"type": "array", "items": {"type": "string"}},
            },
        },
        "assumptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "assumption": {"type": "string"},
                    "risk_if_wrong": {"type": "string"},
                    "owner": {"type": "string"},
                },
            },
        },
        "constraints": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "type": {"type": "string", "enum": ["technical", "budget", "timeline", "regulatory", "resource"]},
                "description": {"type": "string"},
            }},
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "probability": {"type": "string", "enum": ["high", "medium", "low"]},
                    "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                    "mitigation": {"type": "string"},
                },
            },
        },
        "traceability": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "brd_element": {"type": "string"},
                    "source": {"type": "string"},
                    "decision_id": {"type": "string"},
                },
            },
        },
        "open_items": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Items that could not be resolved — surface for human review",
        },
    },
}


class BRDGeneratorAgent(BaseAgent):
    task_type = "brd_generation"
    prompt_template_path = "generators/brd_v1.yaml"

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        """
        Generates a structured BRD from approved intake context.
        Tags every element with its source decision for traceability.
        """
        intake_output = context.get("intake_output", {})
        approved_decisions = context.get("approved_decisions", [])
        assumption_register = context.get("assumptions", [])

        system_prompt = self._build_system_prompt(context)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Product context (from approved intake):\n{intake_output}\n\n"
                    f"Approved decisions:\n{approved_decisions}\n\n"
                    f"Assumption register:\n{assumption_register}\n\n"
                    "Generate a complete, production-quality BRD. "
                    "Every element must be traceable to a source decision or input. "
                    "For anything still unresolved, add it to open_items — never silently assume. "
                    "Output must be valid JSON matching the BRD schema."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            response_schema=BRD_SCHEMA,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": response.structured or {},
            "artifact_type": "BRD",
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
