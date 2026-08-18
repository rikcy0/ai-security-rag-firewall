from fastapi import FastAPI

from backend.app.routes.auth_routes import router as auth_router
from backend.app.routes.admin_routes import router as admin_router
from backend.app.routes.document_routes import router as document_router
from backend.app.routes.retrieval_routes import router as retrieval_router

app = FastAPI(
    title="AI Security RAG Firewall",
    description=(
    "Security-focused RAG backend with authentication, RBAC, "
    "owner-scoped document ingestion, prompt-injection "
    "screening, and semantic retrieval."
    ),
    version="0.1.0",
)


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(document_router)
app.include_router(retrieval_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "AI Security RAG Firewall API is running",
        "status": "ok",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
    }