# CareVoice — AI Safety, Clinical Governance & Limitations

## 1. Clinical Limitations & Intended Use Policy

CareVoice is an assistive healthcare technology platform engineered to facilitate patient pre-consultation triage, structured medical history collection, and clinician encounter documentation. It is designed and deployed under strict regulatory boundaries:

1. **Non-Diagnostic Intended Use**:
   - The conversational AI assistant does **not** provide definitive clinical diagnoses, prescribe prescription-only pharmaceuticals, or replace licensed physician judgment.
   - All AI-generated outputs (symptom classifications, differential summaries, supportive care guidance) are labeled explicitly as educational assessments subject to clinician verification.

2. **No Emergency Substitution**:
   - CareVoice is **never** an emergency response system.
   - Any acute clinical symptoms (crushing chest pain, severe dyspnea, acute neurological deficits, uncontrollable hemorrhage, self-harm crisis) trigger immediate deterministic overrides directing users to national emergency helplines:
     - **General Emergency**: `112`
     - **Ambulance Services**: `108`
     - **Mental Health & Suicide Prevention**: `Tele-MANAS (14416)`

3. **Clinician Primacy in Prescribing & Note Finalization**:
   - AI draft notes and AI draft prescriptions are suggestions only (`is_ai_draft = True`).
   - Patients cannot view draft notes or draft prescriptions until the authorized attending doctor reviews, amends, signs, and finalizes them (`status = "finalized"`).

---

## 2. Drug-Allergy Safety & Prescribing Precautions

When doctors utilize the CareVoice Prescription Builder, the system automatically runs the `check_medication_allergy_conflicts` safety filter against the patient's recorded allergies and cross-reactivity classes:

| Drug Class | Prescribed Example | Known Cross-Reactive Substances | Clinical Action |
| :--- | :--- | :--- | :--- |
| **Penicillins** | Amoxicillin, Ampicillin, Augmentin | Penicillin, Cephalosporins | Block / Warn clinician of anaphylaxis risk |
| **Cephalosporins** | Cephalexin, Cefuroxime, Ceftriaxone | Penicillin (cross-reactive in ~5-10%) | Highlight cross-reactivity warning |
| **NSAIDs** | Ibuprofen, Aspirin, Naproxen, Diclofenac | Aspirin-exacerbated respiratory disease (AERD) | Alert bronchospasm & GI bleed risk |
| **Sulfonamides** | Sulfamethoxazole-Trimethoprim | Sulfa antibiotics, sulfonylureas | Flag Stevens-Johnson / DRESS risk |
| **Fluoroquinolones** | Ciprofloxacin, Levofloxacin | Tendinitis / QT prolongation history | Display black-box advisory |

---

## 3. Adversarial Robustness & Jailbreak Defenses

CareVoice employs multi-layer defenses against adversarial prompt injection, DAN-style overrides, and malicious instruction hijacking:

1. **Input Sanitization**:
   - Strips malicious control tokens, excessive whitespace, and SQL/XSS payloads.
   - Detects prompt-injection tokens (`"ignore previous instructions"`, `"system override"`, `"roleplay as unfiltered AI"`, `"developer mode"`).

2. **Deterministic Emergency Bypass**:
   - Preempts LLM evaluation completely when acute symptom keywords appear. Because this is executed in Python code prior to LLM invocation, prompt injection cannot circumvent emergency triage.

3. **Output Schema Enforcement**:
   - All LLM responses must strictly adhere to the defined Pydantic JSON schema (`AssistantResponseContent`). Unstructured, malicious, or off-topic outputs are rejected with automatic fallback to structured educational summaries.

4. **Citation Binding & Grounding**:
   - The assistant is prohibited from rendering citations from unverified hosts. Every URL must belong to `RAG_APPROVED_SOURCE_HOSTS` (`who.int`, `nih.gov`, `medlineplus.gov`, `mohfw.gov.in`, `nhs.uk`, `cdc.gov`).

---

## 4. Privacy, HIPAA, and Indian DPDP Act Compliance

1. **Digital Personal Data Protection (DPDP) Act (India)**:
   - **Explicit Purpose-Limitation**: Patient consultations require opt-in consent (`consent_given = True`).
   - **Right to Erasure**: Patients can delete individual consultation sessions or completely purge all historical consultation transcripts (`DELETE /api/v1/assistant/conversations`).

2. **Data Isolation**:
   - Cross-patient queries are blocked at the database query level (`where(user_id == current_user.id)`).
   - Clinician access is restricted to patients with valid appointment relationships (`_check_doctor_or_patient_access`).

3. **Audit Trail**:
   - All prescription modifications, note amendments, and medical report reviews record authenticated user IDs and ISO-8601 UTC timestamps.
