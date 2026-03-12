from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import time

from gcp_client import VertexAISearchClient
from google.genai.errors import ClientError as GenAIClientError

try:
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    ResourceExhausted = None  # optional for non–Discovery Engine backends

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

# Discovery Engine answer-generation model versions (Vertex AI Search).
# The actual model in use is configured on the Data Store in GCP Console.
# See: https://cloud.google.com/generative-ai-app-builder/docs/answer-generation-models
DISCOVERY_ENGINE_MODELS = [
    {"id": "vertex-ai-search", "object": "model", "owned_by": "google", "description": "Default route; uses the answer-gen model configured on your Data Store"},
    {"id": "stable", "object": "model", "owned_by": "google", "description": "Alias for gemini-2.5-flash/answer_gen/v1 (default, 128K context)"},
    {"id": "gemini-2.5-flash/answer_gen/v1", "object": "model", "owned_by": "google", "description": "Answer generation (128K context)"},
    {"id": "gemini-3.0-pro-preview/answer_gen/v1", "object": "model", "owned_by": "google", "description": "Answer generation preview (128K context)"},
    {"id": "gemini-2.0-flash-001/answer_gen/v1", "object": "model", "owned_by": "google", "description": "Answer generation (128K context)"},
    {"id": "preview", "object": "model", "owned_by": "google", "description": "Preview alias; may change without notice"},
]

@app.get("/v1/models")
async def get_models():
    """Returns available Discovery Engine answer-generation models. Query this to see which model options you can use."""
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {**m, "created": now} for m in DISCOVERY_ENGINE_MODELS
        ]
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint.
    Maps to Vertex AI Search or Google GenAI depending on configuration.
    """
    body = await request.json()
    
    if not body.get("messages"):
        raise HTTPException(status_code=400, detail="Messages cannot be empty")
    
    try:
        # Call configured GCP backend with the raw dictionary to preserve tools
        backend_response = vertex_client.converse(body)

        # If the backend_response is already a FastAPI Response (like StreamingResponse)
        if isinstance(backend_response, StreamingResponse) or isinstance(backend_response, JSONResponse):
            return backend_response
            
        # Otherwise if it's a litellm response or dict, we can just return it
        return backend_response
        
    except GenAIClientError as e:
        status_code = getattr(e, "code", 500)
        if not isinstance(status_code, int) or status_code < 400:
            status_code = 500
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Vertex AI error ({status_code}): {e}")
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        # Discovery Engine quota: 10 LLM requests/min per project. Return 429 so clients can retry.
        is_rate_limit = (
            (ResourceExhausted is not None and isinstance(e, ResourceExhausted))
            or "429" in str(e)
            or "Quota exceeded" in str(e)
            or "RATE_LIMIT_EXCEEDED" in str(e)
        )
        if is_rate_limit:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Rate limit (429): {e}")
            raise HTTPException(
                status_code=429,
                detail="Discovery Engine quota exceeded (10 LLM requests/min per project). Retry after a minute or request a quota increase: https://cloud.google.com/docs/quotas/help/request_increase",
                headers={"Retry-After": "60"},
            )
        # Pass through 400-style errors from Discovery Engine so clients get correct status
        err_str = str(e)
        # LLM add-on not enabled on the Data Store — return actionable message
        if "large language model add-on" in err_str.lower() or "llm add-on" in err_str.lower():
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] LLM add-on not enabled (400): {e}")
            raise HTTPException(
                status_code=400,
                detail="Vertex AI Search LLM add-on is not enabled. Create a Search App in Agent Builder with 'Generative responses with advanced LLM features' enabled, then set SEARCH_APP_ID in .env to that app's ID. See: https://cloud.google.com/generative-ai-app-builder/docs/create-engine-es",
            )
        if "400" in err_str or "invalid argument" in err_str.lower():
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Bad request (400): {e}")
            raise HTTPException(status_code=400, detail=err_str)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error calling Vertex AI Search: {e}")
        raise HTTPException(status_code=500, detail=err_str)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
