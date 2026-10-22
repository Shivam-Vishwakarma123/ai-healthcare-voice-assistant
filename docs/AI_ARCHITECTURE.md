# CareVoice — AI-First Healthcare Platform Architecture

This document specifies the end-to-end software and AI architecture of CareVoice, detailing the data flow, safety guardrails, retrieval-augmented generation (RAG) pipeline, and clinical decision workflows.

---

## 1. System Topology & Container Architecture

CareVoice is implemented as a production-ready **Modular Monolith** orchestrated via Docker Compose:

```text
[ Browser / Patient Client ]
       |
       | HTTPS / WebSocket (Audio & REST)
       v
+--------------------------------------------------------------------------+
|  FRONTEND CONTAINER (React 18 / Vite / Tailwind)                         |
|  - Web Speech API Audio Capture & Preview Review                         |
|  - Text-to-Speech (TTS) SpeechSynthesis Engine                           |
|  - Responsive Clinical Urgency Badges & Doctor Cards                     |
|  - Consent Toggle & Consultation History Drawer                          |
+--------------------------------------------------------------------------+
       |
       | REST JSON API (Port 8000 /api/v1)
       v
+--------------------------------------------------------------------------+
|  BACKEND CONTAINER (FastAPI / Python 3.12 / Pydantic v2)                 |
|  +--------------------------------------------------------------------+  |
|  | 1. Input Sanitization & Jailbreak Filter                           |  |
|  +--------------------------------------------------------------------+  |
|  | 2. Deterministic Clinical Triage Preemption Engine                  |  |
|  |    (Bypasses AI if acute red-flags in EN, HI, or Hinglish)          |  |
|  +--------------------------------------------------------------------+  |
|  | 3. Evidence-Grounded RAG Pipeline (PostgreSQL Vector Retrieval)     |  |
|  +--------------------------------------------------------------------+  |
|  | 4. Configurable LLM Provider Interface                            |  |
|  |    - Hosted: gpt-6-astra (OpenAI-Compatible REST API)              |  |
|  |    - Local: llama3.2:1b-instruct-q4_K_M (Ollama REST API)          |  |
|  +--------------------------------------------------------------------+  |
|  | 5. Output Safety Post-Filter & Citation Validator                  |  |
|  +--------------------------------------------------------------------+  |
|  | 6. Verified Doctor Recommendation Engine                           |  |
|  +--------------------------------------------------------------------+  |
|  | 7. Patient Consent Gating & Isolation Persistence Layer           |  |
|  +--------------------------------------------------------------------+  |
+--------------------------------------------------------------------------+
       |                                     |
       | SQL Queries / Cosine Search         | HTTP Inference
       v                                     v
+-----------------------------+       +-----------------------------+
|  POSTGRESQL CONTAINER       |       |  OLLAMA CONTAINER (Local)   |
|  - Users & Patients         |       |  - llama3.2:1b-instruct     |
|  - Verified Doctors         |       |  - Port 11434               |
|  - Knowledge Documents      |       +-----------------------------+
|  - Knowledge Chunks         |
|  - Assistant Conversations  |
|  - Assistant Messages       |
+-----------------------------+
```

---

## 2. Complete Request-to-Response Lifecycle

Every user consultation follows an uncompromising, multi-tiered clinical safety sequence:

```text
User Input (Audio / Text)
  │
  ▼
[1] Client-Side Web Speech Transcription
  │ (User reviews and confirms transcript before sending)
  ▼
[2] API Transport: POST /api/v1/assistant/chat
  │ (Transmits messages, conversation_id, and explicit consent_to_store)
  ▼
[3] Input Sanitization & Injection Defense
  │ (Blocks instruction override, system prompts, prompt injections)
  ▼
[4] Deterministic Clinical Triage Engine (CRITICAL SAFETY GATE)
  ├─────────────────────────────────────────┐
  │ Life-Threatening Red Flag Detected?     │ No Acute Red Flags
  ▼ (Cardiac, Stroke, Breathing, Tele-MANAS)│
[EMERGENCY PREEMPTION]                      ▼
  │ Immediately generates emergency advice [5] Prescription / Dosage Guard
  │ Routes to 112, 108, or 14416            │ (Blocks requests for personal
  │ BYPASSES LLM & RAG ENTIRELY             │  dosages or prescription drugs)
  │ (< 1ms execution time)                  ▼
  │                                        [6] Approved Public Health RAG Retrieval
  │                                         │ (Queries PostgreSQL Knowledge Chunks
  │                                         │  for top semantic matches from WHO/NIH)
  │                                         ▼
  │                                        [7] Multi-Source Conflict Detection
  │                                         │ (Flags contradictory urgent-care guidance)
  │                                         ▼
  │                                        [8] Structured LLM Completion
  │                                         │ (gpt-6-astra or llama3.2:1b at temp 0.2
  │                                         │  with JSON schema validation & fence strip)
  │                                         ▼
  │                                        [9] Safety Post-Filter & Citation Binding
  │                                         │ (Validates URLs against approved hosts;
  │                                         │  rejects diagnostic or unsafe claims)
  │                                         ▼
  │                                       [10] Verified Doctor Matching
  │                                         │ (Matches active clinicians in database
  │                                         │  by specialty, symptoms, and fee)
  │                                         ▼
  ├─────────────────────────────────────────┘
  │
  ▼
[11] Patient Consent & Isolation Storage
  │ If consent_to_store=True:
  │   Persists transcript in AssistantConversation and AssistantMessage
  │   Scoped strictly to authenticated user_id
  │ If consent_to_store=False:
  │   Zero database retention
  ▼
[12] JSON Response Payload Returned to Frontend
  │ Rendered with Urgency Badge, Citations, Doctor Cards, and TTS Playback
```

---

## 3. Core Architectural Subsystems

### A. Deterministic Clinical Safety Triage Engine
- **Location:** `backend/app/services/triage_service.py`
- **Design Philosophy:** Probabilistic LLMs must never be the sole gatekeeper for acute clinical emergencies.
- **Red-Flag Coverage:**
  - Cardiac: Crushing chest pain, left-arm radiation, squeezing sensations across English, Hindi, and Hinglish (`\b(seene|chhati)\b.*?\bdard\b`).
  - Stroke: FAST signs (facial drooping, slurred speech, one-sided weakness).
  - Respiratory: Cyanosis, gasping, severe breathlessness (`\bsaans\b.*?\b(takleef|dikkat)\b`).
  - Severe Hemorrhage: Uncontrolled bleeding.
  - Obstetric & Pediatric: Third-trimester heavy bleeding, infant lethargy with blue lips.
  - Psychiatric Crisis: Self-harm and suicide thoughts routed immediately to **Tele-MANAS (14416)** and **Emergency 112**.

### B. Evidence-Grounded Medical RAG Pipeline
- **Location:** `backend/app/services/rag_service.py`
- **Data Store:** `knowledge_documents` and `knowledge_chunks` tables in PostgreSQL.
- **Corpus:** 10 curated clinical documents in `backend/data/knowledge/` with verified provenance from NIH MedQuAD, MedlinePlus, WHO, and Indian MOHFW.
- **Security Constraint:** Only HTTPS URLs on `RAG_APPROVED_SOURCE_HOSTS` are ingested.
- **Conflict Handling:** The system identifies opposing recommendations between sources (e.g., home rest vs. immediate urgent-care referral) and instructs the patient to seek clinical review rather than arbitrarily choosing a side.

### C. Configurable LLM Provider Interface
- **Location:** `backend/app/services/llm_provider.py` & `backend/app/core/config.py`
- **Synchronization:** Dual-mode settings synchronization allows configuration via either `AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`, `AI_BASE_URL` or legacy `LLM_*` variables.
- **Reliability:** Enforces structured JSON schema completion (`json_schema`), code-fence stripping (`parse_model_json_content`), 15-second bounded timeouts, and explicit error status propagation.

### D. Verified Doctor Recommendations
- **Location:** `backend/app/services/doctor_recommendation_service.py`
- **Database Query:** Filters strictly for verified (`verification_status="verified"`), active (`is_active=True`) doctors with active hospital associations.
- **Explainability:** Ranks clinicians based on extracted symptoms and specialty hints, returning transparent match explanations (e.g., *"Specialty matches: Cardiology"*), consultation fees in minor units (`fee_minor`), and real clinic schedules.

### E. Privacy & Cross-Patient Data Isolation
- **Location:** `backend/app/models/conversation.py` & `backend/app/routes/assistant_routes.py`
- **Consent Governance:** Patients must explicitly opt-in to consultation persistence.
- **Tenant Scoping:** Every conversation query enforces `where(AssistantConversation.user_id == current_user.id)`. Requests for foreign assessment IDs return a strict `404 Not Found` without information leakage.

### F. Longitudinal Patient Record Engine
- **Location:** `backend/app/models/clinical.py` & `backend/app/services/clinical_service.py`
- **Architecture:** Unifies triage consultations, clinical notes, prescriptions, laboratory/diagnostic documents, and allergy registers into a chronological patient timeline (`/api/v1/records/timeline`).
- **Access Scoping:** Patients can only access their own records. Doctors can only access records for patients with an active or historical clinical appointment encounter (`_check_doctor_or_patient_access`).

### G. Doctor Clinical Workspace & Prescription Authoring
- **Location:** `frontend/src/components/DoctorWorkspace.jsx` & `backend/app/routes/clinical_routes.py`
- **Encounter Documentation:** Supports AI-assisted note generation from pre-consultation triage data, physical exam findings, and clinical impressions.
- **Structured Prescribing:** Form-based medication builder with dosage form, route, frequency (`1-0-1`), duration, and patient instructions.
- **Drug-Allergy Safety Pre-Screening:** `check_medication_allergy_conflicts` compares prescribed medicines against the patient's active allergies and cross-reactivity classes (penicillin, cephalosporins, NSAIDs, sulfa drugs, fluoroquinolones, macrolides) before saving or signing.
- **Clinician Signature Lifecycle:** Notes and prescriptions remain in `draft` status (hidden from patients) until explicitly finalized and electronically signed by the attending doctor.

### H. Server-Side Clinical PDF Generation (ReportLab)
- **Location:** `backend/app/services/pdf_report_service.py`
- **Execution:** Pure Python ReportLab streaming with zero external headless browser dependencies.
- **Artifacts:**
  - Standardized Clinical Prescriptions (`/records/prescriptions/{id}/pdf`) with hospital letterhead, doctor credentials, Rx grid, allergy alerts, and verification signature.
  - Comprehensive AI Assessment Summaries (`/records/reports/{id}/pdf`) with evidence citations, urgency indicators, and emergency helpline callouts.

### I. HL7 FHIR Release 4 Interoperability
- **Location:** `backend/app/services/clinical_service.py` (`generate_fhir_r4_bundle`)
- **Standard Mapping:** Generates compliant FHIR R4 JSON Bundles (`type: "collection"`) packaging `Patient`, `AllergyIntolerance`, `Encounter`, `MedicationRequest`, `DiagnosticReport`, and `Provenance` resources for export into external hospital EHR systems.

