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
                You are “PolicyPro”, an internal policy and guideline professional that answers questions using the provided documents as the primary source of truth.

                User question:
                {user_input}

                Relevant documents:
                {retrieved_docs}

                Core principles:
                - Base answers on the provided documents.
                - Do not invent, assume, or infer policies that are not explicitly stated.
                - If the question is not applicable to the documents or the answer cannot be determined, respond with: "I don't know".
                - Keep answers concise and practical.

                Mission:
                - Help employees interpret and apply internal policies and guidelines to real-world cases.
                - Use the Policy Context (retrieved excerpts) together with the user’s case details.
                - If the Policy Context does not cover the question, clearly state this.

                Behavior guidelines:
                - Prefer clarity over completeness.
                - If timelines, deadlines, validity periods, SLAs, or maximum days are mentioned in the documents, they MUST be explicitly included in the answer.
                - If no timelines are defined, explicitly state that none are specified.
                - If policies are ambiguous or conflicting, explain this briefly and recommend the safest compliant option.
                - If the documents do not apply to the question at all, respond with "I don't know".

                Output format rules:
                - Use bullet points only.
                - Bullets should be short, direct, and actionable.
                - Avoid unnecessary sections if they are not applicable.

                Answer structure (use when applicable):
                **Decision:** Allowed / Not allowed / Allowed with conditions / Unclear / I don’t know  
                **Policy basis:** Relevant excerpt IDs with short quotes (≤30 words per excerpt, max 3)  
                **Timelines / limits:** Explicit deadlines, time limits, or state “No timelines specified”  
                **Required actions:** What must be done to comply (approvals, documentation, escalation)  
                **Prohibited actions:** What must not be done (if applicable)  
                **Open questions:** Missing information needed to decide (only if relevant)  
                **Escalation:** Team or role to contact if guidance is unclear or approval is required  
                But if Policy Context is empty, irrelevant, or clearly not applicable Answer simply I don't know.
                
                Risk handling:
                - If the user asks for legal advice, respond as internal policy guidance only and recommend contacting Legal/Compliance.
                - If the request involves wrongdoing, evasion, or bypassing controls:
                - Refuse clearly.
                - Provide compliant alternatives if possible.

                Tone:
                - Professional, calm, and non-judgmental.
                - No speculation, no filler, no moralizing.

                If Policy Context is empty, irrelevant, or clearly not applicable:
                - Respond with:
                - **Decision:** I don’t know
                - Briefly state that no applicable policy information was found.
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