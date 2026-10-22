from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _format_datetime(dt: datetime | None) -> str:
    if not dt:
        return "N/A"
    return dt.strftime("%d %b %Y, %I:%M %p UTC")


def generate_medical_report_pdf(
    report_title: str,
    report_id: str,
    report_type: str,
    created_at: datetime,
    patient_name: str,
    patient_email: str,
    urgency_level: str,
    summary: str,
    findings: list[dict[str, Any]],
    red_flags: list[str],
    recommended_next_steps: list[str],
    evidence_sources: list[dict[str, Any]],
    uncertainty_notes: str | None,
    disclaimer: str,
    doctor_name: str | None = None,
    hospital_name: str | None = None,
    reviewed_at: datetime | None = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#0284c7")  # Sky 600
    dark_text = colors.HexColor("#0f172a")  # Slate 900
    muted_text = colors.HexColor("#475569")  # Slate 600
    danger_color = colors.HexColor("#dc2626")  # Red 600
    warning_color = colors.HexColor("#d97706")  # Amber 600
    success_color = colors.HexColor("#16a34a")  # Green 600

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=muted_text,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=dark_text,
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=11,
        textColor=muted_text,
    )

    elements = []

    # Header branding
    elements.append(Paragraph("CareVoice Healthcare AI", title_style))
    elements.append(Paragraph(f"Clinical Assessment Report • {report_title}", subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=12))

    # Patient & Metadata Block
    urgency_color = danger_color if urgency_level == "emergency" else (warning_color if urgency_level == "urgent" else success_color)
    meta_data = [
        [
            Paragraph("<b>Patient Name:</b>", body_style),
            Paragraph(patient_name, body_style),
            Paragraph("<b>Report ID:</b>", body_style),
            Paragraph(report_id, body_style),
        ],
        [
            Paragraph("<b>Patient Email:</b>", body_style),
            Paragraph(patient_email, body_style),
            Paragraph("<b>Date Generated:</b>", body_style),
            Paragraph(_format_datetime(created_at), body_style),
        ],
        [
            Paragraph("<b>Report Type:</b>", body_style),
            Paragraph(report_type.replace("_", " ").title(), body_style),
            Paragraph("<b>Clinical Urgency:</b>", body_style),
            Paragraph(f"<font color='{urgency_color.hexval()}'><b>{urgency_level.upper()}</b></font>", body_style),
        ],
    ]
    if doctor_name or hospital_name:
        meta_data.append([
            Paragraph("<b>Assigned Clinician:</b>", body_style),
            Paragraph(doctor_name or "Self-initiated", body_style),
            Paragraph("<b>Hospital/Facility:</b>", body_style),
            Paragraph(hospital_name or "CareVoice Platform", body_style),
        ])

    meta_table = Table(meta_data, colWidths=[110, 150, 110, 160])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    # Summary
    elements.append(Paragraph("Clinical Summary", heading_style))
    elements.append(Paragraph(summary, body_style))
    elements.append(Spacer(1, 10))

    # Red Flags if any
    if red_flags:
        elements.append(Paragraph("<font color='#dc2626'><b>Critical Red Flags Detected:</b></font>", heading_style))
        for flag in red_flags:
            elements.append(Paragraph(f"• <b>{flag}</b>", body_style))
        elements.append(Spacer(1, 10))

    # Findings
    if findings:
        elements.append(Paragraph("Clinical Findings & Observations", heading_style))
        for finding in findings:
            f_title = finding.get("title") or finding.get("name") or "Observation"
            f_desc = finding.get("description") or str(finding)
            elements.append(Paragraph(f"• <b>{f_title}:</b> {f_desc}", body_style))
        elements.append(Spacer(1, 10))

    # Recommendations
    if recommended_next_steps:
        elements.append(Paragraph("Recommended Next Steps", heading_style))
        for step in recommended_next_steps:
            elements.append(Paragraph(f"• {step}", body_style))
        elements.append(Spacer(1, 10))

    # Evidence Sources & Provenance
    if evidence_sources:
        elements.append(Paragraph("Grounded Medical Evidence & Citations", heading_style))
        for src in evidence_sources:
            stitle = src.get("title", "Clinical Reference")
            surl = src.get("source_url") or src.get("url", "")
            sprov = src.get("provenance", "Reviewed Health Source")
            citation_text = f"• <b>{stitle}</b> ({sprov})"
            if surl:
                citation_text += f"<br/>&nbsp;&nbsp;&nbsp;&nbsp;<u>Provenance URL:</u> {surl}"
            elements.append(Paragraph(citation_text, body_style))
        elements.append(Spacer(1, 10))

    # Uncertainty Notes
    if uncertainty_notes:
        elements.append(Paragraph("Diagnostic Uncertainty & Boundary Notes", heading_style))
        elements.append(Paragraph(uncertainty_notes, body_style))
        elements.append(Spacer(1, 10))

    # Review status
    if reviewed_at:
        elements.append(
            Paragraph(
                f"<i>Clinician Review: Completed by {doctor_name or 'Authorized Doctor'} on {_format_datetime(reviewed_at)}</i>",
                body_style,
            )
        )
        elements.append(Spacer(1, 10))

    # Disclaimer Box
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=8))
    disc_data = [[Paragraph(f"<b>LEGAL & CLINICAL DISCLAIMER:</b> {disclaimer}", disclaimer_style)]]
    disc_table = Table(disc_data, colWidths=[530])
    disc_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fecaca")),
        ])
    )
    elements.append(disc_table)

    doc.build(elements)
    return buffer.getvalue()


def generate_prescription_pdf(
    prescription_number: str,
    created_at: datetime,
    patient_name: str,
    patient_email: str,
    patient_age: int | None,
    patient_gender: str | None,
    doctor_name: str,
    doctor_specialty: str,
    doctor_qualifications: str,
    hospital_name: str | None,
    hospital_address: str | None,
    diagnosis: str | None,
    notes: str | None,
    allergy_warnings: list[str],
    items: list[dict[str, Any]],
    is_finalized: bool,
    finalized_at: datetime | None = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    primary_color = colors.HexColor("#0d9488")  # Teal 600
    dark_text = colors.HexColor("#0f172a")
    muted_text = colors.HexColor("#475569")
    danger_color = colors.HexColor("#dc2626")

    hosp_style = ParagraphStyle(
        "HospName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=primary_color,
    )
    doc_style = ParagraphStyle(
        "DocName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=muted_text,
    )
    body_style = ParagraphStyle(
        "PrescBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    rx_symbol_style = ParagraphStyle(
        "RxSymbol",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=26,
        textColor=primary_color,
    )

    elements = []

    # Header: Hospital & Doctor
    header_data = [
        [
            Paragraph(hospital_name or "CareVoice Clinical Network", hosp_style),
            Paragraph(f"<b>{doctor_name}</b>", doc_style),
        ],
        [
            Paragraph(hospital_address or "Authorized Healthcare Provider Facility", meta_style),
            Paragraph(f"{doctor_specialty} • {doctor_qualifications or 'Registered Medical Practitioner'}", meta_style),
        ],
    ]
    h_table = Table(header_data, colWidths=[310, 220])
    h_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 2),
        ])
    )
    elements.append(h_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=10))

    # Prescription metadata & Patient info
    patient_details_str = f"<b>{patient_name}</b>"
    if patient_age:
        patient_details_str += f" | Age: {patient_age}"
    if patient_gender:
        patient_details_str += f" | Gender: {patient_gender.capitalize()}"

    patient_table_data = [
        [
            Paragraph("<b>Patient:</b>", body_style),
            Paragraph(patient_details_str, body_style),
            Paragraph("<b>Rx No:</b>", body_style),
            Paragraph(f"<b>{prescription_number}</b>", body_style),
        ],
        [
            Paragraph("<b>Email:</b>", body_style),
            Paragraph(patient_email, body_style),
            Paragraph("<b>Date:</b>", body_style),
            Paragraph(_format_datetime(finalized_at or created_at), body_style),
        ],
    ]
    if diagnosis:
        patient_table_data.append([
            Paragraph("<b>Diagnosis:</b>", body_style),
            Paragraph(f"<b>{diagnosis}</b>", body_style),
            Paragraph("<b>Status:</b>", body_style),
            Paragraph(
                "<font color='#16a34a'><b>FINALIZED / SIGNED</b></font>" if is_finalized else "<font color='#d97706'><b>DRAFT</b></font>",
                body_style,
            ),
        ])

    p_table = Table(patient_table_data, colWidths=[60, 250, 60, 160])
    p_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    elements.append(p_table)
    elements.append(Spacer(1, 10))

    # Allergy warnings if present
    if allergy_warnings:
        warn_data = [[
            Paragraph(
                f"<font color='#dc2626'><b>ALLERGY WARNINGS CHECKED:</b> {', '.join(allergy_warnings)}</font>",
                body_style,
            )
        ]]
        w_table = Table(warn_data, colWidths=[530])
        w_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
                ("PADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fecaca")),
            ])
        )
        elements.append(w_table)
        elements.append(Spacer(1, 8))

    # Rx Symbol
    elements.append(Paragraph("℞", rx_symbol_style))
    elements.append(Spacer(1, 4))

    # Medication Table
    med_headers = [
        Paragraph("<b>#</b>", body_style),
        Paragraph("<b>Medication & Strength</b>", body_style),
        Paragraph("<b>Form / Route</b>", body_style),
        Paragraph("<b>Frequency</b>", body_style),
        Paragraph("<b>Duration</b>", body_style),
        Paragraph("<b>Instructions</b>", body_style),
    ]
    med_rows = [med_headers]

    for idx, item in enumerate(items, 1):
        m_name = item.get("medication_name", "Medication")
        m_str = item.get("strength")
        name_cell = f"<b>{m_name}</b>" + (f" ({m_str})" if m_str else "")
        med_rows.append([
            Paragraph(str(idx), body_style),
            Paragraph(name_cell, body_style),
            Paragraph(f"{item.get('dosage_form', 'tab').capitalize()} / {item.get('route', 'oral')}", body_style),
            Paragraph(item.get("frequency", "1-0-1"), body_style),
            Paragraph(item.get("duration", "5 days"), body_style),
            Paragraph(item.get("instructions", "As directed"), body_style),
        ])

    med_table = Table(med_rows, colWidths=[25, 140, 85, 100, 65, 115])
    med_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    elements.append(med_table)
    elements.append(Spacer(1, 12))

    # Notes / Clinical Instructions
    if notes:
        elements.append(Paragraph("<b>Clinician Advice & Notes:</b>", body_style))
        elements.append(Paragraph(notes, body_style))
        elements.append(Spacer(1, 14))

    # Signature Block
    elements.append(Spacer(1, 15))
    sig_data = [
        [
            "",
            Paragraph("<b>Electronically Signed By:</b>", body_style),
        ],
        [
            "",
            Paragraph(f"<b>{doctor_name}</b><br/>{doctor_specialty}<br/>Date: {_format_datetime(finalized_at or created_at)}", meta_style),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[330, 200])
    sig_table.setStyle(
        TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEABOVE", (1, 0), (1, 0), 1, colors.HexColor("#0f172a")),
            ("PADDING", (0, 0), (-1, -1), 2),
        ])
    )
    elements.append(sig_table)
    elements.append(Spacer(1, 10))

    # Footer note
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph(
            "This digital prescription is generated via CareVoice Clinical Records. "
            "Valid under relevant Telemedicine Practice Guidelines when finalized by an authorized licensed practitioner.",
            meta_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()
