import os
from openai import AzureOpenAI
from cosmosdb import create_cosmos_client
from functions import pdf_to_json, docx_to_json, txt_to_json
import json

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
    
def doc_function(filename):

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
        #continue

    # Seivataan input_doc.jsoniksi
    with open("input_doc.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved to input_doc.json")

    input_doc = "input_doc.json"

    try:
        with open(input_doc, "r", encoding="utf-8") as f:
            doc = json.load(f)
            
            # Extract content based on structure
            if 'content' in doc:
                text_to_embed = doc['content']
            elif 'paragraphs' in doc:
                text_to_embed = "\n".join([p['text'] for p in doc['paragraphs']])
            elif 'pages' in doc:
                text_to_embed = "\n".join([p['text'] for p in doc['pages']])
            else:
                text_to_embed = str(doc)
            
            response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text_to_embed[:8000]  # Limit to avoid token limits
            )
            
            embedding_vector = response.data[0].embedding
                
    except Exception as e:
                print("Request failed with error:", e)
                return {"response": f"Error: {str(e)}", "sources": []}
                
    MODEL_NAME = "gpt-4.1"
    TOP_K = 3                   
    RELEVANCE_THRESHOLD = 0.75
                
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
        { "name": "@q", "value": embedding_vector }
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
        #continue

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
                input=build_doc_prompt(text_to_embed, retrieved_docs),
                temperature=0.1,
                max_output_tokens=1000,
                stream=False
            )
            
        assistant_response = response.output_text
            
    except Exception as e:
        print("Request failed with error:", e)
        assistant_response = f"Error: {str(e)}"
    
    return {
        "response": assistant_response,
        "sources": sources
    }