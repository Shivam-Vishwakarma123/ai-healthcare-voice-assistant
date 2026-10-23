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
    "penicillin": ["amoxicillin", "ampicillin", "augmentin", "piperacillin", "penicillin", "oxacillin", "methicillin", "cloxacillin"],
    "sulfa": ["sulfamethoxazole", "bactrim", "septra", "sulfasalazine", "sulfadiazine"],
    "nsaid": ["ibuprofen", "aspirin", "naproxen", "diclofenac", "ketorolac", "mefenamic acid", "piroxicam", "indomethacin", "celecoxib", "etoricoxib"],
    "aspirin": ["aspirin", "acetylsalicylic acid", "ecosprin", "disprin"],
    "paracetamol": ["paracetamol", "acetaminophen", "crocin", "calpol", "dolo"],
    "cephalosporin": ["cephalexin", "cefixime", "ceftriaxone", "cefuroxime", "cefazolin", "cefaclor", "cefepime"],
    "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin", "norfloxacin"],
    "macrolide": ["azithromycin", "clarithromycin", "erythromycin", "roxithromycin"],
}

DRUG_CLASSES: dict[str, list[str]] = {
    "penicillin": ["amoxicillin", "ampicillin", "augmentin", "piperacillin", "penicillin", "oxacillin", "methicillin", "cloxacillin"],
    "cephalosporin": ["cephalexin", "cefixime", "ceftriaxone", "cefuroxime", "cefazolin", "cefaclor", "cefepime"],
    "nsaid": ["ibuprofen", "aspirin", "naproxen", "diclofenac", "ketorolac", "mefenamic acid", "piroxicam", "indomethacin", "celecoxib", "etoricoxib"],
    "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin", "norfloxacin"],
    "macrolide": ["azithromycin", "clarithromycin", "erythromycin", "roxithromycin"],
    "sulfa": ["sulfamethoxazole", "trimethoprim", "bactrim", "septra", "sulfasalazine"],
    "ace_inhibitor": ["enalapril", "ramipril", "lisinopril", "captopril", "perindopril"],
    "arb": ["losartan", "telmisartan", "valsartan", "olmesartan", "irbesartan"],
    "beta_blocker": ["metoprolol", "atenolol", "bisoprolol", "propranolol", "carvedilol", "nebivolol"],
}


# Validates prescription items against patient allergies, contraindications, and drug classes.
def validate_prescription_safety(
    db: Session,
    patient_user_id: int,
    medication_names: list[str],
    conditions: list[str] | None = None,
    vitals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rigorous clinical safety validation:
    - Penicillin allergy hard block on penicillins
    - Cephalosporin cross-reactivity warning (2-5% / 10%)
    - NSAIDs contraindication in dengue / thrombocytopenia (bleeding risk)
    - NSAIDs caution in hypertension
    - Fluoroquinolone (tendonitis/QT) and Macrolide (QT) warnings
    - Sulfa cross-reactivity warning
    - Duplicate medication class prevention
    """
    active_allergies = db.scalars(
        select(PatientAllergy).where(
            PatientAllergy.patient_user_id == patient_user_id,
            PatientAllergy.is_active == True,  # noqa: E712
        )
    ).all()

    conditions_list = [c.lower().strip() for c in (conditions or [])]
    for allergy in active_allergies:
        if allergy.category in ["chronic_condition", "condition"]:
            conditions_list.append(allergy.allergen_or_condition.lower().strip())

    vitals_dict = vitals or {}
    has_dengue = any("dengue" in c for c in conditions_list) or bool(vitals_dict.get("dengue_diagnosed"))
    platelets = vitals_dict.get("platelet_count")
    has_thrombocytopenia = has_dengue or (platelets is not None and platelets < 100000)
    has_hypertension = any("hypertension" in c or "high bp" in c or "bp" in c for c in conditions_list) or (
        vitals_dict.get("systolic_bp") is not None and vitals_dict.get("systolic_bp") >= 140
    )

    hard_blocks: list[str] = []
    warnings: list[str] = []
    duplicate_classes: list[str] = []

    # 1. Allergy & Cross-reactivity checks
    penicillin_allergic = any("penicillin" in a.allergen_or_condition.lower() for a in active_allergies)

    for med in medication_names:
        med_lower = med.lower().strip()

        # Direct allergy matching
        for allergy in active_allergies:
            allergen_clean = allergy.allergen_or_condition.lower().strip()
            if allergen_clean in med_lower or med_lower in allergen_clean:
                msg = f"HARD BLOCK: Patient has recorded allergy '{allergy.allergen_or_condition}' (Severity: {allergy.severity}) matching prescribed '{med}'."
                if msg not in hard_blocks:
                    hard_blocks.append(msg)

        # Penicillin hard block
        if penicillin_allergic:
            is_pen = any(p in med_lower for p in DRUG_CLASSES["penicillin"])
            if is_pen:
                msg = f"HARD BLOCK: Patient has recorded Penicillin allergy. Prescribing '{med}' is strictly contraindicated due to risk of life-threatening anaphylaxis."
                if msg not in hard_blocks:
                    hard_blocks.append(msg)
            # Cephalosporin cross-reactivity (2-5% / 10%)
            is_ceph = any(c in med_lower for c in DRUG_CLASSES["cephalosporin"])
            if is_ceph:
                msg = f"CROSS-REACTIVITY WARNING: Patient has Penicillin allergy. Cephalosporin '{med}' carries a 2-5% (up to 10%) cross-reactivity risk due to beta-lactam core similarity. Exercise caution and verify previous tolerance."
                if msg not in warnings:
                    warnings.append(msg)

        # NSAID Contraindications
        is_nsaid = any(n in med_lower for n in DRUG_CLASSES["nsaid"])
        if is_nsaid:
            if has_thrombocytopenia:
                msg = f"HARD BLOCK / CONTRAINDICATION: NSAID '{med}' is contraindicated in Dengue and Thrombocytopenia due to antiplatelet effects and severe risk of plasma leakage/hemorrhage. Paracetamol is the safe antipyretic of choice."
                if msg not in hard_blocks:
                    hard_blocks.append(msg)
            elif has_hypertension:
                msg = f"CAUTION: NSAID '{med}' may cause renal sodium/water retention and exacerbate systemic hypertension."
                if msg not in warnings:
                    warnings.append(msg)

        # Fluoroquinolones
        if any(f in med_lower for f in DRUG_CLASSES["fluoroquinolone"]):
            msg = f"WARNING: Fluoroquinolone '{med}' carries warnings for tendonitis, tendon rupture, peripheral neuropathy, and QT prolongation."
            if msg not in warnings:
                warnings.append(msg)

        # Macrolides
        if any(m in med_lower for m in DRUG_CLASSES["macrolide"]):
            msg = f"WARNING: Macrolide '{med}' carries risk of QT prolongation and cardiovascular arrhythmias, especially in patients with cardiac risk factors."
            if msg not in warnings:
                warnings.append(msg)

        # Sulfa
        if any("sulfa" in a.allergen_or_condition.lower() for a in active_allergies):
            if any(s in med_lower for s in DRUG_CLASSES["sulfa"]):
                msg = f"HARD BLOCK: Patient has recorded Sulfa allergy. Prescribing sulfonamide '{med}' is contraindicated (risk of Stevens-Johnson syndrome)."
                if msg not in hard_blocks:
                    hard_blocks.append(msg)

    # 2. Duplicate medication class check
    for class_name, drug_list in DRUG_CLASSES.items():
        matched_meds = [
            med for med in medication_names
            if any(d in med.lower() for d in drug_list)
        ]
        if len(matched_meds) >= 2:
            msg = f"DUPLICATE CLASS WARNING: Multiple medications belonging to class '{class_name}' detected ({', '.join(matched_meds)}). Concurrent prescribing increases risk of cumulative toxicity."
            if msg not in duplicate_classes:
                duplicate_classes.append(msg)

    return {
        "is_safe": len(hard_blocks) == 0,
        "hard_blocks": hard_blocks,
        "warnings": warnings,
        "duplicate_classes": duplicate_classes,
    }


# Inspects active patient allergies and warns of direct allergen or drug class conflicts.
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


# Drafts an encounter-linked clinical note marked as unapproved AI draft for doctor review.
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


# Generates an unapproved AI prescription draft with automated allergy conflict checks.
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


# Constructs a standards-compliant HL7 FHIR R4 JSON bundle for patient data portability.
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


# Evaluates patient vitals and lab markers against clinical guidelines (SpO2, Dengue, Hypoglycemia, SNOOP).
def evaluate_vitals_protocols(data: dict[str, Any]) -> dict[str, Any]:
    """Clinical Decision Support engine evaluating vitals and laboratory markers against
    established clinical protocols:
    1. SpO2 < 94% -> WHO COVID-19 / Acute Respiratory awake proning guidelines
    2. Dengue Defervescence -> Hematocrit rise >= 5% and Platelets drop >= 50%
    3. Hypoglycemia (< 70 mg/dL) -> Rule of 15 fast-acting carbohydrates
    4. SNOOP criteria headache -> Thunderclap onset (< 1 min) emergency
    5. Dehydration -> WHO low-osmolarity ORS formula (245 mOsm/L)
    """
    alerts: list[dict[str, Any]] = []
    protocols_triggered: list[str] = []
    critical = False

    # 1. SpO2 < 94% -> WHO Awake Proning Protocol
    spo2 = data.get("spo2")
    if spo2 is not None and spo2 < 94:
        critical = True
        protocols_triggered.append("WHO Awake Proning / Hypoxemia Protocol")
        alerts.append({
            "protocol": "WHO COVID-19 / Acute Respiratory Awake Proning Guidelines",
            "severity": "critical" if spo2 < 90 else "urgent",
            "metric": f"SpO2: {spo2}%",
            "alert_text": f"SpO2 of {spo2}% indicates acute hypoxemia (threshold < 94%). Initiate supplemental oxygen evaluation.",
            "clinical_action": (
                "Implement WHO awake proning protocol under continuous clinical monitoring: "
                "position cycles: 30-120 min prone -> 30-120 min right lateral decubitus -> 30-120 min semi-Fowler's (sitting up) -> 30-120 min left lateral decubitus. "
                "Re-evaluate SpO2 in 15 minutes; prepare advanced airway / high-flow nasal cannula if SpO2 remains < 90%."
            ),
        })

    # 2. Dengue Defervescence Warning
    dengue_diagnosed = bool(data.get("dengue_diagnosed"))
    hct = data.get("hematocrit")
    hct_base = data.get("hematocrit_baseline")
    plt = data.get("platelet_count")
    plt_base = data.get("platelet_count_baseline")

    hct_rise = False
    if hct is not None and hct_base is not None and hct_base > 0:
        pct_increase = ((hct - hct_base) / hct_base) * 100
        if pct_increase >= 5.0 or (hct - hct_base) >= 5.0:
            hct_rise = True
    elif hct is not None and hct >= 45.0:
        hct_rise = True

    plt_drop = False
    if plt is not None and plt_base is not None and plt_base > 0:
        pct_drop = ((plt_base - plt) / plt_base) * 100
        if pct_drop >= 50.0:
            plt_drop = True
    elif plt is not None and plt < 100000:
        plt_drop = True

    if dengue_diagnosed and (hct_rise and plt_drop):
        critical = True
        protocols_triggered.append("WHO Dengue Critical Phase Plasma Leakage Protocol")
        alerts.append({
            "protocol": "WHO Dengue Clinical Management - Critical Phase Plasma Leakage",
            "severity": "critical",
            "metric": f"Hematocrit: {hct}% (Baseline: {hct_base}%), Platelets: {plt}/μL (Baseline: {plt_base}/μL)",
            "alert_text": "CRITICAL DENGUE WARNING: Defervescence phase with signs of active plasma leakage (Hematocrit increase >= 5% and Platelet drop >= 50%). High risk of Dengue Shock Syndrome (DSS).",
            "clinical_action": (
                "Admit immediately for intensive monitoring. Initiate titrated isotonic crystalloids (e.g., Ringer's lactate or 0.9% saline) at 5-7 mL/kg/hour for 1-2 hours. "
                "Strictly avoid NSAIDs/aspirin/intramuscular injections due to hemorrhage hazard. Monitor hematocrit every 4-6 hours, hourly urine output (target > 0.5 mL/kg/h), and vital signs."
            ),
        })

    # 3. Hypoglycemia (< 70 mg/dL) -> Rule of 15
    glucose = data.get("blood_glucose")
    if glucose is not None and glucose < 70:
        protocols_triggered.append("Rule of 15 Hypoglycemia Protocol")
        alerts.append({
            "protocol": "Endocrine Society / ADA Rule of 15 Protocol for Hypoglycemia",
            "severity": "critical" if glucose < 54 else "urgent",
            "metric": f"Blood Glucose: {glucose} mg/dL",
            "alert_text": f"Blood glucose of {glucose} mg/dL constitutes acute hypoglycemia (< 70 mg/dL).",
            "clinical_action": (
                "Execute the Rule of 15 immediately: "
                "1. Administer 15 grams of fast-acting oral carbohydrates (e.g., 1/2 cup fruit juice, 4 glucose tablets, or 3-4 teaspoons sugar). "
                "2. Wait 15 minutes and re-test capillary blood glucose. "
                "3. If blood glucose remains < 70 mg/dL, repeat 15g fast-acting carbohydrate administration. "
                "4. Once blood glucose normalizes (>= 70 mg/dL), provide a complex carbohydrate/protein snack or meal to sustain euglycemia. "
                "If patient is unconscious, confused, or unable to swallow safely, do NOT give oral fluids; administer 25-50 mL 50% Dextrose IV or 1 mg Glucagon IM/SC immediately and call 112/108."
            ),
        })

    # 4. SNOOP Criteria Headache -> Thunderclap / Emergency
    headache = bool(data.get("headache_present"))
    onset_mins = data.get("headache_onset_minutes")
    snoop_flags = [s.lower().strip() for s in (data.get("headache_snoop_criteria") or [])]
    is_thunderclap = (onset_mins is not None and onset_mins <= 1.0) or any(
        k in snoop_flags for k in ["thunderclap", "onset_sudden", "<1 min", "instant"]
    )
    has_snoop_red_flag = is_thunderclap or any(
        k in snoop_flags for k in ["neurologic", "systemic", "papilledema", "positional", "new_onset_elderly"]
    )

    if headache and (is_thunderclap or has_snoop_red_flag):
        critical = True
        protocols_triggered.append("SNOOP Emergency Headache Protocol")
        alerts.append({
            "protocol": "American Headache Society / SNOOP Criteria Secondary Headache Triage",
            "severity": "critical",
            "metric": f"Thunderclap onset: {is_thunderclap}, SNOOP flags: {', '.join(snoop_flags) or 'Acute sudden peak'}",
            "alert_text": "EMERGENCY HEADACHE ALERT: Thunderclap presentation (peak onset < 1 minute) or SNOOP red flags detected. High risk of subarachnoid hemorrhage (SAH), venous sinus thrombosis, or intracranial emergency.",
            "clinical_action": (
                "Immediate urgent transfer to emergency neurovascular service. Order emergent non-contrast head CT immediately. "
                "If non-contrast head CT performed > 6 hours after onset is negative, perform lumbar puncture to evaluate for xanthochromia/erythrocytes. "
                "Maintain strict blood pressure and neurological observation."
            ),
        })

    # 5. Dehydration & Oral Rehydration -> WHO Low-Osmolarity ORS
    dehydration_signs = [d.lower().strip() for d in (data.get("dehydration_signs") or [])]
    is_dehydrated = bool(dehydration_signs) or bool(data.get("dehydration_present"))

    if is_dehydrated:
        protocols_triggered.append("WHO Low-Osmolarity ORS Protocol")
        alerts.append({
            "protocol": "WHO Low-Osmolarity Oral Rehydration Salts (ORS) Protocol",
            "severity": "moderate",
            "metric": f"Clinical signs: {', '.join(dehydration_signs) or 'Dehydration detected'}",
            "alert_text": "Oral rehydration required for clinical dehydration to restore electrolyte balance and circulating blood volume.",
            "clinical_action": (
                "Administer standard WHO low-osmolarity ORS solution (Total Osmolarity: 245 mOsm/L; Sodium: 75 mEq/L; Glucose: 75 mmol/L). "
                "Dosage protocol: For moderate dehydration, administer 75 mL/kg body weight orally over 4 hours. "
                "For ongoing diarrheal loss, administer 100-200 mL ORS for every loose stool. "
                "Continue breastfeeding or regular diet; do NOT withhold food. If patient develops persistent vomiting, altered sensorium, or severe dehydration, switch to IV Ringer's lactate immediately."
            ),
        })

    return {
        "critical_alert": critical,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
        "protocols_triggered": protocols_triggered,
    }


# Scans ambient consultation transcripts for acute emergency indicators triggering immediate exit.
def detect_ambient_emergency_red_flags(text: str) -> list[str]:
    """Inspects ambient consultation transcript for acute life-threatening emergency signs.
    Immediate halt and zero DB logging required if any red flags match.
    """
    clean = (text or "").lower()
    flags: list[str] = []

    # Chest pain / Cardiac
    if any(k in clean for k in [
        "chest pain", "pressure in chest", "crushing chest", "heart attack", "seene mein dard", "chhati mein dard",
        "cardiac arrest", "substernal pain", "radiating to left arm", "radiating to jaw"
    ]):
        flags.append("acute_coronary_syndrome_chest_pain")

    # Respiratory distress
    if any(k in clean for k in [
        "can't breathe", "cannot breathe", "gasping for air", "severe shortness of breath", "saans nahi aa rahi",
        "choking", "stridor", "respiratory failure", "blue lips", "cyanosis"
    ]):
        flags.append("acute_respiratory_distress")

    # Stroke / Acute Neurological Deficit
    if any(k in clean for k in [
        "face drooping", "slurred speech", "weakness on one side", "paralyzed arm", "sudden loss of vision",
        "stroke", "facial droop", "chehra tedha", "bolne mein dikkat"
    ]):
        flags.append("acute_stroke_fast_positive")

    # Thunderclap headache
    if any(k in clean for k in [
        "thunderclap headache", "worst headache of life", "headache reached peak in under 1 minute", "sudden explosive headache"
    ]):
        flags.append("thunderclap_headache_sah_risk")

    # Unconscious / Unresponsive
    if any(k in clean for k in [
        "unconscious", "passed out", "unresponsive", "cannot wake up", "behosh", "loss of consciousness"
    ]):
        flags.append("altered_mental_status_unresponsive")

    # Severe Anaphylaxis
    if any(k in clean for k in [
        "anaphylaxis", "throat closing", "tongue swelling", "lips swelling rapidly", "unable to swallow from swelling"
    ]):
        flags.append("severe_anaphylaxis")

    # Massive Bleeding
    if any(k in clean for k in [
        "severe hemorrhage", "massive bleeding", "vomiting blood", "coughing up blood heavily", "khoon beh raha hai"
    ]):
        flags.append("massive_hemorrhage")

    return flags


def detect_personal_treatment_request(text: str) -> bool:
    """Detects requests attempting to use the ambient scribe or AI to autonomously prescribe or treat without doctor presence."""
    clean = (text or "").lower()
    patterns = [
        "prescribe me",
        "write me a prescription",
        "give me a prescription directly",
        "prescribe without doctor",
        "authorize this medication for me",
        "give me medicine directly",
        "can you prescribe",
        "i need you to prescribe",
    ]
    return any(p in clean for p in patterns)


def extract_ambient_clinical_soap(
    transcript: str, patient_name: str = "Patient", doctor_name: str = "Physician"
) -> dict[str, Any]:
    """Extracts structured SOAP note, vitals, allergies, and prescriptions from consultation transcript."""
    import re
    clean_transcript = transcript.strip()

    vitals_extracted: dict[str, str] = {}
    bp_match = re.search(r"\b(1\d\d/\d\d)\b", clean_transcript)
    if bp_match:
        vitals_extracted["blood_pressure"] = bp_match.group(1)

    spo2_match = re.search(r"\b(?:spo2|oxygen|saturation)[^\d]*(\d{2,3})%?\b", clean_transcript, re.IGNORECASE)
    if spo2_match:
        vitals_extracted["spo2"] = f"{spo2_match.group(1)}%"

    hr_match = re.search(r"\b(?:pulse|heart rate|hr)[^\d]*(\d{2,3})\b", clean_transcript, re.IGNORECASE)
    if hr_match:
        vitals_extracted["heart_rate"] = f"{hr_match.group(1)} bpm"

    temp_match = re.search(r"\b(\d{2,3}(?:\.\d)?)\s*(?:°?\s*[fF]|degrees|fahrenheit)\b", clean_transcript)
    if temp_match:
        vitals_extracted["temperature"] = f"{temp_match.group(1)} °F"

    allergies_noted: list[str] = []
    allergy_matches = re.findall(r"(?:allergic to|allergy to|reaction to)\s+([a-zA-Z]+)", clean_transcript, re.IGNORECASE)
    if allergy_matches:
        allergies_noted = list(dict.fromkeys(allergy_matches))

    prescriptions_drafted: list[dict[str, Any]] = []
    lower_t = clean_transcript.lower()
    if any(k in lower_t for k in ["paracetamol", "dolo", "crocin"]):
        prescriptions_drafted.append({
            "medication_name": "Paracetamol",
            "strength": "650 mg",
            "dosage_form": "tablet",
            "route": "oral",
            "frequency": "1 tablet SOS after meals (max 3 times/day)",
            "duration": "3-5 days",
            "quantity": "10 tablets",
            "instructions": "Take for fever > 100°F or body pain. Ensure 6-hour interval between doses.",
        })
    if any(k in lower_t for k in ["ors", "oral rehydration", "hydration"]):
        prescriptions_drafted.append({
            "medication_name": "Oral Rehydration Salts (ORS)",
            "strength": "21.8 g sachet",
            "dosage_form": "powder",
            "route": "oral",
            "frequency": "Drink freely throughout the day",
            "duration": "3 days",
            "quantity": "5 sachets",
            "instructions": "Mix each sachet in 1 liter clean water. Drink after every loose stool.",
        })
    if any(k in lower_t for k in ["pantoprazole", "antacid", "acidity", "gas"]):
        prescriptions_drafted.append({
            "medication_name": "Pantoprazole",
            "strength": "40 mg",
            "dosage_form": "tablet",
            "route": "oral",
            "frequency": "1-0-0 (Once daily before breakfast)",
            "duration": "7 days",
            "quantity": "7 tablets",
            "instructions": "Take on empty stomach with plain water 30 min before food.",
        })
    if any(k in lower_t for k in ["cetirizine", "cold", "allergy"]):
        prescriptions_drafted.append({
            "medication_name": "Cetirizine",
            "strength": "10 mg",
            "dosage_form": "tablet",
            "route": "oral",
            "frequency": "0-0-1 (Once daily at night)",
            "duration": "5 days",
            "quantity": "5 tablets",
            "instructions": "Take at bedtime. May cause mild sedation.",
        })

    subjective = (
        f"Chief Complaint & History: Patient presented for clinical consultation. "
        f"Key dialogue points transcribed: {clean_transcript[:350]}... "
        f"Symptoms described during clinical dialogue."
    )
    objective = (
        f"Physical Examination & Vitals: "
        f"Vitals extracted from discussion: {', '.join(f'{k}: {v}' for k, v in vitals_extracted.items()) or 'Awaiting clinical entry'}. "
        f"General appearance and system review noted in dialogue."
    )
    assessment = (
        f"Clinical Impression: Preliminary clinical assessment based on ambient encounter between {patient_name} and {doctor_name}. "
        f"Formal differential to be finalized by the attending physician."
    )
    plan = (
        "1. Supportive symptomatic medication as discussed.\n"
        "2. Adequate oral fluid intake and rest.\n"
        "3. Baseline laboratory investigations if symptoms persist beyond 48-72 hours.\n"
        "4. Strict red-flag precautions."
    )
    follow_up = "Follow up in 3 to 5 days, or report immediately to emergency services if severe shortness of breath, persistent vomiting, or high fever develops."

    return {
        "subjective": subjective,
        "objective": objective,
        "assessment": assessment,
        "plan": plan,
        "follow_up_instructions": follow_up,
        "vitals_extracted": vitals_extracted,
        "allergies_noted": allergies_noted,
        "prescriptions_drafted": prescriptions_drafted,
    }


def generate_patient_guide_from_encounter(db: Session, appointment_id: int, language: str = "en") -> dict[str, Any]:
    """Generates an accessible, layperson-friendly patient discharge guide from finalized clinical records.
    Enforces clinical primacy: only finalized records (is_ai_draft == False) are permitted.
    """
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise ValueError("Appointment not found.")

    # Clinical primacy enforcement: Only finalized records
    notes = db.scalars(
        select(ClinicalNote).where(
            ClinicalNote.appointment_id == appointment_id,
            ClinicalNote.status == "finalized",
            ClinicalNote.is_ai_draft == False,
        )
    ).all()

    prescriptions = db.scalars(
        select(Prescription).where(
            Prescription.appointment_id == appointment_id,
            Prescription.status == "finalized",
            Prescription.is_ai_draft == False,
        )
    ).all()

    if not notes and not prescriptions:
        raise ValueError(
            "Encounter has not been finalized by the attending physician. "
            "Patient discharge guide requires verified clinical records."
        )

    patient_name = appt.patient_user.full_name if appt.patient_user else "Patient"
    doctor_name = appt.doctor.user.full_name if (appt.doctor and appt.doctor.user) else "Attending Physician"
    specialty = appt.doctor.specialty if appt.doctor else "General Medicine"

    is_hi = language.strip().lower() == "hi"

    if is_hi:
        title = f"रोगी परामर्श गाइड — {patient_name}"
        overview = f"डॉ. {doctor_name} ({specialty}) के साथ आपका परामर्श सफलतापूर्वक पूरा हो गया है।"
        medications_list: list[dict[str, str]] = []
        for rx in prescriptions:
            for item in rx.items:
                medications_list.append({
                    "medication": item.medication_name,
                    "dose": item.strength or "यथा निर्दिष्ट",
                    "timing": item.frequency,
                    "duration": item.duration,
                    "instructions": item.instructions or "चिकित्सक के निर्देशानुसार लें",
                })
        follow_up = (
            notes[0].follow_up_instructions
            if notes and notes[0].follow_up_instructions
            else "3 से 5 दिनों में पुनः परामर्श करें।"
        )
        red_flags = [
            "तेज़ सांस फूलना या छाती में दर्द",
            "लगातार तेज़ बुखार (>102°F) जो दवा से कम न हो",
            "अत्यधिक कमजोरी, चक्कर आना या बेहोशी",
            "लगातार उल्टी या पानी पीने में असमर्थता",
        ]
        emergency_contacts = ["112 (राष्ट्रीय आपातकालीन सेवा)", "108 (एम्बुलेंस सेवा)", "14416 (टेली-मानस मानसिक स्वास्थ्य)"]
        disclaimer = "यह गाइड आपके डॉक्टर के अंतिम परामर्श नोट्स पर आधारित है। किसी भी आपात स्थिति में तुरंत नज़दीकी अस्पताल जाएं।"
    else:
        title = f"Patient Visit & Care Guide — {patient_name}"
        overview = f"Your consultation with Dr. {doctor_name} ({specialty}) has been finalized and verified."
        medications_list = []
        for rx in prescriptions:
            for item in rx.items:
                medications_list.append({
                    "medication": item.medication_name,
                    "dose": item.strength or "As directed",
                    "timing": item.frequency,
                    "duration": item.duration,
                    "instructions": item.instructions or "Take as directed by doctor",
                })
        follow_up = (
            notes[0].follow_up_instructions
            if notes and notes[0].follow_up_instructions
            else "Follow up in 3 to 5 days or as instructed."
        )
        red_flags = [
            "Severe shortness of breath or persistent chest discomfort",
            "High intractable fever (>102°F) unresponsive to antipyretics",
            "Severe dizziness, fainting, or inability to stay awake",
            "Persistent vomiting or inability to keep fluids down",
        ]
        emergency_contacts = ["112 (National Emergency Helpline)", "108 (Ambulance Services)", "14416 (Tele-MANAS Mental Health)"]
        disclaimer = "This care guide is derived exclusively from your physician's finalized medical records. For sudden worsening, seek emergency care immediately."

    return {
        "appointment_id": appointment_id,
        "patient_name": patient_name,
        "doctor_name": doctor_name,
        "specialty": specialty,
        "language": language,
        "title": title,
        "overview": overview,
        "medications": medications_list,
        "follow_up_instructions": follow_up,
        "red_flag_warnings": red_flags,
        "emergency_contacts": emergency_contacts,
        "disclaimer": disclaimer,
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }
