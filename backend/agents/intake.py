"""
Intake Agent — conducts the initial product discovery conversation.
Captures: product vision, problem statement, goals, KPIs, personas, constraints.
Does NOT generate artifacts — only builds context for downstream agents.
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()

INTAKE_SCHEMA = {
    "type": "object",
    "required": ["product_name", "problem_statement", "goals", "personas", "constraints", "open_questions"],
    "properties": {
        "product_name": {"type": "string"},
        "product_description": {"type": "string"},
        "problem_statement": {"type": "string"},
        "goals": {
            "type": "array",
            "items": {"type": "string"},
        },
        "non_goals": {
            "type": "array",
            "items": {"type": "string"},
        },
        "kpis": {
            "type": "array",
            "items": {"type": "string"},
        },
        "personas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "goals": {"type": "string"},
                    "pain_points": {"type": "string"},
                },
            },
        },
        "constraints": {
            "type": "array",
            "items": {"type": "string"},
        },
        "integrations": {
            "type": "array",
            "items": {"type": "string"},
        },
        "compliance_requirements": {
            "type": "array",
            "items": {"type": "string"},
        },
        "open_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "priority": {"type": "string", "enum": ["must_have", "nice_to_have"]},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "assumptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "assumption": {"type": "string"},
                    "risk_if_wrong": {"type": "string"},
                },
            },
        },
    },
}


class IntakeAgent(BaseAgent):
    task_type = "intake_conversation"
    prompt_template_path = "intake/discovery_v1.yaml"

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        """
        Takes user's raw product description and structures it.
        Returns confirmed facts, assumptions, and prioritized open questions.
        """
        user_input = context.get("user_input", "")
        conversation_history = context.get("history", [])

        system_prompt = self._build_system_prompt(context)

        messages = [
            {"role": "system", "content": system_prompt},
            *conversation_history,
            {
                "role": "user",
                "content": (
                    f"Here is the product description provided by the user:\n\n{user_input}\n\n"
                    "Extract and structure all available information. "
                    "For anything missing or ambiguous, generate targeted open questions. "
                    "Output must be valid JSON matching the schema."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            response_schema=INTAKE_SCHEMA,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": response.structured or {},
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
