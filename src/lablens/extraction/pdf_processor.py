"""PDF to image conversion for vision model processing.

Handles both scanned and digital PDFs. Caps at 20 pages for PDF bomb defense.
"""

import base64
import io
import logging

from pdf2image import convert_from_bytes

logger = logging.getLogger(__name__)

MAX_PAGES = 20


class PDFProcessor:
    """Convert PDF to base64-encoded images for Qwen-OCR."""

    @staticmethod
    def validate_pdf(pdf_bytes: bytes, max_size_mb: int = 20) -> None:
        """Validate PDF magic bytes, size, and page count. Raises ValueError on failure."""
        if not pdf_bytes.startswith(b"%PDF-"):
            raise ValueError("File is not a valid PDF (missing %PDF- magic bytes)")
        size_mb = len(pdf_bytes) / (1024 * 1024)
        if size_mb > max_size_mb:
            raise ValueError(f"PDF too large: {size_mb:.1f}MB (max {max_size_mb}MB)")
        # Page count validation — reject before expensive image conversion
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = len(doc)
            doc.close()
            if page_count > MAX_PAGES:
                raise ValueError(
                    f"PDF has {page_count} pages (max {MAX_PAGES}). "
                    "Upload a shorter document or split into parts."
                )
        except ImportError:
            # PyMuPDF not available — page count enforced later by last_page param
            pass

    @staticmethod
    def pdf_to_base64_images(pdf_bytes: bytes, dpi: int = 200) -> list[str]:
        """Convert each PDF page to base64-encoded PNG. Caps at 20 pages."""
        images = convert_from_bytes(pdf_bytes, dpi=dpi, last_page=MAX_PAGES)
        result = []
        for img in images:
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            result.append(b64)
        logger.info("Converted PDF to %d page images (dpi=%d)", len(result), dpi)
        return result

    @staticmethod
    def is_scanned_pdf(pdf_bytes: bytes) -> bool:
        """Heuristic: if extractable text < 50 chars, likely scanned."""
        try:
            import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = "".join(page.get_text() for page in doc)
            return len(text.strip()) < 50
        except ImportError:
            return True  # Default to image path if PyMuPDF unavailable
