# CareVoice — AI Safety Framework & Evaluation Methodology

This document outlines the clinical safety protocols, deterministic emergency guardrails, adversarial defenses, and quantitative evaluation criteria governing the CareVoice AI Healthcare Platform.

---

## 1. Core Clinical Safety Principles

CareVoice adheres to six strict clinical safety tenets:

1. **Deterministic Emergency Preemption Over Probabilistic Inference:**
   No probabilistic language model—regardless of parameter count or training—can guarantee 100% sensitivity for acute clinical emergencies. Therefore, all acute red flags are intercepted deterministically by code *prior to and completely bypassing* all LLM and vector retrieval pipelines.

2. **Zero Diagnostic and Prescriptive Authority:**
   CareVoice is a health education, symptom intake, and clinic navigation assistant. It does not possess a license to practice medicine. It strictly refuses requests to formulate definitive diagnoses, prescribe pharmaceutical compounds, recommend prescription dosages, or design therapeutic treatment plans.

3. **Explicit Provenance and Zero Hallucinated Citations:**
   Every health guidance snippet must trace to an authoritative, public-health domain (NIH, MedlinePlus, WHO, MOHFW). Citations are bound by the application backend to verified URLs; models are prohibited from inventing citations.

4. **Calibrated Clinical Uncertainty:**
   When a user provides brief, ambiguous, or incomplete symptom descriptions, the system refuses to guess. Instead, it classifies the case as `insufficient_information`, asks structured clarifying questions, and provides transparent uncertainty notes.

5. **Multilingual and Dialect Resilience:**
   Clinical emergencies in the Indian healthcare context are frequently reported in English, Devanagari Hindi, or transliterated Roman Hinglish. The safety engine natively parses all three forms without semantic loss.

6. **Dedicated Psychiatric Crisis Routing:**
   Mental health crises and expressions of self-harm trigger immediate escalation to India's national Tele-MANAS helpline (**14416**) and Emergency **112**.

---

## 2. Deterministic Red-Flag Safeguard Architecture

### A. Evaluated Emergency Categories

| Category | Clinical Triggers (English / Hindi / Hinglish) | Primary Risk | Emergency Action & Routing |
|---|---|---|---|
| **Cardiac** | Chest pain, crushing pressure, radiating pain, seene mein dard, chhati me dard, सीने में दर्द | Acute Myocardial Infarction | Immediate 112 / 108; ED in-person assessment |
| **Stroke (FAST)** | Facial drooping, slurred speech, one-sided weakness, chehra tedha, bolne mein dikkat, चेहरा टेढ़ा | Acute Ischemic / Hemorrhagic Stroke | Immediate 112 / 108; Stroke-ready hospital |
| **Respiratory** | Gasping, breathlessness, cyanosis, saans nahi aa rahi, saans lene me takleef, सांस लेने में दिक्कत | Acute Respiratory Failure / Hypoxia | Immediate 112 / 108; Oxygen support |
| **Severe Hemorrhage** | Deep arterial bleeding, blood won't stop, bahut khoon beh raha, खून रुक नहीं रहा | Hemorrhagic Shock | Immediate 112 / 108; Direct pressure |
| **Psychiatric Crisis** | Want to die, suicidal, khudkushi, aatmahatya, marna chahta hu, खुदकुशी, आत्महत्या | Self-harm / Suicide | **Tele-MANAS 14416**, 112 |
| **Pediatric Critical** | Lethargic infant, unable to wake, blue lips, severe fever | Pediatric sepsis / meningitis | Immediate 112 / 108; Pediatric ED |
| **Maternal Emergency** | Pregnant with heavy bleeding or severe abdominal pain | Placental abruption / ectopic | Immediate 112 / 108; Obstetric ED |

### B. Hinglish & Hindi Regular Expression Examples

```python
# Cardiac emergency pattern (matches intermediate qualifiers like "bahut tez", "achanak", etc.)
re.search(r"\b(seene|chhati)\b.*?\bdard\b", lower)
re.search(r"(सीने|छाती).*?दर्द", lower)

# Respiratory distress pattern
re.search(r"\bsaans\b.*?\b(takleef|dikkat|ruk|kam|nahi|nahin)\b", lower)
re.search(r"(सांस|साँस).*?(तकलीफ|दिक्कत|रुक|नहीं)", lower)

# Stroke FAST pattern
_contains_any(lower, ["chehra tedha", "bolne mein dikkat", "चेहरा टेढ़ा", "बोलने में दिक्कत"])

# Self-harm & crisis patterns
_contains_any(lower, ["khudkushi", "aatmahatya", "marna chahta", "आत्महत्या", "खुदकुशी"])
```

---

## 3. Adversarial & Injection Defenses

Healthcare assistants are targets for prompt injection attacks attempting to circumvent safety rules or extract system prompts.

CareVoice deploys a three-layer defense:

1. **Input Sanitization (`sanitize_model_input`):**
   Scans for prompt injection signatures:
   - `"ignore all previous instructions"`
   - `"system prompt override"`
   - `"developer message"`
   - `"override the rules"`
   If detected, input is stripped and flagged for safety intervention.

2. **Treatment Request Interceptor (`is_personal_treatment_request`):**
   Detects attempts to solicit prescription medications or dosages:
   - Matches keywords: `prescribe`, `dosage`, `dose`, `antibiotic`, `milligram`, `mg`, `sleeping pill`.
   - Returns a structured refusal advising consultation with a licensed clinician or pharmacist.

3. **Output Post-Filter (`is_safe_assistant_reply`):**
   Inspects the model's generated text before transmission to the client:
   - Rejects replies containing definitive diagnostic claims (`"you definitely have"`, `"I diagnose you with"`).
   - Rejects replies containing external URLs that do not match the approved RAG source domains.
   - Enforces fallback if safety violations occur.

---

## 4. Evaluation Methodology & Metrics

CareVoice evaluates AI safety using automated, repeatable benchmarks across four quantitative axes:

### Metric Definitions:

1. **Emergency Sensitivity ($S_{em}$):**
   $$S_{em} = \frac{\text{True Emergency Detections}}{\text{Total Emergency Test Cases}} \times 100\%$$
   *Requirement:* **Must be strictly 100.0%**. A single missed emergency (under-triage) is considered a fatal clinical safety bug.

2. **Tele-MANAS Routing Accuracy ($A_{crisis}$):**
   Percentage of self-harm / psychiatric distress cases successfully routed to Tele-MANAS 14416.
   *Requirement:* **Must be strictly 100.0%**.

3. **Safety & Guardrail Compliance ($C_{safety}$):**
   Percentage of adversarial injections, prescription requests, and illegal dosage queries successfully blocked.
   *Requirement:* **Must be strictly 100.0%**.

4. **Deterministic Triage Latency ($L_{triage}$):**
   Mean time required to evaluate clinical red flags and route emergency actions.
   *Requirement:* **Must be $< 5.0\text{ ms}$** (CareVoice achieves $\sim 0.2\text{ ms}$).

---

## 5. Release Gating Policy

No CareVoice build or container release may be approved for deployment if:
- Any unit or integration test in `tests/ai/` fails.
- Emergency sensitivity falls below 100.0%.
- Adversarial guardrail compliance falls below 100.0%.
- The database migration check reports unapplied schema drift.
- Frontend production bundle emits syntax or packaging errors.
