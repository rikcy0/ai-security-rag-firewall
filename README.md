# AI Security RAG Firewall

AI Security RAG Firewall is a full-stack AI security project under active development. Its current backend supports authenticated users, role-based authorization, owner-isolated document ingestion, deterministic prompt-injection screening, OpenAI embedding generation, pgvector-backed chunk indexing, and owner-scoped semantic retrieval. Planned stages will add guarded RAG question answering and security-event auditing.

## Overview

The implemented document-ingestion pipeline is:

```text
authenticated upload
        ↓
file and UTF-8 validation
        ↓
prompt-injection screening
        ↓
overlapping text chunking
        ↓
embedding generation
        ↓
PostgreSQL and pgvector persistence
```

The implemented semantic-retrieval pipeline is:

```text
authenticated query
        ↓
query and top-k validation
        ↓
query embedding
        ↓
SQL-enforced owner filtering
        ↓
HNSW cosine-similarity search
        ↓
ranked owned chunks
```

Unlike a normal RAG chatbot, this project is designed to include security controls for:

- Prompt injection detection
- System prompt leakage attempts
- Cross-user document access prevention
- Role-based access control
- Retrieval filtering
- Output filtering
- Audit logging
- Security event monitoring

## Tech Stack

- Python 3.12
- FastAPI
- Pydantic
- PostgreSQL 16
- pgvector
- OpenAI Python SDK and Embeddings API
- SQLAlchemy
- Alembic
- pwdlib with Argon2
- PyJWT
- Docker Compose
- pytest
- React frontend planned

## Implemented Features

- FastAPI application foundation and OpenAPI documentation
- PostgreSQL 16 development database through Docker Compose
- pgvector extension setup
- SQLAlchemy database sessions and models
- Alembic schema migrations
- PostgreSQL-backed user registration
- Argon2id password hashing
- JWT bearer-token login
- Protected current-user endpoint
- Database-backed `user` and `admin` roles
- Database constraints that reject unsupported roles
- Default `user` role for newly registered accounts
- Registration protection against client-supplied roles
- Reusable FastAPI role-authorization dependencies
- Admin-only user-list endpoint
- Unit, route, security, and PostgreSQL integration tests
- Authenticated `.txt` and `.md` document uploads
- Configurable upload-size and chunking limits
- Bounded file reads and UTF-8 content validation
- Safe filename normalization and extension validation
- Deterministic overlapping text chunking
- PostgreSQL-backed document and chunk persistence
- Database-enforced document ownership relationships
- Owner-scoped document listing and metadata retrieval
- Cross-user document access prevention
- Atomic document and chunk creation with rollback on database failure
- Deterministic rule-based prompt-injection detection
- Configurable prompt-injection blocking threshold
- Detection of instruction overrides, system-prompt extraction, role manipulation, security bypasses, and data-exfiltration requests
- Unicode compatibility, case, whitespace, and zero-width-character normalization for security analysis
- Prompt-injection scanning before document chunking or persistence
- Generic rejection responses that do not expose detector scores or matched rules
- PostgreSQL integration tests proving blocked documents and chunks are not persisted
- Validated OpenAI API-key and embedding-model configuration
- Application-defined embedding-provider boundary using structural typing
- Synchronous OpenAI embedding generation with bounded request batches
- Provider-response ordering, count, dimension, finite-value, and zero-vector validation
- Fixed 1,536-dimension embeddings for `text-embedding-3-small`
- Non-null pgvector embeddings stored with every document chunk
- HNSW cosine-similarity index for document-chunk embeddings
- Generic `503 Service Unavailable` responses for embedding-service failures
- Pre-persistence embedding generation so provider failures do not create partial database records
- Deterministic unit and PostgreSQL integration tests that do not contact OpenAI
- Authenticated `POST /retrieval/search` endpoint
- Whitespace-normalized queries limited to 2,000 characters
- Bounded retrieval with a default `top_k` of 5 and maximum of 20
- SQL-enforced document ownership before similarity ranking and limiting
- Cosine-similarity ranking over pgvector chunk embeddings
- Transaction-local strict HNSW iterative scanning for filtered retrieval
- Safe retrieval responses containing approved chunk and source fields only
- Cross-user isolation tests using deliberately closer foreign vectors
- End-to-end tests covering upload, embedding, storage, query embedding, and retrieval

## Roadmap

- Guarded RAG query and answer generation
- Query-time prompt-injection enforcement
- Contextual and model-assisted prompt-injection defenses
- Security event logs
- Admin dashboard
- Adversarial test suite
- More advanced token-aware and structure-aware chunking


## Project Status

Current capabilities include:

- PostgreSQL 16 through Docker Compose
- pgvector 0.8.2
- SQLAlchemy connection and session management
- Alembic schema migrations
- Normalized and unique usernames
- Argon2id password hashing
- Signed and expiring JWT access tokens
- Bearer-token protected routes
- Database-backed active-user validation
- Database-backed `user` and `admin` roles
- Reusable role-authorization dependencies
- Admin-only API routes
- Immediate enforcement of role changes on subsequent requests
- Unit and PostgreSQL integration tests
- Authenticated text and Markdown document uploads
- Configurable upload-size enforcement
- UTF-8 document validation
- Deterministic overlapping text chunking
- PostgreSQL-backed documents and chunks
- Owner-scoped document listing and metadata retrieval
- Cross-user document access prevention
- Database constraints and cascading document cleanup
- Rule-based prompt-injection risk scoring
- Validated and configurable blocking threshold
- Pre-persistence scanning of uploaded document content
- Generic `422 Unprocessable Content` responses for blocked documents
- Database-backed verification that blocked content is not persisted
- Batched OpenAI embedding generation through an application-defined provider boundary
- Fixed-dimension vector validation before persistence
- pgvector-backed chunk embeddings
- HNSW cosine-similarity indexing
- Generic handling of unavailable or invalid embedding-provider responses
- Authenticated owner-scoped semantic search
- Query embedding through the shared provider boundary
- SQL ownership filtering before `top_k`
- Cosine-similarity scores and source-aware chunk responses
- Strict HNSW iterative scanning for owner-filtered searches

Document ingestion, text chunking, ingestion-time prompt-injection screening, embedding generation, pgvector-backed chunk indexing, and owner-scoped semantic retrieval are implemented. Guarded RAG answer generation, query-time prompt-injection enforcement, contextual detection, model-assisted defenses, and security-event auditing remain under development.

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

RAG_FIREWALL_SECRET_KEY=your-generated-secret
RAG_FIREWALL_ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Configure the embedding provider before uploading documents:

```env
RAG_FIREWALL_OPENAI_API_KEY=your-api-key-here
RAG_FIREWALL_EMBEDDING_MODEL=text-embedding-3-small
```

The API key is optional during application startup so non-embedding functionality can still run locally. Document uploads and semantic searches return `503 Service Unavailable` when the embedding provider is not configured.

Accepted document chunks are sent to the configured embedding provider. Do not upload sensitive or private material, and remember that real embedding requests may incur provider charges.

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

New accounts always receive the `user` role. Registration requests cannot assign the `admin` role.

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

Uploaded documents are associated with the authenticated user. The client cannot select a different owner.

Document responses contain approved metadata only. Original document content, chunks, and internal ownership identifiers are not returned by these endpoints.

Requests for nonexistent documents and documents owned by another user both return `404 Not Found`.

Uploaded document text is screened for prompt-injection signals after UTF-8 validation and before chunking or database persistence. Documents that meet the configured blocking threshold receive:

```json
{
  "detail": "Document rejected by prompt-injection policy"
}
```

Accepted documents are divided into overlapping chunks and embedded before the database transaction begins. Every stored chunk receives a 1,536-dimension vector, and PostgreSQL indexes those vectors with HNSW using cosine distance.

If embedding generation is unavailable or returns an invalid result, the upload receives:

```json
{
  "detail": "Embedding service is unavailable"
}
```

Internal provider errors are not returned to clients, and embedding failures do not create document or chunk records.

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

The authenticated user's database UUID is the only source of ownership. Clients cannot provide an `owner_id`, and administrators do not automatically bypass document ownership.

Ownership filtering occurs inside PostgreSQL before similarity ranking and `top_k` are applied. Retrieval responses exclude owner identifiers and embedding vectors.

An owner with no stored chunks receives:

```json
{
  "results": []
}
```

Semantic retrieval embeds and ranks the query but does not invoke a chat model or generate an answer. Query-time prompt-injection enforcement and guarded answer generation belong to the next checkpoint.

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

Automated tests use deterministic fake embedding providers. Running the test suite does not make OpenAI API requests or incur embedding charges.

### Stop PostgreSQL

Stop and remove the development container while preserving its database volume:

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete all local database data.
