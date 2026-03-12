import os
import json
import uuid
import git
from typing import List, Dict, Any, Optional
from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import Conflict, Forbidden, NotFound
from google.cloud import storage
from google.cloud import discoveryengine

def _client_options(project_id: str):
    """Quota project only for user ADC; skip when using a service account key (can cause 403)."""
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return None  # Service account key has its own project
    return ClientOptions(quota_project_id=project_id)

def _print_credentials_info():
    """Print which credentials are used (for debugging 403)."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        try:
            with open(creds_path) as f:
                data = json.load(f)
            email = data.get("client_email", "unknown")
            print(f"Using credentials: service account {email}")
        except Exception:
            print(f"Using credentials: key file {creds_path}")
    else:
        print("Using credentials: Application Default (user)")

def create_data_store(
    project_id: str,
    location: str,
    data_store_id: str,
    display_name: str
) -> discoveryengine.DataStore:
    """Creates a Data Store in Vertex AI Search."""
    _print_credentials_info()
    print(f"Creating Data Store {data_store_id}...")
    client_options = _client_options(project_id)
    client = discoveryengine.DataStoreServiceClient(client_options=client_options)
    parent = client.collection_path(
        project=project_id,
        location=location,
        collection="default_collection"
    )

    data_store = discoveryengine.DataStore(
        display_name=display_name,
        industry_vertical=discoveryengine.IndustryVertical.GENERIC,
        solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
        content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
    )

    request = discoveryengine.CreateDataStoreRequest(
        parent=parent,
        data_store_id=data_store_id,
        data_store=data_store,
    )

    try:
        operation = client.create_data_store(request=request)
        print("Waiting for Data Store creation operation to complete...")
        response = operation.result()
        print(f"Data Store created: {response.name}")
        return response
    except Exception as e:
        err_str = str(e)
        if "409" in err_str or "already exists" in err_str.lower():
            print(f"Data Store {data_store_id} already exists, using it.")
        elif "403" in err_str or "IAM_PERMISSION_DENIED" in err_str or "Permission" in err_str:
            print(f"Full error: {e}")
            print(
                "Could not create Data Store (403). Try:\n"
                "  1. Enable the API: gcloud services enable discoveryengine.googleapis.com --project=YOUR_PROJECT_ID\n"
                "  2. If using a service account, grant roles/discoveryengine.admin and wait a few minutes.\n"
                "  3. Or create the data store in Cloud Console (Vertex AI Search), then run with: --skip-create-datastore"
            )
        else:
            print(f"Error creating Data Store (it may already exist): {e}")
        # Proceed using the existing data store
        return client.data_store_path(
            project=project_id,
            location=location,
            data_store=data_store_id,
        )

def ensure_bucket_exists(project_id: str, bucket_name: str, location: str = "us-central1") -> None:
    """Ensure the GCS bucket exists; create if missing. Uses list (object permission) to detect existing bucket without buckets.get."""
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    # Probe with list (only needs storage.objects.list); avoids buckets.get and buckets.create
    try:
        next(iter(storage_client.list_blobs(bucket_name, max_results=1)), None)
        print(f"Using existing bucket gs://{bucket_name}")
        return
    except NotFound:
        pass  # Bucket does not exist, try create below
    except Forbidden:
        print("No permission to access gs://{bucket_name}. Grant the service account roles/storage.objectAdmin on the bucket or project.".format(bucket_name=bucket_name))
        raise SystemExit(1)
    try:
        bucket.create(project=project_id, location=location)
        print(f"Created bucket gs://{bucket_name}")
    except Conflict:
        print(f"Using existing bucket gs://{bucket_name}")
    except Forbidden as e:
        print(
            f"Cannot create bucket (service account lacks storage.buckets.create).\n"
            f"Create the bucket once, then re-run Bifrost:\n\n"
            f"  gcloud storage buckets create gs://{bucket_name} --project={project_id} --location={location}\n"
        )
        raise SystemExit(1) from e
    except Exception as e:
        raise RuntimeError(
            f"Could not create bucket gs://{bucket_name}. "
            f"Create it manually: gcloud storage buckets create gs://{bucket_name} --project={project_id} --location={location}"
        ) from e

def process_repository(
    repo_path: str,
    bucket_name: str,
    gcs_prefix: str
) -> str:
    """Processes a local git repository, uploads files to GCS, and creates metadata.jsonl."""
    print(f"Processing repository at {repo_path}...")
    try:
        repo = git.Repo(repo_path)
    except git.exc.InvalidGitRepositoryError:
        print(f"Error: '{repo_path}' is not a valid git repository.")
        return None

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    metadata_lines = []
    
    # Iterate through all files in the current commit
    try:
        commit = repo.head.commit
        branch = repo.active_branch.name
    except Exception as e:
        print(f"Error accessing git history for '{repo_path}': {e}")
        return None

    for item in commit.tree.traverse():
        if item.type == "blob": # It's a file
            file_path = item.path
            # Upload file to GCS
            blob_path = f"{gcs_prefix}/{file_path}"
            blob = bucket.blob(blob_path)
            
            # Read file content from the git blob
            file_content = item.data_stream.read()
            
            # Skip empty files
            if not file_content:
                continue

            try:
                # Basic text detection
                file_content.decode('utf-8')
            except UnicodeDecodeError:
                print(f"Skipping non-text file: {file_path}")
                continue

            print(f"Uploading {file_path} to gs://{bucket_name}/{blob_path}")
            blob.upload_from_string(file_content)

            # Extract metadata
            author = commit.author.name
            commit_hash = commit.hexsha
            language = os.path.splitext(file_path)[1].replace('.', '') or "text"

            # Create document metadata
            doc_id = f"{commit_hash[:8]}-{uuid.uuid5(uuid.NAMESPACE_URL, file_path)}"
            metadata = {
                "id": doc_id,
                "structData": {
                    "author": author,
                    "commit_hash": commit_hash,
                    "branch": branch,
                    "file_path": file_path,
                    "language": language
                },
                "content": {
                    "mimeType": "text/plain",
                    "uri": f"gs://{bucket_name}/{blob_path}"
                }
            }
            metadata_lines.append(json.dumps(metadata))

    # Write and upload metadata.jsonl
    metadata_filename = "metadata.jsonl"
    with open(metadata_filename, "w") as f:
        f.write("\n".join(metadata_lines))
    
    metadata_blob_path = f"{gcs_prefix}/{metadata_filename}"
    metadata_blob = bucket.blob(metadata_blob_path)
    metadata_blob.upload_from_filename(metadata_filename)
    print(f"Uploaded metadata.jsonl to gs://{bucket_name}/{metadata_blob_path}")
    
    return f"gs://{bucket_name}/{metadata_blob_path}"

def import_documents(
    project_id: str,
    location: str,
    data_store_id: str,
    gcs_uri: str
):
    """Imports documents from the metadata.jsonl file into the Data Store."""
    print(f"Importing documents from {gcs_uri} to Data Store {data_store_id}...")
    client_options = _client_options(project_id)
    document_client = discoveryengine.DocumentServiceClient(client_options=client_options)
    
    parent = document_client.branch_path(
        project=project_id,
        location=location,
        collection="default_collection",
        data_store=data_store_id,
        branch="default_branch",
    )

    request = discoveryengine.ImportDocumentsRequest(
        parent=parent,
        gcs_source=discoveryengine.GcsSource(
            input_uris=[gcs_uri],
            data_schema="document", # Unstructured data with Metadata
        ),
        reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    )

    operation = document_client.import_documents(request=request)
    print("Waiting for document import operation to complete...")
    response = operation.result()
    print("Document import completed.")
    return response

def _resolve_project_id(explicit: Optional[str]) -> Optional[str]:
    """Resolve project ID from flag, GOOGLE_CLOUD_PROJECT, GCLOUD_PROJECT, or gcloud config."""
    if explicit:
        return explicit
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if project:
        return project
    try:
        import subprocess
        out = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bifrost: GitHub to Vertex AI Search Ingestion")
    parser.add_argument("repos", nargs="+", help="Paths to local git repositories to ingest")
    parser.add_argument("--project-id", default=None, help="Google Cloud Project ID (default: env or gcloud config)")
    parser.add_argument("--bucket", default=os.environ.get("BIFROST_GCS_BUCKET", "bifrost-bucket"), help="GCS Bucket Name")
    parser.add_argument("--location", default="global", help="Vertex AI Search Location")
    parser.add_argument("--data-store-id", default="github-repo-store", help="Data Store ID")
    parser.add_argument("--display-name", default="Github-Repo-Store", help="Data Store Display Name")
    parser.add_argument("--skip-create-datastore", action="store_true", help="Skip creating the Data Store (use existing one; use if you lack discoveryengine.dataStores.create)")
    
    args = parser.parse_args()
    args.project_id = _resolve_project_id(args.project_id)

    if not args.project_id:
        print("Error: Could not resolve project ID. Set GOOGLE_CLOUD_PROJECT, run 'gcloud config set project PROJECT_ID', or pass --project-id.")
        exit(1)

    print("--- Bifrost: GitHub to Vertex AI Search Ingestion ---")
    
    # Step A: Create Data Store (unless skipped)
    if not args.skip_create_datastore:
        create_data_store(
            project_id=args.project_id,
            location=args.location,
            data_store_id=args.data_store_id,
            display_name=args.display_name
        )
    else:
        print("Skipping Data Store creation (--skip-create-datastore). Using existing data store.")

    # Ensure GCS bucket exists (create if missing)
    ensure_bucket_exists(args.project_id, args.bucket)
    
    for repo_path in args.repos:
        repo_name = os.path.basename(os.path.abspath(repo_path))
        gcs_prefix = f"{repo_name}"

        # Step B: Process Repo & Upload to GCS
        metadata_gcs_uri = process_repository(
            repo_path=repo_path,
            bucket_name=args.bucket,
            gcs_prefix=gcs_prefix
        )
        
        if metadata_gcs_uri:
            # Step C: Import Documents
            import_documents(
                project_id=args.project_id,
                location=args.location,
                data_store_id=args.data_store_id,
                gcs_uri=metadata_gcs_uri
            )
        else:
             print(f"Skipping ingestion for '{repo_path}' due to processing errors.")
             
    print("Bifrost ingestion pipeline completed.")
