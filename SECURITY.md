# Security Policy

This backend explores defenses against direct and indirect prompt injection, unauthorized document access, data and system-prompt leakage, unsafe answers, and missing auditability. It is a local portfolio project, not a production-hardened security product.

## Trust Boundaries

- Application code and PostgreSQL enforce authorization; the model never decides who can access a document.
- User text and provider responses are untrusted. Screening, ownership filtering, bounded context, and response validation serve different purposes; none alone guarantees safe answers.
- Secrets come from environment configuration, not source code. API keys use Pydantic `SecretStr` to avoid exposure in normal settings representations.
- The vector index accelerates search; SQL ownership predicates provide access control.

## Authentication and Roles

- Usernames are stripped, lowercased, and validated; PostgreSQL enforces uniqueness. Passwords are stored only as Argon2id hashes through `pwdlib`, and neither passwords nor hashes appear in API responses.
- Unknown users and wrong passwords receive the same error. Unknown-user checks verify against a dummy Argon2 hash to reduce timing-based enumeration signals; this is not a constant-time guarantee. Inactive users cannot log in.
- Signed JWTs require `sub`, `iat`, and `exp`, restrict the decoding algorithm, and require a UUID subject. Expired, malformed, and incorrectly signed tokens are rejected.
- Every protected request loads the current user and role from PostgreSQL. Deletion, deactivation, and role changes affect subsequent requests even with an unexpired JWT.
- Accounts default to `user`; registration rejects client-supplied roles. A database check constraint permits only `user` and `admin`.
- Reusable FastAPI dependencies authenticate before checking roles. Both `/admin/users` and `/admin/security-events` require an administrator and expose only approved response fields.

## Document Ingestion and Ownership

- Authenticated uploads accept only UTF-8 `.txt` and `.md` files. Reads are bounded to the configured limit plus one detection byte, and the service rechecks size.
- Filename path components are removed; empty, oversized, or null-containing filenames are rejected. Empty, whitespace-only, invalid UTF-8, and null-containing content are rejected.
- Ownership comes from the authenticated user, never the request body. Lists filter by owner; individual lookups filter by both document and owner UUID. Administrators do not bypass ownership.
- Documents and chunks are saved in one service-owned transaction, with rollback on database failure. Embeddings are generated before document/chunk rows are added, so provider failures leave no partial upload records.
- Foreign keys and cascading deletion prevent orphaned records. Constraints reject empty content, invalid chunk positions, and duplicate positions within a document. Each persisted chunk requires a non-null `vector(1536)`.

## Prompt-Injection Screening

The detector is independent of FastAPI, SQLAlchemy, and external providers. Precompiled, bounded patterns cover instruction override, system-prompt extraction, role manipulation, security bypass, and data exfiltration.

- Detection uses NFKC normalization, case folding, and whitespace normalization. Invisible format characters are both removed and treated as spaces in separate variants, covering split words and word boundaries.
- These transformations affect only the analysis copy, not the stored document or the query sent to providers.
- Matched categories contribute severity weights capped at `100`. The configurable threshold is `1–100`, default `50`; every current rule can block individually at that default. Scores are policy values, not probabilities.
- Uploads are screened after content validation but before chunking, embedding, or persistence. Guarded RAG queries are screened before query embedding, document retrieval, or answer generation.
- Blocks return generic errors and create minimized audit events; scores, categories, reasons, and matched text are not disclosed in rejection responses.

Coverage limits matter: raw `/retrieval/search` does not run the detector because it does not generate answers, and retrieved chunks are not rescanned immediately before generation.

## Embedding and Answer Providers

- Services depend on replaceable provider protocols. Concrete clients are synchronous to match FastAPI routes and SQLAlchemy sessions, created lazily, and closed when request dependencies finish.
- Validated settings control API keys, models, timeouts, retries, and answer-token limits. Startup does not require an API key; provider-dependent operations return a generic `503` when unavailable.
- Embedding requests use bounded batches. Responses must contain one correctly indexed result per input; indexes restore input order.
- Vectors must have exactly 1,536 finite, float-convertible values and must not be all-zero. Invalid results become application-specific errors before persistence.
- Accepted chunks and search queries cross the external embedding boundary. Selected chunk text and the query cross the external answer boundary. Documents and embeddings should be treated as potentially sensitive.
- The answer provider uses structured Responses API output, explicit reasoning effort, and `store=False`. This disables response storage for later retrieval, not all provider retention; it is not a zero-retention guarantee.

## Retrieval and Guarded Answers

### Owner-scoped retrieval

- Queries must be nonblank and at most 2,000 characters. Retrieval `top_k` defaults to `5` and is bounded to `1–20`; extra request fields, including ownership overrides, are rejected.
- PostgreSQL joins chunks to documents and applies the authenticated owner's UUID before cosine ranking and `LIMIT`. Even a closer foreign-owned chunk is excluded.
- HNSW uses `vector_cosine_ops` with transaction-local strict iterative scanning for filtered search. Retrieval is read-only; an empty owned corpus returns an empty result.
- Similarity reports cosine closeness, not a confidence probability. Stored and query vectors must use the same embedding model.

### Context and transaction boundaries

- `POST /rag/answer` accepts only a query. Owner identity, retrieval count, context budget, model, and output-token limit remain server-controlled.
- Raw query length is bounded before minimal whitespace/line-ending normalization. The detector's more aggressive normalization stays separate.
- Retrieved chunks become immutable application data, allowing the service to end the read transaction before waiting on answer generation. This workflow expects no pending writes that need preservation.
- A separate answer-time character budget selects whole chunks, skipping blanks and nonfitting chunks. Source numbers are assigned after selection.
- The model receives only the query, source numbers, and selected text—not UUIDs, filenames, ownership identifiers, similarity values, or embeddings. Grounding instructions treat sources as untrusted data and require answers based only on supplied context.

### Output validation

- The provider validates completion status, refusals, structured output, answer length, and status-specific requirements.
- Answered results need at least one citation. Inline markers must be canonical positive numbers, agree exactly with the declared citation list, and reference supplied context.
- The service repeats contextual citation validation before mapping sources, protecting the contract when a replacement provider is used.
- Public source metadata comes from server-owned retrieval results, not model-generated identifiers; only cited sources are returned.
- Missing or over-budget context skips generation and returns a fixed insufficient-context answer with no sources. Model-declared insufficiency uses the same response.

## Public Responses and Failure Handling

Explicit schemas limit disclosure by endpoint:

| Endpoint family | Returned data | Excluded data |
| --- | --- | --- |
| Document listing and lookup | Approved document metadata | Original text, chunks, owner UUID |
| Semantic retrieval | Chunk/document UUIDs, filename, position, content, similarity | Owner UUID, embeddings |
| Guarded answers | Answer, status, cited-source metadata | Chunk content in source metadata, owner UUID, embeddings |

| Condition | HTTP response |
| --- | --- |
| Invalid credentials or missing/invalid authentication | Generic `401` |
| Authenticated user lacks the required role | Generic `403` |
| Document is nonexistent or belongs to someone else | Same `404` |
| Prompt-injection block or model refusal | Generic `422` |
| Missing provider configuration, provider failure, or invalid provider result | Generic `503` |

Provider exceptions, raw model responses, refusal details, and detector evidence are not returned in public errors. Embedding failures cannot persist partial documents.

## Security-Event Auditing

PostgreSQL stores only these event types:

| Event | Recorded context |
| --- | --- |
| `login_failed` | Normalized submitted username, without claiming that the account exists |
| `authorization_denied` | Actor identity, required role, actual role |
| `prompt_injection_blocked` | Actor identity, upload/query surface, score, sorted matched categories |

- Events exclude passwords, hashes, tokens, document/query text, embeddings, and provider responses. Database constraints restrict event types and require JSON-object details.
- Writes use a separate session and transaction. Audit persistence is best-effort: a logging failure cannot reverse the security decision, and fallback logs contain only the exception type.
- User deletion nulls the event's user UUID while preserving the username snapshot and event history.
- Admin-only review is newest-first by creation time and UUID, with a default limit of `50` and allowed range `1–100`.

## Test Evidence and Evaluation Limits

- Unit and PostgreSQL integration tests cover authentication, roles, rollback, provider validation, and generic errors. Ownership tests deliberately rank a foreign vector closer and verify that foreign content never reaches the answer provider.
- Adversarial pipeline tests check rejection before downstream work, no persisted blocked uploads, and audit responses without raw attack text or credentials.
- A benign positive control covers upload, chunk/vector storage, retrieval, cited-answer metadata, and no security-block event. Service tests directly inject invalid citations from replacement providers.
- Versioned corpora separate regression assertions from exploratory evaluation. The offline report runs the real detector at threshold `50`, reporting category/tag metrics and failure IDs without raw prompt text.

The 49-case baseline has 32 regression and 17 exploratory examples: **18/25 malicious blocked; 14/24 benign allowed**. All regressions meet expectations; exploration exposes seven missed attacks and ten false positives. See [evaluation commands and baseline](README.md#adversarial-tests-and-detector-evaluation).

These examples are small, curated, and implementation-aware—not an independent benchmark or an estimate of deployment accuracy. Exploratory errors are reported rather than required to disappear for pytest to pass. A detector bypass does not demonstrate model compromise or an ownership bypass.

Automated providers are deterministic fakes: tests incur no provider charges and do not measure live-model attack success, embedding relevance, or semantic grounding. Citation validation proves reference consistency, not support for every generated claim.

## Current Limitations

### Detection and answer quality

- Lexical rules do not understand intent. Negated defenses, educational questions, and quoted attacks can cause false positives; encoded text, misspellings, typoglycemia, homoglyphs, fragmentation, and paraphrases can evade detection.
- Rule weights are not statistically calibrated. HNSW is approximate, and filtering can affect recall; the shared index is not a complete large-scale tenant-isolation strategy.
- No calibrated relevance cutoff exists. Nonempty retrieval may be irrelevant, and the model's sufficiency judgment has not been calibrated by this suite.
- No model-assisted classifier, separate output-policy/DLP screening, quarantine, or human-review workflow is implemented. Grounding instructions and input screening are not guarantees against injection.

### Identity and deployment

- No HTTPS termination, production secret management, MFA, refresh tokens, token revocation lists, email verification, password resets, third-party OAuth/OIDC, login rate limiting, or account lockout.
- Roles are limited to `user` and `admin`, with database-only administrative changes; there is no role-management API, permission hierarchy, document sharing, or group access.

### Data and operations

- No rich-document parsing, malware scanning, application-level document encryption, sensitive-data redaction, or provider-specific retention controls.
- One concrete provider and fixed embedding dimension are supported. Changing embedding models requires regenerating stored vectors.
- SDK timeout/retry settings exist, but there is no additional application-level backoff, circuit breaker, cache, or quota system.
- Answer requests are stateless: no conversation history, tools, streaming, or stored model responses.

### Audit coverage

- Successful authentication, document access, retrieval, and answer generation are not audited.
- No audit retention policy, export, alerts, dashboard, or tamper-evident storage exists. Administrative review is manual, not real-time monitoring.

## Responsible Disclosure

This is a personal portfolio project. Do not upload real secrets, private documents, or production credentials.
