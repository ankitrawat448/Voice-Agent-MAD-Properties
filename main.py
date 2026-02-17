import asyncio
import base64
import json
import sys
import websockets
import os
from dotenv import load_dotenv

load_dotenv()


def sts_connect():
  # you can run export DEEPGRAM_API_KEY="your key" in your terminal to set your API key.
  api_key = os.getenv('DEEPGRAM_API_KEY')
  if not api_key:
      raise ValueError("DEEPGRAM_API_KEY environment variable is not set")

  sts_ws = websockets.connect(
      "wss://agent.deepgram.com/v1/agent/converse",
      subprotocols=["token", api_key]
  )
  return sts_ws



def load_config():
    with open('config.json') as f:
        config = json.load(f)
    return config


async def handle_barge_in(decoded, twilio_ws, streamsid):
    if decoded["type"] == "UserStartedSpeaking":
        print("User started speaking, sending barge-in message to Twilio")
        clear_message = {
            "event": "barge-in",
            "streamsid": streamsid
        }
        await twilio_ws.send(json.dumps(clear_message))

async def handle_text_message(decoded, twilio_ws, sts_ws, streamsid):
    await handle_barge_in(decoded, twilio_ws, streamsid)

    #TODO handle function calling

async def sts_sender(sts_ws, audio_queue):
    print("STS Sender started")
    while True:
        chunk = await audio_queue.get()
        await sts_ws.send(chunk)

async def sts_receiver(sts_ws, twilio_ws, streamsid_queue):
    print("STS Receiver started")
    streamsid = await streamsid_queue.get()
    async for message in sts_ws:
        if type(message) == str:
            print(message)
            decoded = json.loads(message)
            await handle_text_message(decoded, twilio_ws, sts_ws, streamsid)
            continue

        raw_mulaw = message

        media_message = {
            "event": "media",
            "streamsid": streamsid,
            "media": {
                "payload": base64.b64encode(raw_mulaw).decode("ascii"),
            }
        }
        await twilio_ws.send(json.dumps(media_message))



async def twilio_receiver(twilio_ws, audio_queue, streamsid_queue):
    BUFFER_SIZE = 20 * 160
    inbuffer = bytearray(b"")

    async for message in twilio_ws:
        try:
            data = json.loads(message)
            event = data["event"]
            
            if event == "start":
                print("GET streamsid")
                start = data["start"]
                streamsid = data["streamsid"]
                streamsid_queue.put_nowait(streamsid)
            elif event == "connected":
                continue
            elif event == "media":
                media = data["media"]
                chunk = base64.b64decode(media["payload"])
                if media["track"] == "inbound":
                    inbuffer.extend(chunk)
            elif event == "stop":
                break

            while len(inbuffer) >= BUFFER_SIZE:
                chunk = inbuffer[:BUFFER_SIZE]
                audio_queue.put_nowait(chunk)
                inbuffer = inbuffer[BUFFER_SIZE:]
                
        except:
            break

async def twilio_handler(twilio_ws):
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    async with sts_connect() as sts_ws:
        config_message = load_config()
        await sts_ws.send(json.dumps(config_message))

        await asyncio.wait([
            asyncio.ensure_future(sts_sender(sts_ws, audio_queue)),
            asyncio.ensure_future(sts_receiver(sts_ws, twilio_ws, streamsid_queue)),
            asyncio.ensure_future(twilio_receiver(twilio_ws, audio_queue, streamsid_queue))
        ])

        await twilio_ws.close()


async def main():
    await websockets.serve(twilio_handler, "localhost", 5000)
    print("Server started on ws://localhost:5000")
    await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())