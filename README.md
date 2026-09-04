# AI Security RAG Firewall

AI Security RAG Firewall is a security-focused RAG backend with authenticated document uploads, owner-isolated semantic retrieval, citation-backed answers, and adversarial evaluation.

## Overview

### Document ingestion

`POST /documents` turns an authenticated upload into searchable, owner-linked chunks:

```text
authenticated upload
        ↓
bounded file read, filename and UTF-8 validation
        ↓
prompt-injection screening
        ↓
overlapping text chunking
        ↓
batched embedding generation and vector validation
        ↓
atomic document, chunk and pgvector persistence
        ↓
approved document metadata response
```

Blocked content never reaches chunking or embedding. Embedding failures leave no partial upload records; database failures roll back the document operation.

### Owner-scoped semantic retrieval

`POST /retrieval/search` finds matching chunks without generating an answer:

```text
authenticated query
        ↓
query and top-k validation
        ↓
query embedding
        ↓
SQL-enforced owner filtering
        ↓
HNSW cosine-similarity ranking and top-k limit
        ↓
ranked owned chunks with approved source metadata
```

Ownership is enforced before ranking and limiting, including for administrators. This endpoint returns chunk text but not owner IDs or embeddings; unlike `/rag/answer`, it does not run query-time prompt-injection screening.

### Guarded RAG answers

`POST /rag/answer` combines query screening, owner-scoped retrieval, and citation-backed generation:

```text
authenticated RAG query
        ↓
query validation and prompt-injection screening
        ↓
query embedding and SQL-enforced owner-scoped retrieval
        ↓
immutable chunk results and database read-transaction release
        ↓
whole-chunk context budgeting and source numbering
        ↓
structured answer generation from minimal context
        ↓
provider and service-level citation validation
        ↓
answer with server-owned metadata for cited sources only
```

The answer model receives only the query, source numbers, and selected chunk text. No usable context skips generation and produces the fixed insufficient-context response; model-declared insufficiency produces the same response. Valid citations establish reference consistency, not semantic proof that every claim is supported.

Blocked uploads and RAG queries also produce minimized security events through a separate, best-effort audit transaction. Audit failures do not change the original rejection decision.

Authorization stays in application code and PostgreSQL, not in model instructions. See [Security Policy](SECURITY.md) for trust boundaries, validation details, and limitations.

## Tech Stack

- Python 3.12, FastAPI, Pydantic
- PostgreSQL 16, pgvector, SQLAlchemy, Alembic
- OpenAI Python SDK, Embeddings API, Responses API
- Argon2id through pwdlib, PyJWT
- Docker Compose, pytest

## Implemented Features

- Authentication and authorization: PostgreSQL-backed users, Argon2id passwords, expiring JWTs, and database-enforced user/admin roles.
- Document ingestion: bounded UTF-8 text and Markdown uploads, overlapping chunks, and atomic document/vector persistence.
- Prompt-injection screening: deterministic rules and Unicode normalization applied to uploads and RAG queries before downstream processing.
- Owner-scoped retrieval: OpenAI embeddings, pgvector HNSW cosine search, and SQL ownership filtering before ranking and limiting.
- Guarded RAG answers: bounded context, structured generation, provider-independent citation validation, and server-owned source metadata.
- Security-event auditing: minimized records for failed logins, authorization denials, and blocked injections, with admin-only review.
- Testing and evaluation: unit and PostgreSQL integration tests, adversarial corpora, reproducible detector metrics, and CI with migration checks.

## Project Status

The backend supports an end-to-end upload, retrieval, and cited-answer workflow. This is a local portfolio project, not a production-hardened security product. Detector limitations and evaluation results are documented in [Security Policy](SECURITY.md) and [Adversarial Evaluation](#adversarial-tests-and-detector-evaluation).

## Local Development

Run all commands from the repository root.

### Requirements

- Python 3.12
- Docker Desktop
- Git

### Create the environment file

Copy the example configuration:

```bash
cp .env.example .env
```

Generate a local JWT signing secret:

```bash
openssl rand -hex 32
```

Set it in `.env`:

```env
RAG_FIREWALL_SECRET_KEY=your-generated-secret
RAG_FIREWALL_ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Configure the OpenAI-backed embedding and answer providers before uploading documents or generating RAG answers:

```env
RAG_FIREWALL_OPENAI_API_KEY=your-api-key-here
RAG_FIREWALL_EMBEDDING_MODEL=text-embedding-3-small
RAG_FIREWALL_GENERATION_MODEL=gpt-5.6-luna
RAG_FIREWALL_OPENAI_TIMEOUT_SECONDS=30
RAG_FIREWALL_OPENAI_MAX_RETRIES=1
RAG_FIREWALL_RAG_ANSWER_TOP_K=5
RAG_FIREWALL_RAG_MAX_CONTEXT_CHARACTERS=20000
RAG_FIREWALL_RAG_MAX_OUTPUT_TOKENS=800
```

The API key is optional during application startup so functionality that does not use OpenAI can still run locally. Document uploads, semantic searches, and guarded RAG answers return `503 Service Unavailable` when their required provider is not configured.

Accepted document chunks and search queries are sent to the configured embedding provider. Guarded answer requests also send the validated query and selected chunk text to the configured answer provider. Do not upload sensitive or private material, and remember that real provider requests may incur charges.

The included database credentials are intended only for local development. Never commit `.env` or use the development credentials in production.

### Create the Python virtual environment

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Install dependencies

```bash
python -m pip install -r backend/requirements.txt
```

### Start PostgreSQL

```bash
docker compose up -d db
docker compose ps
```

Wait until `rag_firewall_db` reports that it is healthy.

The database is exposed only on the local machine at `127.0.0.1:5432`.

### Apply database migrations

```bash
python -m alembic upgrade head
```

Check the current migration:

```bash
python -m alembic current
```

### Run the FastAPI application

```bash
python -m uvicorn backend.app.main:app --reload
```

Open:

- API: http://127.0.0.1:8000
- Health check: http://127.0.0.1:8000/health
- API documentation: http://127.0.0.1:8000/docs

### Authentication and authorization endpoints

| Method | Endpoint | Purpose | Required access |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | Register a new user | Public |
| `POST` | `/auth/login` | Authenticate and receive an access token | Public |
| `GET` | `/auth/me` | Return the current authenticated user | Authenticated user |
| `GET` | `/admin/users` | Return a safe list of registered users | Administrator |
| `GET` | `/admin/security-events` | Return a bounded, newest-first list of security events | Administrator |

Security-event listing defaults to 50 records (`limit`: 1–100). Audit records exclude credentials, tokens, and document/query text.

New accounts receive `user`; registration cannot assign `admin`.

For local development, an existing user can be promoted through PostgreSQL:

```bash
docker compose exec db psql \
  -U postgres \
  -d rag_firewall \
  -c "UPDATE users SET role = 'admin' WHERE username = 'your_username';"
```

### Document endpoints

| Method | Endpoint | Purpose | Required access |
| --- | --- | --- | --- |
| `POST` | `/documents` | Upload, screen, chunk, embed, and store a UTF-8 `.txt` or `.md` document | Authenticated user |
| `GET` | `/documents` | List metadata for the current user's documents | Authenticated user |
| `GET` | `/documents/{document_id}` | Return metadata for an owned document | Document owner |

Ownership comes from the authenticated user. These endpoints return metadata, not original text, chunks, or owner IDs; foreign and nonexistent documents both return `404`.

Uploads are screened before chunking and embedding. Accepted chunks receive 1,536-dimension vectors and are persisted atomically with the document; HNSW indexes support cosine search.

Blocked content returns `422` with `"Document rejected by prompt-injection policy"`. Embedding failures return `503` with `"Embedding service is unavailable"` and leave no partial document/chunk records.

### Semantic retrieval endpoint

| Method | Endpoint | Purpose | Required access |
| --- | --- | --- | --- |
| `POST` | `/retrieval/search` | Retrieve semantically relevant chunks from the current user's documents | Authenticated user |

Example request:

```json
{
  "query": "How should API keys be stored?",
  "top_k": 5
}
```

Example response:

```json
{
  "results": [
    {
      "chunk_id": "00000000-0000-0000-0000-000000000000",
      "document_id": "00000000-0000-0000-0000-000000000000",
      "filename": "security-notes.md",
      "chunk_index": 2,
      "content": "API keys should be stored in environment variables.",
      "similarity": 0.91
    }
  ]
}
```

Queries are limited to 2,000 characters; `top_k` defaults to 5 and permits 1–20. SQL filters by the authenticated owner before ranking and limiting; clients cannot override ownership, and administrators receive no ownership bypass.

Results include chunk text but exclude owner IDs and embeddings. No owned chunks yields `{"results": []}`. This endpoint performs search only; use `/rag/answer` for generation.

### Guarded RAG answer endpoint

| Method | Endpoint | Purpose | Required access |
| --- | --- | --- | --- |
| `POST` | `/rag/answer` | Generate a guarded, citation-backed answer from the current user's documents | Authenticated user |

Example request:

```json
{
  "query": "How should API keys be stored?"
}
```

Example answered response:

```json
{
  "status": "answered",
  "answer": "API keys should be stored in environment variables [1].",
  "sources": [
    {
      "source_number": 1,
      "chunk_id": "00000000-0000-0000-0000-000000000000",
      "document_id": "00000000-0000-0000-0000-000000000000",
      "filename": "security-notes.md",
      "chunk_index": 2,
      "similarity": 0.91
    }
  ]
}
```

Only `query` is client-controlled; retrieval count, ownership, context, model, and token limits are server-controlled. Screening precedes embedding and owner-scoped retrieval.

Generation receives the query, source numbers, and selected text—not IDs, filenames, similarity values, or vectors. Citations are validated before server-owned metadata is returned for cited sources only.

If no usable context is available, or the model reports that the supplied context is insufficient, the endpoint returns the same deterministic response:

```json
{
  "status": "insufficient_context",
  "answer": "I could not find information in your documents to answer that question.",
  "sources": []
}
```

When no context fits the server-controlled budget, the answer provider is not called. Prompt-injection, refusal, embedding-provider, and answer-provider failures use generic public messages rather than exposing internal scores or upstream details.

### Run tests

Run unit tests without external services:

```bash
python -m pytest backend/tests -m "not integration" -v
```

Run PostgreSQL and pgvector integration tests:

```bash
python -m pytest backend/tests -m integration -v
```

PostgreSQL must be running and migrations must be applied before integration tests are executed.

Run the complete suite:

```bash
python -m pytest backend/tests -v
```

Automated tests use deterministic fake embedding and answer providers. Running the test suite does not make OpenAI API requests or incur provider charges.

### Adversarial tests and detector evaluation

The suite lives in `backend/tests/adversarial/`. Run its offline tests:

```bash
python -m pytest backend/tests/adversarial -m "not integration" -v
```

Run its PostgreSQL pipeline tests after starting the database and applying migrations:

```bash
python -m pytest backend/tests/adversarial -m integration -v
```

Generate the detector report without PostgreSQL or an API key:

```bash
python -m backend.tests.adversarial.report
```

The offline report uses corpus schema version 1 and threshold 50, independent of local settings. It groups results by mode, category, and tag, listing error case IDs without raw text or external model calls.

The current 49-case corpus contains 32 regression cases and 17 exploratory evaluation cases:

| Corpus group | Malicious blocked | Benign allowed |
| --- | --- | --- |
| Regression | 18/18 | 14/14 |
| Exploratory evaluation | 0/7 | 0/10 |
| Overall | 18/25 (72.00%) | 14/24 (58.33%) |

False-negative rate: **28.00%**. False-positive rate: **41.67%**. This small, curated, implementation-aware corpus is not a real-world accuracy estimate. Update the baseline when the corpus, detector, or threshold changes.

Regression decisions are asserted; exploratory errors are reported rather than required to disappear for pytest to pass. Passing tests therefore does not mean perfect detection.

Pipeline tests cover blocked requests, persistence and audit safeguards, a benign upload-to-answer workflow, and invalid provider citations. Providers are fakes: these checks do not measure live-model injection resistance, embedding quality, or semantic grounding. Existing CI discovers the tests through their integration markers; see [test evidence and limitations](SECURITY.md#test-evidence-and-evaluation-limits).

### Stop PostgreSQL

Stop and remove the development container while preserving its database volume:

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete all local database data.
