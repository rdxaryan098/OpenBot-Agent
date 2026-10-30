import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any
from google import genai

app = FastAPI()

class Message(BaseModel):
    role: str
    content: str

class AgentRequest(BaseModel):
    messages: Optional[List[Message]] = []
    threadId: Optional[str] = None
    state: Optional[Any] = {}

@app.get("/")
async def root():
    return {"status": "online", "service": "OpenBot Gemini Agent"}

@app.post("/ag-ui")
async def handle_agent(req: AgentRequest):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")
    
    try:
        # Extract the latest user message
        user_prompt = "Hello"
        if req.messages and len(req.messages) > 0:
            user_prompt = req.messages[-1].content

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Act as an expert YouTube Shorts and social media niche strategist. {user_prompt}"
        )
        
        # Return in the exact format OpenBot expects
        return {
            "events": [
                {
                    "type": "TextMessage",
                    "message": response.text
                }
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
