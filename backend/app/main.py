from fastapi import FastAPI

app = FastAPI(
    title="AI Security RAG Firewall",
    description="Secure RAG document-chat platform with prompt-injection defense, RBAC, retrieval filtering, and audit logging.",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "AI Security RAG Firewall API is running",
        "status": "ok",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
    }