def main(docling_json: list, docling_text: str) -> dict:
    texts = []
    for entry in (docling_json or []):
        if not isinstance(entry, dict):
            continue
        for doc in entry.get("documents", []):
            if not isinstance(doc, dict):
                raise ValueError("Docling returned an invalid document entry")
            filename = doc.get("filename", "document")
            if doc.get("status") not in ("success", "partial_success"):
                raise ValueError(f"Document requires review before IMRAD: {filename} ({doc.get('status')})")
            if doc.get("inline_text_omitted"):
                raise ValueError(f"Full text exceeds inline limits: {filename}. Split the source PDF or use its full ZIP export.")
            document = (doc.get("result") or {}).get("document") or {}
            text = document.get("md_content") or document.get("text_content") or ""
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Full per-file text is unavailable: {filename}. Update Docling Remote to 0.1.2 or inspect the ZIP export.")
            texts.append(text)
    if not texts:
        if not isinstance(docling_text, str) or not docling_text.strip():
            raise ValueError("Docling returned no text for IMRAD")
        if "[Text truncated for Dify;" in docling_text:
            raise ValueError("Combined text was truncated. Use full per-file JSON text or split the source PDF.")
        texts = [docling_text]
    return {"texts": texts, "files_count": len(texts)}
