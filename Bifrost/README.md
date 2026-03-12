# Bifrost: GitHub to Vertex AI Search Ingestion

**Bifrost** is a proposed service designed to link deep information from GitHub repositories into Google Vertex AI Search Data Stores via the API. By using this approach rather than out-of-the-box syncing, we maintain fine-grained control over the metadata attached to every code file (e.g., commit hashes, authors, branches).

## 1. Architectural Approach

Because code files are fundamentally unstructured text, but require structured metadata for effective filtering and RAG operations, Bifrost utilizes the `document` schema approach with JSONL imports.

Even when using the API for metadata ingestion, Vertex AI Search expects the actual raw unstructured file content to be hosted in a Google Cloud Storage (GCS) bucket or provided as base64 inline bytes.

### The Data Schema Strategy
Bifrost will format each file in the repository into a JSON object that maps structured data to the unstructured GCS URI:

```json
{
  "id": "commitHash-filePath",
  "structData": {
    "author": "developer-name",
    "commit_hash": "a1b2c3d4",
    "branch": "main",
    "file_path": "src/main.py",
    "language": "python"
  },
  "content": {
    "mimeType": "text/plain",
    "uri": "gs://bifrost-bucket/repo-name/path/to/main.py" 
  }
}
```

## 2. Implementation Steps

### Step A: Create the Data Store via API
Instead of using the UI, Bifrost programmatically creates an empty Data Store configured to accept documents.

```python
from google.cloud import discoveryengine

client = discoveryengine.DataStoreServiceClient()
parent = client.collection_path(project="YOUR_PROJECT", location="global", collection="default_collection")

data_store = discoveryengine.DataStore(
    display_name="Github-Repo-Store",
    industry_vertical=discoveryengine.IndustryVertical.GENERIC,
    solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
    content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
)

request = discoveryengine.CreateDataStoreRequest(
    parent=parent,
    data_store_id="github-repo-store",
    data_store=data_store,
)
client.create_data_store(request=request)
```

### Step B: Prepare the GitHub Data
Bifrost executes the following pipeline:
1. Loops through local or cloned repository files.
2. Extracts git metadata (author, commit hash, timestamp) for each file using a tool like `GitPython`.
3. Uploads the raw source files to a Google Cloud Storage bucket (`gs://bifrost-bucket/`).
4. Generates a `metadata.jsonl` file containing the structural metadata and the GCS URI for each file.
5. Uploads the `metadata.jsonl` to the bucket.

### Step C: Import the Documents via API
Bifrost then calls the `ImportDocuments` API to trigger Vertex AI Search to ingest the JSONL mapping.

```python
document_client = discoveryengine.DocumentServiceClient()
parent = document_client.branch_path(
    project="YOUR_PROJECT",
    location="global",
    data_store="github-repo-store",
    branch="default_branch",
)

request = discoveryengine.ImportDocumentsRequest(
    parent=parent,
    gcs_source=discoveryengine.GcsSource(
        input_uris=["gs://bifrost-bucket/metadata.jsonl"],
        data_schema="document", # Indicates Unstructured data with Metadata
    ),
    reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
)

document_client.import_documents(request=request)
```

## References
*   [About Apps and Data Stores (Vertex AI Search)](https://docs.cloud.google.com/generative-ai-app-builder/docs/create-datastore-ingest?hl=en)
*   [Create a Search Data Store and Import Documents (Python API)](https://docs.cloud.google.com/generative-ai-app-builder/docs/create-data-store-es#api-json)