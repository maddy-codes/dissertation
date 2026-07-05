"""Renders a set of AI review notes into a styled PDF, matching the on-screen report."""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# Mossforge palette (static/css/styles.css), reused so the PDF reads as the
# same product as the web report rather than a generic spreadsheet export.
FOREST = colors.HexColor("#1b342b")
INK = colors.HexColor("#1a2a22")
INK_MUTED = colors.HexColor("#5a6a60")
PAPER = colors.HexColor("#f2efe6")
PAPER_SOFT = colors.HexColor("#ebe6d8")
BORDER = colors.HexColor("#ddd7c6")
SUCCESS = colors.HexColor("#3b7a4a")
ERROR = colors.HexColor("#b23a3a")

_STYLES = {
    "title": ParagraphStyle(
        "ReportTitle", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=FOREST,
    ),
    "subtitle": ParagraphStyle(
        "ReportSubtitle", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK,
        spaceBefore=2,
    ),
    "meta": ParagraphStyle(
        "ReportMeta", fontName="Helvetica", fontSize=8.5, leading=13, textColor=INK_MUTED,
        spaceBefore=8,
    ),
    "account_heading": ParagraphStyle(
        "AccountHeading", fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=INK,
        spaceBefore=16, spaceAfter=8,
    ),
    "account_body": ParagraphStyle(
        "AccountBody", fontName="Helvetica", fontSize=9.5, leading=15, textColor=INK_MUTED,
        alignment=TA_JUSTIFY,
    ),
    "account_body_error": ParagraphStyle(
        "AccountBodyError", fontName="Helvetica", fontSize=9.5, leading=15, textColor=ERROR,
        alignment=TA_JUSTIFY,
    ),
    "footer": ParagraphStyle(
        "Footer", fontName="Helvetica", fontSize=7.5, textColor=INK_MUTED,
    ),
    "summary_title": ParagraphStyle(
        "SummaryTitle", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=FOREST,
        spaceBefore=4, spaceAfter=10,
    ),
    "table_header": ParagraphStyle(
        "TableHeader", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=FOREST,
    ),
    "table_header_r": ParagraphStyle(
        "TableHeaderRight", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=FOREST,
        alignment=TA_RIGHT,
    ),
    "table_cell": ParagraphStyle(
        "TableCell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK,
    ),
    "table_cell_r": ParagraphStyle(
        "TableCellRight", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK_MUTED,
        alignment=TA_RIGHT,
    ),
}

_MARGIN = 20 * mm


def _fmt_money(value) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if amount != amount:  # NaN
        return "N/A"
    sign = "-" if amount < 0 else ""
    return f"{sign}£{abs(amount):,.0f}"


def _fmt_pct(value) -> str:
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if pct != pct:  # NaN
        return "n/a"
    return f"{pct:+.1f}%"


def _build_summary_table(rows) -> Table:
    header = [
        Paragraph("Account", _STYLES["table_header"]),
        Paragraph("Current Year", _STYLES["table_header_r"]),
        Paragraph("Prior Year", _STYLES["table_header_r"]),
        Paragraph("Variance", _STYLES["table_header_r"]),
    ]
    data = [header]

    for row in rows:
        name = str(row.get("name") or "").strip() or "Unnamed account"
        code = str(row.get("code") or "").strip()
        label = f"{escape(name)} <font color='#5a6a60' size='7'>({escape(code)})</font>" if code else escape(name)

        variance_abs = row.get("variance_abs")
        try:
            variance_is_negative = float(variance_abs) < 0
        except (TypeError, ValueError):
            variance_is_negative = False
        variance_color = "#b23a3a" if variance_is_negative else "#3b7a4a"
        variance_pct = row.get("variance_pct")
        variance_text = (
            f"<font color='{variance_color}'>{_fmt_money(variance_abs)} "
            f"({_fmt_pct(variance_pct)})</font>"
        )

        data.append([
            Paragraph(label, _STYLES["table_cell"]),
            Paragraph(_fmt_money(row.get("current_value")), _STYLES["table_cell_r"]),
            Paragraph(_fmt_money(row.get("prior_value")), _STYLES["table_cell_r"]),
            Paragraph(variance_text, _STYLES["table_cell_r"]),
        ])

    usable_width = A4[0] - 2 * _MARGIN
    table = Table(
        data,
        colWidths=[usable_width * 0.46, usable_width * 0.18, usable_width * 0.18, usable_width * 0.18],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PAPER),
        ("LINEBELOW", (0, 0), (-1, 0), 1.25, BORDER),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER_SOFT]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _draw_page_frame(canvas, doc, tenant_name: str):
    canvas.saveState()
    page_width, page_height = A4

    # Header rule + running client name, on every page after the first.
    if doc.page > 1:
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.75)
        canvas.line(_MARGIN, page_height - 14 * mm, page_width - _MARGIN, page_height - 14 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(INK_MUTED)
        canvas.drawString(_MARGIN, page_height - 12 * mm, tenant_name)
        canvas.drawRightString(page_width - _MARGIN, page_height - 12 * mm, "AI Review Notes")

    # Footer rule + page number + confidentiality note.
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.75)
    canvas.line(_MARGIN, 14 * mm, page_width - _MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(INK_MUTED)
    canvas.drawString(_MARGIN, 10 * mm, "Generated from live Xero data — for internal review purposes.")
    canvas.drawRightString(page_width - _MARGIN, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_review_pdf(
    tenant_name: str,
    year_end: str | None,
    year_start: str | None,
    run_id: str,
    rows,
    generated_at: datetime | None = None,
) -> bytes:
    """Build a styled PDF of review notes and return it as raw bytes.

    `rows` is an iterable of dicts/namedtuples with `name`, `code`, and
    `summary` (the single-paragraph AI note, or a "FAILED TO PROCESS…" string).
    """
    buffer = io.BytesIO()
    generated_at = generated_at or datetime.now(timezone.utc)

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=28 * mm,
        bottomMargin=20 * mm,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        title=f"AI Review Notes — {tenant_name}",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="main",
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame], onPage=lambda c, d: _draw_page_frame(c, d, tenant_name)),
    ])

    # Nominal codes the reviewer didn't select for this run never got an AI
    # summary written (see main_routes._run_analysis' selected_nominal_codes
    # filtering) — they're out of scope, not failures, so drop them entirely
    # rather than presenting them as "no note produced".
    analyzed_rows = [row for row in rows if str(row.get("summary") or "").strip()]

    story = [
        Paragraph("AI Review Notes", _STYLES["title"]),
        Paragraph(escape(tenant_name), _STYLES["subtitle"]),
        Paragraph(
            f"Year end: {escape(str(year_end or 'N/A'))} &nbsp;·&nbsp; Prior year: {escape(str(year_start or 'N/A'))} "
            f"&nbsp;·&nbsp; Generated: {generated_at.strftime('%Y-%m-%d %H:%M UTC')} "
            f"&nbsp;·&nbsp; Run ref: {escape(str(run_id))}",
            _STYLES["meta"],
        ),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=1.25, color=FOREST, spaceAfter=4),
        Spacer(1, 6),
    ]

    if analyzed_rows:
        story.append(Paragraph("SUMMARY OF MOVEMENTS", _STYLES["summary_title"]))
        story.append(_build_summary_table(analyzed_rows))
        story.append(Spacer(1, 20))

    for row in analyzed_rows:
        name = str(row.get("name") or "").strip() or "Unnamed account"
        code = str(row.get("code") or "").strip()
        summary = str(row.get("summary") or "").strip()
        is_failure = summary.upper().startswith("FAILED TO PROCESS")

        heading = (
            f"{escape(name)} &nbsp;<font color='#5a6a60' size='9'>({escape(code)})</font>"
            if code else escape(name)
        )
        section: list = [Paragraph(heading, _STYLES["account_heading"])]
        style = _STYLES["account_body_error"] if is_failure else _STYLES["account_body"]
        section.append(Paragraph(escape(summary), style))
        section.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceBefore=10, spaceAfter=2))
        story.append(KeepTogether(section))

    doc.build(story)
    return buffer.getvalue()


def build_review_pdf_from_csv(csv_path: str, **kwargs) -> bytes:
    """Convenience wrapper: build a PDF straight from a saved review-notes CSV."""
    import pandas as pd

    df = pd.read_csv(csv_path)
    text_cols = ["xero_names", "xero_codes", "ai_summary"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    numeric_cols = ["current_value", "prior_value", "variance_abs", "variance_pct"]
    rows = []
    for r in df.to_dict(orient="records"):
        row = {"name": r.get("xero_names"), "code": r.get("xero_codes"), "summary": r.get("ai_summary")}
        for col in numeric_cols:
            row[col] = r.get(col)
        rows.append(row)
    return build_review_pdf(rows=rows, **kwargs)


def load_or_render_pdf(
    upload_folder: str,
    run_id: str,
    tenant_name: str,
    year_end: str | None,
    year_start: str | None,
) -> bytes | None:
    """Return a run's PDF, rendering it from the CSV on the fly if needed.

    Runs created before PDF generation was wired into the pipeline only have
    a `.csv` on disk — this lets them still show up in "download all" zips
    and email attachments instead of silently being skipped.
    """
    pdf_path = os.path.join(upload_folder, f"{run_id}.pdf")
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as fh:
            return fh.read()

    csv_path = os.path.join(upload_folder, f"{run_id}.csv")
    if not os.path.exists(csv_path):
        return None

    try:
        pdf_bytes = build_review_pdf_from_csv(
            csv_path, tenant_name=tenant_name, year_end=year_end, year_start=year_start, run_id=run_id,
        )
    except Exception:
        logging.getLogger(__name__).exception("Failed to render PDF on the fly for run %s", run_id)
        return None

    try:
        with open(pdf_path, "wb") as fh:
            fh.write(pdf_bytes)
    except OSError:
        logging.getLogger(__name__).warning("Could not cache rendered PDF for run %s", run_id)

    return pdf_bytes
