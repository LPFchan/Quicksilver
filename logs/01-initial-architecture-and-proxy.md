# Session 01: Quicksilver Architecture & Implementation

**Date:** March 12, 2026  
**Goal:** Build Quicksilver, a local proxy server providing an OpenAI API-compatible interface to Google Cloud Vertex AI services, strictly bounded by the GenAI Offer 2025 SKUs.

## 1. Project Initialization & Authentication
*   **Repository:** Initialized a private GitHub repository (`Quicksilver`) and pushed initial code.
*   **Environment:** Set up a Python 3 environment with FastAPI and Uvicorn.
*   **Authentication:** Configured Application Default Credentials (ADC) to interact with the GCP Project (`lostplusfound`).

## 2. Dual Backend Architecture
Implemented a flexible routing system in `gcp_client.py` and `main.py` allowing users to choose between two underlying Vertex AI services:

### A. Generative Models API (Raw Models)
*   **Use Case:** General-purpose AI chat and agent operations.
*   **Implementation:** Migrated from the deprecated `vertexai` library to the modern `google-genai` SDK (`genai.Client(vertexai=True)`).
*   **Model Validation:** Created a dynamic probing script (`fetch_models.py`) to verify which Gemini models are whitelisted for the specific GCP project, suppressing stderr warnings.
*   **Context/Memory:** Upgraded from single-prompt stateless execution to stateful multi-turn conversations by parsing the incoming `messages` array and utilizing `genai_client.chats.create(history=...)`.
*   **Streaming:** Implemented Server-Sent Events (SSE) streaming (`request.stream = True`) to support fluid UI rendering in clients like Cursor.
*   **Complex Payloads:** Added support for parsing complex dictionary arrays (e.g., multimodal text blocks) sent by advanced clients like LiteLLM.
*   **Model Aliasing:** Implemented fallback logic so requests for models like `quicksilver` gracefully default to the configured `DEFAULT_MODEL` (e.g., `gemini-2.5-pro`) instead of throwing 404s.

### B. Discovery Engine API (Vertex AI Search)
*   **Use Case:** RAG (Retrieval-Augmented Generation) against proprietary, user-uploaded data stores.
*   **Implementation:** Configured `google-cloud-discoveryengine` to target specific Data Store IDs via the `converseConversation` endpoint.

## 3. Interactive CLI Configuration
*   Created `quicksilver.sh`, an interactive bash script to handle local orchestration.
*   Automates virtual environment creation, dependency installation, and `.env` file generation.
*   Prompts the user for:
    *   Backend preference.
    *   Dynamic model selection (if Generative Models backend).
    *   Data Store ID (if Discovery Engine backend).
    *   Custom local proxy port (to avoid `Errno 48: Address already in use` conflicts, specifically alongside LiteLLM running on 4000).

## 4. Integration with LiteLLM
*   Successfully bridged Quicksilver with LiteLLM by adding a custom route in `~/.litellm/config.yaml`.
*   Resolved networking hiccups by explicitly mapping `api_base` to `http://127.0.0.1:<PORT>/v1` and utilizing the `custom_openai/` provider prefix to ensure proper routing of OpenAI-style payloads.

## 5. Architectural Probing & Research
*   **Third-Party Models:** Probed GCP endpoints for Anthropic (Claude) and Meta (Llama) Model Garden access. Confirmed they are not active in the project and fall outside the GenAI 2025 Offer constraints.
*   **Bifrost Concept:** Explored and documented a theoretical architecture (`Bifrost/README.md`) for syncing GitHub repositories to Vertex AI Search Data Stores via the `ImportDocuments` API using custom JSONL schemas, ensuring strict metadata control (commit hashes, authors).

## 6. Observability
*   Overrode Uvicorn's default logging configuration to prepend explicit `YYYY-MM-DD HH:MM:SS` timestamps to all server requests.
*   Added a custom `log()` wrapper for Quicksilver's internal terminal outputs to ensure chronological parity.