#!/bin/bash

# Quicksilver Interactive Launcher
echo "=================================================="
echo "          QUICKSILVER - API PROXY SETUP           "
echo "=================================================="
echo ""

# Ensure we are in the right directory and venv is set up
if [ ! -d "venv" ]; then
    echo "Creating virtual environment and installing dependencies..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Function to get current GCP Project
get_gcp_project() {
    python -c "
import google.auth
try:
    _, project = google.auth.default()
    print(project if project else '')
except:
    print('')
" 2>/dev/null
}

PROJECT_ID=$(get_gcp_project)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ Could not automatically detect Google Cloud Project."
    read -p "Please enter your GCP Project ID: " PROJECT_ID
else
    echo "✅ Detected GCP Project: $PROJECT_ID"
fi

LOCATION="us-central1" # Default

echo ""
echo "Which backend would you like Quicksilver to use?"
echo "1) Vertex AI Generative Models API (Raw Models like Gemini 2.5 Pro)"
echo "2) Vertex AI Search / Discovery Engine API (Chat with your Data Store)"
echo ""
read -p "Enter 1 or 2: " BACKEND_CHOICE

API_BACKEND=""
SELECTED_MODEL=""
DATA_STORE_ID=""

if [ "$BACKEND_CHOICE" == "1" ]; then
    API_BACKEND="GENERATIVE_MODELS"
    echo ""
    echo "Fetching available Gemini models for your project..."
    
    # Run the helper script to fetch models
    MODEL_LIST=$(python fetch_models.py "$PROJECT_ID" "$LOCATION")
    
    if [ $? -ne 0 ]; then
        echo "❌ Error fetching models."
        exit 1
    fi
    
    echo "$MODEL_LIST"
    
    # Parse the output to create an array of models
    IFS=$'\n' read -r -d '' -a model_array <<< "$(echo "$MODEL_LIST" | grep -E '^[0-9]+\)' | sed 's/^[0-9]*\) //')"
    
    echo ""
    read -p "Select a model by number: " MODEL_INDEX
    
    # Array is 0-indexed, UI is 1-indexed
    ARRAY_INDEX=$((MODEL_INDEX - 1))
    
    if [ $ARRAY_INDEX -ge 0 ] && [ $ARRAY_INDEX -lt ${#model_array[@]} ]; then
        SELECTED_MODEL=${model_array[$ARRAY_INDEX]}
        echo "✅ Selected Model: $SELECTED_MODEL"
    else
        echo "❌ Invalid selection."
        exit 1
    fi

elif [ "$BACKEND_CHOICE" == "2" ]; then
    API_BACKEND="DISCOVERY_ENGINE"
    LOCATION="global" # Discovery engine usually defaults to global
    echo ""
    read -p "Enter your Vertex AI Search Data Store ID: " DATA_STORE_ID
    echo "✅ Configured for Discovery Engine using Data Store: $DATA_STORE_ID"
else
    echo "❌ Invalid choice."
    exit 1
fi

# Write configurations to .env
echo "GOOGLE_CLOUD_PROJECT=$PROJECT_ID" > .env
echo "LOCATION=$LOCATION" >> .env
echo "QUICKSILVER_BACKEND=$API_BACKEND" >> .env
if [ "$API_BACKEND" == "GENERATIVE_MODELS" ]; then
    echo "DEFAULT_MODEL=$SELECTED_MODEL" >> .env
else
    echo "DATA_STORE_ID=$DATA_STORE_ID" >> .env
fi

echo ""
echo "=================================================="
echo "✅ Configuration saved to .env"
echo "🚀 Starting Quicksilver Server..."
echo "=================================================="
echo ""

# Run the server
python main.py
