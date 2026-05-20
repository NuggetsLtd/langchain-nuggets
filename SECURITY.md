# Security Policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in `langchain-nuggets` or any package shipped from this repository, please report it privately.

**Email:** security@nuggets.life

Please include:

- A description of the issue and its impact
- Steps to reproduce, ideally with a minimal proof of concept
- The package(s) and version(s) affected
- Any suggested mitigation

Do not open public GitHub issues for security reports.

## What to expect

- We will acknowledge your report within 3 business days.
- We will keep you informed of progress while we investigate.
- Once a fix is available, we will coordinate disclosure timing with you.

## Scope

In scope:

- All packages published from this repository (`langchain-nuggets`, `@nuggetslife/langchain`, `@nuggetslife/mcp-server`).
- The Authority Middleware's interaction with the Nuggets backend.

Out of scope:

- Vulnerabilities in third-party dependencies — please report those upstream. We will track the advisory and update on release.
- Issues that require physical access to a developer's machine.
- Self-XSS, missing security headers on docs, or other non-exploitable findings.

## Supported versions

We support the most recent minor release on the current major. Older versions receive security fixes at our discretion.
