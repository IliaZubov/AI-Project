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
        
cosmos_client = create_cosmos_client()
    
try:
    databases = list(cosmos_client.list_databases())
    print("Databases:", [db['id'] for db in databases])
except exceptions.CosmosHttpResponseError as e:
    print(f"Could not list databases: {e}")