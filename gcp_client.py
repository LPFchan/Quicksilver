import os
from google.cloud import discoveryengine_v1alpha as discoveryengine
import vertexai
from vertexai.generative_models import GenerativeModel
from dotenv import load_dotenv

load_dotenv()

class VertexAISearchClient:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("LOCATION", "global")
        self.backend = os.getenv("QUICKSILVER_BACKEND", "DISCOVERY_ENGINE")
        
        if not self.project_id:
            print("Warning: GOOGLE_CLOUD_PROJECT not set. Google Cloud APIs will not work.")
            return

        if self.backend == "DISCOVERY_ENGINE":
            self.data_store_id = os.getenv("DATA_STORE_ID")
            if not self.data_store_id:
                print("Warning: DATA_STORE_ID not set. Vertex AI Search backend will fail.")
                return
                
            self.client = discoveryengine.ConversationalSearchServiceClient()
            self.session_path_format = f"projects/{self.project_id}/locations/{self.location}/collections/default_collection/dataStores/{self.data_store_id}/sessions/{{}}"
            self.serving_config = f"projects/{self.project_id}/locations/{self.location}/collections/default_collection/dataStores/{self.data_store_id}/servingConfigs/default_config"
            print(f"Initialized Quicksilver with Vertex AI Search (Data Store: {self.data_store_id})")
            
        elif self.backend == "GENERATIVE_MODELS":
            # In Generative Models mode, the model itself is passed dynamically from main.py 
            # based on the user's OpenAI API request (or the default set in .env).
            vertexai.init(project=self.project_id, location=self.location)
            self.default_model = os.getenv("DEFAULT_MODEL", "gemini-2.5-pro")
            print(f"Initialized Quicksilver with Vertex AI Generative Models (Default: {self.default_model})")

    def converse(self, query: str, session_id: str = "-", requested_model: str = None):
        """
        Sends a query to the configured backend.
        
        Args:
            query (str): The user's question.
            session_id (str): Optional session ID (used for Discovery Engine).
            requested_model (str): The model specified in the OpenAI request.
            
        Returns:
            The conversational response string.
        """
        if self.backend == "DISCOVERY_ENGINE":
            if not hasattr(self, 'client'):
                raise Exception("Vertex AI Search client is not initialized. Check your environment variables.")

            session = self.session_path_format.format(session_id)
            query_obj = discoveryengine.TextInput(input=query)
            
            request = discoveryengine.ConverseConversationRequest(
                name=session,
                query=query_obj,
                serving_config=self.serving_config,
            )
            
            response = self.client.converse_conversation(request)
            
            if response.reply and response.reply.reply:
                return response.reply.reply
            elif response.reply and hasattr(response.reply, 'summary') and response.reply.summary.summary_text:
                return response.reply.summary.summary_text
            else:
                return "I'm sorry, I couldn't generate an answer from the provided documents."
                
        elif self.backend == "GENERATIVE_MODELS":
            # If the user passes a model name that doesn't start with "gemini-", they are likely 
            # just passing their proxy's generic route name (like "quicksilver").
            # In that case, we should fallback to the default model configured in .env.
            model_name = requested_model if requested_model and requested_model.startswith("gemini-") else self.default_model
            try:
                model = GenerativeModel(model_name)
                response = model.generate_content(query)
                return response.text
            except Exception as e:
                raise Exception(f"Failed to generate content using {model_name}: {e}")

