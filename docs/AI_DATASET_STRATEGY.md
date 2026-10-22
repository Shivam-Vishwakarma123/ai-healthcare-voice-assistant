# CareVoice — Clinical Dataset Strategy & Knowledge Base Provenance

## 1. Corpus Architecture & Provenance Governance

Medical retrieval-augmented generation (RAG) is only as trustworthy as the corpus behind it. CareVoice strictly bans uncurated web scraping or open crawler datasets. All internal reference documents are sourced from verified public-health institutions and peer-reviewed clinical guidelines:

| Document Key | Title | Authoritative Source | Primary Clinical Focus |
| :--- | :--- | :--- | :--- |
| `pediatric_fever_management` | Pediatric Fever and Dehydration Care | WHO & Indian Academy of Pediatrics | Infant hydration, antipyretic dosing, red flags |
| `adult_hypertension_lifestyle` | Hypertension Lifestyle & Emergency Guidance | MedlinePlus & NIH NHLBI | Dietary sodium, exercise, hypertensive crisis |
| `acute_pharyngitis_care` | Sore Throat & Pharyngitis Clinical Care | NIH MedQuAD & CDC | Viral vs. streptococcal pharyngitis, home care |
| `type2_diabetes_self_management`| Type 2 Diabetes Self-Care & Hypoglycemia | WHO Guidelines & MedlinePlus | Glucose monitoring, Rule of 15 hypoglycemia |
| `asthma_action_plan_home_care` | Adult Asthma Flare-up & Action Plans | Global Initiative for Asthma (GINA) & NHS | Inhaler technique, peak flow, acute exacerbation |
| `migraine_and_headache_red_flags`| Migraine Care & Acute Headache Red Flags | NIH MedQuAD & NHS | SNOOP criteria, thunderclap headache warnings |
| `gastroenteritis_oral_rehydration`| Acute Diarrhea & ORS Formulation | WHO & Indian MOHFW | Standard WHO ORS prep, electrolyte management |
| `dengue_fever_warning_signs` | Dengue Management & Warning Signs | Indian MOHFW & WHO SEARO | Platelet monitoring, defervescence phase, shock |
| `urinary_tract_infection_care` | UTI Symptoms, Hydration & Clinical Care | MedlinePlus & NIH | Red flags (fever, flank pain), hydration advice |
| `covid19_respiratory_monitoring`| Respiratory Viral Care & SpO2 Monitoring | WHO & MOHFW Clinical Management | Pulse oximetry (<94%), proning, escalation |

---

## 2. Ingestion & Chunking Pipeline

- **Storage Tables:** `knowledge_documents` and `knowledge_chunks` in PostgreSQL.
- **Chunk Size Strategy:**
  - Semantic sliding window of 350-500 tokens per chunk.
  - 10% overlap (50 tokens) to ensure clinical context is preserved across chunk boundaries.
- **Approved Host Whitelist:**
  - Configured via `RAG_APPROVED_SOURCE_HOSTS` in `backend/app/core/config.py`:
    `["who.int", "medlineplus.gov", "nih.gov", "mohfw.gov.in", "nhs.uk", "cdc.gov"]`
  - Any knowledge entry citing a domain outside this list is rejected during ingestion.

---

## 3. Hybrid Retrieval: Vector & Lexical Matching

1. **Vector Embedding Layer**:
   - Computes cosine similarity between user query vectors and chunk embeddings.
   - Supports configurable OpenAI `text-embedding-3-small`, local HuggingFace sentence-transformers, or deterministic hash embeddings for resource-constrained environments.
2. **Lexical Keyword Boost**:
   - Augments vector search with clinical token matching (e.g., matching `"ORS"`, `"SpO2"`, `"14416"`, `"112"`).
3. **Relevance Thresholding**:
   - Only chunks exceeding a minimum similarity score (0.45) are injected into the LLM context.
   - If no chunks pass the threshold, the system transparently indicates insufficient specific reference material rather than hallucinating guidance.

---

## 4. Conflict Resolution & Contradiction Handling

When retrieved guidelines contain conflicting advice (e.g., contrasting recommendations regarding home recovery vs. immediate clinic evaluation):
- The CareVoice engine surfaces both perspectives.
- Applies the **Precautionary Clinical Principle**: when in doubt, the system recommends the safer course of action (e.g., seeking prompt in-person clinician assessment) and records uncertainty notes in the response.
