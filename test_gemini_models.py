import vertexai
from vertexai.generative_models import GenerativeModel
import os

def test_models():
    project_id = "lostplusfound"
    location = "us-central1"
    vertexai.init(project=project_id, location=location)
    
    models_to_test = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3.0-flash",
        "gemini-3.0-pro",
        "gemini-3.1-pro",
        "gemini-3.1-flash-lite",
    ]
    
    print(f"Testing Generation from Models in Vertex AI ({location}):\n")
    
    for model_name in models_to_test:
        try:
            model = GenerativeModel(model_name)
            response = model.generate_content("Hi", generation_config={"max_output_tokens": 1})
            print(f"✅ {model_name} is AVAILABLE")
        except Exception as e:
            err_msg = str(e)
            if "not found" in err_msg.lower() or "404" in err_msg:
                print(f"❌ {model_name} is NOT AVAILABLE (Not Found)")
            elif "permission" in err_msg.lower():
                print(f"⚠️ {model_name} might be available, but Permission Denied")
            else:
                print(f"❌ {model_name} Failed: {err_msg[:100]}...")

if __name__ == "__main__":
    test_models()
