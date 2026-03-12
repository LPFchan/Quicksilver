#!/bin/bash

# Quicksilver Interactive Launcher (Discovery Engine only)
echo "=================================================="
echo "     QUICKSILVER - DISCOVERY ENGINE PROXY         "
echo "=================================================="
echo ""

# Ensure we are in the right directory and venv is set up
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

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

# Discovery Engine uses global location for data stores
LOCATION="global"

echo ""
echo "To find your Data Store ID:"
echo "  1. Go to Google Cloud Console → Search & Conversation (Vertex AI Agent Builder)"
echo "  2. Click 'Data Stores' in the left menu"
echo "  3. Copy the 'ID' (not the Display Name) of the Data Store you want to use"
echo ""
read -p "Enter your Vertex AI Search Data Store ID: " DATA_STORE_ID

if [ -z "$DATA_STORE_ID" ]; then
    echo "❌ Data Store ID is required."
    exit 1
fi
echo "✅ Data Store: $DATA_STORE_ID"

echo ""
echo "Search App ID (needed for LLM / generative responses):"
echo "  Search & Conversation → Apps → your app → copy the App ID."
echo "  Leave blank if you only have a Data Store and no Search App yet."
echo ""
read -p "Enter App ID: " SEARCH_APP_ID
if [ -n "$SEARCH_APP_ID" ]; then
    echo "✅ App ID: $SEARCH_APP_ID"
fi

echo ""
read -p "Enter the port number for Quicksilver to listen on [8000]: " PORT_CHOICE
if [ -z "$PORT_CHOICE" ]; then
    PORT_CHOICE=8000
fi

# Write configuration to .env
echo "GOOGLE_CLOUD_PROJECT=$PROJECT_ID" > .env
echo "LOCATION=$LOCATION" >> .env
echo "QUICKSILVER_BACKEND=DISCOVERY_ENGINE" >> .env
echo "DATA_STORE_ID=$DATA_STORE_ID" >> .env
[ -n "$SEARCH_APP_ID" ] && echo "SEARCH_APP_ID=$SEARCH_APP_ID" >> .env
echo "PORT=$PORT_CHOICE" >> .env

echo ""
echo "=================================================="
echo "✅ Configuration saved to .env"
echo "🚀 Starting Quicksilver Server..."
echo "=================================================="
echo ""
echo "Tip: Query available answer-generation models with: curl http://localhost:$PORT_CHOICE/v1/models"
echo ""

# Run the server
python "$SCRIPT_DIR/main.py"
