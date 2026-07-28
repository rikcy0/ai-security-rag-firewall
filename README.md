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

- FastAPI
- PostgreSQL
- pgvector
- SQLAlchemy
- Python
- React
- Docker
- pytest

## Planned Features

- User authentication
- Role-based access control
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

Currently in early development.

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If non-Windows:

```bash
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload
```

### Tests

Run backend tests from project root:

```bash
python -m pytest backend/tests -v
```