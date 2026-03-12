#!/bin/bash
# Bifrost Launcher - macOS compatible
# Usage: ./bifrost.sh [--project-id PROJECT] [--bucket BUCKET] [--skip-create-datastore] [repo_path_1] [repo_path_2] ...

# Exit on error
set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
PYTHON_SCRIPT="$SCRIPT_DIR/main.py"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse optional flags (--project-id / -p, --bucket / -b)
PYTHON_EXTRA_ARGS=()
REPO_ARGS=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --project-id|-p)
            [ -n "${2:-}" ] || { echo -e "${RED}Error: --project-id requires a value.${NC}"; exit 1; }
            PYTHON_EXTRA_ARGS+=(--project-id "$2")
            shift 2
            ;;
        --bucket|-b)
            [ -n "${2:-}" ] || { echo -e "${RED}Error: --bucket requires a value.${NC}"; exit 1; }
            PYTHON_EXTRA_ARGS+=(--bucket "$2")
            shift 2
            ;;
        --skip-create-datastore)
            PYTHON_EXTRA_ARGS+=(--skip-create-datastore)
            shift
            ;;
        *)
            REPO_ARGS+=("$1")
            shift
            ;;
    esac
done

echo -e "${GREEN}Starting Bifrost Pipeline...${NC}"

# Check that we have at least one repo path
if [ "${#REPO_ARGS[@]}" -eq 0 ]; then
    echo -e "${YELLOW}No repositories specified.${NC}"
    echo "Usage: ./bifrost.sh [--project-id PROJECT] [--bucket BUCKET] [--skip-create-datastore] <repo_path_1> [repo_path_2] ..."
    echo "Example: ./bifrost.sh --project-id my-gcp-project /path/to/repo1"
    echo "         ./bifrost.sh --skip-create-datastore /path/to/repo1  # use existing data store"
    echo "Or set: export GOOGLE_CLOUD_PROJECT=my-gcp-project"
    exit 1
fi

# 1. Project ID: from flag, env, or gcloud config
if [[ " ${PYTHON_EXTRA_ARGS[*]} " != *" --project-id "* ]]; then
    if [ -z "${GOOGLE_CLOUD_PROJECT:-}" ] && [ -z "${GCLOUD_PROJECT:-}" ]; then
        GCLOUD_PROJECT="$(gcloud config get-value project 2>/dev/null)" || true
        if [ -n "${GCLOUD_PROJECT:-}" ]; then
            export GOOGLE_CLOUD_PROJECT="$GCLOUD_PROJECT"
            echo -e "${GREEN}Using project from gcloud: ${GOOGLE_CLOUD_PROJECT}${NC}"
        fi
    fi
    if [ -z "${GOOGLE_CLOUD_PROJECT:-}" ]; then
        # Try GCLOUD_PROJECT if set (e.g. by user)
        [ -n "${GCLOUD_PROJECT:-}" ] && export GOOGLE_CLOUD_PROJECT="$GCLOUD_PROJECT"
    fi
    if [ -z "${GOOGLE_CLOUD_PROJECT:-}" ]; then
        echo -e "${RED}Error: Project ID not set.${NC}"
        echo "Set GOOGLE_CLOUD_PROJECT, run 'gcloud config set project YOUR_PROJECT', or pass --project-id."
        exit 1
    fi
fi

if [ -z "${BIFROST_GCS_BUCKET:-}" ] && [[ " ${PYTHON_EXTRA_ARGS[*]} " != *" --bucket "* ]]; then
    echo -e "${YELLOW}Warning: BIFROST_GCS_BUCKET not set. Defaulting to 'bifrost-bucket'.${NC}"
fi

# 2. Virtual Environment Setup
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Setting up virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# 3. Install Requirements
echo -e "${GREEN}Checking dependencies...${NC}"
pip install -q -r "$REQUIREMENTS_FILE"

# 4. Run Python Script
echo -e "${GREEN}Executing Python pipeline...${NC}"

# Pass optional flags then repo paths to the python script
python "$PYTHON_SCRIPT" "${PYTHON_EXTRA_ARGS[@]}" "${REPO_ARGS[@]}"

# Deactivate virtual environment
deactivate

echo -e "${GREEN}Bifrost script finished successfully.${NC}"
