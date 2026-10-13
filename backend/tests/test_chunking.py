from app.services.chunking import chunk_pages
from app.services.parsing import ExtractedPage


def test_chunk_creation_order_and_overlap() -> None:
    text = "A" * 80 + " B" * 80
    chunks = chunk_pages([ExtractedPage(page_number=3, content=text, metadata={})], chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert [chunk.metadata["page_number"] for chunk in chunks] == [3] * len(chunks)
    assert chunks[0].metadata["end_offset"] > chunks[1].metadata["start_offset"]
    assert chunks[0].content[-20:] in chunks[1].content


def test_empty_input_has_no_chunks() -> None:
    assert chunk_pages([], chunk_size=100, overlap=10) == []
