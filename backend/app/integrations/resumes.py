from abc import ABC, abstractmethod
from io import BytesIO

import pdfplumber
from docx import Document


class ResumeParser(ABC):
    @abstractmethod
    def extract_text(self, *, filename: str, content: bytes) -> str:
        """Extract plain text from an uploaded resume file."""


class LocalResumeParser(ResumeParser):
    """Format adapter only; semantic extraction belongs to a separate LLM use-case."""

    def extract_text(self, *, filename: str, content: bytes) -> str:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix == "txt":
            return content.decode("utf-8", errors="replace")
        if suffix == "pdf":
            with pdfplumber.open(BytesIO(content)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        if suffix == "docx":
            return "\n".join(paragraph.text for paragraph in Document(BytesIO(content)).paragraphs)
        raise ValueError("Supported resume formats: PDF, DOCX, TXT")


class ResumeStructurer(ABC):
    @abstractmethod
    async def structure(self, raw_text: str) -> dict:
        """Return skills, experience, grade, stack, location and salary expectations."""


class StubResumeStructurer(ResumeStructurer):
    async def structure(self, raw_text: str) -> dict:
        # TODO: use LLMProvider with a versioned JSON schema and human correction flow.
        return {"skills": [], "experience": [], "grade": None, "stack": [], "location": None, "salary": None}
