# CareVoice — AI Setup & Operational Guide

This document provides step-by-step instructions for configuring, deploying, verifying, and troubleshooting the CareVoice AI Healthcare Assistant.

---

## 1. Quick Start (Local Offline Mode with Ollama)

CareVoice runs completely locally without external API keys or network dependencies using Docker Compose and Ollama.

### Step 1: Clone and Configure Environment
Copy `.env.example` to `.env` if you have not already:
```bash
cp .env.example .env
```

Ensure the following default AI settings are present in `.env`:
```dotenv
AI_PROVIDER=ollama
AI_MODEL=llama3.2:1b-instruct-q4_K_M
AI_BASE_URL=http://ollama:11434/v1
AI_API_KEY=

EMBEDDING_PROVIDER=hash
RAG_ENABLED=true
```

### Step 2: Start All Docker Containers
```bash
docker compose up -d --build
```
This starts four synchronized services:
- `db`: PostgreSQL 16 (Port 5432)
- `backend`: FastAPI Python 3.12 (Port 8000)
- `frontend`: React 18 / Vite Development Server (Port 3000)
- `ollama`: Ollama Local Inference Service (Port 11434)

### Step 3: Pull the Quantized Local Model
Download the compact 1B quantized model into Ollama once:
```bash
docker compose exec ollama ollama pull llama3.2:1b-instruct-q4_K_M
```
*Note:* The model (~1.3 GB) is persisted in the `ollama_data` Docker volume and remains cached across restarts.

### Step 4: Ingest the Curated Medical Knowledge Corpus
Ingest the reviewed medical literature from NIH MedQuAD, MedlinePlus, WHO, and Indian MOHFW:
```bash
docker compose exec backend python -m app.cli ingest-knowledge
```
*Output:*
```text
Successfully ingested/refreshed 10 knowledge documents into RAG database.
```

### Step 5: Verify AI Health
Verify that both application health and AI provider health report `healthy`:
```bash
curl http://localhost:8000/api/v1/assistant/health
```
*Response:*
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

## 2. Hosted AI Mode (OpenAI-Compatible `gpt-6-astra`)

To use high-throughput hosted inference (e.g. `gpt-6-astra`), update your `.env` file:

```dotenv
AI_PROVIDER=openai_compatible
AI_MODEL=gpt-6-astra
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-your-actual-api-key-here
```

*(Note: Legacy variables `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` are also supported and kept automatically in bidirectional synchronization).*

Restart the backend container to apply:
```bash
docker compose restart backend
```

---

## 3. Running Automated Tests & Evaluations

### Run Complete Backend Test Suite (149 Tests)
```bash
docker compose exec -T backend pytest -q
```

### Run Dedicated AI Safety & Assessment Tests (17 Tests)
```bash
docker compose exec -T backend pytest tests/ai/ -v
```

### Run AI Platform Evaluation & Benchmark Suite
```bash
docker compose exec -T backend python scripts/evaluate_ai_platform.py
```
This runs the full 30-case clinical benchmark (cardiac, stroke, respiratory, bleeding, Tele-MANAS, routine, adversarial) and outputs machine-readable metrics to `backend/eval_results.json`.

### Run Frontend Test Suite (33 Tests)
```bash
docker compose exec -T frontend npm test
```

### Build Frontend Production Assets
```bash
docker compose exec -T frontend npm run build
```

---

## 4. Troubleshooting & FAQ

### Issue: "Local AI model is not downloaded"
- **Cause:** Ollama is running, but the model `llama3.2:1b-instruct-q4_K_M` has not been pulled yet.
- **Fix:** Execute `docker compose exec ollama ollama pull llama3.2:1b-instruct-q4_K_M`.

### Issue: "Cannot connect to local AI"
- **Cause:** Ollama container is restarting or unhealthy.
- **Fix:** Check container status with `docker compose ps` and logs with `docker compose logs ollama`.

### Issue: "RAG search returns 503 / 0 documents"
- **Cause:** Knowledge corpus has not been ingested into the PostgreSQL database.
- **Fix:** Run `docker compose exec backend python -m app.cli ingest-knowledge`.

### Issue: Emergency Triage Response Time
- **Note:** Emergency triage runs deterministically in $< 1\text{ ms}$ and functions 100% offline even if Ollama or hosted AI is down.
