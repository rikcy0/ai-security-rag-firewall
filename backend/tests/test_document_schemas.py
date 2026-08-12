from datetime import datetime, timezone
from uuid import uuid4

from backend.app.db.models import Document
from backend.app.schemas.documents import DocumentResponse


def test_document_response_excludes_content_and_owner() -> None:
    private_content = "private security document"

    database_document = Document(
        owner_id=uuid4(),
        filename="security.txt",
        content_type="text/plain",
        size_bytes=len(private_content.encode("utf-8")),
        content=private_content
    )
    database_document.id = uuid4()
    database_document.created_at = datetime.now(timezone.utc)

    response = DocumentResponse.model_validate(database_document)
    response_data = response.model_dump()

    assert response.filename == "security.txt"
    assert set(response_data) == {
        "id",
        "filename",
        "content_type",
        "size_bytes",
        "created_at"
    }
    assert "owner_id" not in response_data
    assert "content" not in response_data
    assert private_content not in repr(response)