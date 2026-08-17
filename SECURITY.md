# Security Policy

This document explains how to report vulnerabilities, how the project treats secrets and destructive commands, and recommended best practices for safely operating this repository and its produced artifacts.

Supported versions
- The project supports Python 3.9 and later. Security fixes are backported only to actively maintained release series documented in the CHANGELOG and release notes.

Reporting security issues
- Use GitHub's private security advisories for confidential reports: https://docs.github.com/en/code-security/security-advisories/about-security-advisories
- If you cannot use GitHub advisories, open a private issue addressed to the maintainers or email the listed project contact in the repo metadata (do not include exploited secrets in public channels).
- Do NOT open public issues for unverified or sensitive vulnerability reports.

Private vulnerability disclosure process
- Maintain the confidentiality of reports until a fix and coordinated disclosure are prepared.
- The repository owner should enable the GitHub security advisory feature and can add a CODEOWNER or security contact in the repository settings.

Secrets and token handling
- Never commit bot tokens, webhooks, .env files, or other credentials. Add them to GitHub Secrets or use a secrets manager.
- Treat Discord bot tokens as highly privileged: revoke rotated tokens immediately from the Discord Developer Portal if exposed.
- Use least-privilege OAuth scopes / bot intents. Grant only permissions necessary for the task (e.g., read-only where possible).
- In CI, use the repository Secrets store (Settings → Secrets) or GitHub Environments for runtime secrets. Do not hardcode secrets in workflows.

Destructive operations and dry-run modes
- Commands that delete, ban, prune, or otherwise mutate server state must offer a dry-run or `--yes` confirmation flag.
- Tests and automation should default to non-destructive behavior and require explicit flags to execute destructive actions.
- Document any destructive commands in the CLI docs and recipes with examples using dry-run first.

Secret rotation and incident response
- Rotate a compromised token immediately in the Discord Developer Portal and revoke any OAuth grants.
- After rotation, update any deployed secrets in GitHub Actions or platform-specific secret stores.

Scope limitations and safe use
- This project is a CLI automation tool that performs actions on behalf of a bot account; it does not claim to provide server-level backup guarantees.
- Operators should verify permissions before running bulk operations and test changes in a non-production environment first.

Maintainer responsibilities
- Keep dependencies up-to-date and monitor Dependabot/GitHub security alerts.
- Respond to security advisories in a timely manner and coordinate patch releases.

Contact
- Report private vulnerabilities via GitHub Security Advisories for this repository. The repository owner may be contacted via the email address in the project metadata if the advisories are not available.

Notes for repository owners (administrator actions)
- To receive private security reports via GitHub, enable the repository's security advisory feature in Settings → Code security and analysis.
- Consider adding a maintainer contact or security@ email address to the project metadata for alternate private reporting.
