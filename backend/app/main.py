from fastapi import FastAPI

from backend.app.routes.auth_routes import router as auth_router
from backend.app.routes.admin_routes import router as admin_router
from backend.app.routes.document_routes import router as document_router

app = FastAPI(
    title="AI Security RAG Firewall",
    description="Secure RAG document-chat platform with prompt-injection defense, RBAC, retrieval filtering, and audit logging.",
    version="0.1.0",
)


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(document_router)


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