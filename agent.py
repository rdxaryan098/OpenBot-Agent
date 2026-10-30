import os
import json
import traceback
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from google import genai

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "online", "service": "OpenBot AG-UI Agent"}

@app.post("/ag-ui")
async def handle_agent(request: Request):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")
    
    try:
        body = await request.json()
        user_prompt = "Hello"
        if "messages" in body and isinstance(body["messages"], list) and len(body["messages"]) > 0:
            last_msg = body["messages"][-1]
            if isinstance(last_msg, dict):
                user_prompt = last_msg.get("content", "Hello")
            else:
                user_prompt = str(last_msg)
        elif "prompt" in body:
            user_prompt = body["prompt"]

        client = genai.Client(api_key=api_key)
        
        # Generate content from Gemini
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Act as an expert YouTube Shorts and social media niche strategist. {user_prompt}"
        )
        agent_reply = response.text

        async def event_stream():
            # AG-UI protocol event stream format
            yield f"data: {json.dumps({"type": "RUN_STARTED"})}

"
            yield f"data: {json.dumps({"type": "TEXT_MESSAGE_START"})}

"
            
            # Send the text chunk
            yield f"data: {json.dumps({"type": "TEXT_MESSAGE_CONTENT", "delta": agent_reply})}

"
            
            yield f"data: {json.dumps({"type": "TEXT_MESSAGE_END"})}

"
            yield f"data: {json.dumps({"type": "RUN_FINISHED"})}

"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    except Exception as e:
        print("INTERNAL ERROR:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
