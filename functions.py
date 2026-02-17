"""
Function definitions and execution routing for MAD Apartments Complaint Hotline.
Each function maps directly to a Deepgram FunctionCallRequest.
"""
import json
import logging
from typing import Any, Dict

from business_logic import ComplaintSystem

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Deepgram function schemas
# ─────────────────────────────────────────────

FUNCTION_DEFINITIONS = [
    {
        "name": "agent_filler",
        "description": (
            "Speak a brief holding phrase while a lookup is in progress. "
            "ALWAYS call this before any other function so the tenant isn't greeted with silence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Short natural phrase, e.g. 'Let me pull that up for you.'"
                }
            },
            "required": ["message"],
        },
        "client_side": True,
    },
    {
        "name": "verify_tenant",
        "description": (
            "Verify a caller is a registered tenant by their unit number. "
            "Call this first for every new call before filing anything."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "unit_number": {
                    "type": "string",
                    "description": "The flat or unit number the caller gave, e.g. '101'.",
                }
            },
            "required": ["unit_number"],
        },
        "client_side": True,
    },
    {
        "name": "get_complaint_categories",
        "description": (
            "Return the full list of available complaint categories — both emergency and "
            "non-emergency — so you can guide an uncertain caller to the right option."
        ),
        "parameters": {"type": "object", "properties": {}},
        "client_side": True,
    },
    {
        "name": "file_complaint",
        "description": (
            "File a new complaint (emergency or non-emergency). "
            "Returns a ticket ID, SLA, a step-by-step response plan, and a full assurance "
            "message that you MUST read aloud word-for-word to the tenant."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "unit_number": {
                    "type": "string",
                    "description": "Tenant's unit number.",
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "gas_leak", "fire", "flood", "structural_damage",
                        "no_heat_winter", "power_outage", "security_breach", "medical_emergency",
                        "plumbing", "electrical", "hvac", "appliance", "pest",
                        "noise_complaint", "neighbour_dispute", "parking", "common_area",
                        "lift", "entry_system", "rubbish", "leaking", "damp_mould", "other",
                    ],
                    "description": "Category that best matches the issue.",
                },
                "description": {
                    "type": "string",
                    "description": "Verbatim description of the problem as the tenant described it.",
                },
                "tenant_name": {
                    "type": "string",
                    "description": "Full name of the caller.",
                },
                "contact_number": {
                    "type": "string",
                    "description": "Best callback number. Optional if not provided.",
                },
            },
            "required": ["unit_number", "category", "description", "tenant_name"],
        },
        "client_side": True,
    },
    {
        "name": "check_complaint_status",
        "description": "Check the current status and remaining SLA for an existing complaint ticket.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "Ticket reference, e.g. 'MAD-A1B2C3D4'.",
                }
            },
            "required": ["ticket_id"],
        },
        "client_side": True,
    },
    {
        "name": "list_tenant_complaints",
        "description": "List all complaints on record for a given unit number.",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_number": {
                    "type": "string",
                    "description": "The unit number to look up.",
                }
            },
            "required": ["unit_number"],
        },
        "client_side": True,
    },
]


# ─────────────────────────────────────────────
# Routing map
# ─────────────────────────────────────────────

async def _agent_filler(message: str) -> Dict:
    return {"success": True, "message": message}


FUNCTION_MAP = {
    "agent_filler":             _agent_filler,
    "verify_tenant":            ComplaintSystem.verify_tenant,
    "get_complaint_categories": ComplaintSystem.get_complaint_categories,
    "file_complaint":           ComplaintSystem.file_complaint,
    "check_complaint_status":   ComplaintSystem.check_complaint_status,
    "list_tenant_complaints":   ComplaintSystem.list_tenant_complaints,
}


# ─────────────────────────────────────────────
# Execution entry point
# ─────────────────────────────────────────────

async def execute_function(name: str, arguments: Dict[str, Any]) -> str:
    """Execute a named function and return a JSON string result."""
    logger.info(f"[FUNCTION] {name}  args={arguments}")
    try:
        fn = FUNCTION_MAP.get(name)
        if fn is None:
            return json.dumps({"success": False, "error": f"Unknown function: {name}"})

        result = await fn(**arguments)
        logger.info(f"[FUNCTION] {name} → success")
        return json.dumps(result)

    except Exception as exc:
        logger.error(f"[FUNCTION] {name} raised {exc}", exc_info=True)
        return json.dumps({"success": False, "error": str(exc)})