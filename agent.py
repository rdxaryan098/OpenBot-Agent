import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai

app = FastAPI()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

class PromptRequest(BaseModel):
    prompt: str

@app.post("/ag-ui")
async def handle_agent(req: PromptRequest):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Act as a YouTube Shorts and social media niche strategist. {req.prompt}"
        )
        return {"response": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
