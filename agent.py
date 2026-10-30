import os
import traceback
from fastapi import FastAPI, Request, HTTPException
from google import genai

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "online", "service": "OpenBot Gemini Agent"}

@app.post("/ag-ui")
async def handle_agent(request: Request):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")
    
    try:
        # Safely parse incoming JSON regardless of structure
        body = await request.json()
        print("INCOMING REQUEST:", body)
        
        # Extract user message safely from various possible OpenBot payload keys
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
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Act as an expert YouTube Shorts and social media niche strategist. {user_prompt}"
        )
        
        return {
            "events": [
                {
                    "type": "TextMessage",
                    "message": response.text
                }
            ]
        }
    except Exception as e:
        print("INTERNAL ERROR:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
