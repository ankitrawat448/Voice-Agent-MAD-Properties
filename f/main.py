"""
MAD Apartments – Complaints Hotline Voice Agent
Real-time voice AI over phone (Twilio → Deepgram → OpenAI → Deepgram → Twilio)
Handles emergency and non-emergency tenant complaints with full tool-calling support.
"""
import asyncio
import base64
import json
import logging
import os

import websockets
from dotenv import load_dotenv

from functions import execute_function, FUNCTION_DEFINITIONS
from rag_engine import build_index

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise ValueError("DEEPGRAM_API_KEY is not set in your environment or .env file.")

DEEPGRAM_URL  = "wss://agent.deepgram.com/agent"
WEBSOCKET_PORT = 5000
SAMPLE_RATE    = 8000
CHUNK_MS       = 20
BYTES_PER_CHUNK = int(SAMPLE_RATE * CHUNK_MS / 1000)   # 160 bytes


# ─────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────

def load_config() -> dict:
    with open("config.json") as f:
        cfg = json.load(f)
    # Inject live function definitions at runtime
    cfg["agent"]["think"]["functions"] = FUNCTION_DEFINITIONS
    return cfg


# ─────────────────────────────────────────────
# Audio pipeline tasks
# ─────────────────────────────────────────────

async def twilio_receiver(ws_twilio, audio_queue: asyncio.Queue):
    """Read μ-law audio from Twilio and push 20 ms chunks to the queue."""
    try:
        buf = bytearray()
        async for raw in ws_twilio:
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                buf.extend(base64.b64decode(msg["media"]["payload"]))
                while len(buf) >= BYTES_PER_CHUNK:
                    await audio_queue.put(bytes(buf[:BYTES_PER_CHUNK]))
                    buf = buf[BYTES_PER_CHUNK:]

            elif event == "start":
                logger.info(f"Twilio stream started  sid={msg.get('streamSid')}")

            elif event == "stop":
                logger.info("Twilio stream stopped.")
                break

    except websockets.exceptions.ConnectionClosed:
        logger.info("Twilio disconnected (twilio_receiver).")
    except Exception as exc:
        logger.error(f"twilio_receiver error: {exc}", exc_info=True)
    finally:
        await audio_queue.put(None)          # sentinel → end of stream


async def sts_sender(ws_dg, audio_queue: asyncio.Queue):
    """Forward buffered audio chunks to Deepgram."""
    try:
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                await ws_dg.close()
                break
            await ws_dg.send(chunk)
    except Exception as exc:
        logger.error(f"sts_sender error: {exc}", exc_info=True)


async def sts_receiver(ws_dg, ws_twilio):
    """
    Receive from Deepgram:
      - binary frames  → forward as audio to Twilio
      - JSON frames    → handle events & function calls
    """
    try:
        async for raw in ws_dg:
            # ── Binary audio ────────────────────────────────────
            if isinstance(raw, bytes):
                await ws_twilio.send(json.dumps({
                    "event":     "media",
                    "streamSid": _stream_sid(ws_twilio),
                    "media":     {"payload": base64.b64encode(raw).decode()},
                }))
                continue

            # ── JSON control / event ─────────────────────────────
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")

            if mtype == "ConversationText":
                role    = msg.get("role", "?").upper()
                content = msg.get("content", "")
                logger.info(f"[{role}] {content}")

            elif mtype == "FunctionCallRequest":
                await _handle_function_call(msg, ws_dg)

            elif mtype == "UserStartedSpeaking":
                # Barge-in: stop any audio currently playing on Twilio
                await ws_twilio.send(json.dumps({
                    "event":     "clear",
                    "streamSid": _stream_sid(ws_twilio),
                }))

            elif mtype in ("Welcome", "SettingsApplied", "AgentThinking", "AgentAudioDone"):
                logger.info(f"Deepgram event: {mtype}")

            elif mtype in ("AgentError", "AgentWarning"):
                logger.warning(f"Deepgram {mtype}: {msg}")

    except websockets.exceptions.ConnectionClosed:
        logger.info("Deepgram disconnected (sts_receiver).")
    except Exception as exc:
        logger.error(f"sts_receiver error: {exc}", exc_info=True)


# ─────────────────────────────────────────────
# Function-call handler
# ─────────────────────────────────────────────

async def _handle_function_call(req: dict, ws_dg):
    name    = req.get("name")
    call_id = req.get("id")
    args    = req.get("arguments", {})

    logger.info(f"[TOOL CALL] {name}  args={args}")

    if not req.get("client_side", True):
        logger.info(f"[TOOL CALL] {name} is server-side — skipping client execution.")
        return

    content = await execute_function(name, args)

    await ws_dg.send(json.dumps({
        "type":    "FunctionCallResponse",
        "id":      call_id,
        "name":    name,
        "content": content,
    }))
    logger.info(f"[TOOL RESPONSE] {name} sent.")


# ─────────────────────────────────────────────
# Connection handler
# ─────────────────────────────────────────────

async def handle_twilio_connection(ws_twilio, path):
    logger.info(f"Incoming call  remote={ws_twilio.remote_address}")
    audio_queue: asyncio.Queue = asyncio.Queue()

    try:
        cfg = load_config()
        async with websockets.connect(
            DEEPGRAM_URL,
            extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
        ) as ws_dg:
            logger.info("Connected to Deepgram Agent API.")
            await ws_dg.send(json.dumps(cfg))
            logger.info(f"Settings sent  ({len(FUNCTION_DEFINITIONS)} functions registered).")

            await asyncio.gather(
                twilio_receiver(ws_twilio, audio_queue),
                sts_sender(ws_dg, audio_queue),
                sts_receiver(ws_dg, ws_twilio),
                return_exceptions=True,
            )

    except Exception as exc:
        logger.error(f"Connection handler error: {exc}", exc_info=True)
    finally:
        logger.info("Call ended.")
        await ws_twilio.close()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _stream_sid(ws) -> str:
    """Extract Twilio streamSid from the WebSocket path (best-effort)."""
    try:
        return ws.path.split("/")[-1]
    except Exception:
        return ""


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

async def main():
    logger.info(f"Starting MAD Apartments Complaint Hotline on port {WEBSOCKET_PORT}")

    # Build / refresh the RAG knowledge base index at startup
    logger.info("Building RAG knowledge base index…")
    total_chunks = await build_index()
    logger.info(f"Knowledge base ready: {total_chunks} chunks indexed.")

    async with websockets.serve(handle_twilio_connection, "0.0.0.0", WEBSOCKET_PORT):
        logger.info("Server ready. Waiting for calls…")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
