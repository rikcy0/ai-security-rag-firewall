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
- The LLM is not trusted to make access-control decisions.
- Retrieved documents are filtered by user permissions before being sent to the model.
- Security events are logged for monitoring and auditing.
- Suspicious inputs are scored and may be blocked before retrieval.
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
- Document ownership and document-level permissions are not implemented.
- Authorization decisions are not yet recorded in an audit log.

Document-level access controls, audit logging, and AI-specific security controls remain under development.

## Responsible Disclosure

This is a personal portfolio project. Do not upload real secrets, private documents, or production credentials.
