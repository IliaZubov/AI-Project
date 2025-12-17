import os
from openai import AzureOpenAI
import json
import sys
from azure.cosmos import CosmosClient, exceptions
import re
import time

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
    
def load_documents(file_list):
    documents = []
    for file in file_list:
        with open(file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            documents.append(doc)
    return documents
    
doc_files = ["doc1.json", "doc2.json", "doc3.json", "doc4.json", "doc5.json", "doc6.json", "doc7.json", "doc8.json", "doc9.json", "doc10.json"]

if __name__ in "__main__":
    
    cosmos_client = create_cosmos_client()
    
    try:
        databases = list(cosmos_client.list_databases())
        print("Databases:", [db['id'] for db in databases])
    except exceptions.CosmosHttpResponseError as e:
        print(f"Could not list databases: {e}")
    
    documents = load_documents(doc_files)
    
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
                
        text_to_embed = f"{doc['title']}\n\n{doc['content']}"
        
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text_to_embed
        )
        
        embedding_vector = response.data[0].embedding
        print(f"Embedding length: {len(embedding_vector)}")
        print(embedding_vector[:10])
        
        item = {
            "id": doc["id"],
            "company": doc["company"],
            "documentType": doc["documentType"],
            "version": doc["version"],
            "status": doc["status"],
            "effectiveDate": doc["effectiveDate"],
            "lastUpdated": doc["lastUpdated"],
            "changeLog": doc["changeLog"],
            "title": doc["title"],
            "content": doc["content"],
            "source": f"{doc['id']}: {doc['title']}",
            "originalSource": doc["source"],
            "tags": doc["tags"],
            "embedding": embedding_vector
        }
        
        try:
            container.upsert_item(item)
            print("Document inserted successfully")
        except exceptions.CosmosHttpResponseError as e:
            print("Failed to insert document: ", e)