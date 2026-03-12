import os
import re

from google.cloud import discoveryengine_v1alpha as discoveryengine
from google import genai
from google.genai import errors as genai_errors
import litellm
from fastapi.responses import StreamingResponse
import json
import uuid
import time
from dotenv import load_dotenv

load_dotenv()

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


class VertexAISearchClient:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("LOCATION", "us-central1")
        self.backend = os.getenv("QUICKSILVER_BACKEND", "DISCOVERY_ENGINE")
        
        if not self.project_id:
            log("Warning: GOOGLE_CLOUD_PROJECT not set. Google Cloud APIs will not work.")
            return

        if self.backend == "DISCOVERY_ENGINE":
            self.data_store_id = os.getenv("DATA_STORE_ID")
            self.search_app_id = os.getenv("SEARCH_APP_ID")  # optional: engine ID when LLM is enabled on the Search App
            if not self.data_store_id:
                log("Warning: DATA_STORE_ID not set. Vertex AI Search backend will fail.")
                return
            self.search_client = discoveryengine.ConversationalSearchServiceClient()
            # serving_config must always be dataStores/.../servingConfigs/... (API rejects engines path for this field)
            self.serving_config = f"projects/{self.project_id}/locations/global/collections/default_collection/dataStores/{self.data_store_id}/servingConfigs/default_config"
            # Conversation name: use engine (Search App) path when SEARCH_APP_ID set (LLM add-on), else data store path
            if self.search_app_id:
                self.conversation_path_format = f"projects/{self.project_id}/locations/global/collections/default_collection/engines/{self.search_app_id}/conversations/{{}}"
                log(f"Initialized Quicksilver with Vertex AI Search (Search App: {self.search_app_id}, Data Store: {self.data_store_id})")
            else:
                self.conversation_path_format = f"projects/{self.project_id}/locations/global/collections/default_collection/dataStores/{self.data_store_id}/conversations/{{}}"
                log(f"Initialized Quicksilver with Vertex AI Search (Data Store: {self.data_store_id})")
            
        elif self.backend == "GENERATIVE_MODELS":
            self.genai_client = genai.Client(
                vertexai=True, 
                project=self.project_id, 
                location=self.location
            )
            self.default_model = os.getenv("DEFAULT_MODEL", "gemini-2.5-pro")
            log(f"Initialized Quicksilver with Google GenAI SDK (Default: {self.default_model})")

    def converse(self, body: dict):
        """
        Sends a query to the configured backend.
        """
        if self.backend == "DISCOVERY_ENGINE":
            # Extract tools if any
            tools = body.get("tools", [])
            
            # Reconstruct the logic to extract query for Discovery Engine from the raw OpenAI request format
            messages = body.get("messages", [])
            
            system_prompt = ""
            conversation_history = ""
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                # Handle multimodal arrays
                if isinstance(content, list):
                    text_content = "\n".join([c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"])
                else:
                    text_content = str(content) if content else ""
                    
                if role in ["system", "developer"]:
                    system_prompt += text_content + "\n\n"
                elif role == "user":
                    conversation_history += f"User: {text_content}\n"
                elif role == "assistant":
                    conversation_history += f"Assistant: {text_content}\n"
                    # Include tool calls made by the assistant if they exist
                    if msg.get("tool_calls"):
                        for tc in msg.get("tool_calls"):
                            func = tc.get("function", {})
                            conversation_history += f"Assistant called tool {func.get('name')} with arguments {func.get('arguments')}\n"
                elif role == "tool":
                    conversation_history += f"Tool Result (from {msg.get('name', 'unknown')}): {text_content}\n"

            # If we have tools, we inject our mega-prompt instruction
            tool_instruction = ""
            if tools:
                tool_instruction = "\n\nCRITICAL INSTRUCTION: You are an autonomous AI agent. You have access to the following tools to help the user:\n"
                tool_instruction += json.dumps(tools, indent=2)
                tool_instruction += "\n\nIf you need to use a tool to accomplish the task, you MUST reply with ONLY the following XML format and absolutely no other text:\n"
                tool_instruction += "<tool_call>\n{\"name\": \"tool_name\", \"arguments\": {\"arg1\": \"val1\"}}\n</tool_call>"

            # Combine it all into the single query Vertex AI Search expects
            # Discovery Engine is highly sensitive to the term "Conversation History" when using the converse API,
            # as it automatically injects its own conversation history based on the session ID. Let's just pass the query.
            
            user_queries = [msg.get("content", "") for msg in messages if msg.get("role") == "user"]
            last_query = user_queries[-1] if user_queries else "Hello"
            
            final_query = f"{last_query}"
            
            # Print the final query being sent to Discovery Engine so we can debug what is actually going on.
            print("==================== DEBUG: SENDING QUERY ====================")
            print(final_query)
            print("==============================================================")

            if not hasattr(self, "search_client"):
                raise Exception("Vertex AI Search client is not initialized. Check your environment variables (DATA_STORE_ID).")

            conversation_id = "-"  # auto session mode: API creates a new conversation
            conversation_name = self.conversation_path_format.format(conversation_id)
            query_obj = discoveryengine.TextInput(input=final_query)
            
            # The summary_spec configuration allows us to dictate how the summary is generated.
            # We set these to True to bypass Google's internal checks that often decide a query
            # doesn't "deserve" a summary, which is what causes the "A summary could not be generated" error.
            summary_spec = discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=5,
                ignore_adversarial_query=False,
                ignore_non_summary_seeking_query=False,
            )
            
            request = discoveryengine.ConverseConversationRequest(
                name=conversation_name,
                query=query_obj,
                serving_config=self.serving_config,
                summary_spec=summary_spec
            )
            response = self.search_client.converse_conversation(request)
            text_reply = "I'm sorry, I couldn't generate an answer from the provided documents."
            if response.reply and response.reply.reply:
                text_reply = response.reply.reply
            elif response.reply and hasattr(response.reply, "summary") and response.reply.summary.summary_text:
                text_reply = response.reply.summary.summary_text

            # Debug the full response
            print("==================== DEBUG: RESPONSE FROM DISCOVERY ENGINE ====================")
            print(f"Reply text: {text_reply}")
            print(f"Has Search Results: {bool(getattr(response, 'search_results', None) or getattr(response, 'searchResults', None))}")
            if hasattr(response.reply, "summary") and response.reply.summary:
                try:
                    summary = response.reply.summary
                    print(f"Summary with properties: {dir(summary)}")
                    print(f"summary_skipped_reasons: {getattr(summary, 'summary_skipped_reasons', 'N/A')}")
                    print(f"safety_attributes: {getattr(summary, 'safety_attributes', 'N/A')}")
                except Exception as e:
                    print(f"Debug error: {e}")
            print("===============================================================================")

            # When the API skips the LLM summary it returns a fallback message; append actual search results so the user sees them
            summary_skipped = "summary could not be generated" in text_reply.lower() or "here are some search results" in text_reply.lower()
            search_results = getattr(response, "search_results", None) or getattr(response, "searchResults", None)
            if summary_skipped and search_results:
                parts = []
                for i, res in enumerate(list(search_results)[:10], 1):
                    title = getattr(res, "title", None) or f"Result {i}"
                    if hasattr(res, "document") and res.document:
                        doc = res.document
                        title = getattr(doc, "title", None) or title
                        struct = getattr(doc, "derived_struct_data", None)
                        if struct and isinstance(struct, dict):
                            snippet = struct.get("snippet") or struct.get("link") or ""
                        else:
                            snippet = getattr(struct, "snippet", None) if struct else None
                    else:
                        snippet = getattr(res, "snippet", None) or getattr(res, "snippet_content", None)
                    text = (snippet or getattr(res, "content", "") or "").strip()
                    if isinstance(text, bytes):
                        text = text.decode("utf-8", errors="replace")[:500]
                    else:
                        text = str(text)[:500]
                    if text:
                        parts.append(f"**{title}**\n{text}")
                if parts:
                    text_reply = text_reply.rstrip() + "\n\n---\n\n" + "\n\n".join(parts)

            stream = body.get("stream", False)
            model_name = body.get("model", "discovery-engine")
            response_id = f"chatcmpl-{uuid.uuid4().hex}"
            created_time = int(time.time())

            # Detect if the model outputted a tool call
            tool_call_match = re.search(r'<tool_call>\s*({.*?})\s*</tool_call>', text_reply, re.DOTALL)
            parsed_tool_call = None
            if tool_call_match:
                try:
                    parsed_tool_call = json.loads(tool_call_match.group(1))
                    # Fallback text reply to empty if we're calling a tool, or keep the thought process if there's text outside the tag
                    text_reply = text_reply.replace(tool_call_match.group(0), "").strip()
                except Exception as e:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Failed to parse tool call JSON: {e}")

            if stream:
                async def generate_stream():
                    # Send role
                    yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model_name, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    
                    if parsed_tool_call:
                        # Yield the tool call chunk exactly as OpenAI/Cursor expects it
                        tool_call_id = f"call_{uuid.uuid4().hex[:10]}"
                        
                        # Cursor expects tool calls to be streamed in parts (index, id, function name, then arguments string)
                        tc_chunk_1 = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": model_name,
                            "choices": [{
                                "index": 0,
                                "delta": {
                                    "tool_calls": [{
                                        "index": 0,
                                        "id": tool_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": parsed_tool_call.get("name", ""),
                                            "arguments": ""
                                        }
                                    }]
                                },
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(tc_chunk_1)}\n\n"
                        
                        tc_chunk_2 = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": model_name,
                            "choices": [{
                                "index": 0,
                                "delta": {
                                    "tool_calls": [{
                                        "index": 0,
                                        "function": {
                                            "arguments": json.dumps(parsed_tool_call.get("arguments", {}))
                                        }
                                    }]
                                },
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(tc_chunk_2)}\n\n"
                        
                        # Stop reason should be "tool_calls"
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model_name, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]})}\n\n"
                    
                    else:
                        # Standard text response
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model_name, 'choices': [{'index': 0, 'delta': {'content': text_reply}, 'finish_reason': None}]})}\n\n"
                        yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model_name, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    
                    yield "data: [DONE]\n\n"
                return StreamingResponse(generate_stream(), media_type="text/event-stream")
            else:
                # Non-streaming response format
                choice_data = {
                    "index": 0,
                    "message": {
                        "role": "assistant"
                    }
                }
                
                if parsed_tool_call:
                    choice_data["message"]["content"] = None
                    choice_data["message"]["tool_calls"] = [{
                        "id": f"call_{uuid.uuid4().hex[:10]}",
                        "type": "function",
                        "function": {
                            "name": parsed_tool_call.get("name", ""),
                            "arguments": json.dumps(parsed_tool_call.get("arguments", {}))
                        }
                    }]
                    choice_data["finish_reason"] = "tool_calls"
                else:
                    choice_data["message"]["content"] = text_reply
                    choice_data["finish_reason"] = "stop"

                return {
                    "id": response_id,
                    "object": "chat.completion",
                    "created": created_time,
                    "model": model_name,
                    "choices": [choice_data],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }
                
        elif self.backend == "GENERATIVE_MODELS":
            # Just pass everything over to LiteLLM, which natively handles tools, streams, etc.
            # Use "gemini/..." prefix to ensure LiteLLM routes through the new `google-genai` SDK
            # instead of the older `google-cloud-aiplatform` SDK. This ensures Gen AI 2025 promotional
            # billing is properly applied.
            requested_model = body.get("model", "")
            model_name = requested_model if requested_model and requested_model.startswith("gemini-") else self.default_model
            litellm_model = f"gemini/{model_name}"

            # Prepare args for litellm.completion
            litellm_args = body.copy()
            litellm_args["model"] = litellm_model
            
            # Passing these explicitly tells the `gemini/` provider in LiteLLM to use 
            # Vertex AI credentials (genai.Client(vertexai=True)) rather than an AI Studio API key.
            litellm_args["vertex_project"] = self.project_id
            litellm_args["vertex_location"] = self.location

            stream = body.get("stream", False)
            
            try:
                response = litellm.completion(**litellm_args)

                if stream:
                    # litellm returns a generator for streams, we need to wrap it in a FastAPI StreamingResponse
                    async def generate_stream():
                        for chunk in response:
                            # LiteLLM yields chunks. We need strictly valid JSON strings with double quotes.
                            if hasattr(chunk, "model_dump_json"):
                                chunk_json = chunk.model_dump_json()
                            elif hasattr(chunk, "json") and callable(getattr(chunk, "json")):
                                # Some litellm objects return a dict when json() is called, some return a string.
                                val = chunk.json()
                                chunk_json = json.dumps(val) if isinstance(val, dict) else val
                                # Quick fix if the string still has single quotes (often from str())
                                if isinstance(chunk_json, str) and chunk_json.startswith("{'") :
                                    chunk_json = json.dumps(chunk.model_dump() if hasattr(chunk, "model_dump") else dict(chunk))
                            elif hasattr(chunk, "model_dump"):
                                chunk_json = json.dumps(chunk.model_dump())
                            else:
                                # Fallback to standard dict conversion
                                chunk_json = json.dumps(dict(chunk) if hasattr(chunk, "keys") else chunk)
                                
                            yield f"data: {chunk_json}\n\n"
                        yield "data: [DONE]\n\n"
                    return StreamingResponse(generate_stream(), media_type="text/event-stream")
                else:
                    return response.model_dump()
            except litellm.exceptions.AuthenticationError as e:
                raise Exception(f"Authentication failed: {e}")
            except litellm.exceptions.RateLimitError as e:
                # We can mock a GenAIClientError to be caught by main.py
                raise genai_errors.ClientError(code=429, response_json={"error": {"message": str(e)}}, response=None)
            except Exception as e:
                # Wrap general litellm errors so we know where they came from
                raise Exception(f"LiteLLM error calling {litellm_model}: {e}")

