import streamlit as st
import os
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from openai import AzureOpenAI
import pdfplumber
from docx import Document
from document_check import doc_function
from chat import chat_function
load_dotenv()

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
        # Save uploaded file to temporary location
        file_type = uploaded_file.name.split('.')[-1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        try:
            with st.spinner('🔍 Analyzing document...'):
                result = doc_function(tmp_path)
            
            st.markdown("### :page_facing_up: Compliance Evaluation")
            st.markdown(result["response"])
            if result["sources"]:
                st.markdown("#### :books: Sources")
                st.write(", ".join(result["sources"]))
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
        finally:
            # Clean up temp file
            os.unlink(tmp_path)

# Oikea sarake - Chat-käyttöliittymä
with col2:
    st.header("💬 Guideline Assistant")
    st.write("Chat with NordSure AI Assistant")
    
    # Alusta chat-historia
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Chat-syöte
    if prompt := st.chat_input("Type your message here..."):
        # Lisää käyttäjän viesti chat-historiaan
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Näytä käyttäjän viesti
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Hae AI-vastaus
        try:
            result = chat_function(prompt)
            
            # Lisää avustajan vastaus chat-historiaan
            st.session_state.messages.append({"role": "assistant", "content": f"{result['response']}\n\n---\nSources: {result['sources']}"})
            
            # Näytä avustajan vastaus
            with st.chat_message("assistant"):
                st.markdown(result["response"])
                if result["sources"]:
                    st.markdown("#### :books: Sources")
                    st.write(", ".join(result["sources"]))
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
            
    # Näytä chat-viestit
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.messages[:-2]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    
    # Tyhjennä chat-painike
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

# Alatunniste
st.divider()
st.caption("Policy and Guideline Agent - Powered by Azure OpenAI")
