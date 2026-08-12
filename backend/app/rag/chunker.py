def chunk_text(text:str, chunk_size: int, overlap: int) -> list[str]:
    """
    Divide text into deterministic, overlapping character windows.

    The function does not read application settings directly. Callers provide
    the desired chunk size and overlap, keeping the algorithm independently
    testable and reusable.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    # Ensure normalizing creates the same chunks regardless of OS
    normalized_text = (text.replace("\r\n","\n").replace("\r","\n").strip())
    if not normalized_text: return []

    chunks = []
    step_size = chunk_size - overlap
    for start in range(0, len(normalized_text), step_size):
        end = min(start + chunk_size, len(normalized_text))
        chunks.append(normalized_text[start:end])

        if end == len(normalized_text): break

    return chunks