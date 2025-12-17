import os
from openai import AzureOpenAI
from cosmosdb import create_cosmos_client, load_documents, chunk_document, chunk_full_document, chunk_by_paragraph
import time
from functions import pdf_to_json, docx_to_json, txt_to_json
import json
from azure.cosmos import exceptions


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
                - If the answer is not found, say "I don't know"
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
                
PROMPT_TEMPLATE_DOC = """
                You are DocuPRO, an internal document compliance and quality evaluator.
                
                User document for evaluation:
                {input_doc}
                
                Relevant documents:
                {retrieved_docs}
                
                Primary role
                - Evaluate whether a given text complies with the organization’s internal policies and guidelines.
                - Policies are provided ONLY via embedded documents (retrieved policy context).
                - Do NOT rely on external sources, assumptions, or general company practices when assessing compliance.
                Strict policy usage rules
                - You MUST base all compliance judgments exclusively on the embedded policy documents.
                - If a rule is not explicitly present in the embedded documents, you must state that it cannot be evaluated.
                - Never invent, infer, or extrapolate policy requirements.
                Evaluation tasks
                1) Determine overall compliance of the text against the embedded policies.
                2) Identify specific non-compliant or ambiguous parts of the text.
                3) Explain clearly what is wrong or missing, referencing the relevant policy sections.
                4) Propose concrete correction suggestions that would make the text compliant.
                5) Provide general quality improvement suggestions (3–4 items) using your full professional knowledge, even if they are not policy-mandated.
                Required output structure (always follow this order)
                Section 1: Overall assessment
                - Compliance status: Compliant / Partially compliant / Non-compliant / Cannot be fully assessed
                - Short rationale (2–3 sentences maximum)
                Section 2: Policy-based findings
                For each issue:
                - Text excerpt: Quote the exact relevant part of the evaluated text
                - Policy reference: Cite the embedded document identifier and section
                - Issue: Explain precisely why this part is non-compliant, unclear, or incomplete
                - Correction suggestion: Provide a specific, actionable rewrite or addition
                If no issues are found:
                - Explicitly state that no policy deviations were detected based on the available documents
                Section 3: General improvement suggestions (non-policy)
                - Provide 3–4 concise, constructive suggestions
                - These may cover clarity, tone, structure, risk awareness, completeness, or best practices
                - These suggestions may use your broader professional knowledge
                - Clearly distinguish these from policy requirements
                - Keep the tone positive, supportive, and improvement-oriented
                Tone and style
                - Professional, neutral, and constructive
                - Supportive and improvement-focused, never accusatory
                - Clear and precise language
                - Avoid legal conclusions; this is a policy evaluation, not legal advice
                Handling uncertainty
                - If embedded policy coverage is incomplete or insufficient:
                - Clearly state the limitation
                - Specify what type of policy or document would be required to complete the evaluation
                Formatting rules
                - Use clear section headers
                - Use bullet points where appropriate
                - Quote text excerpts exactly and sparingly
                - Do not repeat large portions of the input text
                You will receive:
                - The text to be evaluated
                - Embedded policy documents retrieved via vector search
                Your goal is to help the author improve the document so it aligns with internal policies while encouraging high-quality, well-structured, and professional documentation.
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
    
def build_doc_prompt(input_doc, docs):
    joined_docs = "\n\n".join(
    [
        f"Title: {doc['title']}\n"
        f"Content: {doc['content']}"
        for doc in docs
    ]
    )
    return PROMPT_TEMPLATE_DOC.format(
        retrieved_docs=joined_docs,
        input_doc=input_doc
    )
    
    
    
input_tokens_used = None
output_tokens_used = None

while True:
    
    MODEL_NAME = "gpt-4.1"
    TOP_K = 3                   
    RELEVANCE_THRESHOLD = 0.75
    
    user_input = input("Question: ")

    if user_input.lower() in ["exit", "quit"]:
        break
    
    elif user_input == "":
        
        ### Tästä aloitetaan huomenna ###
        filename = r"C:\temp python\sample.txt"

        ### Tunnista file formatti ja kutsu oikea funktio sen mukaan ###
        # Muunna tiedostotyypin mukaan
        file_type = filename.split('.')[-1].lower()
        print(f"File type: {file_type}")

        if file_type == "pdf":
            json_data = pdf_to_json(filename)
            print(f"✅ Converted {filename} (PDF)")
        elif file_type == "docx":
            json_data = docx_to_json(filename)
            print(f"✅ Converted {filename} (DOCX)")
        elif file_type == "txt":
            json_data = txt_to_json(filename)
            print(f"✅ Converted {filename} (TXT)")
        elif file_type == "json":
            with open(filename, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            print(f"✅ Loaded {filename} (JSON)")
        else:
            print(f"\n❌ Couldn't determine file type!")
            print(f"Supported formats: PDF, DOCX, TXT, JSON")
            print(f"Your file: {filename}\n")
            continue

        # Seivataan input_doc.jsoniksi
        with open("input_doc.json", "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved to input_doc.json")

        # printataan JSON data
        print("\n" + "="*50)
        print(json.dumps(json_data, indent=2, ensure_ascii=False))
        print("="*50)
        print(f"\nJSON filename: {json_filename}")
        print(f"Original file path: {filename}")

        ### Promptin kutsu kun uusi tiedosto laadattu ###
        
        input_doc = "input_doc.json"
        
        try:
            with open(input_doc, "r", encoding="utf-8") as f:
                doc = json.load(f)
                
                text_to_embed = f"{doc['id']}\n\n{doc['content']}"
                
                response = client.embeddings.create(
                model="text-embedding-ada-002",
                input=text_to_embed
                )
                
                embedding_vector = response.data[0].embedding
                print(f"Embedding length: {len(embedding_vector)}")
                print(embedding_vector[:10])
                
                item = {
                    "id": doc["id"],
                    "content": doc["content"],
                    "embedding": embedding_vector
                }
                
                print("Embedding length:", len(item["embedding"]))
                print("Embedding type:", type(item["embedding"][0]))
                
                try:
                    container.upsert_item(item)
                    print("Document inserted successfully")
                except exceptions.CosmosHttpResponseError as e:
                    print("Failed to insert document: ", e)
                    
        except Exception as e:
                    print("Request failed with error:", e)
    
    elif user_input != "":
        
        try:
            start = time.time()
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
            
            #for r in results:
            #    print(r["source"], "score:", r["score"])

            filtered_results = [
                r for r in results
                if r["score"] >= RELEVANCE_THRESHOLD
            ]
            
            if not filtered_results:
                print("\nAssistant: I don't know.")
                print("\nSources: none")
                print("\n---\n")
                continue

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
                
                print("\nAssistant:\n\n", end="")
                
                assistant_response = ""
                
                for event in response:
                        
                    if event.type == "response.output_text.delta":
                        print(event.delta, end="")
                        assistant_response += event.delta
                        
                    if event.type == "response.completed":
                        usage = event.response.usage
                        input_tokens_used = usage.input_tokens
                        output_tokens_used = usage.output_tokens
                
            except Exception as e:
                print("Request failed with error:", e)
                
            print("\n\nSources:", ", ".join(sources))
                
            print("\n---\n")
            
        except Exception as e:
            print("Request failed with error:", e)
            
        end = time.time()

        latency = end - start

        log_per_query = {
            "Query": user_input,
            "Latency": latency,
            "Model": MODEL_NAME,
            "Top-K": TOP_K,
            "Input tokens": input_tokens_used,
            "Output tokens": output_tokens_used,
            "Total tokens": input_tokens_used + output_tokens_used
        }
        
        for key in log_per_query:
            print(f"{key}:", log_per_query[key])
        print()