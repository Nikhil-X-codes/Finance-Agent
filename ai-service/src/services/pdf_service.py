"""Broker statement extraction from PDFs with a text layer."""

from pypdf import PdfReader

from src.config.models import ParseStatementResponse
from src.services.statement_extraction import parse_sections


class PDFService:
    def parse_statement(self, file_path: str) -> ParseStatementResponse:
        try:
            with open(file_path, "rb") as stream:
                reader = PdfReader(stream)
                if reader.is_encrypted or len(reader.pages) > 40:
                    raise ValueError("Upload an unlocked PDF with at most 40 pages.")
                sections = [page.extract_text() or "" for page in reader.pages]
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Could not read the PDF statement.") from exc
        return parse_sections([section for section in sections if section.strip()])
