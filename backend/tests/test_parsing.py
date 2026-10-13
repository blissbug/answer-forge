from pathlib import Path

import pytest

from app.services.parsing import ParsingError, parse_document


def test_txt_and_markdown_parse(tmp_path: Path) -> None:
    text = tmp_path / "guide.txt"
    text.write_text("Customer data is encrypted.", encoding="utf-8")
    markdown = tmp_path / "guide.md"
    markdown.write_text("# Security\n\nTLS is required.", encoding="utf-8")
    assert parse_document(text, "text/plain")[0].content.startswith("Customer")
    assert parse_document(markdown, "text/markdown")[0].page_number == 1


def test_empty_and_unsupported_files_fail(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ParsingError, match="no usable text"):
        parse_document(empty, "text/plain")
    with pytest.raises(ParsingError, match="Only PDF"):
        parse_document(empty, "application/vnd.ms-excel")


def test_corrupt_pdf_fails(tmp_path: Path) -> None:
    corrupt = tmp_path / "broken.pdf"
    corrupt.write_bytes(b"not a PDF")
    with pytest.raises(ParsingError, match="could not be read"):
        parse_document(corrupt, "application/pdf")
