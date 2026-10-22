# CareVoice Longitudinal Patient Records & Doctor Clinical Workflow

## 1. Executive Summary & Clinical Governance Architecture

CareVoice is an AI-first healthcare assistance and clinical records platform designed to bridge patient pre-consultation triage with structured, authorized clinician workflows. The system adheres strictly to the principle of **clinician primacy**: AI serves as an assistive synthesis and triage layer, while all diagnostic decisions, clinical note finalization, and prescription issuance require explicit, authenticated clinician action.

```
+----------------------------------------------------------------------------------------------------+
|                                     CAREVOICE CLINICAL ECOSYSTEM                                   |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  PATIENT PORTAL                                             DOCTOR WORKSPACE                       |
|  +--------------------------------+                         +-----------------------------------+  |
|  | - Conversational AI Triage     |                         | - Assigned Patients Overview      |  |
|  | - Longitudinal Timeline        |                         | - Triage Assessment Review Inbox  |  |
|  | - Download Signed Rx (PDF)     |                         | - AI-Assisted Clinical Notes      |  |
|  | - Download Medical Reports     |                         | - Prescription Builder (Rx)       |  |
|  | - Upload Diagnostic Documents  |                         | - Real-Time Drug-Allergy Warning  |  |
|  | - Export HL7 FHIR R4 Bundle    |                         | - Electronic Signature & Seal     |  |
|  +----------------+---------------+                         +-----------------+-----------------+  |
|                   |                                                           |                    |
|                   +-------------------> [ POSTGRESQL ] <----------------------+                    |
|                                         |            |                                             |
|                                         v            v                                             |
|                             [ Immutable Audit Log ] [ ReportLab PDF Engine ]                       |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Longitudinal Patient Record Architecture

The patient health record connects every point of care across encounters into an aggregated, chronological timeline:

### 2.1 Core Entities & Database Schema

1. **`clinical_notes`**:
   - Stores consultation notes, SOAP notes, and encounter progress notes.
   - Lifecycle: `draft` -> `finalized` (or `amended`).
   - Fields: `chief_complaint`, `history_of_present_illness`, `examination_findings`, `assessment`, `plan`, `follow_up_instructions`.
   - Immutable metadata: `is_ai_draft` flag, `version`, `finalized_at`, `finalized_by_user_id`.

2. **`prescriptions` & `prescription_items`**:
   - Structured digital prescriptions containing medication name, dosage form (tablet, capsule, syrup, inhaler, drops, ointment), strength, route (oral, topical, inhalation, IV, IM), frequency (`1-0-1`, `1-1-1`, `0-0-1`, etc.), duration, quantity, and specific patient instructions.
   - Distinct prescription tracking identifier: `RX-YYYYMMDD-XXXXXX`.
   - Lifecycle: `draft` -> `finalized` -> `cancelled` / `amended`.

3. **`patient_allergies`**:
   - Records active drug allergies, chronic conditions, and adverse medication reactions.
   - Fields: `allergen_or_condition`, `category`, `severity` (`mild`, `moderate`, `severe`, `life_threatening`), `reaction`, `is_active`.

4. **`medical_reports`**:
   - Synthesized clinical assessment reports generated from conversational AI triage encounters.
   - Evidence-grounded: Includes cited medical guideline sources, urgency classification (`routine`, `urgent`, `emergency`), red flags, and uncertainty disclaimers.

5. **`medical_documents`**:
   - Uploaded diagnostic records, lab reports, discharge summaries, and medical imaging documents.
   - Stores MIME type, byte size, file hash, and clinical notes.

---

## 3. Access Control & Privacy Scoping

CareVoice enforces strict multi-tenant, role-based, and encounter-scoped access controls via `_check_doctor_or_patient_access`:

| Role | Access Scope | Note/Prescription Draft Visibility | Finalized Record Access |
| :--- | :--- | :--- | :--- |
| **Patient** | Self-owned records only (`patient_user_id == user.id`) | ❌ Hidden until finalized | ✅ Full view & PDF download |
| **Doctor** | Assigned patients only (active or historical appointments) | ✅ Full authoring & drafting | ✅ View, print, sign & amend |
| **Unassigned Doctor** | None (HTTP 403 Forbidden) | ❌ Denied | ❌ Denied |
| **Hospital Admin** | Hospital-scoped reporting and metadata | ❌ Denied without encounter | ❌ Protected health information scoped |
| **Platform Admin** | System auditing and tenant management | ❌ Clinical content masked | ❌ Clinical content masked |

---

## 4. Clinician Workflow & AI-Assisted Prescribing

### 4.1 Encounter Note Generation
1. **Pre-Consultation Intake**: Patient completes a triage check or AI conversational consultation.
2. **AI Draft Generation**: The doctor clicks `✨ AI Draft Note from Context`. The backend analyzes the consultation summary, symptoms, and reported duration to populate chief complaint, HPI, examination guidance, differential assessment, and follow-up precautions.
3. **Doctor Verification & Customization**: The clinician modifies findings, adds physical exam observations (e.g., vitals, chest auscultation), and saves as `draft` or `finalizes`.
4. **Electronic Signing**: Finalization marks `is_ai_draft = False`, sets `finalized_at = UTC timestamp`, stamps `finalized_by_user_id = doctor_user_id`, and makes the record immutable.

### 4.2 Drug-Allergy Safety Pre-Screening
Before a prescription is saved or finalized, the prescribing engine runs `check_medication_allergy_conflicts`:
- Compares the active ingredients and brand names of all prescribed items against the patient's recorded allergies.
- Checks known pharmacological cross-reactivity classes:
  - **Penicillin Class**: Amoxicillin, Ampicillin, Augmentin, Penicillin V.
  - **Cephalosporins**: Cephalexin, Cefuroxime, Cefixime, Ceftriaxone.
  - **NSAIDs**: Ibuprofen, Aspirin, Naproxen, Diclofenac, Meloxicam.
  - **Sulfa Drugs**: Sulfamethoxazole, Trimethoprim-Sulfamethoxazole, Bactrim, Septra.
  - **Fluoroquinolones**: Ciprofloxacin, Levofloxacin, Ofloxacin.
  - **Macrolides**: Azithromycin, Clarithromycin, Erythromycin.
- If a conflict is detected, high-prominence clinical alerts are returned in the API and rendered in red banners in the Doctor Workspace.

---

## 5. Server-Side PDF Generation (ReportLab)

CareVoice utilizes server-side ReportLab rendering for high-fidelity, printable clinical documents:
- **Prescription PDF (`/api/v1/records/prescriptions/{id}/pdf`)**:
  - Hospital header and branding.
  - Doctor name, medical registration number, specialty.
  - Patient demographics (name, age, gender, contact).
  - Rx symbol, structured medication grid (Medication, Strength, Form, Frequency, Duration, Instructions).
  - Allergy alert box (if any known allergies or warnings exist).
  - Clinician signature block with electronic verification stamp and timestamp.
- **Medical Assessment PDF (`/api/v1/records/reports/{id}/pdf`)**:
  - Clinical assessment overview and urgency indicator.
  - Reported symptoms and triage findings.
  - Recommended next steps and emergency helpline callouts (112 / 108).
  - Grounded source citations and clinical safety disclaimers.

---

## 6. HL7 FHIR R4 Interoperability

Patient records can be exported in the internationally recognized **HL7 FHIR Release 4** standard JSON Bundle (`/api/v1/records/fhir/export`):
- `Bundle`: Resource collection container (`type: "collection"`).
- `Patient`: Demographics, telecom, identifier.
- `AllergyIntolerance`: Substance, clinicalStatus, verificationStatus, criticality.
- `Encounter`: Consultation visit metadata, period, participants.
- `MedicationRequest`: Prescribed medications, dosageInstruction, timing, intent.
- `DiagnosticReport`: AI clinical assessment summaries, status, conclusion.
- `Provenance`: Audit records tracking the authoring doctor, creation timestamps, and software system signature.
