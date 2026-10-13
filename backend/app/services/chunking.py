from dataclasses import dataclass

from app.services.parsing import ExtractedPage


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    metadata: dict


def chunk_pages(pages: list[ExtractedPage], chunk_size: int, overlap: int) -> list[ChunkDraft]:
    if not pages:
        return []
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap smaller than chunk_size")

    chunks: list[ChunkDraft] = []
    for page in pages:
        text = page.content.strip()
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            if end < len(text):
                boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
                if boundary > start + chunk_size // 2:
                    end = boundary + (2 if text[boundary:boundary + 2] == ". " else 0)
            content = text[start:end].strip()
            if content:
                chunks.append(ChunkDraft(
                    content=content,
                    metadata={"page_number": page.page_number, "start_offset": start, "end_offset": end},
                ))
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks
