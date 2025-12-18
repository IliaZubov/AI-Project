import os
from openai import AzureOpenAI
from cosmosdb import create_cosmos_client


cosmos_client = create_cosmos_client()

database_name = os.getenv("COSMOS_DATABASE")
container_name = os.getenv("COSMOS_CONTAINER")

database = cosmos_client.get_database_client(database_name)
container = database.get_container_client(container_name)

api_key = os.getenv("AZURE_API_KEY")
api_version = os.getenv("AZURE_API_VERSION")
azure_endpoint = os.getenv("AZURE_ENDPOINT")

client = AzureOpenAI(
    api_key=api_key,
    api_version=api_version,
    azure_endpoint=azure_endpoint
)

PROMPT_TEMPLATE = """
                You are “PolicyPro”, an internal policy and guideline professional that answers questions based only on the provided documents.

                User question:
                {user_input}

                Relevant documents:
                {retrieved_docs}

                Instructions:
                - Use only the information from the documents
                - If the answer is not found and out of context, say "I don't know"
                - Keep the answer concise
                Mission:
                - Help employees interpret and apply internal policies and guidelines to specific real-world cases.
                - Use ONLY the information provided in the retrieved policy excerpts (the “Policy Context”) plus the user’s case details.
                - If the Policy Context is insufficient, say so and request the missing information needed to decide.
                Critical behavior rules:
                - Output format MUST be strict bullet points only (no paragraphs).
                - Bullets must be short, direct, and action-oriented.
                - Never invent policy. Never assume a rule exists if not in Policy Context.
                - If policies conflict or are ambiguous, state the conflict and give the safest compliant path.
                - Always include any time limits defined in the document
                Answer structure (ALWAYS)
                **Decision:** Allowed / Not allowed / Allowed with conditions / Unclear (needs more info)
                **Policy basis:** Cite the relevant excerpt IDs and quote <= 30 words per excerpt (max 3 excerpts)
                **Required actions:** Concrete steps the user must take (approvals, documentation, escalation)
                **Prohibited actions:** What not to do (if applicable)
                **Open questions:** Only if “Unclear” or “Allowed with conditions” needs case details
                **Escalation:** Who/what team to contact when needed
                Risk handling:
                - If the user asks for legal advice, respond as internal policy guidance and recommend contacting Legal/Compliance.
                - If the user requests wrongdoing, evasion, or policy-bypass, refuse and provide compliant alternatives (still bullet points).
                Tone:
                - Professional, firm, non-judgmental.
                - No fluff, no speculation.
                You will receive:
                - User case
                - Policy Context (retrieved excerpts)
                If Policy Context is empty or irrelevant:
                - Mark decision as “Unclear (needs policy)” and ask for the specific policy area or owner to retrieve.
                """
                
def build_prompt(user_input, docs):
    joined_docs = "\n\n".join(
    [
        f"Title: {doc['title']}\n"
        f"Content: {doc['content']}"
        for doc in docs
    ]
    )
    return PROMPT_TEMPLATE.format(
        user_input=user_input,
        retrieved_docs=joined_docs
    )
    
def chat_function(user_input):
    
    MODEL_NAME = "gpt-4.1"
    TOP_K = 3                   
    RELEVANCE_THRESHOLD = 0.75

    #user_input = input("Question: ")

    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=user_input
        )
        
        query_embedding = response.data[0].embedding
        
        query = f"""
            SELECT TOP {TOP_K}
                c.id,
                c.title,
                c.content,
                c.source,
                c.originalSource,
                VectorDistance(c.embedding, @q) AS score
            FROM c
            ORDER BY VectorDistance(c.embedding, @q)
            """

        parameters = [
            { "name": "@q", "value": query_embedding }
        ]

        results = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))

        filtered_results = [
            r for r in results
            if r["score"] >= RELEVANCE_THRESHOLD
        ]
        
        if not filtered_results:
            print("\nAssistant: I don't know.")
            print("\nSources: none")
            print("\n---\n")
            

        retrieved_docs = [
            {
                "title": r["title"],
                "content": r["content"],
                "source": r["source"],
                "originalSource": r["originalSource"]
            }
            for r in filtered_results
        ]
        
        sources = list(dict.fromkeys(doc["source"] for doc in retrieved_docs))
            
        try:
            response = client.responses.create(
                model=MODEL_NAME,
                input=build_prompt(user_input, retrieved_docs),
                temperature=0.1,
                max_output_tokens=1000,
                stream=True
            )
            
            #print("\nAssistant:\n\n", end="")
            
            assistant_response = ""
            
            for event in response:
                    
                """if event.type == "response.output_text.delta":
                    print(event.delta, end="")
                    assistant_response += event.delta"""
                    
                if event.type == "response.completed":
                    usage = event.response.usage
                    input_tokens_used = usage.input_tokens
                    output_tokens_used = usage.output_tokens
            
        except Exception as e:
            print("Request failed with error:", e)
            
        #print("\n\nSources:", ", ".join(sources))
            
        #print("\n---\n")
        
    except Exception as e:
        print("Request failed with error:", e)
        
    assistant_response = event.response.output[0].content[0].text
        
    return {
        "response": assistant_response,
        "sources": sources
    }