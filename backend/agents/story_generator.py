"""
Story Generator — produces user stories and acceptance criteria from approved FRD.
Every story links to a functional requirement and persona.
Acceptance criteria are written to be testable (Given/When/Then).
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()

STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "persona": {"type": "string"},
                    "statement": {
                        "type": "string",
                        "description": "As a [persona], I want [goal], so that [benefit]",
                    },
                    "frd_req_id": {"type": "string"},
                    "prd_req_id": {"type": "string"},
                    "priority": {"type": "string", "enum": ["must_have", "should_have", "nice_to_have"]},
                    "story_points": {"type": "integer"},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "scenario": {"type": "string"},
                                "given": {"type": "string"},
                                "when": {"type": "string"},
                                "then": {"type": "string"},
                                "edge_case": {"type": "boolean"},
                            },
                        },
                    },
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
            },
        },
        "uat_checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_id": {"type": "string"},
                    "story_id": {"type": "string"},
                    "scenario": {"type": "string"},
                    "expected_result": {"type": "string"},
                    "tester_role": {"type": "string"},
                },
            },
        },
    },
}


class StoryGeneratorAgent(BaseAgent):
    task_type = "story_generation"
    prompt_template_path = "generators/brd_v1.yaml"  # TODO: add story_v1.yaml prompt

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        approved_frd = context.get("approved_frd", {})
        approved_prd = context.get("approved_prd", {})

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert product analyst. "
                    "Generate user stories in the format: 'As a [persona], I want [goal], so that [benefit]'. "
                    "Every acceptance criterion must be testable using Given/When/Then format. "
                    "Include edge cases as separate AC items marked edge_case=true. "
                    "Do not generate vague or non-testable criteria — these are a review blocker."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Approved FRD:\n{approved_frd}\n\n"
                    f"Approved PRD (for persona context):\n{approved_prd}\n\n"
                    "Generate complete user stories with acceptance criteria for all functional requirements. "
                    "Also produce a UAT checklist. "
                    "Output must be valid JSON matching the story schema."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            response_schema=STORY_SCHEMA,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": response.structured or {},
            "artifact_type": "STORIES",
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
