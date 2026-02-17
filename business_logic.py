"""
Business Logic for MAD Apartments Complaint Hotline
Handles emergency and non-emergency complaints with full SLA tracking
and tenant assurance messaging for every complaint type.
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

# ─────────────────────────────────────────────
# In-memory store  (swap for a real DB in production)
# ─────────────────────────────────────────────

TENANTS = {
    "101": {"name": "Priya Sharma",  "phone": "+447700900001", "email": "priya@example.com"},
    "202": {"name": "James O'Brien", "phone": "+447700900002", "email": "james@example.com"},
    "305": {"name": "Aisha Patel",   "phone": "+447700900003", "email": "aisha@example.com"},
    "410": {"name": "Carlos Mendez", "phone": "+447700900004", "email": "carlos@example.com"},
}

COMPLAINTS: Dict[str, dict] = {}

# ─────────────────────────────────────────────
# Category config  (label, sla_hours, responsible_team, priority_rank)
# ─────────────────────────────────────────────

COMPLAINT_CONFIG = {
    # ── EMERGENCIES ─────────────────────────────────────────────
    "gas_leak":          ("Gas Leak",                  1,   "Emergency Response",       1),
    "fire":              ("Fire / Smoke",               1,   "Emergency Response",       1),
    "flood":             ("Flooding / Burst Pipe",      2,   "Emergency Response",       1),
    "structural_damage": ("Structural Damage",          2,   "Emergency Response",       1),
    "no_heat_winter":    ("No Heating (Winter)",        4,   "Emergency Maintenance",    2),
    "power_outage":      ("Power Outage",               4,   "Emergency Maintenance",    2),
    "security_breach":   ("Security / Break-in",        2,   "Security Team",            1),
    "medical_emergency": ("Medical Emergency",          0,   "Emergency Services (999)", 1),
    # ── NON-EMERGENCIES ─────────────────────────────────────────
    "plumbing":          ("Plumbing Issue",            24,   "Maintenance Team",         3),
    "electrical":        ("Electrical Issue",          24,   "Maintenance Team",         3),
    "hvac":              ("Heating / AC Issue",        24,   "Maintenance Team",         3),
    "appliance":         ("Appliance Fault",           48,   "Maintenance Team",         4),
    "pest":              ("Pest Infestation",          48,   "Pest Control Team",        4),
    "noise_complaint":   ("Noise Complaint",           24,   "Property Management",      3),
    "neighbour_dispute": ("Neighbour Dispute",         48,   "Property Management",      4),
    "parking":           ("Parking Issue",             48,   "Property Management",      4),
    "common_area":       ("Common Area Issue",         48,   "Facilities Team",          4),
    "lift":              ("Lift / Elevator Issue",     12,   "Maintenance Team",         3),
    "entry_system":      ("Entry System / Keys",       12,   "Maintenance Team",         3),
    "rubbish":           ("Waste / Rubbish",           72,   "Facilities Team",          5),
    "leaking":           ("Leak (non-urgent)",         24,   "Maintenance Team",         3),
    "damp_mould":        ("Damp / Mould",              72,   "Maintenance Team",         4),
    "other":             ("General Complaint",         48,   "Property Management",      4),
}

EMERGENCY_CATEGORIES = {
    "gas_leak", "fire", "flood", "structural_damage",
    "no_heat_winter", "power_outage", "security_breach", "medical_emergency",
}

# ─────────────────────────────────────────────
# Assurance scripts – spoken aloud after filing
# ─────────────────────────────────────────────

ASSURANCE_SCRIPTS = {
    "gas_leak": (
        "This is a critical emergency. Our emergency response team has been alerted "
        "right now and will be at your property within one hour. Please leave your flat "
        "immediately, do not touch any light switches or electrical devices, and wait outside. "
        "We will call you back within 15 minutes to confirm someone is on their way."
    ),
    "fire": (
        "I've flagged this as a life-safety emergency. Please evacuate the building now "
        "and call 999 if you haven't already. Our emergency team is being dispatched and "
        "will coordinate with the fire service. You will receive a call back within 15 minutes."
    ),
    "flood": (
        "A burst pipe or flooding is a critical emergency. Our emergency plumber has been "
        "paged and will arrive within two hours. If it's safe to do so, please turn off the "
        "water stopcock — it's usually under the kitchen sink. Move valuables away from the "
        "water if possible. We'll call you within 30 minutes to confirm the engineer's ETA."
    ),
    "structural_damage": (
        "Structural damage is being treated as an emergency. A qualified surveyor will inspect "
        "your property within two hours. Please avoid the affected area for your safety. "
        "We'll call you within 30 minutes with an update."
    ),
    "no_heat_winter": (
        "No heating in winter is classified as urgent under housing law. An emergency heating "
        "engineer has been assigned and will contact you within four hours. If you have "
        "vulnerable individuals — children, elderly, or anyone with a medical condition — "
        "please let me note that now so we can escalate the priority further."
    ),
    "power_outage": (
        "We've raised this as an urgent electrical fault. Our team will assess within four hours. "
        "Please avoid using candles for safety. If the outage affects the entire building, we're "
        "already contacting the utility provider. You'll receive a text update within the hour."
    ),
    "security_breach": (
        "Your safety is the top priority. Our security team has been alerted and will respond "
        "within two hours. If you feel you are in immediate danger, please call 999 right now. "
        "We will also review CCTV footage and arrange a security review of your entry points."
    ),
    "medical_emergency": (
        "Please call 999 immediately — this requires the ambulance service directly. "
        "I'm logging this on your account so our property manager is made aware and can provide "
        "any assistance needed. Please stay on the line with the emergency services."
    ),
    "plumbing": (
        "Your plumbing complaint has been logged and assigned to our maintenance team. "
        "A qualified plumber will contact you within 24 hours to arrange a convenient time "
        "to visit. You'll also receive a confirmation text shortly. "
        "If the issue gets worse or causes flooding, please call us back immediately."
    ),
    "electrical": (
        "Your electrical complaint has been raised with our maintenance team and will be "
        "assessed within 24 hours. An electrician will contact you to arrange access. "
        "In the meantime, please avoid using any faulty sockets or switches. "
        "If you notice sparking or smell burning, please call us back straight away."
    ),
    "hvac": (
        "Your heating or air conditioning issue has been logged. Our HVAC team will "
        "be in touch within 24 hours to arrange a visit. If this becomes urgent — "
        "particularly in cold weather — call back and we'll escalate it immediately."
    ),
    "appliance": (
        "Your appliance fault has been recorded and passed to our maintenance team. "
        "They will contact you within 48 hours to assess and repair or replace it. "
        "If it's a landlord-provided appliance, all costs will be covered by us."
    ),
    "pest": (
        "A pest report has been raised and passed to our specialist pest control team. "
        "They will contact you within 48 hours to arrange an inspection and treatment. "
        "Please try not to disturb any nesting areas in the meantime."
    ),
    "noise_complaint": (
        "Your noise complaint has been formally logged. Our property management team will "
        "investigate and contact the relevant party within 24 hours. If the noise is causing "
        "serious distress tonight, you can also contact your local council's noise service. "
        "We'll send you a written update within two working days."
    ),
    "neighbour_dispute": (
        "Your concern has been noted and will be reviewed by our property manager. "
        "We take disputes seriously and aim to mediate fairly for all residents. "
        "A member of the team will contact you within 48 hours to discuss next steps."
    ),
    "parking": (
        "Your parking complaint has been logged. Our facilities team will review the "
        "situation within 48 hours. If there is a vehicle blocking emergency access, "
        "please let me know now and we can escalate that as a priority."
    ),
    "common_area": (
        "Your report about the common area has been sent to our facilities team, "
        "who aim to address communal issues within 48 hours. If it is a safety hazard, "
        "please say so now and we'll treat it as a priority."
    ),
    "lift": (
        "The lift issue has been raised with our maintenance team as a priority fault. "
        "An engineer will be assigned within 12 hours. If you have accessibility needs and "
        "the lift is your only route of access, please tell me now and we'll arrange a priority visit today."
    ),
    "entry_system": (
        "Your entry system or key issue has been logged. Our maintenance team will respond "
        "within 12 hours. If you are currently locked out, please stay on the line and "
        "I'll connect you with our out-of-hours locksmith service right now."
    ),
    "rubbish": (
        "Your waste and rubbish complaint has been passed to our facilities team and "
        "will be addressed within 72 hours. Thank you for flagging this — keeping "
        "communal areas clean is important for everyone in the building."
    ),
    "leaking": (
        "The non-urgent leak has been logged and our plumbing team will contact you within "
        "24 hours to arrange an inspection. If the leak worsens, please call back immediately "
        "so we can upgrade the priority."
    ),
    "damp_mould": (
        "Damp and mould is a health concern we take very seriously. Your complaint has been "
        "logged and our maintenance team will carry out a full assessment within 72 hours. "
        "We will recommend the appropriate treatment and ensure this is resolved properly."
    ),
    "other": (
        "Your complaint has been logged and a reference number has been created. "
        "Our property management team will review it within 48 hours and contact you "
        "with an update. If you feel this needs urgent attention, please let me know now."
    ),
}


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

class ComplaintSystem:

    @staticmethod
    async def verify_tenant(unit_number: str) -> Dict:
        """Verify a tenant by unit number before filing a complaint."""
        tenant = TENANTS.get(unit_number.strip())
        if tenant:
            return {
                "verified": True,
                "unit_number": unit_number,
                "tenant_name": tenant["name"],
            }
        return {
            "verified": False,
            "message": (
                f"I couldn't find unit {unit_number} in our system. "
                "Could you double-check that number? If you've recently moved in, "
                "I can still take your complaint and we'll verify your details afterwards."
            ),
        }

    @staticmethod
    async def file_complaint(
        unit_number: str,
        category: str,
        description: str,
        tenant_name: str,
        contact_number: Optional[str] = None,
    ) -> Dict:
        """
        File a complaint. Returns ticket ID, SLA, response plan,
        and a full assurance message to read back to the tenant.
        """
        category = category.lower().strip()
        if category not in COMPLAINT_CONFIG:
            category = "other"

        label, sla_hours, team, priority = COMPLAINT_CONFIG[category]
        is_emergency = category in EMERGENCY_CATEGORIES

        ticket_id = "MAD-" + str(uuid.uuid4())[:8].upper()
        now = datetime.utcnow()
        deadline = now + timedelta(hours=sla_hours) if sla_hours > 0 else now

        response_plan = _build_response_plan(category, label, team, sla_hours, is_emergency)

        record = {
            "ticket_id": ticket_id,
            "unit_number": unit_number,
            "tenant_name": tenant_name,
            "contact_number": contact_number,
            "category": category,
            "label": label,
            "description": description,
            "is_emergency": is_emergency,
            "priority": priority,
            "team": team,
            "sla_hours": sla_hours,
            "status": "open",
            "created_at": now.isoformat(),
            "deadline": deadline.isoformat(),
            "response_plan": response_plan,
        }
        COMPLAINTS[ticket_id] = record

        assurance = ASSURANCE_SCRIPTS.get(category, ASSURANCE_SCRIPTS["other"])

        return {
            "success": True,
            "ticket_id": ticket_id,
            "is_emergency": is_emergency,
            "label": label,
            "team": team,
            "sla_hours": sla_hours,
            "sla_description": _sla_to_words(sla_hours),
            "response_plan": response_plan,
            "assurance_message": assurance,
        }

    @staticmethod
    async def check_complaint_status(ticket_id: str) -> Dict:
        """Return current status and next steps for an existing complaint ticket."""
        ticket = COMPLAINTS.get(ticket_id.strip().upper())
        if not ticket:
            return {
                "found": False,
                "message": (
                    f"I couldn't find ticket {ticket_id}. "
                    "The reference starts with MAD- followed by eight characters. "
                    "Would you like to check whether you have the right number?"
                ),
            }

        now = datetime.utcnow()
        deadline = datetime.fromisoformat(ticket["deadline"])
        hours_remaining = max(0.0, (deadline - now).total_seconds() / 3600)

        return {
            "found": True,
            "ticket_id": ticket_id,
            "label": ticket["label"],
            "status": ticket["status"],
            "team": ticket["team"],
            "created_at": ticket["created_at"],
            "sla_description": _sla_to_words(ticket["sla_hours"]),
            "hours_remaining": round(hours_remaining, 1),
            "response_plan": ticket["response_plan"],
            "is_emergency": ticket["is_emergency"],
        }

    @staticmethod
    async def list_tenant_complaints(unit_number: str) -> Dict:
        """Return all complaints on file for a given unit."""
        tickets = [
            {
                "ticket_id": t["ticket_id"],
                "label": t["label"],
                "status": t["status"],
                "created_at": t["created_at"],
                "sla_description": _sla_to_words(t["sla_hours"]),
            }
            for t in COMPLAINTS.values()
            if t["unit_number"] == unit_number
        ]

        if not tickets:
            return {
                "found": False,
                "message": f"There are no logged complaints for unit {unit_number}.",
            }

        return {
            "found": True,
            "unit_number": unit_number,
            "count": len(tickets),
            "complaints": tickets,
        }

    @staticmethod
    async def get_complaint_categories() -> Dict:
        """Return categorised list of complaint types to help guide the caller."""
        emergency = [
            {"category": k, "label": v[0], "sla": _sla_to_words(v[1])}
            for k, v in COMPLAINT_CONFIG.items()
            if k in EMERGENCY_CATEGORIES
        ]
        non_emergency = [
            {"category": k, "label": v[0], "sla": _sla_to_words(v[1])}
            for k, v in COMPLAINT_CONFIG.items()
            if k not in EMERGENCY_CATEGORIES
        ]
        return {
            "emergency_categories": emergency,
            "non_emergency_categories": non_emergency,
        }


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _sla_to_words(hours: int) -> str:
    if hours == 0:
        return "immediate – call 999 now"
    if hours == 1:
        return "within 1 hour"
    if hours < 24:
        return f"within {hours} hours"
    days = hours // 24
    return f"within {days} working day{'s' if days > 1 else ''}"


def _build_response_plan(
    category: str,
    label: str,
    team: str,
    sla_hours: int,
    is_emergency: bool,
) -> str:
    """Plain-English steps so the tenant knows exactly what happens next."""
    if category == "medical_emergency":
        return (
            "Step 1 – Call 999 immediately for the ambulance service.\n"
            "Step 2 – Your property manager has been notified and will follow up.\n"
            "Step 3 – A welfare check will be arranged if needed."
        )
    if is_emergency:
        return (
            f"Step 1 – Your complaint has been flagged as an EMERGENCY with our {team}.\n"
            f"Step 2 – A specialist will be dispatched {_sla_to_words(sla_hours)}.\n"
            "Step 3 – You will receive a call-back within 15–30 minutes to confirm the engineer's ETA.\n"
            "Step 4 – Once the immediate risk is made safe, a follow-up inspection will be scheduled.\n"
            "Step 5 – A written incident report will be sent to you within 24 hours of resolution."
        )
    return (
        f"Step 1 – Your {label} complaint has been logged and assigned to the {team}.\n"
        f"Step 2 – A team member will contact you {_sla_to_words(sla_hours)} to arrange access or discuss next steps.\n"
        "Step 3 – All repair work will be carried out by a qualified contractor at no cost to you.\n"
        "Step 4 – You will receive SMS and email updates as the ticket progresses.\n"
        "Step 5 – Once the work is complete, we will ask you to confirm the issue is resolved before closing the ticket."
    )