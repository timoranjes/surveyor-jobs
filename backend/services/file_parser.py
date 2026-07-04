"""
PDF and DOCX file parsing service.
Extracts text from uploaded CV files.
Supports: PDF (text and scanned), DOCX, and plain text fallback.
"""

import io
import os
import tempfile

from PyPDF2 import PdfReader


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from a PDF file. Returns empty string if no text found (scanned PDF)."""
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n\n".join(text_parts)


def extract_docx_text(file_bytes: bytes) -> str:
    """Extract text from a DOCX file."""
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)
    return "\n".join(paragraphs)


def extract_text(filename: str, file_bytes: bytes) -> str:
    """
    Extract text from an uploaded file based on its extension.
    
    Args:
        filename: Original filename (used to detect format)
        file_bytes: Raw file content
    
    Returns:
        Extracted text string
    
    Raises:
        ValueError: Unsupported file type or extraction failed
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        text = extract_pdf_text(file_bytes)
        if not text.strip():
            raise ValueError(
                "No text could be extracted from this PDF. It may be a scanned image — "
                "please use a text-based PDF or paste your CV text manually."
            )
        return text

    elif ext in (".docx", ".doc"):
        text = extract_docx_text(file_bytes)
        if not text.strip():
            raise ValueError("No text found in the document.")
        return text

    elif ext in (".txt", ".md", ".rtf"):
        # Try UTF-8 first, fall back to other encodings
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return file_bytes.decode("latin-1")
            except UnicodeDecodeError:
                raise ValueError("Could not decode text file — unsupported encoding.")

    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: PDF, DOCX, TXT, MD"
        )
