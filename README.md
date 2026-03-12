# Quicksilver

Quicksilver is a local proxy server that wraps Google Cloud's Vertex AI Search, exposing an OpenAI API-compatible interface. This allows you to use standard AI tools and agents (that expect to talk to an OpenAI-compatible endpoint) to interact directly with your proprietary data stored in Vertex AI Search.

## Requirements

- Python 3.9+
- A Google Cloud Project with Vertex AI Search enabled
- A Data Store created in Vertex AI Search
- Google Cloud credentials (e.g., `gcloud auth application-default login`)

## Installation

1. Clone the repository
2. Run the interactive startup script:
   ```bash
   ./quicksilver.sh
   ```

## Configuration

The `quicksilver.sh` script will automatically create a `.env` file for you based on your choices. 

You can choose between two backends during setup:

1. **Vertex AI Generative Models API (Raw Models):**
   * This backend routes your standard OpenAI requests straight to Google's foundation models (like `gemini-2.5-pro`).
   * The script will dynamically fetch and test which Gemini models your GCP project has access to, and let you select a default model. 
   * *If an OpenAI client passes a specific model in the request payload (e.g., `"model": "gemini-2.0-flash"`), Quicksilver will attempt to use that specific model instead of the default.*

2. **Vertex AI Search (Discovery Engine API):**
   * This backend routes your questions to a specific Data Store you have configured in the Google Cloud Console.
   * It relies on your indexed documents (PDFs, wikis, etc.) to generate grounded answers using the conversational search API.
   * Requires a `DATA_STORE_ID`.

## Manual Server Start

If you already have a `.env` configured, you can start the server manually using Uvicorn:

```bash
source venv/bin/activate
python main.py
```

The server will start on `http://0.0.0.0:8000`.

## Usage

You can now point any OpenAI-compatible client to Quicksilver. 

**Base URL:** `http://localhost:8000/v1`

**Example cURL request:**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "vertex-ai-search",
    "messages": [
      {
        "role": "user",
        "content": "What is the policy on remote work?"
      }
    ]
  }'
```

## Supported Endpoints

- `GET /v1/models` - Returns a dummy list of models for compatibility.
- `POST /v1/chat/completions` - Takes a standard OpenAI chat completion request, extracts the user query, queries Vertex AI Search, and returns the generated answer in the OpenAI response format.

## SKU Compliance

Quicksilver is designed to utilize the API calls associated with the Vertex GenAI Offer 2025 SKUs. 

Depending on your backend choice, it will trigger the following eligible SKUs:
*   **Generative Models Backend:** Triggers "Text Input - Predictions" and "Text Output - Predictions" SKUs for the selected Gemini models (e.g., `gemini-2.5-pro`).
*   **Discovery Engine Backend:** Triggers the Conversational API (`converseConversation` method), billing the "Advance Generative Answers Request Count" and "Grounded Generation" SKUs.

