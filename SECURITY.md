# Security Policy

## Reporting a Vulnerability

Please report security issues privately rather than opening a public issue:

- **Email**: `brahmasmi22@gmail.com` (subject: `[MediBot Security]`)
- **Project**: [MediBot Repository](https://github.com/AnshumanPanda1/bytexl-panda-)

Please include a description, affected endpoint or component, and steps to reproduce.

## Security Practices

MediBot implements the following key security safeguards:
- **Server-Side API Keys**: Provider keys (Groq, OpenAI, Google) are strictly server-side and never exposed to the frontend or git.
- **Multi-Tenant Isolation**: Row-level tenant partitioning and scoped session JWT validation.
- **Synthetic Data Standard**: All demo records and imported test cases are synthetic/de-identified.
- **FHIR R4 Access Control**: Standard OAuth2 token validation for interoperability surfaces.
