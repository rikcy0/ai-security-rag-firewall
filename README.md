# AI Security RAG Firewall

A secure RAG document-chat platform with prompt-injection defense, role-based access control, retrieval filtering, and audit logging.

## Overview

AI Security RAG Firewall is a full-stack AI security project that allows users to upload documents, ask questions over those documents, and receive answers through a retrieval-augmented generation pipeline.

Unlike a normal RAG chatbot, this project includes security controls for:

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

## Roadmap

- Document upload
- Text chunking
- Embedding generation
- Vector search
- RAG answer generation
- Prompt-injection firewall
- Security event logs
- Admin dashboard
- Adversarial test suite

## Project Status

The FastAPI backend, PostgreSQL/pgvector infrastructure, user authentication, and role-based access control checkpoints are implemented.

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

Document upload and text chunking are the next implementation checkpoint.

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

### Stop PostgreSQL

Stop and remove the development container while preserving its database volume:

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete all local database data.