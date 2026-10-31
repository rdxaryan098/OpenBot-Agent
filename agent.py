import os
import json
import uuid
import traceback
from datetime import datetime, timezone
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

NL = chr(10) + chr(10)

# Fallback chain of current Gemini 3.x Flash models for new AQ.Ab keys
MODELS_TO_TRY = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
]

def sse_event(data: dict) -> str:
    return "data: " + json.dumps(data) + NL

STRATEGIST_SYSTEM_PROMPT = (
    "You are an elite YouTube Shorts and Reels Niche Strategist. "
    "Analyze trends, identify high-retention hooks, and generate structured, "
    "actionable content blueprints and prompts that can be handed off directly "
    "to a video scriptwriter."
)

CREATOR_SYSTEM_PROMPT = (
    "You are an expert short-form Video Scriptwriter, Editor, and Social Media Manager. "
    "Take the user strategy or prompt and write a high-retention 60-second video script "
    "(with [Visual/Audio Cues], a 3-second viral hook, and pacing notes) followed by "
    "a ready-to-publish caption and hashtags."
)

@app.get("/")
@app.get("/health")
@app.get("/info")
@app.get("/ag-ui")
@app.get("/ag-ui/info")
@app.get("/ag-ui-creator")
@app.get("/ag-ui-creator/info")
async def health_and_info():
    return {
        "status": "online",
        "version": "2.0-fallback",
        "models": MODELS_TO_TRY,
        "agents": [
            {"id": "strategist", "name": "Shorts and Reels Niche Scout"},
            {"id": "creator", "name": "Video and Post Creator"}
        ]
    }

# --- COMPLETE THREAD & STATE ENDPOINTS FOR OPENBOT ---
def make_thread_Obj(tid: str, metadata: dict = None):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "threadId": tid,
        "thread_id": tid,
        "id": tid,
        "status": "idle",
        "created_at": now,
        "updated_at": now,
        "values": {"messages": []},
        "messages": [],
        "metadata": metadata or {}
    }

@app.post("/threads")
@app.get("/threads")
@app.post("/ag-ui/threads")
@app.get("/ag-ui/threads")
@app.post("/ag-ui-creator/threads")
@app.get("/ag-ui-creator/threads")
@app.api_route("/threads/{thread_id}", methods=["GET", "POST", "PATCH"])
@app.api_route("/ag-ui/threads/{thread_id}", methods=["GET", "POST", "PATCH"])
@app.api_route("/ag-ui-creator/threads/{thread_id}", methods=["GET", "POST", "PATCH"])
async def handle_threads(request: Request, thread_id: str = None):
    try:
        body = await request.json()
    except Exception:
        body = {}
    tid = thread_id or (body.get("threadId") if isinstance(body, dict) else None) or (body.get("thread_id") if isinstance(body, dict) else None) or str(uuid.uuid4())
    meta = body.get("metadata", {}) if isinstance(body, dict) else {}
    return JSONResponse(make_thread_Obj(tid, meta))

@app.api_route("/threads/{thread_id}/state", methods=["GET", "POST"])
@app.api_route("/ag-ui/threads/{thread_id}/state", methods=["GET", "POST"])
@app.api_route("/ag-ui-creator/threads/{thread_id}/state", methods=["GET", "POST"])
async def handle_thread_state(thread_id: str):
    return JSONResponse({
        "values": {"messages": []},
        "next": [],
        "tasks": [],
        "metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint": {"thread_id": thread_id, "checkpoint_ns": "", "checkpoint_id": thread_id}
    })

@app.api_route("/threads/{thread_id}/history", methods=["GET", "POST"])
@app.api_route("/ag-ui/threads/{thread_id}/history", methods=["GET", "POST"])
@app.api_route("/ag-ui-creator/threads/{thread_id}/history", methods=["GET", "POST"])
async def handle_thread_history(thread_id: str):
    return JSONResponse([])

@app.api_route("/threads/{thread_id}/messages", methods=["GET", "POST"])
@app.api_route("/ag-ui/threads/{thread_id}/messages", methods=["GET", "POST"])
@app.api_route("/ag-ui-creator/threads/{thread_id}/messages", methods=["GET", "POST"])
async def handle_thread_messages(thread_id: str):
    return JSONResponse({"messages": [], "data": []})

def build_conversation_prompt(body: dict, default_prompt: str) -> str:
    if not isinstance(body, dict):
        return default_prompt
    # Support nested input payloads from LangGraph / OpenBot REST runners
    input_obj = body.get("input")
    messages = body.get("messages")
    if not messages and isinstance(input_obj, dict):
        messages = input_obj.get("messages")

    if isinstance(messages, list) and len(messages) > 0:
        history = []
        for msg in messages[-10:]:
            if isinstance(msg, dict):
                role = msg.get("role", msg.get("type", "user")).upper()
                content = msg.get("content", msg.get("text", ""))
                if isinstance(content, list):
                    content = " ".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                if isinstance(content, str) and content.strip():
                    history.append(role + ": " + content.strip())
            elif isinstance(msg, str) and msg.strip():
                history.append("USER: " + msg.strip())
        if history:
            return chr(10).join(history)

    for key in ("prompt", "input", "message", "text", "query"):
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return default_prompt

async def run_ag_ui_stream(request: Request, system_instruction: str, default_prompt: str, thread_id_param: str = None):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    thread_id = thread_id_param or body.get("threadId") or body.get("thread_id") or str(uuid.uuid4())
    run_id = body.get("runId") or body.get("run_id") or str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    conversation_text = build_conversation_prompt(body, default_prompt)

    async def event_stream():
        yield sse_event({"type": "RUN_STARTED", "threadId": thread_id, "runId": run_id})
        yield sse_event({"type": "TEXT_MESSAGE_START", "messageId": msg_id, "role": "assistant"})

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            yield sse_event({
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": msg_id,
                "delta": "Configuration Error: GEMINI_API_KEY is missing in Render environment variables."
            })
        else:
            client = genai.Client(api_key=api_key)
            success = False
            last_error = ""

            for model_name in MODELS_TO_TRY:
                try:
                    response_stream = client.models.generate_content_stream(
                        model=model_name,
                        contents=conversation_text,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                        ),
                    )
                    sent_any = False
                    for chunk in response_stream:
                        if chunk.text:
                            sent_any = True
                            success = True
                            yield sse_event({
                                "type": "TEXT_MESSAGE_CONTENT",
                                "messageId": msg_id,
                                "delta": chunk.text
                            })
                    if sent_any:
                        break
                except Exception as e:
                    last_error = f"[{model_name}] {str(e)}"
                    print("MODEL FALLBACK WARNING:", last_error)
                    continue

            if not success:
                yield sse_event({
                    "type": "TEXT_MESSAGE_CONTENT",
                    "messageId": msg_id,
                    "delta": "All models failed. Last error: " + last_error
                })

        yield sse_event({"type": "TEXT_MESSAGE_END", "messageId": msg_id})
        yield sse_event({"type": "RUN_FINISHED", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )

# --- BOT 1: NICHE & PROMPT STRATEGIST ---
@app.post("/ag-ui")
@app.post("/ag-ui/runs")
@app.post("/ag-ui/runs/stream")
@app.post("/ag-ui/runs/wait")
@app.post("/ag-ui/threads/{thread_id}/runs")
@app.post("/ag-ui/threads/{thread_id}/runs/stream")
@app.post("/ag-ui/threads/{thread_id}/runs/wait")
@app.post("/runs")
@app.post("/runs/stream")
@app.post("/threads/{thread_id}/runs")
@app.post("/threads/{thread_id}/runs/stream")
async def strategy_agent(request: Request, thread_id: str = None):
    return await run_ag_ui_stream(
        request=request,
        system_instruction=STRATEGIST_SYSTEM_PROMPT,
        default_prompt="Give me 3 high-retention YouTube Shorts niche ideas and viral hooks for this week.",
        thread_id_param=thread_id
    )

# --- BOT 2: VIDEO SCRIPT & POST CREATOR ---
@app.post("/ag-ui-creator")
@app.post("/ag-ui-creator/runs")
@app.post("/ag-ui-creator/runs/stream")
@app.post("/ag-ui-creator/runs/wait")
@app.post("/ag-ui-creator/threads/{thread_id}/runs")
@app.post("/ag-ui-creator/threads/{thread_id}/runs/stream")
@app.post("/ag-ui-creator/threads/{thread_id}/runs/wait")
async def creator_agent(request: Request, thread_id: str = None):
    return await run_ag_ui_stream(
        request=request,
        system_instruction=CREATOR_SYSTEM_PROMPT,
        default_prompt="Write a viral 60-second YouTube Shorts script and caption based on the latest strategy.",
        thread_id_param=thread_id
    )
