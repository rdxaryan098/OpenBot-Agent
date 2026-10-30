import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai

app = FastAPI()

# Initialize Gemini client safely
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

class PromptRequest(BaseModel):
    prompt: str

@app.get("/")
async def root():
    return {"status": "online", "service": "YouTube Shorts Niche Scout Agent"}

@app.post("/ag-ui")
async def handle_agent(req: PromptRequest):
    if not client:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable not configured.")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Act as a YouTube Shorts and social media niche strategist. {req.prompt}"
        )
        return {"response": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
