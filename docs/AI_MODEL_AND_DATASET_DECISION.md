# CareVoice — AI Model & Dataset Architectural Decision

This document details the architectural evaluation, comparative trade-offs, and final selection of AI models and evidence datasets for the CareVoice AI Healthcare Platform.

---

## 1. Model Selection Criteria & Decision Matrix

To ensure patient safety, low latency, and regulatory compliance, CareVoice evaluates models across ten standardized dimensions:

1. **Clinical Correctness & Evidence-Grounded Reasoning:** Ability to synthesize medical facts accurately without confabulation.
2. **Safety, Refusal, and Uncertainty Calibration:** Rigorous compliance with emergency disclaimers, refusal to prescribe drugs, and clear disclosure of evidence limitations.
3. **Structured JSON Output:** Deterministic JSON schema enforcement without invalid escape characters or markdown fences.
4. **Retrieval & Context Utilization:** Effective comprehension of multi-paragraph clinical guidelines passed via RAG context.
5. **Multilingual & Code-Mixed Support:** Understanding English, Devanagari Hindi, and transliterated Hinglish.
6. **Inference Latency & Context Window:** Real-time conversational responsiveness (< 2.5s time-to-first-token for voice).
7. **Operational Cost & Availability:** Cost per token, free-tier or open-weight accessibility.
8. **Privacy & Data Retention:** Zero-day retention guarantees; no model training on transmitted patient data.
9. **Hardware Footprint & Edge Deployment:** Ability to execute locally on CPU-only machines in resource-constrained clinics.
10. **Licensing & Commercial Reuse:** Permissive software licenses allowing healthcare and clinical deployment.

---

## 2. Comparative Model Evaluation

| Model | Deployment Type | Structured JSON | Emergency Safety | Hinglish Comprehension | Memory / Hardware | License / Privacy | Selection Verdict |
|---|---|---|---|---|---|---|---|
| **GPT-6-Astra** | Hosted (OpenAI-compatible) | **Excellent** (Native JSON schema) | **High** (Low variance at temp 0.2) | **Excellent** (Native Hindi & Hinglish) | Cloud API (0 local RAM) | Standard Commercial API (Zero-data retention available) | **Primary Hosted Default** |
| **Llama 3.2 1B Instruct (q4_K_M)** | Local Open-Weight (Ollama) | **Good** (Schema with markdown fallback) | **High** (With deterministic preemption) | **Moderate** (Good on common Hinglish) | **1.3 GB RAM** (Runs on CPU laptop) | Llama 3.2 Community License (Permissive) | **Primary Local Default** |
| **GPT-6-Luna** | Hosted (Provisional) | **Good** | **High** | **Good** | Cloud API | Commercial API | Evaluated candidate; Astra preferred for latency |
| **Mistral 7B Instruct v0.3** | Local Open-Weight | **Good** | **Moderate** | **Moderate** | **5.5 GB RAM** (Requires GPU or 16GB RAM) | Apache 2.0 | Excluded: Exceeds resource limit for local Docker |
| **Phi-3 Mini 3.8B** | Local Open-Weight | **Moderate** (Occasional parse error) | **Moderate** | **Poor** on Hinglish code-mixing | **2.8 GB RAM** | MIT | Excluded: Weaker code-mixed Indic support |

### Rationale for Selected Models:

1. **Primary Hosted Candidate: `gpt-6-astra`**
   - Configured via `AI_PROVIDER=openai_compatible` and `AI_MODEL=gpt-6-astra` (with backward-compatible `LLM_*` variables).
   - Demonstrates superior clinical instruction-following, strict JSON schema compliance, low latency, and robust code-mixed Hinglish interpretation.
   - Operates with bounded timeouts (15s), max tokens (1,000), and temperature 0.2 for deterministic, low-variance generation.

2. **Primary Local Open-Weight Candidate: `llama3.2:1b-instruct-q4_K_M`**
   - Packaged and pre-configured via the local `ollama` Docker Compose service.
   - Compact quantized footprint (~1.3 GB) allows the entire CareVoice stack (PostgreSQL, FastAPI backend, React frontend, Ollama) to run simultaneously on standard developer workstations or local hospital servers without dedicated GPUs.
   - Operates 100% offline with zero external network dependencies, ensuring complete patient data privacy and zero API costs.

---

## 3. Dataset Selection & Provenance Registry

CareVoice enforces strict segregation between datasets used for **Retrieval (RAG)**, datasets used for **Evaluation**, and clinical datasets excluded due to legal or ethical constraints.

### A. RAG Knowledge Corpus (Integrated in `backend/data/knowledge/`)

| Dataset / Source | Source Authority | Content Scope | License | Implementation in CareVoice |
|---|---|---|---|---|
| **NIH MedQuAD** | National Institutes of Health (NIH) | 47,457 medical question-answer pairs curated from 12 NIH institutes | Public Domain (U.S. Govt Work) | Curated clinical answers for cardiology, pulmonology, diabetes |
| **MedlinePlus** | U.S. National Library of Medicine | Consumer health guidance on symptoms, diseases, medications | Public Domain / Open Access | Pediatric fever, dehydration, stroke FAST protocols |
| **WHO Guidelines** | World Health Organization | Global clinical management for infectious diseases (dengue, respiratory) | Creative Commons BY-NC-SA 3.0 IGO | Vector-borne diseases, maternal warning signs |
| **MOHFW National Guidelines** | Ministry of Health & Family Welfare, India | Indian national clinical protocols, emergency helpline standards (112, 108, Tele-MANAS) | Government Open Data Licence - India (GODL) | Emergency routing, stroke, hypertension, mental health |

*Ingestion Command:* `docker compose exec backend python -m app.cli ingest-knowledge`

---

### B. Benchmark & Research Datasets Evaluated

#### 1. PubMedQA (Biomedical Question Answering)
- **Official Source:** [pubmedqa.github.io](https://pubmedqa.github.io/)
- **Task Fit:** Evaluates whether biomedical questions can be answered with `yes`, `no`, or `maybe` based on PubMed abstracts.
- **Licence:** MIT License.
- **Analysis:** Highly valuable for evaluating biomedical reasoning and citation-constrained extraction. However, PubMedQA questions reflect academic research queries (e.g., drug trial outcomes) rather than direct patient symptom triage.
- **CareVoice Use:** Used as an evaluation reference for factual reasoning, but not for direct patient conversational dialogue.

#### 2. MedQA (USMLE Multiple Choice) & MedMCQA (AIIMS/NEET-PG)
- **Official Sources:** Jin et al. (2021) / Pal et al. (2022).
- **Task Fit:** 4-option and 5-option medical licensing examination questions.
- **Licence:** Open research / non-commercial.
- **Analysis:** Exam-based datasets measure academic memorization of rare pathology and biochemical mechanisms. High MedQA scores do NOT correlate with safe patient communication, empathy, or triage red-flag detection.
- **CareVoice Use:** Consulted for research baselines; excluded from real-time patient routing to prevent over-diagnosis.

#### 3. MIMIC-IV Clinical Database
- **Official Source:** [mimic.mit.edu](https://mimic.mit.edu/docs/) (Johnson et al., PhysioNet).
- **Task Fit:** De-identified Electronic Health Records (EHR) from Beth Israel Deaconess Medical Center.
- **Licence:** Restricted Data Use Agreement (DUA) requiring human CITI training certification.
- **Analysis:** Strict legal constraints prohibit uploading MIMIC-IV records to third-party commercial LLM APIs, and forbid redistribution in open-source educational repositories.
- **CareVoice Decision:** **Strictly Excluded** from runtime and repository files to guarantee ethical compliance. Synthetic clinical records are used instead.

---

### C. Synthetic Safety Evaluation Dataset (`backend/tests/ai/`)

CareVoice incorporates a versioned, clearly labeled synthetic clinical evaluation suite:

- **Emergency Red Flags (20 cases):** Cardiac (crushing pain, pressure), stroke FAST (facial drooping, arm weakness, slurred speech), respiratory distress (gasping, cyanosis), uncontrolled hemorrhage, pediatric lethargy, maternal heavy bleeding, and psychiatric crisis across English, Hindi, and Hinglish.
- **Routine Symptoms (4 cases):** Mild self-limiting symptoms (scratchy throat, minor rash, transient headache).
- **Adversarial & Injection Attacks (6 cases):** System prompt overrides, developer bypasses, prescription requests, drug dosage requests.
- **Vague / Insufficient Symptoms (5 cases):** Single-word inputs ("pain", "help", "dard") requiring triage clarification.

*Evaluation Execution:* `docker compose exec backend python scripts/evaluate_ai_platform.py`
