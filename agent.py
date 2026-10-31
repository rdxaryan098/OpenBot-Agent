import os
import json
import uuid
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from google import genai
from google.genai import types

app = FastAPI(title="OpenBot Multi-Agent Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

NL = "\n\n"

def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}{NL}"

STRATEGIST_SYSTEM_PROMPT = (
    "You are an elite YouTube Shorts and Reels Niche Strategist. "
    "Analyze trends, identify high-retention hooks, and generate structured, "
    "actionable content blueprints and prompts that can be handed off directly "
    "to a video scriptwriter."
)

CREATOR_SYSTEM_PROMPT = (
    "You are an expert short-form Video Scriptwriter, Editor, and Social Media Manager. "
    "Take the user's strategy or prompt and write a high-retention 60-second video script "
    "(with [Visual/Audio Cues], a 3-second viral hook, and pacing notes) followed by "
    "a ready-to-publish caption and hashtags."
)

@app.get("/")
@app.get("/health")
@app.get("/ag-ui")
@app.get("/ag-ui-creator")
async def health_check():
    return {
        "status": "online",
        "service": "OpenBot Multi-Agent System",
        "endpoints": ["/ag-ui", "/ag-ui-creator"]
    }

@app.post("/threads")
@app.post("/ag-ui/threads")
@app.post("/ag-ui-creator/threads")
@app.get("/threads/{thread_id}")
@app.post("/threads/{thread_id}")
async def handle_threads(request: Request, thread_id: str = None):
    try:
        body = await request.json()
    except Exception:
        body = {}

    tid = thread_id or body.get("threadId") or body.get("thread_id") or str(uuid.uuid4())
    return JSONResponse({
        "threadId": tid,
        "thread_id": tid,
        "id": tid,
        "status": "initialized",
        "values": {},
        "metadata": body.get("metadata", {})
    })

def build_conversation_prompt(body: dict, default_prompt: str) -> str:
    messages = body.get("messages")
    if isinstance(messages, list) and len(messages) > 0:
        history = []
        for msg in messages[-10:]:
            if isinstance(msg, dict):
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                if isinstance(content, str) and content.strip():
                    history.append(f"{role}: {content.strip()}")
            elif isinstance(msg, str) and msg.strip():
                history.append(f"USER: {msg.strip()}")
        if history:
            return "\n".join(history)

    if isinstance(body.get("prompt"), str) and body["prompt"].strip():
        return body["prompt"].strip()
    if isinstance(body.get("input"), str) and body["input"].strip():
        return body["input"].strip()

    return default_prompt

async def run_ag_ui_stream(request: Request, system_instruction: str, default_prompt: str):
    try:
        body = await request.json()
    except Exception:
        body = {}

    thread_id = body.get("threadId") or body.get("thread_id") or str(uuid.uuid4())
    run_id = body.get("runId") or body.get("run_id") or str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    conversation_text = build_conversation_prompt(body, default_prompt)

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
            yield sse_event({
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": msg_id,
                "delta": "Configuration Error: GEMINI_API_KEY is missing in Render environment variables."
            })
        else:
            try:
                client = genai.Client(api_key=api_key)
                response_stream = client.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=conversation_text,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.7,
                    ),
                )
                sent_any = False
                for chunk in response_stream:
                    if chunk.text:
                        sent_any = True
                        yield sse_event({
                            "type": "TEXT_MESSAGE_CONTENT",
                            "messageId": msg_id,
                            "delta": chunk.text
                        })
                if not sent_any:
                    yield sse_event({
                        "type": "TEXT_MESSAGE_CONTENT",
                        "messageId": msg_id,
                        "delta": "No output generated. Try rephrasing your prompt."
                    })
            except Exception as e:
                print("GEMINI STREAM ERROR:", traceback.format_exc())
                yield sse_event({
                    "type": "TEXT_MESSAGE_CONTENT",
                    "messageId": msg_id,
                    "delta": f"Backend Error: {str(e)}"
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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/ag-ui")
@app.post("/ag-ui/runs")
@app.post("/ag-ui/threads/{thread_id}/runs")
async def strategy_agent(request: Request, thread_id: str = None):
    return await run_ag_ui_stream(
        request=request,
        system_instruction=STRATEGIST_SYSTEM_PROMPT,
        default_prompt="Give me 3 high-retention YouTube Shorts niche ideas and viral hooks for this week."
    )

@app.post("/ag-ui-creator")
@app.post("/ag-ui-creator/runs")
@app.post("/ag-ui-creator/threads/{thread_id}/runs")
async def creator_agent(request: Request, thread_id: str = None):
    return await run_ag_ui_stream(
        request=request,
        system_instruction=CREATOR_SYSTEM_PROMPT,
        default_prompt="Write a viral 60-second YouTube Shorts script and caption based on the latest strategy."
    )
