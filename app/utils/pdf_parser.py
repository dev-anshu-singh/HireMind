import io
from typing import Union
from pypdf import PdfReader


def extract_text_from_pdf(pdf_source: Union[bytes, str, io.BytesIO]) -> str:
    """
    Extracts plain text content from a PDF file (bytes or file path).

    Args:
        pdf_source: PDF file as bytes, file path string, or BytesIO buffer.

    Returns:
        str: Extracted plain text content.
    """
    if isinstance(pdf_source, bytes):
        stream = io.BytesIO(pdf_source)
        reader = PdfReader(stream)
    else:
        reader = PdfReader(pdf_source)

    text_pages = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_pages.append(page_text)

    return "\n\n".join(text_pages).strip()
