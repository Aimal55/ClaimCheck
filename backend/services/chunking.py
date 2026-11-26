"""Bounded overlapping text chunking with character offsets."""


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[tuple[str, int, int]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    clean = text.strip()
    if not clean:
        return []

    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(clean):
        end = min(start + chunk_size, len(clean))
        candidate = clean[start:end]
        chunks.append((candidate.strip(), start, end))
        if end >= len(clean):
            break
        start = end - overlap
    return chunks
