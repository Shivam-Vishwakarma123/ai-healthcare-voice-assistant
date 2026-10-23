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


# Formats datetime objects into human-readable UTC timestamp strings.
def _format_datetime(dt: datetime | None) -> str:
    if not dt:
        return "N/A"
    return dt.strftime("%d %b %Y, %I:%M %p UTC")


# Generates a clinical assessment PDF with triage level, findings, and disclaimer.
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


# Generates an official prescription PDF with medication schedule and doctor sign-off.
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


# Generates a clinical consultation note PDF structured in SOAP note format.
def generate_clinical_note_pdf(
    note_id: int,
    note_type: str,
    status: str,
    is_ai_draft: bool,
    created_at: datetime,
    finalized_at: datetime | None,
    patient_name: str,
    patient_email: str,
    patient_age: int | None,
    patient_gender: str | None,
    doctor_name: str,
    doctor_specialty: str,
    doctor_qualifications: str,
    hospital_name: str | None,
    hospital_address: str | None,
    chief_complaint: str | None,
    history_of_present_illness: str | None,
    examination_findings: str | None,
    assessment: str | None,
    plan: str | None,
    follow_up_instructions: str | None,
    appointment_date: datetime | None = None,
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
    amber_color = colors.HexColor("#d97706")
    badge_bg = colors.HexColor("#fef3c7") if is_ai_draft else colors.HexColor("#ccfbf1")

    hosp_style = ParagraphStyle(
        "NoteHospName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=primary_color,
    )
    doc_style = ParagraphStyle(
        "NoteDocName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "NoteMetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=muted_text,
    )
    sec_style = ParagraphStyle(
        "NoteSecHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=dark_text,
        spaceBefore=8,
        spaceAfter=3,
    )
    body_style = ParagraphStyle(
        "NoteBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
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
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=8))

    # Note Title and Status Badge
    type_display = note_type.replace("_", " ").title()
    status_label = "FINALIZED & ELECTRONICALLY SIGNED" if status == "finalized" else "CLINICAL DRAFT - NOT SIGNED"
    if is_ai_draft and status != "finalized":
        status_label = "AI-ASSISTED CLINICAL DRAFT (PENDING CLINICIAN REVIEW)"

    banner_data = [
        [
            Paragraph(f"<b>CLINICAL DOCUMENTATION — {type_display.upper()}</b>", ParagraphStyle("TitleB", fontName="Helvetica-Bold", fontSize=13, textColor=dark_text)),
            Paragraph(f"<b>{status_label}</b>", ParagraphStyle("BadgeB", fontName="Helvetica-Bold", fontSize=8, textColor=primary_color if status == "finalized" else amber_color, alignment=2)),
        ]
    ]
    banner_table = Table(banner_data, colWidths=[330, 200])
    banner_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), badge_bg),
            ("PADDING", (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(banner_table)
    elements.append(Spacer(1, 8))

    # Patient & Encounter details
    patient_details_str = f"<b>{patient_name}</b>"
    if patient_age:
        patient_details_str += f" | Age: {patient_age}"
    if patient_gender:
        patient_details_str += f" | Gender: {patient_gender.capitalize()}"

    enc_date_str = _format_datetime(appointment_date or created_at)
    patient_table_data = [
        [
            Paragraph("<b>Patient:</b>", body_style),
            Paragraph(patient_details_str, body_style),
            Paragraph("<b>Note ID:</b>", body_style),
            Paragraph(f"NOTE-{note_id:06d}", body_style),
        ],
        [
            Paragraph("<b>Email:</b>", body_style),
            Paragraph(patient_email, body_style),
            Paragraph("<b>Date & Time:</b>", body_style),
            Paragraph(enc_date_str, body_style),
        ],
    ]
    p_table = Table(patient_table_data, colWidths=[65, 230, 85, 150])
    p_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ])
    )
    elements.append(p_table)
    elements.append(Spacer(1, 10))

    # Clinical Sections (SOAP style)
    sections = [
        ("Chief Complaint", chief_complaint),
        ("History of Present Illness (HPI)", history_of_present_illness),
        ("Examination Findings / Vitals", examination_findings),
        ("Clinical Assessment & Diagnosis", assessment),
        ("Treatment Plan & Medical Orders", plan),
        ("Follow-up Instructions & Warning Signs", follow_up_instructions),
    ]

    for title, content in sections:
        if content:
            elements.append(Paragraph(title, sec_style))
            elements.append(Paragraph(content, body_style))
            elements.append(Spacer(1, 6))

    # Clinician Signature / Sign-off block
    elements.append(Spacer(1, 15))
    if status == "finalized":
        sig_data = [
            [
                "",
                Paragraph("<b>Electronically Signed By:</b>", body_style),
            ],
            [
                "",
                Paragraph(f"<b>{doctor_name}</b><br/>{doctor_specialty}<br/>Verified at: {_format_datetime(finalized_at or created_at)}", meta_style),
            ],
        ]
    else:
        sig_data = [
            [
                "",
                Paragraph("<b>Draft Status:</b>", body_style),
            ],
            [
                "",
                Paragraph("Unsigned Draft Document — For review and clinical evaluation only.", meta_style),
            ],
        ]

    sig_table = Table(sig_data, colWidths=[330, 200])
    sig_table.setStyle(
        TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEABOVE", (1, 0), (1, 0), 1, primary_color if status == "finalized" else amber_color),
            ("PADDING", (0, 0), (-1, -1), 2),
        ])
    )
    elements.append(sig_table)
    elements.append(Spacer(1, 8))

    # Footer Disclaimer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph(
            "Confidential Medical Record. This document contains protected health information (PHI) "
            "maintained under applicable clinical governance and data confidentiality regulations.",
            meta_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()


# Generates a comprehensive longitudinal patient health passport summary PDF.
def generate_patient_health_summary_pdf(
    patient_name: str,
    patient_email: str,
    patient_age: int | None,
    patient_gender: str | None,
    allergies: list[dict[str, Any]],
    recent_assessments: list[dict[str, Any]],
    recent_prescriptions: list[dict[str, Any]],
    recent_notes: list[dict[str, Any]],
    upcoming_appointments: list[dict[str, Any]],
    generated_at: datetime | None = None,
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

    primary_color = colors.HexColor("#0d9488")
    dark_text = colors.HexColor("#0f172a")
    muted_text = colors.HexColor("#475569")
    danger_color = colors.HexColor("#dc2626")

    title_style = ParagraphStyle(
        "SummTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )
    sec_style = ParagraphStyle(
        "SummSec",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=dark_text,
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "SummBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "SummMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=muted_text,
    )

    elements = []

    # Title & Header
    header_data = [
        [
            Paragraph("CareVoice Health", title_style),
            Paragraph("<b>COMPREHENSIVE PATIENT HEALTH SUMMARY</b>", ParagraphStyle("SubH", fontName="Helvetica-Bold", fontSize=10, textColor=dark_text, alignment=2)),
        ],
        [
            Paragraph("Digital Patient Health Passport", meta_style),
            Paragraph(f"Generated: {_format_datetime(generated_at or datetime.now())}", ParagraphStyle("SubM", fontName="Helvetica", fontSize=8, textColor=muted_text, alignment=2)),
        ],
    ]
    h_table = Table(header_data, colWidths=[260, 270])
    elements.append(h_table)
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=8))

    # Patient Identification
    demo_str = f"<b>Name:</b> {patient_name}  |  <b>Email:</b> {patient_email}"
    if patient_age:
        demo_str += f"  |  <b>Age:</b> {patient_age}"
    if patient_gender:
        demo_str += f"  |  <b>Gender:</b> {patient_gender.capitalize()}"

    p_table = Table([[Paragraph(demo_str, body_style)]], colWidths=[530])
    p_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#99f6e4")),
        ])
    )
    elements.append(p_table)
    elements.append(Spacer(1, 8))

    # 1. Allergies & Adverse Reactions
    elements.append(Paragraph("1. Recorded Allergies & Adverse Reactions", sec_style))
    if allergies:
        alg_rows = [[Paragraph("<b>Allergen / Condition</b>", body_style), Paragraph("<b>Severity</b>", body_style), Paragraph("<b>Reaction Notes</b>", body_style)]]
        for a in allergies:
            alg_rows.append([
                Paragraph(f"<font color='{danger_color}'><b>{a.get('allergen_or_condition', 'Allergy')}</b></font>", body_style),
                Paragraph(a.get("severity", "moderate").upper(), body_style),
                Paragraph(a.get("reaction_description") or "Documented in health record", body_style),
            ])
        alg_table = Table(alg_rows, colWidths=[180, 100, 250])
        alg_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fef2f2")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#fecaca")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(alg_table)
    else:
        elements.append(Paragraph("<i>No active drug or food allergies on record.</i>", body_style))
    elements.append(Spacer(1, 8))

    # 2. Recent Active Prescriptions
    elements.append(Paragraph("2. Recent Prescriptions & Medications", sec_style))
    if recent_prescriptions:
        rx_rows = [[Paragraph("<b>Rx #</b>", body_style), Paragraph("<b>Diagnosis / Condition</b>", body_style), Paragraph("<b>Prescribed Meds</b>", body_style), Paragraph("<b>Date</b>", body_style)]]
        for rx in recent_prescriptions:
            med_list = ", ".join([it.get("medication_name", "") for it in rx.get("items", [])]) or "Standard protocol"
            rx_rows.append([
                Paragraph(rx.get("prescription_number", "RX"), body_style),
                Paragraph(rx.get("diagnosis") or "Clinical assessment", body_style),
                Paragraph(med_list, body_style),
                Paragraph(_format_datetime(rx.get("created_at")), meta_style),
            ])
        rx_table = Table(rx_rows, colWidths=[95, 145, 190, 100])
        rx_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(rx_table)
    else:
        elements.append(Paragraph("<i>No active prescriptions on record.</i>", body_style))
    elements.append(Spacer(1, 8))

    # 3. Recent AI Triage & Clinical Assessments
    elements.append(Paragraph("3. Recent AI Symptom Assessments & Triage History", sec_style))
    if recent_assessments:
        rep_rows = [[Paragraph("<b>Assessment Title</b>", body_style), Paragraph("<b>Urgency Level</b>", body_style), Paragraph("<b>Summary & Recommended Next Steps</b>", body_style)]]
        for r in recent_assessments:
            rep_rows.append([
                Paragraph(f"<b>{r.get('title', 'Health Assessment')}</b>", body_style),
                Paragraph(r.get("urgency_level", "routine").upper(), body_style),
                Paragraph(r.get("summary") or "Triage complete.", body_style),
            ])
        rep_table = Table(rep_rows, colWidths=[150, 90, 290])
        rep_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(rep_table)
    else:
        elements.append(Paragraph("<i>No AI assessments recorded.</i>", body_style))
    elements.append(Spacer(1, 8))

    # 4. Upcoming Consultations & Review Dates
    elements.append(Paragraph("4. Scheduled Appointments & Review Encounters", sec_style))
    if upcoming_appointments:
        app_rows = [[Paragraph("<b>Doctor / Specialist</b>", body_style), Paragraph("<b>Specialty</b>", body_style), Paragraph("<b>Scheduled For</b>", body_style), Paragraph("<b>Type</b>", body_style)]]
        for a in upcoming_appointments:
            app_rows.append([
                Paragraph(a.get("doctor_name", "Doctor"), body_style),
                Paragraph(a.get("specialty", "General"), body_style),
                Paragraph(_format_datetime(a.get("scheduled_for")), body_style),
                Paragraph(a.get("consultation_type", "in_person").replace("_", " ").title(), body_style),
            ])
        app_table = Table(app_rows, colWidths=[150, 130, 150, 100])
        app_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(app_table)
    else:
        elements.append(Paragraph("<i>No upcoming appointments currently scheduled.</i>", body_style))
    elements.append(Spacer(1, 12))

    # Footer Disclaimer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph(
            "<b>Clinical Notice:</b> This summary is compiled from CareVoice patient records. "
            "AI assessments are informational and not a substitute for clinical diagnosis. "
            "For medical emergencies, dial 112 or 108 immediately.",
            meta_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()


# Generates an appointment confirmation booking slip PDF with facility instructions.
def generate_appointment_confirmation_pdf(
    appointment_id: int,
    scheduled_for: datetime,
    duration_minutes: int,
    consultation_type: str,
    status: str,
    doctor_name: str,
    doctor_specialty: str,
    hospital_name: str | None,
    hospital_address: str | None,
    patient_name: str,
    patient_email: str,
    created_at: datetime | None = None,
    notes: str | None = None,
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

    primary_color = colors.HexColor("#0d9488")
    dark_text = colors.HexColor("#0f172a")
    muted_text = colors.HexColor("#475569")

    title_style = ParagraphStyle(
        "ApptTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )
    body_style = ParagraphStyle(
        "ApptBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "ApptMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=muted_text,
    )

    elements = []

    # Header
    header_data = [
        [
            Paragraph("CareVoice Health", title_style),
            Paragraph("<b>APPOINTMENT CONFIRMATION SLIP</b>", ParagraphStyle("SubH", fontName="Helvetica-Bold", fontSize=11, textColor=dark_text, alignment=2)),
        ],
        [
            Paragraph(hospital_name or "CareVoice Clinical Network", meta_style),
            Paragraph(f"Booking Ref: #{appointment_id:06d}", ParagraphStyle("SubM", fontName="Helvetica-Bold", fontSize=9, textColor=primary_color, alignment=2)),
        ],
    ]
    h_table = Table(header_data, colWidths=[260, 270])
    elements.append(h_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=10))

    # Details Grid
    details_data = [
        [Paragraph("<b>Status:</b>", body_style), Paragraph(f"<b>{status.upper()}</b>", body_style)],
        [Paragraph("<b>Scheduled For:</b>", body_style), Paragraph(f"<b>{_format_datetime(scheduled_for)}</b> ({duration_minutes} minutes)", body_style)],
        [Paragraph("<b>Consultation Mode:</b>", body_style), Paragraph(consultation_type.replace("_", " ").title(), body_style)],
        [Paragraph("<b>Doctor / Clinician:</b>", body_style), Paragraph(f"<b>{doctor_name}</b> ({doctor_specialty})", body_style)],
        [Paragraph("<b>Facility / Address:</b>", body_style), Paragraph(f"{hospital_name or 'CareVoice Clinic'}<br/>{hospital_address or 'Authorized Medical Centre'}", body_style)],
        [Paragraph("<b>Patient Name:</b>", body_style), Paragraph(f"<b>{patient_name}</b>", body_style)],
        [Paragraph("<b>Patient Email:</b>", body_style), Paragraph(patient_email, body_style)],
    ]
    if notes:
        details_data.append([Paragraph("<b>Instructions:</b>", body_style), Paragraph(notes, body_style)])

    d_table = Table(details_data, colWidths=[140, 390])
    d_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    elements.append(d_table)
    elements.append(Spacer(1, 14))

    # Patient Instructions
    elements.append(Paragraph("<b>Important Guidelines for your Visit:</b>", body_style))
    elements.append(Paragraph("• Please arrive 15 minutes before your scheduled appointment time.", body_style))
    elements.append(Paragraph("• Bring any relevant prior medical records, lab reports, and medication lists.", body_style))
    elements.append(Paragraph("• For online video consultations, ensure a stable internet connection in a quiet space.", body_style))
    elements.append(Paragraph("• If you need to reschedule or cancel, please do so at least 2 hours in advance.", body_style))
    elements.append(Spacer(1, 12))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph(
            "CareVoice Digital Healthcare Platform. For appointment support or queries, contact your healthcare provider.",
            meta_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()


# Generates an itemized healthcare invoice PDF with billing and provider details.
def generate_invoice_pdf(
    invoice_number: str,
    created_at: datetime,
    patient_name: str,
    patient_email: str,
    hospital_name: str | None,
    hospital_address: str | None,
    description: str,
    amount_minor: int,
    currency: str,
    status: str,
    paid_at: datetime | None = None,
    appointment_reference: str | None = None,
    doctor_name: str | None = None,
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

    primary_color = colors.HexColor("#0d9488")
    dark_text = colors.HexColor("#0f172a")
    muted_text = colors.HexColor("#475569")
    status_color = colors.HexColor("#16a34a") if status == "paid" else colors.HexColor("#ea580c")

    title_style = ParagraphStyle(
        "InvTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
    )
    body_style = ParagraphStyle(
        "InvBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "InvMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=muted_text,
    )

    elements = []

    # Header
    header_data = [
        [
            Paragraph("CareVoice Health", title_style),
            Paragraph("<b>TAX INVOICE</b>", ParagraphStyle("SubH", fontName="Helvetica-Bold", fontSize=14, textColor=dark_text, alignment=2)),
        ],
        [
            Paragraph(f"{hospital_name or 'CareVoice Clinical Network'}<br/>{hospital_address or 'Healthcare Provider Facility'}", meta_style),
            Paragraph(f"<b>Invoice #: {invoice_number}</b><br/>Date: {_format_datetime(created_at)}<br/>Status: <font color='{status_color}'><b>{status.upper()}</b></font>", ParagraphStyle("SubM", fontName="Helvetica", fontSize=9, leading=12, alignment=2)),
        ],
    ]
    h_table = Table(header_data, colWidths=[280, 250])
    elements.append(h_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=10))

    # Billed to
    bill_data = [
        [Paragraph("<b>Billed To:</b>", body_style), Paragraph("<b>Healthcare Facility:</b>", body_style)],
        [
            Paragraph(f"<b>{patient_name}</b><br/>Email: {patient_email}", body_style),
            Paragraph(f"<b>{hospital_name or 'CareVoice Health Network'}</b><br/>{hospital_address or 'Authorized Clinical Network'}", body_style),
        ],
    ]
    b_table = Table(bill_data, colWidths=[265, 265])
    b_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ])
    )
    elements.append(b_table)
    elements.append(Spacer(1, 12))

    # Line Items Table
    amount_major = amount_minor / 100.0
    item_rows = [
        [Paragraph("<b>#</b>", body_style), Paragraph("<b>Service Description</b>", body_style), Paragraph("<b>Clinician / Reference</b>", body_style), Paragraph("<b>Amount (INR)</b>", ParagraphStyle("RAlign", parent=body_style, alignment=2))],
        [
            Paragraph("1", body_style),
            Paragraph(description, body_style),
            Paragraph(f"{doctor_name or 'Clinical Service'}" + (f" (Ref #{appointment_reference})" if appointment_reference else ""), body_style),
            Paragraph(f"₹{amount_major:,.2f}", ParagraphStyle("RAlign", parent=body_style, alignment=2)),
        ],
        [
            "",
            "",
            Paragraph("<b>Total Due:</b>", ParagraphStyle("TotB", parent=body_style, alignment=2)),
            Paragraph(f"<b>₹{amount_major:,.2f}</b>", ParagraphStyle("TotVal", fontName="Helvetica-Bold", fontSize=10, textColor=primary_color, alignment=2)),
        ],
    ]
    it_table = Table(item_rows, colWidths=[30, 240, 140, 120])
    it_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#cbd5e1")),
            ("LINEABOVE", (2, 2), (-1, 2), 1, primary_color),
            ("PADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(it_table)
    elements.append(Spacer(1, 14))

    # Status / Payment Notice
    if status == "paid":
        elements.append(Paragraph(f"<b>Payment Received:</b> This invoice was paid on {_format_datetime(paid_at)}.", body_style))
    else:
        elements.append(Paragraph("<b>Payment Terms:</b> Payment is due upon receipt. Pay online via CareVoice Billing Portal using UPI, Card, or Net Banking.", body_style))
    elements.append(Spacer(1, 14))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph(
            "This is a system-generated Tax Invoice issued through CareVoice Health. Subject to applicable healthcare GST exemptions where provided under law.",
            meta_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()


# Generates an official payment receipt PDF with transaction verification and demo badges.
def generate_payment_receipt_pdf(
    receipt_number: str,
    transaction_id: str,
    invoice_number: str,
    payment_date: datetime,
    amount_minor: int,
    currency: str,
    patient_name: str,
    patient_email: str,
    hospital_name: str | None,
    hospital_address: str | None,
    description: str,
    payment_method: str = "Razorpay Online",
    is_demo: bool = False,
    appointment_reference: str | None = None,
    doctor_name: str | None = None,
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

    primary_color = colors.HexColor("#0d9488")
    dark_text = colors.HexColor("#0f172a")
    muted_text = colors.HexColor("#475569")
    success_color = colors.HexColor("#16a34a")
    amber_color = colors.HexColor("#d97706")

    title_style = ParagraphStyle(
        "RecTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
    )
    body_style = ParagraphStyle(
        "RecBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "RecMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=muted_text,
    )

    elements = []

    # Header
    header_data = [
        [
            Paragraph("CareVoice Health", title_style),
            Paragraph("<b>OFFICIAL PAYMENT RECEIPT</b>", ParagraphStyle("SubH", fontName="Helvetica-Bold", fontSize=14, textColor=success_color, alignment=2)),
        ],
        [
            Paragraph(f"{hospital_name or 'CareVoice Clinical Network'}<br/>{hospital_address or 'Authorized Healthcare Provider Facility'}", meta_style),
            Paragraph(f"<b>Receipt #: {receipt_number}</b><br/>Tx Ref: <code>{transaction_id}</code><br/>Paid: {_format_datetime(payment_date)}", ParagraphStyle("SubM", fontName="Helvetica", fontSize=8, leading=11, alignment=2)),
        ],
    ]
    h_table = Table(header_data, colWidths=[280, 250])
    elements.append(h_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=8))

    # Demo Payment Banner
    if is_demo:
        demo_banner = Table(
            [[Paragraph("<b>DEMO TRANSACTION — SIMULATED PAYMENT (NOT A REAL FINANCIAL TRANSACTION)</b>", ParagraphStyle("DemoB", fontName="Helvetica-Bold", fontSize=9, textColor=amber_color, alignment=1))]],
            colWidths=[530],
        )
        demo_banner.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("BOX", (0, 0), (-1, -1), 1, amber_color),
            ])
        )
        elements.append(demo_banner)
        elements.append(Spacer(1, 8))

    # Receipt Information
    amount_major = amount_minor / 100.0
    rec_details = [
        [Paragraph("<b>Payer Name:</b>", body_style), Paragraph(f"<b>{patient_name}</b>", body_style)],
        [Paragraph("<b>Payer Email:</b>", body_style), Paragraph(patient_email, body_style)],
        [Paragraph("<b>Invoice Number:</b>", body_style), Paragraph(invoice_number, body_style)],
        [Paragraph("<b>Service Description:</b>", body_style), Paragraph(description, body_style)],
        [Paragraph("<b>Attending Clinician:</b>", body_style), Paragraph(doctor_name or "Clinical Consultation", body_style)],
        [Paragraph("<b>Payment Gateway / Method:</b>", body_style), Paragraph(f"{payment_method}" + (" (Demo Simulator)" if is_demo else " (Verified)"), body_style)],
        [Paragraph("<b>Payment Status:</b>", body_style), Paragraph("<font color='#16a34a'><b>PAID & VERIFIED</b></font>", body_style)],
        [Paragraph("<b>Amount Paid:</b>", ParagraphStyle("AmtH", fontName="Helvetica-Bold", fontSize=11, textColor=dark_text)), Paragraph(f"<b>₹{amount_major:,.2f} {currency}</b>", ParagraphStyle("AmtVal", fontName="Helvetica-Bold", fontSize=13, textColor=primary_color))],
    ]
    r_table = Table(rec_details, colWidths=[160, 370])
    r_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    elements.append(r_table)
    elements.append(Spacer(1, 14))

    # Seal & Signature representation
    seal_data = [
        [
            "",
            Paragraph("<b>CareVoice Verification Authority</b><br/>Digitally stamped and verified transaction.", meta_style),
        ]
    ]
    seal_table = Table(seal_data, colWidths=[330, 200])
    elements.append(seal_table)
    elements.append(Spacer(1, 10))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph(
            "This payment receipt is issued electronically by CareVoice Health pursuant to confirmed server-side payment verification. Retain this receipt for your personal tax and insurance records.",
            meta_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()


# Generates a diagnostic lab report metadata summary PDF with pathologist notes.
def generate_diagnostic_report_summary_pdf(
    document_title: str,
    document_type: str,
    created_at: datetime,
    patient_name: str,
    patient_email: str,
    file_name: str,
    file_size_bytes: int,
    mime_type: str,
    hospital_name: str | None = None,
    verified_by: str | None = None,
    summary_notes: str | None = None,
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

    primary_color = colors.HexColor("#0d9488")
    dark_text = colors.HexColor("#0f172a")
    muted_text = colors.HexColor("#475569")

    title_style = ParagraphStyle(
        "DiagTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )
    body_style = ParagraphStyle(
        "DiagBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "DiagMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=muted_text,
    )

    elements = []

    # Header
    header_data = [
        [
            Paragraph("CareVoice Health", title_style),
            Paragraph("<b>DIAGNOSTIC / LAB REPORT METADATA</b>", ParagraphStyle("SubH", fontName="Helvetica-Bold", fontSize=11, textColor=dark_text, alignment=2)),
        ],
        [
            Paragraph(hospital_name or "CareVoice Laboratory & Diagnostics Services", meta_style),
            Paragraph(f"Uploaded: {_format_datetime(created_at)}", ParagraphStyle("SubM", fontName="Helvetica", fontSize=8, alignment=2)),
        ],
    ]
    h_table = Table(header_data, colWidths=[270, 260])
    elements.append(h_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=8))

    size_kb = round(file_size_bytes / 1024, 1)
    doc_details = [
        [Paragraph("<b>Document Title:</b>", body_style), Paragraph(f"<b>{document_title}</b>", body_style)],
        [Paragraph("<b>Document Type:</b>", body_style), Paragraph(document_type.replace("_", " ").title(), body_style)],
        [Paragraph("<b>Patient Name:</b>", body_style), Paragraph(patient_name, body_style)],
        [Paragraph("<b>Patient Email:</b>", body_style), Paragraph(patient_email, body_style)],
        [Paragraph("<b>Source File Name:</b>", body_style), Paragraph(file_name, body_style)],
        [Paragraph("<b>File Size & MIME:</b>", body_style), Paragraph(f"{size_kb} KB ({mime_type})", body_style)],
        [Paragraph("<b>Clinical Verification:</b>", body_style), Paragraph(verified_by or "Verified within CareVoice Patient Records", body_style)],
    ]
    if summary_notes:
        doc_details.append([Paragraph("<b>Summary Observations:</b>", body_style), Paragraph(summary_notes, body_style)])

    d_table = Table(doc_details, colWidths=[150, 380])
    d_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    elements.append(d_table)
    elements.append(Spacer(1, 14))

    # Clinical Note
    elements.append(Paragraph("<b>Notice regarding Diagnostic Documents:</b>", body_style))
    elements.append(Paragraph("Laboratory results and diagnostic findings must be interpreted in clinical context by a licensed physician or specialist. Do not make diagnostic or therapeutic changes independently.", body_style))
    elements.append(Spacer(1, 10))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph("CareVoice Diagnostic Records. Protected under medical record confidentiality standards.", meta_style)
    )

    doc.build(elements)
    return buffer.getvalue()


# Generates a bilingual patient follow-up care plan PDF with red-flag warning signs.
def generate_followup_plan_pdf(
    patient_name: str,
    patient_email: str,
    doctor_name: str,
    doctor_specialty: str,
    hospital_name: str | None,
    created_at: datetime,
    review_date: datetime | str | None,
    follow_up_instructions: str,
    care_plan: str | None,
    warning_signs: list[str] | None = None,
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

    primary_color = colors.HexColor("#0d9488")
    dark_text = colors.HexColor("#0f172a")
    muted_text = colors.HexColor("#475569")
    danger_color = colors.HexColor("#dc2626")

    title_style = ParagraphStyle(
        "FollTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )
    body_style = ParagraphStyle(
        "FollBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_text,
    )
    meta_style = ParagraphStyle(
        "FollMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=muted_text,
    )

    elements = []

    # Header
    header_data = [
        [
            Paragraph("CareVoice Health", title_style),
            Paragraph("<b>PATIENT FOLLOW-UP & CARE PLAN</b>", ParagraphStyle("SubH", fontName="Helvetica-Bold", fontSize=11, textColor=dark_text, alignment=2)),
        ],
        [
            Paragraph(hospital_name or "CareVoice Clinical Network", meta_style),
            Paragraph(f"Created: {_format_datetime(created_at)}", ParagraphStyle("SubM", fontName="Helvetica", fontSize=8, alignment=2)),
        ],
    ]
    h_table = Table(header_data, colWidths=[270, 260])
    elements.append(h_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=8))

    review_str = review_date if isinstance(review_date, str) else _format_datetime(review_date) if review_date else "As instructed by clinician"
    foll_details = [
        [Paragraph("<b>Patient Name:</b>", body_style), Paragraph(patient_name, body_style)],
        [Paragraph("<b>Patient Email:</b>", body_style), Paragraph(patient_email, body_style)],
        [Paragraph("<b>Attending Doctor:</b>", body_style), Paragraph(f"<b>{doctor_name}</b> ({doctor_specialty})", body_style)],
        [Paragraph("<b>Recommended Review Date:</b>", body_style), Paragraph(f"<b>{review_str}</b>", body_style)],
    ]
    f_table = Table(foll_details, colWidths=[170, 360])
    f_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    elements.append(f_table)
    elements.append(Spacer(1, 10))

    # Follow-up Instructions
    elements.append(Paragraph("<b>Follow-Up Instructions:</b>", body_style))
    elements.append(Paragraph(follow_up_instructions, body_style))
    elements.append(Spacer(1, 8))

    # Care Plan
    if care_plan:
        elements.append(Paragraph("<b>Ongoing Care Plan:</b>", body_style))
        elements.append(Paragraph(care_plan, body_style))
        elements.append(Spacer(1, 8))

    # Red Flag Warning Signs
    if warning_signs:
        elements.append(Paragraph(f"<font color='{danger_color}'><b>Red-Flag Warning Signs (Seek Immediate Medical Care):</b></font>", body_style))
        for sign in warning_signs:
            elements.append(Paragraph(f"• {sign}", body_style))
        elements.append(Spacer(1, 8))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
    elements.append(
        Paragraph("CareVoice Clinical Follow-Up Plan. Emergency contacts: 112 / 108.", meta_style)
    )

    doc.build(elements)
    return buffer.getvalue()
