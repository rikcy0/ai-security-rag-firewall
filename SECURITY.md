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
- The planned retrieval pipeline will apply user authorization before content is sent to an LLM.
- Planned security-event logging will support monitoring and auditing.
- Uploaded document text is screened for prompt-injection signals before chunking and persistence.
- Future query and retrieval paths will apply the same security boundary before invoking AI providers.
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
- Internal detector results remain available for future security-event logging.
- PostgreSQL integration tests verify that rejected uploads create neither document nor chunk rows.

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
- Authorization decisions are not yet recorded in an audit log.

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
- The detector currently protects document ingestion but is not yet connected to a user-query or retrieval pipeline.
- Model-assisted classification, output screening, rate limiting, quarantine workflows, and human review are not implemented.
- Prompt-injection detection is one defense layer and is not a guarantee that all attacks will be identified.

Audit logging, vector retrieval controls, query-time enforcement, contextual detection, and model-assisted security controls remain under development.

## Responsible Disclosure

This is a personal portfolio project. Do not upload real secrets, private documents, or production credentials.
