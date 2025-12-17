import json
import pdfplumber
from pathlib import Path
from docx import Document

def docx_to_json(docx_path, json_path):
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
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pdf_to_json(pdf_path, json_path):
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
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)