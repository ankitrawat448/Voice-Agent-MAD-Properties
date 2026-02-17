# MAD Apartments – Complaint Hotline Voice Agent

A production-ready voice AI agent that tenants call to file **emergency and non-emergency complaints** by phone. The agent verifies the caller, categorises the issue, logs a ticket, and reads a **specific assurance message** telling them exactly what will happen next — response time, responsible team, and five concrete steps.

Built with **Deepgram Agent API**, **OpenAI GPT-4o-mini**, and **Twilio** over real-time WebSocket streaming.

---

## How It Works

```
Tenant calls → Alex greets → Asks for unit number
    → Verifies tenant → Asks what the problem is
    → Identifies category (emergency / non-emergency)
    → Collects name + callback number
    → Files complaint → Reads assurance message aloud
    → Gives ticket reference → Offers further help
```

For **life-threatening emergencies** (gas leak, fire, medical) the agent instructs the tenant to call 999 *before* filing the ticket.

Policy questions ("what are my rights?", "how long do repairs take?") are answered directly from the three policy documents embedded in the system prompt — no hallucination, no RAG overhead.

---

## Complaint Categories

### 🚨 Emergency (SLA: 1–4 hours, 24/7)
| Category | SLA |
|---|---|
| Gas Leak | 1 hour |
| Fire / Smoke | 1 hour |
| Flooding / Burst Pipe | 2 hours |
| Structural Damage | 2 hours |
| Security / Break-in | 2 hours |
| No Heating (Winter) | 4 hours |
| Power Outage | 4 hours |
| Medical Emergency | Call 999 immediately |

### 🔧 Non-Emergency (SLA: 12 hours – 3 working days)
Plumbing · Electrical · HVAC · Appliance · Pest · Noise Complaint · Neighbour Dispute · Parking · Common Area · Lift · Entry System / Keys · Damp & Mould · Rubbish · Leaking (non-urgent) · General

---

## Assurance Messages

Every category has a hand-written assurance script the agent reads verbatim after filing. Example for a gas leak:

> *"This is a critical emergency. Our emergency response team has been alerted right now and will be at your property within one hour. Please leave your flat immediately, do not touch any light switches or electrical devices, and wait outside. We will call you back within 15 minutes to confirm someone is on their way."*

---

## Project Structure

```
Voice-Agent-MAD-Properties/
├── main.py                  # WebSocket server — Twilio ↔ Deepgram bridge
├── functions.py             # Tool schemas + execution routing (6 tools)
├── business_logic.py        # SLA config, assurance scripts, complaint store
├── config.json              # Agent settings, voice, prompt + embedded policy docs
├── knowledge_base/          # Source policy documents (edit these to update policy)
│   ├── emergency_procedures.txt
│   ├── maintenance_policy.txt
│   └── tenant_rights_and_escalation.txt
├── test_complaints.py       # 13-scenario test suite (no API keys needed)
├── pyproject.toml           # uv project config
└── .env                     # Your API key (not committed)
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Deepgram account](https://console.deepgram.com) (free tier: $200 credit)
- [Twilio account](https://twilio.com) (free trial includes a phone number)
- [ngrok](https://ngrok.com) (for local development)

### 1. Clone and install

```bash
git clone https://github.com/ankitrawat448/Voice-Agent-MAD-Properties.git
cd Voice-Agent-MAD-Properties
uv sync
```

### 2. Add your API key

```bash
echo "DEEPGRAM_API_KEY=your_key_here" > .env
```

Get your key at [console.deepgram.com](https://console.deepgram.com) → API Keys → Create Key.

### 3. Test locally (no phone needed)

```bash
uv run test_complaints.py
```

All 13 scenarios should pass — verifies the entire complaint pipeline without needing Twilio or Deepgram.

### 4. Start the server

```bash
uv run main.py
```

```
14:00:00  INFO     Starting MAD Apartments Complaint Hotline on port 5000
14:00:00  INFO     Server ready. Waiting for calls…
```

### 5. Expose with ngrok

```bash
ngrok http 5000
```

Copy the `wss://` forwarding URL (e.g. `wss://abc123.ngrok.io`).

### 6. Connect Twilio

1. Go to your Twilio number → **Configure**
2. Under **"A Call Comes In"** → select **WebSocket**
3. Paste your ngrok `wss://` URL
4. Save

### 7. Call it

Call your Twilio number. Alex will answer:

> *"Hello, thank you for calling MAD Apartments. My name is Alex and I'm here to help. Could I start by getting your flat or unit number please?"*

---

## Tool Calls (Function Calling)

The agent uses 6 tools via Deepgram's function calling API:

| Tool | Triggered when |
|---|---|
| `agent_filler` | Before every lookup — fills silence naturally |
| `verify_tenant` | Caller gives their unit number |
| `get_complaint_categories` | Caller is unsure what type of complaint to file |
| `file_complaint` | All details collected — creates ticket + returns assurance message |
| `check_complaint_status` | Caller asks about an existing ticket reference |
| `list_tenant_complaints` | Caller wants to see all open complaints for their unit |

---

## Policy Documents

Three plain-text documents in `knowledge_base/` are embedded directly into the system prompt at startup:

| Document | Covers |
|---|---|
| `emergency_procedures.txt` | What qualifies as an emergency, response times, what to do while waiting, out-of-hours contacts |
| `maintenance_policy.txt` | Landlord vs tenant responsibilities, repair priority levels, damp/mould (Awaab's Law), costs |
| `tenant_rights_and_escalation.txt` | Legal rights, 4-stage escalation up to Housing Ombudsman, Shelter/CAB contacts |

To update a policy, edit the relevant `.txt` file and restart the server.

---

## Environment Variables

```env
DEEPGRAM_API_KEY=your_deepgram_api_key_here
```

---

## Customisation

**Add a complaint category** — edit `COMPLAINT_CONFIG` and `ASSURANCE_SCRIPTS` in `business_logic.py`. No other files need changing.

**Update a policy** — edit the relevant file in `knowledge_base/` and restart the server.

**Change the voice** — update `speak.model` in `config.json`:
- `aura-2-thalia-en` — female (default)
- `aura-2-orion-en` — male

**Connect a real database** — replace the `TENANTS` and `COMPLAINTS` dicts in `business_logic.py` with async DB calls.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Telephony | Twilio Voice WebSocket Streams |
| Speech-to-Text | Deepgram Nova-3 |
| LLM | OpenAI GPT-4o-mini (via Deepgram Agent API) |
| Text-to-Speech | Deepgram Aura-2 Thalia |
| Server | Python `asyncio` + `websockets` |
| Package manager | `uv` |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `DEEPGRAM_API_KEY is not set` | Check `.env` exists in the project root |
| `ModuleNotFoundError: business_logic` | File may be saved as `buisness_logic.py` — rename it |
| No audio / silence on call | Verify Twilio is set to **WebSocket**, not HTTP webhook |
| ngrok URL rejected | Make sure you're pasting the `wss://` URL, not `https://` |
| Tests fail | Run `uv sync` first to ensure dependencies are installed |
