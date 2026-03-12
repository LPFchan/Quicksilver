# Quicksilver

Quicksilver is a local proxy server that wraps Google Cloud's Vertex AI APIs, exposing an OpenAI API-compatible interface. This allows you to use standard AI tools and agents (like Cursor, AutoGPT, or LiteLLM) that expect to talk to an OpenAI-compatible endpoint to interact directly with Google's foundation models or your proprietary data stored in Vertex AI Search.

## Requirements

- Python 3.9+
- A Google Cloud Project
- Google Cloud credentials (e.g., `gcloud auth application-default login`)
- (Optional) A Data Store created in Vertex AI Search (for the Discovery Engine backend)

## Installation & Setup

1. Clone the repository
2. Run the interactive startup script:
   ```bash
   ./quicksilver.sh
   ```

The script will automatically:
- Create a Python virtual environment (`venv`) and install dependencies (including the `google-genai` SDK and FastAPI).
- Detect your current Google Cloud Project.
- Allow you to choose between two backend modes.
- If using Generative Models, dynamically probe Google's servers to see which Gemini models you have access to.
- Ask which port you want the proxy to listen on (default 8000).
- Save your choices to a `.env` file and launch the server.

## Backend Modes

### 1. Vertex AI Generative Models API (Raw Models)
- Routes your standard OpenAI requests straight to Google's foundation models (like `gemini-2.5-pro`).
- Supports multi-turn conversation memory, system prompts, and Server-Sent Events (SSE) streaming.
- *Model Aliasing:* If an OpenAI client passes a specific model in the request payload (e.g., `"model": "gemini-2.0-flash"`), Quicksilver will attempt to use that specific model. If the client passes a generic alias (e.g., `"model": "quicksilver"`), it gracefully falls back to your configured default model.

### 2. Vertex AI Search (Discovery Engine API)
- Routes your questions to a specific Data Store you have configured in the Google Cloud Console.
- Relies on your indexed documents (PDFs, wikis, GitHub repos) to generate grounded answers using the conversational search API.
- Requires a `DATA_STORE_ID`.

## Usage with LiteLLM

Quicksilver pairs perfectly with LiteLLM for routing. In your `~/.litellm/config.yaml`, add:

```yaml
model_list:
  - model_name: quicksilver
    litellm_params:
      model: custom_openai/quicksilver
      api_base: http://127.0.0.1:8000/v1  # Replace 8000 with your chosen port
      api_key: dummy-key-not-used
```

## Manual Server Start

If you already have a `.env` configured, you can start the server manually using Uvicorn:

```bash
source venv/bin/activate
python main.py
```
The server will start on `http://0.0.0.0:<PORT>`. You can point any OpenAI client to the Base URL: `http://localhost:<PORT>/v1`

## SKU Compliance (Vertex GenAI Offer 2025)

Quicksilver is designed to strictly utilize API calls associated with the **Vertex GenAI Offer 2025** SKUs.

Depending on your backend choice, it will trigger the following eligible SKUs:
*   **Generative Models Backend:** Triggers standard "Text Input - Predictions" and "Text Output - Predictions" SKUs for the selected Gemini models via the `google-genai` library.
*   **Discovery Engine Backend:** Triggers the Conversational API (`converseConversation` method), billing the "Advance Generative Answers Request Count" and "Grounded Generation" SKUs.
*   *Note: Third-party models (Anthropic, Meta) via Model Garden are not supported to maintain compliance with this offer.*

