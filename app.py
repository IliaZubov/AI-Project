import streamlit as st
import os
import json
import tempfile
from pathlib import Path
#from dotenv import load_dotenv
from openai import AzureOpenAI
import pdfplumber
from docx import Document

from document_check import doc_function

# Alusta Azure OpenAI client
@st.cache_resource
def get_azure_client():
    api_key = os.getenv("AZURE_API_KEY")
    api_version = os.getenv("AZURE_API_VERSION")
    azure_endpoint = os.getenv("AZURE_ENDPOINT")
    
    return AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=azure_endpoint
    )

# Muunnos funktiot
"""def docx_to_json_data(docx_path):
    doc = Document(docx_path)
    data = {
        "file_name": Path(docx_path).name,
        "paragraphs": []
    }
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if text:
            data["paragraphs"].append({
                "index": i,
                "text": text
            })
    return data

def pdf_to_json_data(pdf_path):
    data = {
        "file_name": Path(pdf_path).name,
        "pages": []
    }
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            data["pages"].append({
                "page": page_num,
                "text": text.strip()
            })
    return data"""

# Sivun asetukset
st.set_page_config(
    page_title="Policy and Guideline Agent",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Policy and Guideline Agent")

# Luo kaksi saraketta pääasettelulle
col1, col2 = st.columns([1, 1])

# Vasen sarake - Tiedostomuunnin
with col1:
    st.header("🔄 Guideline and Compliance Checker")
    st.write("Upload PDF or DOCX files to check compliance and get improvement suggestions.")
    
    uploaded_file = st.file_uploader(
        "Drag and drop files here",
        type=["pdf", "docx", "txt", "json"],
        accept_multiple_files=False
    )
    
    if uploaded_file is not None:
        doc_function(uploaded_file.name)
        
                
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

# Oikea sarake - Chat-käyttöliittymä
with col2:
    st.header("💬 Guideline Assistant")
    st.write("Chat with Azure OpenAI")
    
    # Alusta chat-historia
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Näytä chat-viestit
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    
    # Chat-syöte
    if prompt := st.chat_input("Type your message here..."):
        # Lisää käyttäjän viesti chat-historiaan
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Näytä käyttäjän viesti
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Hae AI-vastaus
        try:
            client = get_azure_client()
            
            # Valmistele viestit API:lle
            api_messages = [{"role": m["role"], "content": m["content"]} 
                        for m in st.session_state.messages]
            
            # Kutsu Azure OpenAI
            response = client.chat.completions.create(
                model="gpt-4o",  # Päivitä käyttöönottonimellä
                messages=api_messages,
                temperature=0.7,
                max_tokens=800
            )
            
            assistant_response = response.choices[0].message.content
            
            # Lisää avustajan vastaus chat-historiaan
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            
            # Näytä avustajan vastaus
            with st.chat_message("assistant"):
                st.markdown(assistant_response)
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    # Tyhjennä chat-painike
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

# Alatunniste
st.divider()
st.caption("Policy and Guideline Agent - Powered by Azure OpenAI")
