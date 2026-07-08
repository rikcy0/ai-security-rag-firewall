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

## Responsible Disclosure

This is a personal portfolio project. Do not upload real secrets, private documents, or production credentials.