"""PDF error report generator for failed passport extractions."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF

if TYPE_CHECKING:
    from passport_telegram.queue import QueueItem

logger = logging.getLogger(__name__)

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _shape(text: str) -> str:
    """Reshape and reorder Arabic text for PDF rendering."""
    result = get_display(arabic_reshaper.reshape(text))
    return result if isinstance(result, str) else result.decode()


def generate_error_report_pdf(
    failures: list[tuple[int, QueueItem]],
    total: int,
) -> bytes:
    """Generate a PDF report for failed passport extractions."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    pdf.add_font("dejavu", "", _FONT_PATH)
    pdf.add_font("dejavu", "B", _FONT_BOLD_PATH)

    pdf.add_page()

    # Title.
    pdf.set_font("dejavu", "B", 18)
    pdf.cell(
        w=0,
        h=15,
        text=f"Error Report  —  {len(failures)} / {total}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )
    pdf.ln(5)

    # Subtitle in Arabic.
    pdf.set_font("dejavu", "", 12)
    _rtl_cell(pdf, _shape(f"تقرير الأخطاء — {len(failures)} من {total}"))
    pdf.ln(10)

    for idx, item in failures:
        _render_failure(pdf, idx, item)

    # Footer note.
    pdf.ln(5)
    pdf.set_font("dejavu", "", 10)
    _rtl_cell(pdf, _shape("أعد إرسال الصور التي فشلت بصورة أوضح أو كملف."))

    result = pdf.output()
    return bytes(result) if result else b""


def _render_failure(pdf: FPDF, idx: int, item: QueueItem) -> None:
    """Render a single failure entry with image thumbnail and reason."""
    if pdf.get_y() > 230:
        pdf.add_page()

    # Separator.
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)

    # Header.
    pdf.set_font("dejavu", "B", 13)
    pdf.cell(
        w=0,
        h=8,
        text=f"#{idx}  —  {item.upload.filename}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    # Arabic reason.
    pdf.set_font("dejavu", "", 11)
    reason = item.failure_reason or "خطأ غير محدد"
    _rtl_cell(pdf, _shape(f"السبب: {reason}"))
    pdf.ln(3)

    # English reason.
    pdf.set_font("dejavu", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(w=0, h=6, text=_english_reason(item.failure_reason), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Image thumbnail.
    if item.payload:
        try:
            pdf.image(io.BytesIO(item.payload), w=60, h=0)
        except Exception:
            pdf.set_font("dejavu", "", 9)
            pdf.cell(w=0, h=6, text="[image could not be rendered]", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)


def _rtl_cell(pdf: FPDF, text: str) -> None:
    """Write pre-shaped Arabic text right-aligned."""
    pdf.cell(w=0, h=8, text=text, new_x="LMARGIN", new_y="NEXT", align="R")


def _english_reason(reason: str | None) -> str:
    """Map Arabic failure reasons to English descriptions."""
    mapping = {
        "خطأ أثناء قراءة الجواز": "Processing error (server or model failure)",
        "انتهت مهلة المعالجة": "Processing timed out (model took too long)",
        "الصورة ليست لجواز واضح": "Image not recognized as a clear passport",
        "لم تكتمل المعالجة": "Processing did not complete successfully",
        "تجاوز الحد المسموح": "Monthly quota exceeded",
        "ضغط على الخدمة — أعد المحاولة لاحقاً": "Rate limited by provider",
        "خطأ غير متوقع أثناء المعالجة": "Unexpected processing error",
    }
    return mapping.get(reason or "", f"Error: {reason or 'unknown'}")
