from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import (
    ClinicalNote,
    MedicalDocument,
    MedicalReport,
    PatientAllergy,
    Prescription,
    PrescriptionItem,
)
from app.models.conversation import AssistantConversation, AssistantMessage
from app.models.patient import Patient
from app.models.providers import Appointment, Doctor, Hospital
from app.models.user import User

logger = logging.getLogger(__name__)

# Known allergy cross-reactivity mapping for safety checks
_COMMON_ALLERGY_KEYWORDS: dict[str, list[str]] = {
    "penicillin": ["amoxicillin", "ampicillin", "augmentin", "piperacillin", "penicillin"],
    "sulfa": ["sulfamethoxazole", "bactrim", "septra", "sulfasalazine"],
    "nsaid": ["ibuprofen", "aspirin", "naproxen", "diclofenac", "ketorolac"],
    "aspirin": ["aspirin", "acetylsalicylic acid", "ecosprin"],
    "paracetamol": ["paracetamol", "acetaminophen", "crocin", "calpol", "dolo"],
    "cephalosporin": ["cephalexin", "cefixime", "ceftriaxone", "cefuroxime"],
}


def check_medication_allergy_conflicts(
    db: Session, patient_user_id: int, medication_names: list[str]
) -> list[str]:
    """Inspects patient's active allergies and flags any potential allergen conflicts."""
    active_allergies = db.scalars(
        select(PatientAllergy).where(
            PatientAllergy.patient_user_id == patient_user_id,
            PatientAllergy.is_active == True,  # noqa: E712
        )
    ).all()

    warnings: list[str] = []
    for allergy in active_allergies:
        allergen_lower = allergy.allergen_or_condition.lower().strip()
        matched_classes = []
        for class_name, drugs in _COMMON_ALLERGY_KEYWORDS.items():
            if class_name in allergen_lower:
                matched_classes.extend(drugs)

        for med in medication_names:
            med_lower = med.lower().strip()
            # Direct match
            if allergen_lower in med_lower or med_lower in allergen_lower:
                warnings.append(
                    f"POTENTIAL ALLERGY CONFLICT: Patient has recorded allergy '{allergy.allergen_or_condition}' (Severity: {allergy.severity}) matching prescribed '{med}'."
                )
            # Class match
            elif any(d in med_lower for d in matched_classes):
                warnings.append(
                    f"CROSS-REACTIVITY WARNING: '{med}' may cross-react with recorded allergy '{allergy.allergen_or_condition}'."
                )

    return list(dict.fromkeys(warnings))


def draft_clinical_note_with_ai(
    db: Session,
    patient_user_id: int,
    doctor_id: int,
    appointment_id: int | None = None,
    conversation_id: int | None = None,
    symptoms_context: str | None = None,
) -> dict[str, Any]:
    """Drafts an encounter-linked clinical note from patient consultation history.

    Marked explicitly as AI-generated and unapproved.
    """
    patient = db.get(User, patient_user_id)
    patient_name = patient.full_name if patient else "Patient"

    chief_complaint = symptoms_context or "General healthcare consultation"
    hpi = "Patient presented for evaluation. "
    if conversation_id:
        conv = db.get(AssistantConversation, conversation_id)
        if conv and conv.summary:
            chief_complaint = conv.title or conv.summary
            hpi += f"Preliminary AI triage noted: {conv.summary}."
            if conv.urgency_level:
                hpi += f" Urgency classified as {conv.urgency_level}."

    exam_findings = "Vitals and physical examination to be conducted and verified by attending clinician."
    assessment = f"Educational assessment: Evaluation for symptoms related to {chief_complaint}. Requires definitive in-person clinical diagnosis."
    plan = (
        "1. Complete clinical examination.\n"
        "2. Order baseline diagnostic laboratory investigations if clinically indicated.\n"
        "3. Review symptom progression and provide supportive symptomatic care."
    )
    follow_up = "Follow up in 3 to 5 days, or immediately proceed to emergency care if red-flag symptoms arise."

    return {
        "patient_user_id": patient_user_id,
        "doctor_id": doctor_id,
        "appointment_id": appointment_id,
        "note_type": "consultation_note",
        "chief_complaint": chief_complaint,
        "history_of_present_illness": hpi,
        "examination_findings": exam_findings,
        "assessment": assessment,
        "plan": plan,
        "follow_up_instructions": follow_up,
        "is_ai_draft": True,
        "status": "draft",
        "version": 1,
    }


def draft_prescription_with_ai(
    db: Session,
    patient_user_id: int,
    doctor_id: int,
    diagnosis_hint: str,
    appointment_id: int | None = None,
    symptoms_context: str | None = None,
) -> dict[str, Any]:
    """Generates an unapproved AI prescription draft with allergy conflict checks."""
    diag_lower = diagnosis_hint.lower()

    suggested_items: list[dict[str, Any]] = []

    if any(k in diag_lower for k in ["fever", "headache", "pain", "body ache", "dard"]):
        suggested_items.append({
            "medication_name": "Paracetamol",
            "strength": "500 mg",
            "dosage_form": "tablet",
            "route": "oral",
            "frequency": "SOS / Max 3 times daily after food",
            "duration": "3 days",
            "quantity": "10 tablets",
            "instructions": "Take for fever > 100°F or headache. Maintain minimum 6-hour interval between doses.",
        })
    elif any(k in diag_lower for k in ["cold", "allergy", "rhinitis", "cough", "khansi"]):
        suggested_items.append({
            "medication_name": "Cetirizine",
            "strength": "10 mg",
            "dosage_form": "tablet",
            "route": "oral",
            "frequency": "0-0-1 (Once daily at night)",
            "duration": "5 days",
            "quantity": "5 tablets",
            "instructions": "Take at bedtime. May cause mild drowsiness.",
        })
    elif any(k in diag_lower for k in ["acidity", "gastritis", "gerd", "stomach"]):
        suggested_items.append({
            "medication_name": "Pantoprazole",
            "strength": "40 mg",
            "dosage_form": "tablet",
            "route": "oral",
            "frequency": "1-0-0 (Once daily before breakfast)",
            "duration": "7 days",
            "quantity": "7 tablets",
            "instructions": "Take on an empty stomach with a full glass of water 30 minutes before morning meal.",
        })
    else:
        suggested_items.append({
            "medication_name": "Oral Rehydration Salts (ORS)",
            "strength": "21.8 g sachet",
            "dosage_form": "powder",
            "route": "oral",
            "frequency": "As needed throughout the day",
            "duration": "3 days",
            "quantity": "5 sachets",
            "instructions": "Dissolve one packet in 1 liter of clean drinking water. Drink throughout the day to maintain hydration.",
        })

    # Check allergy warnings
    med_names = [it["medication_name"] for it in suggested_items]
    allergy_warnings = check_medication_allergy_conflicts(db, patient_user_id, med_names)

    return {
        "patient_user_id": patient_user_id,
        "doctor_id": doctor_id,
        "appointment_id": appointment_id,
        "diagnosis": diagnosis_hint,
        "notes": "AI-drafted supportive medication suggestions. Attending clinician MUST review and verify doses prior to issuing.",
        "allergy_warnings": allergy_warnings,
        "is_ai_draft": True,
        "status": "draft",
        "items": suggested_items,
    }


def generate_fhir_r4_bundle(db: Session, patient_user_id: int) -> dict[str, Any]:
    """Builds a standards-aligned HL7 FHIR R4 JSON Bundle for the patient's longitudinal record."""
    patient_user = db.get(User, patient_user_id)
    if not patient_user:
        return {"resourceType": "Bundle", "type": "collection", "entry": []}

    patient_profile = db.scalar(select(Patient).where(Patient.owner_user_id == patient_user_id))

    bundle_entries: list[dict[str, Any]] = []

    # 1. Patient Resource
    patient_resource = {
        "resourceType": "Patient",
        "id": f"patient-{patient_user.id}",
        "identifier": [
            {
                "system": "https://carevoice.health/identifiers/patient",
                "value": str(patient_user.id),
            }
        ],
        "active": patient_user.is_active,
        "name": [
            {
                "use": "official",
                "text": patient_user.full_name,
            }
        ],
        "telecom": [
            {"system": "email", "value": patient_user.email},
        ],
        "gender": getattr(patient_profile, "gender", "unknown") if patient_profile else "unknown",
    }
    if getattr(patient_user, "phone_number", None):
        patient_resource["telecom"].append({"system": "phone", "value": patient_user.phone_number})

    bundle_entries.append({
        "fullUrl": f"urn:uuid:patient-{patient_user.id}",
        "resource": patient_resource,
    })

    # 2. Condition & Allergy Resources
    allergies = db.scalars(
        select(PatientAllergy).where(PatientAllergy.patient_user_id == patient_user_id)
    ).all()
    for al in allergies:
        allergy_res = {
            "resourceType": "AllergyIntolerance",
            "id": f"allergy-{al.id}",
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": "active" if al.is_active else "inactive",
                    }
                ]
            },
            "category": ["medication" if al.category == "medication_reaction" else "environment"],
            "criticality": "high" if al.severity in ["severe", "life_threatening"] else "low",
            "patient": {"reference": f"Patient/patient-{patient_user.id}"},
            "code": {
                "text": al.allergen_or_condition,
            },
            "reaction": [{"manifestation": [{"text": al.reaction or "Adverse reaction"}]}],
        }
        bundle_entries.append({
            "fullUrl": f"urn:uuid:allergy-{al.id}",
            "resource": allergy_res,
        })

    # 3. Encounters (Appointments)
    appointments = db.scalars(
        select(Appointment).where(Appointment.patient_user_id == patient_user_id)
    ).all()
    for appt in appointments:
        enc_res = {
            "resourceType": "Encounter",
            "id": f"encounter-{appt.id}",
            "status": "finished" if appt.status == "completed" else "planned",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory",
            },
            "subject": {"reference": f"Patient/patient-{patient_user.id}"},
            "period": {
                "start": appt.scheduled_for.isoformat() if appt.scheduled_for else None,
            },
        }
        bundle_entries.append({
            "fullUrl": f"urn:uuid:encounter-{appt.id}",
            "resource": enc_res,
        })

    # 4. MedicationRequests (Prescriptions)
    prescriptions = db.scalars(
        select(Prescription).where(
            Prescription.patient_user_id == patient_user_id,
            Prescription.status.in_(["finalized", "draft"]),
        )
    ).all()
    for rx in prescriptions:
        for it in rx.items:
            med_req = {
                "resourceType": "MedicationRequest",
                "id": f"medreq-{it.id}",
                "status": "active" if rx.status == "finalized" else "draft",
                "intent": "order",
                "subject": {"reference": f"Patient/patient-{patient_user.id}"},
                "medicationCodeableConcept": {
                    "text": f"{it.medication_name} {it.strength or ''}".strip(),
                },
                "dosageInstruction": [
                    {
                        "text": f"{it.frequency} for {it.duration}. Instructions: {it.instructions or 'As directed'}",
                        "route": {"text": it.route},
                    }
                ],
                "authoredOn": rx.finalized_at.isoformat() if rx.finalized_at else rx.created_at.isoformat(),
            }
            bundle_entries.append({
                "fullUrl": f"urn:uuid:medreq-{it.id}",
                "resource": med_req,
            })

    # 5. DiagnosticReports (Medical Reports)
    reports = db.scalars(
        select(MedicalReport).where(MedicalReport.patient_user_id == patient_user_id)
    ).all()
    for rep in reports:
        diag_rep = {
            "resourceType": "DiagnosticReport",
            "id": f"report-{rep.id}",
            "status": "final" if rep.status in ["finalized", "reviewed"] else "preliminary",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                            "code": "GE",
                            "display": "General Healthcare Assessment",
                        }
                    ]
                }
            ],
            "code": {
                "text": rep.title,
            },
            "subject": {"reference": f"Patient/patient-{patient_user.id}"},
            "conclusion": rep.summary,
            "issued": rep.created_at.isoformat() if rep.created_at else None,
        }
        bundle_entries.append({
            "fullUrl": f"urn:uuid:report-{rep.id}",
            "resource": diag_rep,
        })

    # 6. Provenance
    provenance = {
        "resourceType": "Provenance",
        "id": f"provenance-bundle-{patient_user.id}",
        "target": [{"reference": f"Patient/patient-{patient_user.id}"}],
        "recorded": datetime.now(timezone.utc).isoformat(),
        "activity": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-DocumentCompletion",
                    "code": "AU",
                    "display": "authenticated",
                }
            ]
        },
        "agent": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                            "code": "author",
                        }
                    ]
                },
                "who": {"display": "CareVoice Clinical Health Platform"},
            }
        ],
    }
    bundle_entries.append({
        "fullUrl": f"urn:uuid:provenance-{patient_user.id}",
        "resource": provenance,
    })

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(bundle_entries),
        "entry": bundle_entries,
    }
