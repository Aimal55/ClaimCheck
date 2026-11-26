"""LangChain document abstraction and traceable text splitting."""

import uuid

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_source_documents(
    source_id: str,
    atomic_claim_id: str,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator=True,
    )
    documents: list[Document] = splitter.create_documents(
        [text],
        metadatas=[{
            "source_id": source_id,
            "atomic_claim_id": atomic_claim_id,
        }],
    )

    records: list[dict] = []
    search_from = 0
    for document in documents:
        start = text.find(document.page_content, search_from)
        if start < 0:
            start = search_from
        end = start + len(document.page_content)
        search_from = max(start + 1, end - chunk_overlap)
        records.append({
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "atomic_claim_id": atomic_claim_id,
            "text": document.page_content,
            "char_start": start,
            "char_end": end,
            "lexical_score": None,
            "semantic_score": None,
            "fused_score": None,
            "rerank_score": None,
            "document": document,
        })
    return records
