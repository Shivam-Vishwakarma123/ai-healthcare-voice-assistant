# CareVoice — AI Assistant API Reference

All AI Assistant endpoints are mounted under `/api/v1/assistant`.

---

## 1. System & Health Endpoints

### `GET /api/v1/assistant/health`
Checks and reports both application and AI provider health independently.

- **Access:** Public (no authentication required)
- **Status Codes:**
  - `200 OK`: Successful health query (status may be `healthy` or `degraded`)
- **Response Schema:**
  ```json
  {
    "status": "healthy",
    "app_healthy": true,
    "database_connected": true,
    "rag_documents_count": 10,
    "ai_provider": {
      "provider": "ollama",
      "model": "llama3.2:1b-instruct-q4_K_M",
      "is_local": true,
      "configured": true,
      "base_url": "http://ollama:11434/v1"
    },
    "embedding_provider": {
      "provider": "hash",
      "model": "text-embedding-3-small",
      "rag_enabled": true
    }
  }
  ```

---

### `GET /api/v1/assistant/knowledge/status`
Returns administrative statistics on ingested RAG documents and vector chunks.

- **Access:** Authenticated (`platform_admin`, `hospital_admin`, or `hospital_staff`)
- **Status Codes:**
  - `200 OK`: Status retrieved successfully
  - `401 Unauthorized`: Not authenticated
  - `403 Forbidden`: Patient account attempted access
- **Response Schema:**
  ```json
  {
    "total_documents": 10,
    "total_chunks": 10,
    "approved_hosts": [
      "who.int",
      "medlineplus.gov",
      "nih.gov",
      "mohfw.gov.in",
      "nhs.uk",
      "cdc.gov"
    ],
    "embedding_provider": "hash",
    "embedding_model": "text-embedding-3-small",
    "documents": [
      {
        "id": 1,
        "title": "Clinical Triage and Red Flag Guidance",
        "source_url": "https://www.who.int/news-room/fact-sheets/detail/emergency-care-systems",
        "version": "1.0",
        "licence": "Open Access (WHO)",
        "provenance": "World Health Organization",
        "category": "public_health",
        "retrieval_date": "2026-10-22T10:00:00+00:00"
      }
    ]
  }
  ```

---

## 2. Clinical Triage & Consultation Endpoints

### `POST /api/v1/assistant/triage`
Evaluates symptoms deterministically against clinical red flags across English, Hindi, and Hinglish.

- **Access:** Public (available for anonymous pre-registration triage)
- **Request Schema:**
  ```json
  {
    "text": "Mujhe seene me bahut tez dard ho raha hai",
    "age_band": "adult",
    "pregnancy": false,
    "chronic_condition": false
  }
  ```
- **Response Schema (`TriageResponse`):**
  ```json
  {
    "urgency": "emergency",
    "category": "emergency",
    "summary": "The reported symptoms meet emergency red-flag criteria and require immediate medical attention.",
    "guidance": "Call 112 for emergency assistance and 108 for ambulance support. Go to the nearest emergency-capable hospital or urgent care center without delay.",
    "emergency_numbers": ["112", "108"],
    "flags": ["chest_pain"],
    "is_medical_guidance_only": true,
    "safety_block": false,
    "urgency_level": "emergency",
    "reported_symptoms": ["red_flag_chest_pain"],
    "follow_up_questions": [],
    "possible_explanations": ["Acute emergency medical condition requiring immediate in-person hospital evaluation."],
    "recommended_next_steps": [
      "Call 112 (National Emergency Helpline) or 108 (Ambulance) right now.",
      "Proceed immediately to the nearest hospital emergency department."
    ],
    "emergency_warning": "CRITICAL EMERGENCY: Red-flag symptoms detected. Immediate emergency care is required.",
    "uncertainty_note": null,
    "disclaimer": "CareVoice provides health education and navigation assistance only. It does not provide a definitive medical diagnosis or replace consultation with a qualified clinician.",
    "specialty_hint": "General Medicine",
    "recommended_doctors": []
  }
  ```

---

### `POST /api/v1/assistant/chat`
Conversational healthcare consultation endpoint with evidence retrieval and clinician matching.

- **Access:** Authenticated (Bearer JWT Token)
- **Request Schema:**
  ```json
  {
    "messages": [
      {
        "role": "user",
        "content": "I have had a mild persistent headache since yesterday morning"
      }
    ],
    "conversation_id": null,
    "consent_to_store": true
  }
  ```
- **Response Schema (`ChatResponse`):**
  ```json
  {
    "reply": "A mild headache can have various common causes such as tension, dehydration, or eye strain. Ensure adequate hydration, rest in a quiet environment, and monitor your symptoms.",
    "citations": [
      {
        "title": "Headache and Migraine Clinical Guidelines",
        "source_url": "https://medlineplus.gov/headache.html",
        "citation": "MedlinePlus Headache Guidance (v1.0)",
        "licence": "Public Domain",
        "allowed_use": "Public health education",
        "provenance": "NIH MedlinePlus",
        "publication_date": "2024-01-01T00:00:00Z",
        "updated_at": "2024-06-01T00:00:00Z",
        "retrieval_date": "2026-10-22T10:00:00Z",
        "version": "1.0"
      }
    ],
    "evidence_available": true,
    "source_conflict": false,
    "conversation_id": 12,
    "urgency": "routine",
    "recommended_doctors": [
      {
        "doctor_id": 7,
        "doctor_name": "Dr. Riya Sample",
        "specialty": "Neurology",
        "hospital_name": "DEMO - Cedar Valley Care Hospital",
        "score": 1.0,
        "match_reasons": ["Specialty matches: Neurology"],
        "fee_minor": 90000,
        "available_slots": [],
        "schedules": [],
        "availability_note": "Verified clinician in CareVoice directory."
      }
    ]
  }
  ```

---

## 3. Structured Assessment Endpoints

### `GET /api/v1/assistant/assessments`
Lists stored clinical assessments for the authenticated patient where consent was granted.

- **Access:** Authenticated (Owner-scoped)
- **Response Schema:** Array of `AssessmentSummary`
  ```json
  [
    {
      "assessment_id": "b7c2a1e0-4f5a-4b11-9a8e-289f6d4d1234",
      "id": 12,
      "title": "Persistent headache",
      "urgency_level": "routine",
      "category": "advice",
      "created_at": "2026-10-22T10:30:00Z",
      "updated_at": "2026-10-22T10:30:15Z",
      "message_count": 2
    }
  ]
  ```

---

### `GET /api/v1/assistant/assessments/{assessment_id}`
Retrieves full structured clinical assessment details by UUID or integer ID.

- **Access:** Authenticated (Strictly owner-scoped; returns 404 if accessed by another user)
- **Response Schema (`AssessmentResponse`):**
  ```json
  {
    "assessment_id": "b7c2a1e0-4f5a-4b11-9a8e-289f6d4d1234",
    "language": "en",
    "symptom_summary": "Persistent headache",
    "follow_up_questions": [
      "How many days have you experienced these symptoms?",
      "Have you noticed any other symptoms such as chills, body aches, or nausea?"
    ],
    "red_flags": [],
    "triage_level": "routine",
    "recommended_next_steps": [
      "Rest, ensure adequate oral fluid intake, and monitor your symptoms.",
      "Schedule an appointment with a general practitioner if symptoms persist for more than 48-72 hours."
    ],
    "care_urgency": "routine",
    "possible_explanations": [
      "Common self-limiting conditions (such as tension headache or dehydration)."
    ],
    "evidence_sources": [
      {
        "title": "Headache Guidance",
        "source_url": "https://medlineplus.gov/headache.html",
        "citation": "MedlinePlus (v1.0)",
        "licence": "Public Domain",
        "allowed_use": "Public health",
        "provenance": "NIH MedlinePlus",
        "publication_date": null,
        "updated_at": null,
        "retrieval_date": "2026-10-22T10:00:00Z",
        "version": "1.0"
      }
    ],
    "uncertainty_notes": "Assessment is preliminary and educational; diagnosis requires in-person medical evaluation.",
    "disclaimer": "CareVoice provides health education and navigation assistance only. It does not provide a definitive medical diagnosis or replace consultation with a qualified clinician.",
    "model_metadata": {
      "provider": "ollama",
      "model": "llama3.2:1b-instruct-q4_K_M",
      "version": "1.0.0"
    },
    "created_at": "2026-10-22T10:30:00Z"
  }
  ```

---

## 4. Conversation Lifecycle Endpoints

| Endpoint | Method | Access | Description |
|---|---|---|---|
| `/api/v1/assistant/conversations` | `GET` | Signed in | List all saved consultation transcripts for the patient |
| `/api/v1/assistant/conversations` | `POST` | Signed in | Initialize consultation with explicit consent (`consent_given: true`) |
| `/api/v1/assistant/conversations/{id}` | `GET` | Signed in | Retrieve full conversation messages and structured records |
| `/api/v1/assistant/conversations/{id}` | `DELETE` | Signed in | Delete a single consultation session and its messages |
| `/api/v1/assistant/conversations` | `DELETE` | Signed in | Clear all consultation history for the authenticated patient |

---

## 5. RAG Retrieval & Speech Endpoints

### `POST /api/v1/assistant/rag/search`
Queries the PostgreSQL public-health knowledge base with lexical and cosine vector matching.
- **Request:** `{"query": "fever and dehydration in children", "category": "public_health"}`
- **Response:** Array of matched documents with citation, snippet, and relevance score.

### `POST /api/v1/assistant/speech-to-text`
Accepts multipart audio (`audio/webm`, `audio/wav`) and returns transcribed text with language metadata.
- **Response:** `{"transcript": "...", "language": "en", "provider": "browser/hosted", "requires_confirmation": true}`
- **Safety Policy:** All transcripts require user review before transmission to the chat endpoint.

---

## 6. Longitudinal Records & Clinical Workflow Endpoints (`/api/v1/records`)

### 6.1 Timeline & Overview
- `GET /api/v1/records/timeline?patient_user_id={id}`
  - Chronological timeline combining encounters, triage sessions, notes, prescriptions, and reports.
  - Scoping: Patient can view own records. Doctors can view assigned patients.
- `GET /api/v1/records/overview?patient_user_id={id}`
  - High-level demographic, allergy, and active medication summary for a patient.

### 6.2 Doctor Clinical Workspace
- `GET /api/v1/records/doctor/workspace`
  - Access: Doctors only.
  - Returns: Assigned patient roster with visit dates, active allergies, pending AI triage assessments, and today's appointment schedule.

### 6.3 Clinical Notes Lifecycle
- `POST /api/v1/records/notes/ai-draft`
  - Synthesizes encounter context and pre-consultation triage into a draft note.
- `POST /api/v1/records/notes`
  - Creates a new consultation or progress note (`draft` status).
- `GET /api/v1/records/notes?patient_user_id={id}`
  - Retrieves clinical notes. Draft notes are hidden from patients until finalized.
- `POST /api/v1/records/notes/{id}/finalize`
  - Electronically signs and finalizes a note, making it immutable.

### 6.4 Digital Prescriptions & Allergy Safety
- `POST /api/v1/records/prescriptions/ai-draft`
  - Generates supportive prescription items with automated drug-allergy pre-screening.
- `POST /api/v1/records/prescriptions`
  - Creates a prescription with medication items, dosage instructions, and allergy checks.
- `GET /api/v1/records/prescriptions?patient_user_id={id}`
  - Lists prescriptions for a patient.
- `POST /api/v1/records/prescriptions/{id}/finalize`
  - Finalizes prescription with doctor timestamp and signature.
- `GET /api/v1/records/prescriptions/{id}/pdf`
  - Streams high-fidelity, printable prescription PDF generated via ReportLab.

### 6.5 Medical Assessment Reports & PDF
- `POST /api/v1/records/reports/generate`
  - Creates structured AI clinical assessment report from triage conversation.
- `GET /api/v1/records/reports/{report_id}/pdf`
  - Streams clinical assessment summary PDF with citations and emergency guidance.
- `POST /api/v1/records/reports/{report_id}/review`
  - Marks an AI triage assessment as reviewed by the attending doctor.

### 6.6 HL7 FHIR Interoperability
- `GET /api/v1/records/fhir/export?patient_user_id={id}`
  - Generates and exports an HL7 FHIR Release 4 standard JSON Bundle containing `Patient`, `AllergyIntolerance`, `Encounter`, `MedicationRequest`, `DiagnosticReport`, and `Provenance` resources.

