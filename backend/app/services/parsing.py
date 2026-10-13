from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


class ParsingError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    content: str
    metadata: dict


def parse_document(path: Path, mime_type: str) -> list[ExtractedPage]:
    if mime_type in {"text/plain", "text/markdown"}:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ParsingError("The file contains no usable text.")
        return [ExtractedPage(page_number=1, content=text, metadata={"source_type": "text"})]

    if mime_type == "application/pdf":
        try:
            reader = PdfReader(str(path))
            pages = [
                ExtractedPage(page_number=index, content=(page.extract_text() or "").strip(), metadata={"source_type": "pdf"})
                for index, page in enumerate(reader.pages, start=1)
            ]
        except Exception as error:
            raise ParsingError("The PDF could not be read. It may be corrupt or encrypted.") from error
        usable = [page for page in pages if page.content]
        if not usable:
            raise ParsingError("The PDF contains no extractable text. OCR is not enabled.")
        return usable

    raise ParsingError("Only PDF, TXT, and MD files are supported.")
