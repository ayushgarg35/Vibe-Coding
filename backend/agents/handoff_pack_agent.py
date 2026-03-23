"""
Handoff Pack Agent — assembles the developer-ready delivery package.
Combines: FRD + stories + AC + screen specs + API stubs + UAT checklist.
Output is structured for direct engineering consumption.
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()


class HandoffPackAgent(BaseAgent):
    task_type = "handoff_assembly"
    prompt_template_path = "generators/brd_v1.yaml"  # TODO: add handoff_v1.yaml prompt

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        """
        Assembles all approved artifacts into a single developer handoff pack.
        Does not generate new content — curates, cross-references, and structures.
        """
        approved_artifacts = context.get("approved_artifacts", {})

        messages = [
            {
                "role": "system",
                "content": (
                    "You are assembling a developer handoff pack. "
                    "Your job is to structure all approved artifacts into a clean, "
                    "unambiguous package that developers can immediately act on. "
                    "Flag any remaining open questions that engineering needs answered. "
                    "Do not invent content — only curate and cross-reference existing approved artifacts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Approved artifacts:\n{approved_artifacts}\n\n"
                    "Produce a structured developer handoff pack with:\n"
                    "1. Executive summary for engineering\n"
                    "2. Scope and non-scope (clear boundaries)\n"
                    "3. All functional requirements with acceptance criteria\n"
                    "4. Screen specs with field definitions\n"
                    "5. State machines per entity\n"
                    "6. Role-permission matrix\n"
                    "7. API contract stubs\n"
                    "8. Integration requirements\n"
                    "9. Notification matrix\n"
                    "10. Open items that need PM clarification before dev can proceed\n"
                    "11. UAT checklist\n"
                    "Output as structured JSON."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": {"handoff_pack": response.content},
            "artifact_type": "DEVELOPER_HANDOFF",
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
