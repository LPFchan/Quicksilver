from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
import time
import uuid

from gcp_client import VertexAISearchClient
from google.genai.errors import ClientError as GenAIClientError

import uvicorn
import os
import logging
from uvicorn.config import LOGGING_CONFIG

# Configure custom formatting for uvicorn logs to include time+seconds
LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelprefix)s %(message)s"
LOGGING_CONFIG["formatters"]["access"]["fmt"] = "%(asctime)s - %(levelprefix)s %(client_addr)s - \"%(request_line)s\" %(status_code)s"
LOGGING_CONFIG["formatters"]["default"]["datefmt"] = "%Y-%m-%d %H:%M:%S"
LOGGING_CONFIG["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

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

    # In a more advanced version, we could handle conversational history
    # We now format the entire conversation history for Vertex AI
    formatted_messages = []
    
    # We need to extract the query from the last message (what we will actually "send" as the prompt)
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
        
    # Build the conversation history for GenAI SDK (Vertex AI expects a specific format)
    # The last message is the query, the preceding messages are history.
    history = []
    if len(request.messages) > 1:
        for msg in request.messages[:-1]:
            # Convert system messages to user messages for Gemini (if it doesn't support system instructions at this layer)
            role = "user" if msg.role in ["user", "system"] else "model"
            
            # Extract content string
            content_str = ""
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        content_str += block.get("text", "") + "\n"
            else:
                content_str = str(msg.content)
            
            if content_str.strip():
                history.append({
                    "role": role,
                    "parts": [{"text": content_str}]
                })
    
    try:
        # Call configured GCP backend
        backend_response = vertex_client.converse(
            query=query,
            history=history,
            requested_model=request.model,
            stream=request.stream
        )

        response_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        # If the client requested a streaming response, pre-flight the stream so any
        # upstream error (e.g. 429) is raised before we send 200 OK.
        stream_first_chunk = None
        if request.stream and not isinstance(backend_response, str):
            try:
                stream_first_chunk = next(backend_response)
            except StopIteration:
                pass

        # If the client requested a streaming response, we need to return server-sent events (SSE)
        if request.stream:
            async def generate_stream():
                # Send the initial role chunk
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk)}\n\n"

                # Check if backend_response is a string (Discovery Engine fallback) or a generator (GenAI SDK)
                if isinstance(backend_response, str):
                    chunk = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": request.model,
                        "choices": [{"index": 0, "delta": {"content": backend_response}, "finish_reason": None}]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                else:
                    # Yield the first chunk we consumed during pre-flight (if any)
                    if stream_first_chunk is not None and getattr(stream_first_chunk, "text", None):
                        chunk = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": request.model,
                            "choices": [{"index": 0, "delta": {"content": stream_first_chunk.text}, "finish_reason": None}]
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                    # Then the rest of the stream
                    for response_chunk in backend_response:
                        if response_chunk.text:
                            chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": request.model,
                                "choices": [{"index": 0, "delta": {"content": response_chunk.text}, "finish_reason": None}]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"

                # Send the final stop chunk
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate_stream(), media_type="text/event-stream")
        
        # If not streaming, format as standard OpenAI JSON response
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
                        content=str(backend_response)
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
        
    except GenAIClientError as e:
        status_code = getattr(e, "code", 500)
        if not isinstance(status_code, int) or status_code < 400:
            status_code = 500
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Vertex AI error ({status_code}): {e}")
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error calling Vertex AI Search: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
