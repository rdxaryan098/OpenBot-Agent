import os
import json
import uuid
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from google import genai

app = FastAPI()
NL = chr(10) + chr(10)

def sse_event(data: dict) -> str:
    return "data: " + json.dumps(data) + NL

@app.get("/")
async def root():
    return {"status": "online", "service": "OpenBot AG-UI Agent"}

@app.post("/ag-ui")
async def handle_agent(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    thread_id = body.get("threadId") or str(uuid.uuid4())
    run_id = body.get("runId") or str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    user_prompt = "Hello! Introduce yourself briefly."
    messages = body.get("messages")
    if isinstance(messages, list) and len(messages) > 0:
        last_msg = messages[-1]
        if isinstance(last_msg, dict):
            content = last_msg.get("content")
            if isinstance(content, str) and content.strip():
                user_prompt = content
        elif isinstance(last_msg, str) and last_msg.strip():
            user_prompt = last_msg
    elif isinstance(body.get("prompt"), str) and body.get("prompt").strip():
        user_prompt = body.get("prompt")

    async def event_stream():
        yield sse_event({
            "type": "RUN_STARTED",
            "threadId": thread_id,
            "runId": run_id
        })
        yield sse_event({
            "type": "TEXT_MESSAGE_START",
            "messageId": msg_id,
            "role": "assistant"
        })

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            reply_text = "Error: GEMINI_API_KEY is not set in Render Environment Variables."
        else:
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="Act as an expert YouTube Shorts and social media niche strategist. " + user_prompt
                )
                reply_text = response.text or "No response generated."
            except Exception as e:
                print("GEMINI ERROR:", traceback.format_exc())
                reply_text = "Gemini API Error: " + str(e)

        yield sse_event({
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": msg_id,
            "delta": reply_text
        })
        yield sse_event({
            "type": "TEXT_MESSAGE_END",
            "messageId": msg_id
        })
        yield sse_event({
            "type": "RUN_FINISHED",
            "threadId": thread_id,
            "runId": run_id
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
