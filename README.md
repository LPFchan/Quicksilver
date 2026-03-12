# Quicksilver

Quicksilver is a local proxy server that exposes an **OpenAI API–compatible** interface to **Vertex AI Search (Discovery Engine)**. It lets you use standard AI tools and agents (Cursor, LiteLLM, etc.) to chat with your indexed data and run agent-style tool calls, while staying within **Vertex GenAI Offer 2025**–eligible SKUs (Grounded Generation / Advance Generative Answers).

## Requirements

- Python 3.9+
- A Google Cloud Project
- Google Cloud credentials (e.g. `gcloud auth application-default login`)
- A **Data Store** in Vertex AI Search (Search & Conversation / Agent Builder). For LLM/converse features you also need a **Search App** with “Generative responses with advanced LLM features” enabled; set `SEARCH_APP_ID` to that app’s ID (see below).

## Installation & setup

1. Clone the repository.
2. Run the interactive launcher:

   ```bash
   ./quicksilver.sh
   ```

The script will:

- Create a Python virtual environment (`venv`) and install dependencies.
- Detect your Google Cloud project (or prompt for it).
- Ask for your **Vertex AI Search Data Store ID**.
- Optionally ask for your **Search App ID** (recommended if you use a Search App with LLM/generative responses enabled).
- Ask which port to use (default `8000`).
- Write configuration to `.env` and start the server.

**Search App ID (optional):** The converse API can be called with either a Data Store or a Search App (engine). If you get “Large Language Model add-on is not enabled”, create a Search App in Agent Builder, turn on “Generative responses with advanced LLM features”, and set `SEARCH_APP_ID` in `.env` to that app’s ID. Quicksilver will then use the engine path (`.../engines/{SEARCH_APP_ID}/conversations/-`) so the LLM add-on is used.

## Discovery Engine only

Quicksilver uses **only** the Vertex AI Search / Discovery Engine API (`converseConversation`). There is no “raw” Generative Models API path. All requests are grounded through your Data Store and billed under:

- **Vertex AI Search: Advance Generative Answers Request Count**
- **Vertex AI Search: Grounded Generation**

So usage stays within the Gen AI 2025 offer when you use this proxy.

### Answer-generation model

Under the hood, Discovery Engine uses a Gemini-based **answer generation** model (e.g. `gemini-2.5-flash/answer_gen/v1`). The exact model is determined by your Data Store configuration in the Google Cloud Console, not by the request body.

### “A summary could not be generated”

Sometimes the API returns this and “Here are some search results” instead of an LLM summary (e.g. query out-of-domain, no relevant docs, or summary skipped by policy). Quicksilver appends the actual search result snippets to the reply when this happens so you still see what was retrieved. To get more summaries, use queries that match your indexed content and ensure the Data Store has enough relevant documents.

### Tool calling (Option C)

Quicksilver supports **OpenAI-style tool/function calling** over Discovery Engine: it turns the client’s `tools` array into a prompt, and parses the model’s `<tool_call>…</tool_call>` output back into `tool_calls` for Cursor and other clients. This allows agent-style workflows (e.g. run terminal, read/write files) while still using only the Grounded Generation API.

## Querying available models

You can ask the server which model options are available (for reference; the actual model is set on the Data Store):

```bash
curl http://localhost:8000/v1/models
```

Replace `8000` with your chosen port. The response lists Discovery Engine answer-generation model IDs and short descriptions (e.g. `stable`, `gemini-2.5-flash/answer_gen/v1`, `gemini-3.0-pro-preview/answer_gen/v1`).

## Usage with LiteLLM

Add a route in `~/.litellm/config.yaml`:

```yaml
model_list:
  - model_name: quicksilver
    litellm_params:
      model: custom_openai/quicksilver
      api_base: http://127.0.0.1:8000/v1   # use your port
      api_key: dummy-key-not-used
```

Then use the model name `quicksilver` in Cursor or any OpenAI-compatible client.

## Manual server start

If `.env` is already set:

```bash
source venv/bin/activate
python main.py
```

The server listens on `http://0.0.0.0:<PORT>`. Use base URL `http://localhost:<PORT>/v1` for OpenAI clients.

## SKU compliance (Vertex GenAI Offer 2025)

Quicksilver is built to use only APIs that map to **Vertex GenAI Offer 2025** SKUs:

- **Discovery Engine:** All traffic goes through the Conversational API and is billed as “Advance Generative Answers Request Count” and “Grounded Generation,” which are covered by the offer.

See [docs/vertex-genai-offer-2025-sku-groups.md](docs/vertex-genai-offer-2025-sku-groups.md) for the full SKU list.
