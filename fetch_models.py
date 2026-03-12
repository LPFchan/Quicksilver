import vertexai
from vertexai.generative_models import GenerativeModel
import sys
import os

# Suppress standard error output so we don't clutter the terminal with deprecation warnings
import warnings
warnings.filterwarnings("ignore")

def fetch_models(project_id, location):
    try:
        vertexai.init(project=project_id, location=location)
        
        # A list of known models to test. 
        # (Vertex API does not have a simple "list all allowed base models" endpoint 
        # that reliably works without special permissions, so we probe the known list).
        models_to_test = [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3.0-flash",
            "gemini-3.0-pro",
            "gemini-3.1-pro",
            "gemini-3.1-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ]
        
        available_models = []
        
        # Suppress stderr to hide warnings during initialization tests
        old_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        
        for model_name in models_to_test:
            try:
                model = GenerativeModel(model_name)
                # Quick test to ensure it's actually usable
                response = model.generate_content("Hi", generation_config={"max_output_tokens": 1})
                available_models.append(model_name)
            except Exception:
                pass
                
        # Restore stderr
        sys.stderr.close()
        sys.stderr = old_stderr
        
        if not available_models:
            print("No models were found to be available. Check your GCP permissions.")
            sys.exit(1)
            
        for i, model in enumerate(available_models, 1):
            print(f"{i}) {model}")
            
    except Exception as e:
        print(f"Error initializing Vertex AI: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python fetch_models.py <project_id> <location>")
        sys.exit(1)
        
    fetch_models(sys.argv[1], sys.argv[2])
