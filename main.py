from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
import time
import uuid

from gcp_client import VertexAISearchClient

app = FastAPI(title="Quicksilver", description="OpenAI API proxy for Vertex AI Search")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

vertex_client = VertexAISearchClient()

# OpenAI Compatible Models
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0
    frequency_penalty: Optional[float] = 0
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None

class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatCompletionResponseUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: ChatCompletionResponseUsage


@app.get("/v1/models")
async def get_models():
    """Returns a list of dummy models for compatibility."""
    return {
        "object": "list",
        "data": [
            {
                "id": "vertex-ai-search",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
            }
        ]
    }

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint.
    Maps to Vertex AI Search Conversational API.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty")

    # Extract the last user message as the query
    # In a more advanced version, we could handle conversational history
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
        
    query = ""
    last_content = user_messages[-1].content
    if isinstance(last_content, list):
        # Handle cases where content is a list of dictionaries (e.g. multimodal or complex text blocks from LiteLLM/Cursor)
        for block in last_content:
            if isinstance(block, dict) and block.get("type") == "text":
                query += block.get("text", "") + "\n"
    else:
        query = str(last_content)
        
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="User message content cannot be empty")
    
    try:
        # Call configured GCP backend
        answer_text = vertex_client.converse(query=query, requested_model=request.model)

        # Format as OpenAI response
        response_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())
        
        return ChatCompletionResponse(
            id=response_id,
            object="chat.completion",
            created=created_time,
            model=request.model,
            choices=[
                ChatCompletionResponseChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=str(answer_text)
                    ),
                    finish_reason="stop"
                )
            ],
            usage=ChatCompletionResponseUsage(
                prompt_tokens=0, # Dummy values for now
                completion_tokens=0,
                total_tokens=0
            )
        )
        
    except Exception as e:
        print(f"Error calling Vertex AI Search: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
