"""
FRD Generator — produces a Functional Requirements Document from approved PRD.
Includes: screen specs, field definitions, state machines, business rules,
role-permission stubs, notification matrix stubs.
"""
import structlog

from agents.base import BaseAgent

log = structlog.get_logger()

FRD_SCHEMA = {
    "type": "object",
    "required": [
        "functional_modules",
        "screen_specifications",
        "field_definitions",
        "state_machines",
        "business_rules",
        "role_permission_matrix",
        "notification_matrix",
        "traceability",
    ],
    "properties": {
        "functional_modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "prd_req_ids": {"type": "array", "items": {"type": "string"}},
                    "features": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "screen_specifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "screen_name": {"type": "string"},
                    "module_id": {"type": "string"},
                    "accessible_by": {"type": "array", "items": {"type": "string"}},
                    "purpose": {"type": "string"},
                    "components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "fields": {"type": "array", "items": {"type": "string"}},
                                "actions": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "validations": {"type": "array", "items": {"type": "string"}},
                    "edge_cases": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "field_definitions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string"},
                    "screen_id": {"type": "string"},
                    "data_type": {"type": "string"},
                    "required": {"type": "boolean"},
                    "validation_rules": {"type": "array", "items": {"type": "string"}},
                    "default_value": {"type": "string"},
                    "placeholder": {"type": "string"},
                    "help_text": {"type": "string"},
                    "pii": {"type": "boolean"},
                },
            },
        },
        "state_machines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "states": {"type": "array", "items": {"type": "string"}},
                    "transitions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from_state": {"type": "string"},
                                "to_state": {"type": "string"},
                                "trigger": {"type": "string"},
                                "actor": {"type": "string"},
                                "conditions": {"type": "array", "items": {"type": "string"}},
                                "actions": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "initial_state": {"type": "string"},
                    "terminal_states": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "business_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "rule": {"type": "string"},
                    "applies_to": {"type": "array", "items": {"type": "string"}},
                    "enforcement": {"type": "string", "enum": ["hard_block", "soft_warning", "audit_log"]},
                },
            },
        },
        "role_permission_matrix": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "permissions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "resource": {"type": "string"},
                                "actions": {
                                    "type": "array",
                                    "items": {"type": "string", "enum": ["create", "read", "update", "delete", "approve", "export"]},
                                },
                            },
                        },
                    },
                },
            },
        },
        "notification_matrix": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "trigger_event": {"type": "string"},
                    "recipients": {"type": "array", "items": {"type": "string"}},
                    "channels": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["email", "in_app", "sms", "webhook", "push"]},
                    },
                    "template_hint": {"type": "string"},
                },
            },
        },
        "traceability": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "frd_element_id": {"type": "string"},
                    "prd_req_id": {"type": "string"},
                    "brd_objective_id": {"type": "string"},
                },
            },
        },
        "open_items": {"type": "array", "items": {"type": "string"}},
    },
}


class FRDGeneratorAgent(BaseAgent):
    task_type = "frd_generation"
    prompt_template_path = "generators/frd_v1.yaml"

    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        approved_prd = context.get("approved_prd", {})
        approved_brd = context.get("approved_brd", {})

        system_prompt = self._build_system_prompt(context)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Approved PRD:\n{approved_prd}\n\n"
                    f"Approved BRD:\n{approved_brd}\n\n"
                    "Generate a complete FRD. "
                    "Be precise on field definitions — include data types, validation, PII flags. "
                    "State machines must be exhaustive — no missing transitions. "
                    "Role-permission matrix must cover all actors from the PRD. "
                    "Anything unresolved goes to open_items. "
                    "Output must be valid JSON matching the FRD schema."
                ),
            },
        ]

        response = await self._call_model(
            messages=messages,
            context=context,
            response_schema=FRD_SCHEMA,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        return {
            "output": response.structured or {},
            "artifact_type": "FRD",
            "agent": self.task_type,
            "model_used": response.model_used,
            "cost_usd": response.cost_usd,
            "session_id": session_id,
        }
