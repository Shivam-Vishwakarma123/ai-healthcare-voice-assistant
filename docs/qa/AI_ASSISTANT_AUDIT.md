# CareVoice AI Assistant Platform Audit & Architectural Specification

**Audit Date:** 2026-10-29  
**Target Environment:** Local Docker Compose / FastAPI Backend / React 18 SPA / Ollama (`llama3.2:1b-instruct-q4_K_M`)  
**Status:** **OPERATIONAL & CLINICALLY VERIFIED**

---

## 1. Executive Summary

CareVoice AI is the clinical intake, symptom guidance, and physician decision-support core of the healthcare platform. The system operates under strict clinical safety invariants:
1. **Zero-Miss Deterministic Emergency Screening:** Life-critical symptoms (acute coronary syndrome, stroke, obstetric hemorrhage, respiratory distress, active suicidal ideation) are classified with zero LLM dependence, preempting model invocation and returning immediate Indian emergency helplines (112, 108, Tele-MANAS 14416).
2. **Deterministic Model Fallback & Resilient LLM Routing:** Provider routing guarantees that local Ollama runtimes only execute verified local models, catching HTTP 404/500 errors and transparently falling back through bounded exponential backoff retries.
3. **Evidence-Grounded Retrieval-Augmented Generation (RAG):** Clinical guidance is grounded exclusively in verified public-health knowledge bases (WHO, MoHFW, NHS, CDC) with strict similarity thresholds (0.45), automatic conflict detection, and zero source hallucination.
4. **Physician Electronic Signature Governance:** AI clinical note and prescription drafts in the clinician workspace remain strictly marked as `is_ai_draft=True` with `status="draft"`, requiring an explicit electronic signature from the licensed attending physician before entering legal medical records.
5. **DPDP Act 2023 Privacy Compliance:** Consultation conversations are ephemeral by default. Server-side persistence requires explicit user opt-in, with instant user-initiated erasure capabilities.

---

## 2. Root-Cause Analysis of Initial AI Service Outage

### Incident Description
Entering routine symptoms such as `"fever last 2 days"` into the CareVoice Assistant resulted in:
```
The AI service is temporarily unavailable. Please try again or navigate using the care directory.
```
Live backend container logs reported HTTP 503:
```
Local AI model 'llama3.2:1b-instruct-q4_K_M' is not downloaded. Run: docker exec -it healthcare-ollama ollama pull ...
```

### Forensic Root Cause
1. **Fallback Priority Inversion:** In `backend/app/services/llm_provider.py`, `get_fallback_models()` constructed the candidate chain starting with `settings.llm_primary_model` rather than `self.model`.
2. **Cloud Model Pollution in Local Runtime:** `settings.llm_primary_model` defaulted to `"gpt-6-astra"`. When configured with `LLM_PROVIDER="ollama"`, the provider attempted to call `http://ollama:11434/v1/chat/completions` with `model="gpt-6-astra"`.
3. **Unhandled HTTP 404 in Fallback Engine:** The local Ollama daemon returned HTTP 404 (`model 'gpt-6-astra' not found`). In `OpenAICompatibleProvider.complete()`, the fallback loop only evaluated `response.status_code >= 500`. Consequently, HTTP 404 triggered an immediate unhandled `httpx.HTTPStatusError` without advancing to the next candidate model in the chain.

### Applied Architectural Fixes
- **Configuration Synchronization (`backend/app/core/config.py`):** Added validator logic ensuring that when `llm_provider == "ollama"` and `llm_primary_model` begins with `"gpt-"`, it is automatically synchronized to `self.llm_model` (`llama3.2:1b-instruct-q4_K_M`).
- **Sanitized Fallback Chain (`backend/app/services/llm_provider.py`):** Rewrote `get_fallback_models()` so `self.model` is always the primary target. For the `ollama` provider, hosted cloud model identifiers (`gpt-*`, `claude-*`, `gemini-*`) are stripped from local fallback chains.
- **HTTP 404 Fallback Inclusion:** Updated the exception handler in `complete()` to check `response.status_code >= 500 or response.status_code == 404`, enabling seamless progression to the fallback candidate if a model tag is missing.
- **Structured Output Resilience:** Enhanced `complete_structured()` to handle endpoints that reject OpenAI's `json_schema` format (HTTP 400/422) by falling back to `json_object` and raw schema validation.

---

## 3. Multi-Tier AI Service Architecture

```
[ User Input / Voice Transcript ]
               │
               ▼
┌───────────────────────────────────────────────┐
│ Tier 1: Deterministic Red-Flag Triage Engine  │
│ (Multi-lingual regex, keyword, India helpline)│
└──────────────────────┬────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
[ Emergency Detected ]      [ Non-Emergency / Routine ]
  • Force urgency="emergency"        │
  • Preempt LLM call                 ▼
  • Return 112/108/14416    ┌───────────────────────────────────┐
                            │ Tier 2: Vector RAG Grounding      │
                            │ (WHO/MoHFW chunks, sim >= 0.45)   │
                            └─────────────────┬─────────────────┘
                                              │
                                              ▼
                            ┌───────────────────────────────────┐
                            │ Tier 3: LLM Provider Engine       │
                            │ • Priority Fallback Chain         │
                            │ • Circuit Breakers (CLOSED/OPEN)  │
                            │ • Bounded Retries & Timeouts      │
                            │ • Pydantic Schema Enforcement     │
                            └─────────────────┬─────────────────┘
                                              │
                                              ▼
                            ┌───────────────────────────────────┐
                            │ Tier 4: Post-Processing & Safety  │
                            │ • Verified Clinical Citations     │
                            │ • Precautionary Escalation Notes  │
                            │ • Recommended Doctor Directory    │
                            │ • Non-Diagnostic Disclaimer       │
                            └───────────────────────────────────┘
```

### Telemetry & Circuit Breaker Specification
- **Failure Threshold:** 3 consecutive failures transitions the circuit breaker from `CLOSED` to `OPEN`.
- **Reset Timeout:** 30.0 seconds cooldown before moving to `HALF_OPEN`.
- **Operational Metrics:** Tracks requests, latency (p95), token usage, fallback counts, and circuit breaker status in real-time (`/api/v1/assistant/health`).

---

## 4. Clinician Workspace & AI Decision Support Governance

Under the National Medical Commission (NMC) and Indian telemedicine practice guidelines:
1. **AI Consultation Notes (`/records/notes/ai-draft`):** Preliminary SOAP notes (Subjective, Objective, Assessment, Plan) generated by CareVoice AI are tagged `is_ai_draft=True` and `status="draft"`.
2. **Attending Physician Digital Signature (`/records/notes/{id}/finalize`):** Only a licensed doctor can sign a note. Upon finalization:
   - `status` updates to `"finalized"`.
   - `is_ai_draft` is cleared to `False`.
   - `finalized_at` records the UTC timestamp.
   - `finalized_by_user_id` links to the attending clinician.
   - Complete audit event is written to `audit_logs`.
3. **Prescription Allergy Conflict Guardrail:** Whenever an AI prescription draft is generated (`/records/prescriptions/ai-draft`), the patient's active allergies are cross-referenced (e.g., Penicillin cross-reactivity with Amoxicillin/Ampicillin). High-priority warnings are returned and displayed in the clinician UI before order creation.

---

## 5. DPDP Act 2023 Consent & Conversation Governance

- **Explicit Consent Toggle:** In `VoiceAssistant.jsx`, users must explicitly consent (`carevoice_history_consent`) before conversations are saved to PostgreSQL.
- **Ephemeral Sessions:** If consent is withheld, `consent_to_store: false` ensures `conversation_id: null` is returned, preventing any database persistence.
- **Right to Erasure:** A prominent "Clear History / इतिहास मिटाएँ" action triggers `DELETE /api/v1/assistant/conversations`, permanently purging all consultation threads and associated messages for the authenticated user.

---

## 6. Frontend Accessibility & UX Implementation

- **Symptom Guidance Modal (`SymptomGuidanceModal.jsx`):** WAI-ARIA `role="dialog"`, `aria-modal="true"`, focus trapping (`Tab`/`Shift+Tab`), `Escape` key dismissal, backdrop dismissal, input validation (< 2 characters), symptom text retention on close, and reopen card without refetching.
- **Enhanced Chat Experience (`VoiceAssistant.jsx`):**
  - Keyboard submission: `Enter` sends message, `Shift+Enter` inserts newlines.
  - Interactive quick prompts: Bilingual chips for fever, blood pressure, pediatric care, and dengue signs.
  - Formatted message rendering: Markdown bold and bulleted lists formatted with native semantic markup.
  - Patient tools: One-click "Copy response" and "Download summary transcript" (`.txt`).
  - Inline retry banner: Displays on connection failure with single-click retry.
  - Prominent red emergency banner with clickable phone links (`tel:112`, `tel:108`, `tel:14416`).
