"""
PRD Generator — produces a Product Requirements Document from approved BRD.
Only runs after Gate 2 (BRD approval) is passed.
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()

PRD_SCHEMA = {
    "type": "object",
    "required": [
        "overview",
        "problem_statement",
        "goals_and_non_goals",
        "user_personas",
        "use_cases",
        "functional_requirements",
        "non_functional_requirements",
        "user_journeys",
        "traceability",
    ],
    "properties": {
        "overview": {"type": "string"},
        "problem_statement": {"type": "string"},
        "goals_and_non_goals": {
            "type": "object",
            "properties": {
                "goals": {"type": "array", "items": {"type": "string"}},
                "non_goals": {"type": "array", "items": {"type": "string"}},
            },
        },
        "user_personas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "goals": {"type": "array", "items": {"type": "string"}},
                    "pain_points": {"type": "array", "items": {"type": "string"}},
                    "technical_proficiency": {"type": "string"},
                },
            },
        },
        "use_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "actor": {"type": "string"},
                    "preconditions": {"type": "array", "items": {"type": "string"}},
                    "main_flow": {"type": "array", "items": {"type": "string"}},
                    "alternate_flows": {"type": "array", "items": {"type": "string"}},
                    "postconditions": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "functional_requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "enum": ["must_have", "should_have", "nice_to_have"]},
                    "persona_ids": {"type": "array", "items": {"type": "string"}},
                    "brd_objective_id": {"type": "string"},
                },
            },
        },
        "non_functional_requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["performance", "security", "scalability", "availability", "compliance", "usability"]},
                    "requirement": {"type": "string"},
                    "measure": {"type": "string"},
                },
            },
        },
        "user_journeys": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "persona_id": {"type": "string"},
                    "journey_name": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "touchpoints": {"type": "array", "items": {"type": "string"}},
                    "pain_points": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "traceability": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prd_req_id": {"type": "string"},
                    "brd_objective_id": {"type": "string"},
                    "source_decision": {"type": "string"},
                },
            },
        },
        "open_items": {"type": "array", "items": {"type": "string"}},
    },
}


class PRDGeneratorAgent(BaseAgent):
    task_type = "prd_generation"
    prompt_template_path = "generators/prd_v1.yaml"

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        approved_brd = context.get("approved_brd", {})
        intake_context = context.get("intake_output", {})

        system_prompt = self._build_system_prompt(context)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Approved BRD:\n{approved_brd}\n\n"
                    f"Product context:\n{intake_context}\n\n"
                    "Generate a complete PRD. "
                    "Every functional requirement must trace back to a BRD business objective. "
                    "Every persona must be grounded in the intake context. "
                    "Anything unresolved goes to open_items. "
                    "Output must be valid JSON matching the PRD schema."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            response_schema=PRD_SCHEMA,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": response.structured or {},
            "artifact_type": "PRD",
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
