from docx import Document
import json
from pathlib import Path

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
# usage
docx_to_json("input.docx", "output.json")