import os
from openai import AzureOpenAI
import json
import sys
from azure.cosmos import CosmosClient, exceptions
import re
from pathlib import Path
from azure.storage.blob import BlobServiceClient

conn_str = os.getenv("BLOB_CONNECTION_STRING")

blob_service = BlobServiceClient.from_connection_string(conn_str)

container_name = "ilzu"
container_client = blob_service.get_container_client(container_name)

doc_files = []

for blob in container_client.list_blobs():
    if blob.name.startswith("docs/") and blob.name.endswith(".json"):
        blob_client = container_client.get_blob_client(blob.name)
        raw = blob_client.download_blob().readall()
        json_doc = json.loads(raw)
        doc_files.append(json_doc)

def create_cosmos_client():

    account_uri = os.getenv("COSMOS_ENDPOINT")
    account_key = os.getenv("COSMOS_KEY")

    try:
        cos_client = CosmosClient(account_uri, credential=account_key)
        print("Cosmos DB client created successfully.")
        return cos_client
    except exceptions.CosmosHttpResponseError as e:
        print(f"Failed to connect to Cosmos DB: {e}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    
def load_documents(container_client):
    documents = []

    for blob in container_client.list_blobs():
        if blob.name.startswith("docs/") and blob.name.endswith(".json"):
            blob_client = container_client.get_blob_client(blob.name)
            raw = blob_client.download_blob().readall()
            doc = json.loads(raw)

            # Skip non-dict JSON files
            if not isinstance(doc, dict):
                print(f"Skipping blob {blob.name} — not a JSON object")
                continue

            # Skip objects without content
            if "content" not in doc:
                print(f"Skipping blob {blob.name} — no content field")
                continue

            documents.append(doc)

    return documents


def split_into_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s]

def chunk_full_document(doc):
    return [
        {
            "chunk_index": 0,
            "content": f"{doc['title']}\n\n{doc['content']}"
        }
    ]
        
def chunk_by_paragraph(doc):
    paragraphs = [p.strip() for p in doc["content"].split("\n\n") if p.strip()]
    
    return [
        {
            "chunk_index": i,
            "content": paragraph
        } 
        for i, paragraph in enumerate(paragraphs)
    ]
    
def enrich_chunks(doc, raw_chunks):
    enriched = []
    
    for chunk in raw_chunks:
        enriched.append(
            {
                "id": f"{doc['id']}_chunk_{chunk['chunk_index']}",
                "parent_doc_id": doc["id"],
                "chunk_index": chunk["chunk_index"],
                "title": doc["title"],
                "content": chunk["content"],
                "source": f"{doc['id']}: {doc['title']}",
                "company": doc["company"],
                "documentType": doc["documentType"],
                "version": doc["version"],
                "status": doc["status"],
                "effectiveDate": doc["effectiveDate"],
                "lastUpdated": doc["lastUpdated"],
                "changeLog": doc["changeLog"],
                "originalSource": doc["source"],
                "tags": doc["tags"]
            }
        )
    return enriched

def chunk_document(doc):
    if len(split_into_sentences(doc["content"])) <= 10:
        raw = chunk_full_document(doc)
    else:
        raw = chunk_by_paragraph(doc)
    
    return enrich_chunks(doc,raw)

if __name__ in "__main__":
    
    cosmos_client = create_cosmos_client()
    
    try:
        databases = list(cosmos_client.list_databases())
        print("Databases:", [db['id'] for db in databases])
    except exceptions.CosmosHttpResponseError as e:
        print(f"Could not list databases: {e}")
    
    container_client = blob_service.get_container_client("ilzu")
    
    documents = load_documents(container_client)
    
    api_key = os.getenv("AZURE_API_KEY")
    api_version = os.getenv("AZURE_API_VERSION")
    azure_endpoint = os.getenv("AZURE_ENDPOINT")

    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=azure_endpoint
    )
        
    database_name = os.getenv("COSMOS_DATABASE")
    container_name = os.getenv("COSMOS_CONTAINER")
    
    database = cosmos_client.get_database_client(database_name)
    container = database.get_container_client(container_name)
    
    for doc in documents:
        
        if "content" not in doc:
            print(f"Skipping doc {doc.get('id', 'unknown')} — no content field")
            continue

        chunks = chunk_document(doc)
        
        for chunk in chunks:
            
            response = client.embeddings.create(
                model="text-embedding-ada-002",
                input=chunk["content"]
            )
            
            embedding_vector = response.data[0].embedding
            
            chunk["embedding"] = embedding_vector
            
            try:
                container.upsert_item(chunk)
                print("Document inserted successfully")
            except exceptions.CosmosHttpResponseError as e:
                print("Failed to insert document: ", e)