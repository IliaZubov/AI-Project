
import json
import pdfplumber
from pathlib import Path
from docx import Document


def docx_to_json(docx_path):
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
    with open("output_doc.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
        
def pdf_to_json(pdf_path):
    data = {
        "id": Path(pdf_path).name,
        "content": []
    }
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            data["content"] = text.strip()
    with open("output_doc.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def txt_to_json(txt_path):
    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    data = {
        "file_name": Path(txt_path).name,
        "content": content,
        "lines": [line for line in content.split('\n') if line.strip()]
    }
    with open("output_doc.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

