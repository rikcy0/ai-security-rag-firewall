# Security Policy

## Project Security Goals

This project explores application-level defenses for AI and RAG systems.

Primary risks addressed:

- Prompt injection
- Indirect prompt injection
- Unauthorized document access
- Cross-user data leakage
- System prompt leakage
- Unsafe model output
- Missing auditability

## Security Design Principles

- Authorization is enforced in backend application logic.
- The LLM will not be trusted to make access-control decisions.
- Document ownership is enforced before stored content can be accessed.
- Semantic retrieval filters by the authenticated owner inside PostgreSQL before ranking and limiting results.
- Selected security-sensitive failures are recorded as data-minimized PostgreSQL audit events.
- Uploaded document text is screened for prompt-injection signals before chunking and persistence.
- Only accepted document chunks cross the external embedding-provider boundary.
- Embedding-provider responses are treated as untrusted input and validated before persistence.
- Guarded answer generation reuses owner-scoped retrieval before sending minimal context to an external model.
- Sensitive configuration values are stored in environment variables, not source code.

## Implemented Authentication Controls

### Credential handling

- Usernames are stripped, normalized to lowercase, and validated before database access.
- PostgreSQL enforces username uniqueness.
- Plaintext passwords are never stored.
- Passwords are hashed with Argon2id through `pwdlib`.
- Passwords and password hashes are excluded from API responses.

### Login behavior

- Unknown usernames and incorrect passwords return the same public error.
- Unknown usernames perform verification against a dummy Argon2 hash to reduce username-enumeration signals from response timing.
- Inactive users cannot log in.
- Login failures do not reveal whether an account exists or is disabled.

### Access tokens

- Access tokens are signed JWTs with required `sub`, `iat`, and `exp` claims.
- JWT decoding restricts the accepted signing algorithm.
- Token subjects must contain valid user UUIDs.
- Expired, malformed, and incorrectly signed tokens are rejected.
- JWT signing secrets are loaded from environment variables.

### Protected requests

- Bearer tokens identify users by UUID.
- Protected requests retrieve the current user from PostgreSQL.
- Users who have been disabled or deleted are rejected even if they possess an otherwise valid, unexpired token.

## Implemented Authorization Controls

### Role storage

- User roles are stored in PostgreSQL.
- The supported roles are `user` and `admin`.
- Newly registered accounts receive the `user` role by default.
- A database check constraint rejects unsupported role values.
- Registration schemas reject client-supplied role fields, preventing users from assigning themselves administrative access.

### Permission enforcement

- Authentication is completed before role authorization is evaluated.
- Reusable FastAPI dependencies enforce required roles on protected routes.
- The `/admin/users` endpoint requires the `admin` role.
- Authenticated users without the required role receive `403 Forbidden`.
- Missing, malformed, expired, or otherwise invalid authentication receives `401 Unauthorized`.
- JWTs identify users by UUID but do not serve as the authoritative source for roles.
- Protected requests retrieve the current user and role from PostgreSQL.
- Role changes therefore affect subsequent requests even when the user still has an unexpired access token.

### Response safety

- Protected endpoints use explicit response schemas.
- Passwords and password hashes are excluded from user responses.
- The administrative user-list endpoint returns only approved user fields.

## Implemented Document Security Controls

### Upload validation

- Document upload requires a valid authenticated user.
- Upload reads are bounded to the configured maximum size plus one detection byte.
- Upload size is validated again by the document service.
- Only `.txt` and `.md` filenames are accepted.
- Filename path components are removed before persistence.
- Empty filenames, excessively long filenames, and null characters are rejected.
- Document content must contain valid UTF-8 text.
- Empty, whitespace-only, and null-containing document content is rejected.

### Ownership enforcement

- Document ownership is derived from the authenticated database user.
- Clients cannot provide or override a document owner.
- Document listing queries filter by the authenticated user's UUID.
- Individual document queries filter by both document UUID and owner UUID.
- Another user's valid document UUID does not grant access.
- Foreign-owned and nonexistent documents return the same `404 Not Found` response.
- Document responses exclude original content, chunks, and `owner_id`.

### Persistence safeguards

- Documents and chunks are created as one service-owned transaction.
- Database failures roll back the document operation.
- PostgreSQL foreign keys connect documents to users and chunks to documents.
- Cascading deletion prevents orphaned documents and chunks.
- Database constraints reject empty content, invalid chunk indexes, and duplicate chunk positions.
- Every persisted chunk requires a fixed 1,536-dimension embedding.
- Chunk embeddings are generated before the database transaction begins, so embedding failures do not create partial document records.
- PostgreSQL indexes chunk embeddings with HNSW and cosine distance operations.

## Implemented Prompt-Injection Controls

### Detection

- Uploaded document text is analyzed after size, UTF-8, null-character, and readable-content validation.
- Detection occurs before text chunking and before any document or chunk is added to the database session.
- The detector is independent of FastAPI, SQLAlchemy, and external AI providers.
- Detection rules are precompiled and use bounded matching expressions.
- Current categories include instruction override, system-prompt extraction, role manipulation, security bypass, and data exfiltration.
- Each matched category contributes a project-defined severity weight.
- Combined risk scores are capped at `100`.
- Risk scores are deterministic policy values and must not be interpreted as probabilities.
- The blocking threshold is validated between `1` and `100` and defaults to `50`.

### Normalization

- Detection uses Unicode NFKC compatibility normalization.
- Analysis is case-insensitive through Unicode case folding.
- Repeated whitespace, tabs, and line breaks are normalized.
- Invisible Unicode format characters are analyzed using two representations.
- One representation removes format characters to reconstruct split words.
- The other treats format characters as boundaries to avoid joining adjacent words.
- Normalization is applied only to the security-analysis copy; stored document content is not rewritten by the detector.

### Enforcement

- Content meeting the configured threshold is rejected before chunking and persistence.
- Rejected uploads receive `422 Unprocessable Content`.
- Public responses do not reveal scores, categories, reasons, or matching content.
- Blocked document uploads and RAG queries create security events containing only the surface, risk score, and sorted matched categories.
- PostgreSQL integration tests verify that rejected uploads create neither document nor chunk rows.

## Implemented Embedding Security Controls

### Provider boundary

- The OpenAI API key and embedding model are loaded through validated application settings.
- The API key uses Pydantic `SecretStr` and is excluded from normal settings representations.
- The application can start without an embedding API key, but document uploads and semantic searches return `503 Service Unavailable` until a provider is configured.
- Application services depend on an embedding-provider protocol rather than directly constructing an OpenAI client.
- The current OpenAI implementation uses the synchronous client to remain consistent with the synchronous FastAPI and SQLAlchemy architecture.
- Provider clients are closed after the FastAPI dependency finishes handling the request.
- Embedding requests use bounded batches instead of submitting an unlimited number of chunks at once.
- Prompt-injection screening occurs before chunk text is sent to the embedding provider.

### Provider-response validation

- Every input chunk must receive exactly one provider result.
- Provider response indexes are checked and used to restore input order.
- Every vector value must be convertible to a finite floating-point number.
- Every vector must contain exactly 1,536 values.
- All-zero vectors are rejected because they are not useful for cosine similarity.
- Invalid provider responses are translated into an application-specific embedding error.

### Failure containment

- Embeddings are generated before documents or chunks are added to the database session.
- Provider failures and invalid responses therefore create neither document nor chunk rows.
- Public failures use the generic message `Embedding service is unavailable` and do not expose provider details.
- Automated tests use deterministic fake providers and do not send document content or credentials to OpenAI.

### Vector storage

- PostgreSQL requires a non-null `vector(1536)` value for every document chunk.
- The HNSW index uses `vector_cosine_ops` for cosine-similarity retrieval.
- Embeddings remain connected to document ownership through the chunk and document foreign-key relationships.
- The vector index is a performance structure, not an authorization control; retrieval queries separately enforce ownership in SQL.

## Implemented Semantic-Retrieval Controls

### Request validation

- Semantic retrieval requires an authenticated, active database user.
- Queries are stripped and limited to 2,000 characters.
- Whitespace-only queries are rejected.
- `top_k` defaults to `5` and is limited between `1` and `20`.
- Extra request fields are rejected, including client-supplied ownership identifiers.

### Ownership enforcement

- The retrieval owner is always derived from the authenticated user's database UUID.
- Clients cannot select or override the retrieval owner.
- Administrators do not automatically bypass document ownership.
- Document chunks are joined to their parent documents inside the retrieval query.
- The owner condition is applied in SQL before cosine ranking and `LIMIT`.
- Foreign-owned chunks are never returned, even when they are more similar than every owned chunk.

### Vector retrieval

- Search queries are embedded through the same validated provider boundary used during ingestion.
- Chunk results are ordered by cosine distance.
- API responses expose cosine similarity, where larger values represent closer matches.
- HNSW iterative scanning uses transaction-local strict ordering to improve filtered retrieval.
- Retrieval is read-only and does not commit database changes.
- An empty owned corpus returns a successful empty result set.

### Response safety

- Responses contain only chunk UUID, document UUID, filename, chunk position, chunk content, and similarity.
- Responses exclude `owner_id` and embedding vectors.
- Embedding-provider failures return a generic `503 Service Unavailable`.
- Provider-specific error details are not returned to clients.
- Automated tests prove that closer foreign-owned vectors cannot cross the ownership boundary.

## Implemented Guarded RAG Answer Controls

### Query validation and policy enforcement

- `POST /rag/answer` requires an authenticated, active database user.
- The request accepts only a query; extra fields such as `owner_id`, `top_k`, model names, or context limits are rejected.
- Query length is bounded before and after minimal whitespace and line-ending normalization.
- The prompt-injection detector analyzes the query before embedding generation, database retrieval, or answer generation.
- Blocked queries receive a generic `422 Unprocessable Content` response that does not reveal detector scores, categories, or matched text.
- Security-specific normalization remains internal to the detector; the minimally normalized query is used for embedding and generation.

### Context isolation and minimization

- RAG retrieval derives ownership exclusively from the authenticated database user's UUID.
- PostgreSQL applies the owner condition before similarity ranking and limiting.
- Retrieved chunks are materialized as immutable application data before the database read transaction is ended.
- The database transaction is not held open while waiting for the external answer provider.
- Answer-time context has an independent, server-controlled total character budget.
- Context selection preserves whole chunks and skips blank or nonfitting chunks rather than splitting them.
- Source numbers are assigned only after final context selection.
- The answer provider receives only the query, source numbers, and selected chunk text.
- UUIDs, filenames, ownership identifiers, similarity values, and embedding vectors are not sent to the answer model.

### Answer-provider boundary

- Application services depend on an answer-provider protocol rather than directly constructing an OpenAI client.
- The current implementation uses the synchronous Responses API to match the synchronous FastAPI and SQLAlchemy architecture.
- The generation model, output-token limit, provider timeout, and retry count are controlled by validated server settings.
- Responses are requested with structured output, explicit reasoning effort, and `store=False`.
- `store=False` prevents the response from being stored for later API retrieval; it should not be interpreted as a complete data-retention guarantee.
- Grounding instructions require the model to treat both the query and sources as untrusted data, ignore instructions inside sources, and answer only from supplied context.
- Provider clients are created lazily and closed after the request dependency finishes.

### Output and citation validation

- The provider validates completion status, refusals, structured output, answer length, and status-specific response requirements.
- Answered results require at least one declared source citation.
- Inline citation markers must use canonical positive source numbers.
- Inline citations must exactly agree with the provider's declared citation list.
- Every cited source number must exist in the server-supplied context.
- Public source metadata is reconstructed from server-owned retrieval results rather than model-generated identifiers.
- Only cited source metadata is returned to the client; chunk content, `owner_id`, and embeddings are excluded.

### Failure containment and test evidence

- Empty or over-budget retrieval context produces a fixed insufficient-context response without calling the answer provider.
- Model-declared insufficient context produces the same fixed public response with an empty source list.
- Model refusals, embedding failures, and answer-provider failures use generic public error messages.
- Provider exception details, refusal text, request bodies, and raw model responses are not exposed to clients.
- Automated tests use fake providers and therefore do not contact OpenAI or incur API charges.
- PostgreSQL integration tests use a deliberately closer foreign-owned chunk and prove that it never reaches the answer provider.

## Implemented Security-Event Audit Controls

### Recorded events

- Failed login attempts create `login_failed` events.
- Role-check failures create `authorization_denied` events.
- Blocked document uploads and RAG queries create `prompt_injection_blocked` events.
- Event types are restricted by a PostgreSQL check constraint.

### Data minimization

- Failed-login events store the normalized submitted username without claiming that the account exists.
- Authorization-denial events store the actor identity and required and actual roles.
- Prompt-injection events store the protected surface, deterministic risk score, and sorted matched categories.
- Events do not store passwords, password hashes, access tokens, uploaded document content, RAG query text, embeddings, or provider responses.

### Persistence and failure behavior

- Audit events are written using a separate database session and transaction.
- An audit persistence failure cannot reverse or weaken the original authentication, authorization, or prompt-injection decision.
- Audit failures write only the exception type to the application logger.
- Deleting a user sets the event's user UUID to null while preserving the username snapshot and event history.

### Administrative review

- `GET /admin/security-events` requires the current database user to have the `admin` role.
- Results are ordered newest first using creation time and event UUID.
- The result limit defaults to 50 and is bounded between 1 and 100.
- Responses use an explicit schema containing only approved event fields.


## Current Limitations

This is a local portfolio project and not a production identity platform.

The current security implementation does not provide:

- HTTPS termination
- Refresh tokens
- Token revocation lists
- Multi-factor authentication
- Email verification
- Password reset workflows
- Login rate limiting
- Account lockout
- Third-party OAuth or OpenID Connect
- Production secret management

The current authorization model is intentionally limited:

- Only the `user` and `admin` roles are supported.
- Administrative role changes require direct access to the local development database.
- There is no administrative role-management API.
- Granular permissions and role hierarchies are not implemented.

The current document-security implementation is intentionally limited:

- Document access is based only on individual ownership.
- Document sharing, groups, and granular document permissions are not implemented.
- Administrators do not automatically bypass document ownership.
- Uploaded files are limited to UTF-8 `.txt` and `.md` documents.
- Malware scanning and rich-document parsing are not implemented.
- Document-access decisions are not yet recorded in an audit log.
- Stored document content should not be treated as encrypted application data.

The current prompt-injection detector is intentionally limited:

- Detection is based on lexical rules and does not understand semantic intent.
- Negated defensive statements may match the same rules as malicious instructions.
- Quoted attack examples in cybersecurity material may produce false positives.
- The current detector may miss encoded instructions, creative misspellings, typoglycemia, homoglyph substitution, fragmented instructions, and semantic paraphrases.
- Current rule weights have not been statistically calibrated against a large adversarial and benign corpus.
- At the default threshold, every current rule is individually strong enough to block.
- The detector protects document ingestion and guarded RAG queries, but it is not applied to the raw semantic-retrieval endpoint because that endpoint does not invoke an answer model.
- Retrieved chunks are not currently rescanned immediately before answer generation; the system relies on ingestion-time screening, owner-scoped retrieval, minimal context disclosure, and grounding instructions.
- Model-assisted classification, output screening, rate limiting, quarantine workflows, and human review are not implemented.
- Prompt-injection detection is one defense layer and is not a guarantee that all attacks will be identified.

The current embedding implementation is intentionally limited:

- Accepted document chunks are sent to an external embedding provider.
- Data-loss prevention, sensitive-data redaction, and provider-specific retention controls are not implemented.
- Only one concrete provider and one fixed embedding dimension are currently supported.
- Provider timeout and retry counts are configurable, but application-level exponential backoff, circuit breaking, caching, and quota management are not implemented.
- Stored embeddings should be treated as potentially sensitive derived data.
- Query text is sent to the configured external embedding provider.
- Stored vectors and query vectors must use the same embedding model; changing models requires regenerating stored embeddings.
- HNSW is an approximate index, so filtering can affect retrieval recall even though SQL ownership filtering prevents cross-user results.
- The current shared vector index is appropriate for this local portfolio project but is not a complete large-scale tenant-isolation strategy.
- Similarity scores have not been calibrated into a minimum relevance threshold.

The current guarded-answer implementation is intentionally limited:

- There is no calibrated minimum similarity threshold, so nonempty retrieval does not necessarily mean that the chunks are relevant.
- The answer model decides whether nonempty context is sufficient; the adversarial evaluation suite has not yet calibrated this behavior.
- Structured output and citation validation prove that citations reference supplied sources, but do not prove that every generated claim is semantically supported by those sources.
- Model output is not yet scanned by a separate content-policy or data-loss-prevention layer.
- The answer provider receives selected document text through an external API, so sensitive or private documents should not be used.
- `store=False` is a response-state control and is not presented as a general zero-retention guarantee.
- The answer workflow is stateless and does not provide conversation history, streaming, tools, or stored model responses.
- Audit coverage is intentionally limited to selected security failures; per-user quotas, rate limiting, and provider circuit breaking are not implemented.

The current audit implementation is intentionally limited:

- Only failed logins, authorization denials, and blocked prompt-injection attempts are recorded.
- Successful authentication, document access, retrieval, and answer generation are not audited.
- There is no retention policy, export system, alerting pipeline, dashboard, or tamper-evident storage.
- Audit persistence is best-effort so logging failures do not alter the original security decision.
- The administrative endpoint provides manual review rather than real-time monitoring.

Contextual detection, model-assisted security controls, output screening, automated alerting, and the broader adversarial evaluation suite remain under development.

## Responsible Disclosure

This is a personal portfolio project. Do not upload real secrets, private documents, or production credentials.
