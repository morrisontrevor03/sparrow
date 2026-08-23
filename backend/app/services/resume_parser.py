import io
import logging
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pdfplumber
from docx import Document

from app.config import settings

logger = logging.getLogger(__name__)

RESUME_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "location": {"type": "string"},
        "summary": {"type": "string"},
        "linkedin": {"type": "string"},
        "github": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "role": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["company", "role", "bullets"],
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "year": {"type": "string"},
                },
            },
        },
        "certifications": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "skills", "experience"],
}

PARSE_TOOL = {
    "name": "save_parsed_resume",
    "description": "Save the structured resume data extracted from the raw text.",
    "input_schema": RESUME_SCHEMA,
}


def extract_text_from_pdf(file_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


async def parse_resume(file_bytes: bytes, file_type: str) -> tuple[str, dict]:
    """
    Returns (raw_text, structured_data).
    Uses Claude with forced tool-use to extract structured JSON.
    """
    if file_type == "pdf":
        raw_text = extract_text_from_pdf(file_bytes)
    elif file_type in ("docx", "doc"):
        raw_text = extract_text_from_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    if not raw_text.strip():
        raise ValueError("Could not extract text from file")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        tools=[PARSE_TOOL],
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": f"Parse this resume and extract all structured information:\n\n{raw_text[:8000]}",
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "save_parsed_resume":
            return raw_text, block.input

    raise ValueError(
        "Resume parser failed to extract structured data — please re-upload the file "
        "and ensure it contains readable text (not a scanned image)"
    )


def save_upload(file_bytes: bytes, filename: str, user_id: str) -> str:
    """Saves file to disk and returns the path."""
    upload_dir = Path(settings.upload_dir) / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{filename}"
    path = upload_dir / safe_name
    path.write_bytes(file_bytes)
    return str(path)
