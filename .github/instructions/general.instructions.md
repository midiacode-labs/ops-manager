---
description: |
  Ops Manager - general application instructions.
  Use this file for baseline architecture, coding patterns, and development workflow.
applyTo: "frontend/ops-manager" # Apply to all files in this project
---

# Ops Manager - General Instructions

## Objective

This file defines only the basic application structure, organization patterns, and development workflow.

Authentication details are defined in a separate file:
- `.github/instructions/auth.instructions.md`

## Base Application Structure

- Main entry point: `app.py`
- Core modules: `auth.py`, `slack_notifications.py`
- Multipage screens: `pages/` directory
- Utility scripts: files in the root folder (for example: environment control)
- Documentation: `README.md` and files in `docs/`

## Architecture Principles

### Frontend (Streamlit)
- Use a multipage architecture with `app.py` as the main dashboard.
- Prioritize explicit user feedback with `st.success`, `st.warning`, and `st.error`.
- Use `st.session_state` for UI state and temporary data.
- Handle external integration failures with clear messages and safe recovery.

### Integrations
- Supabase for application data and operational user control.
- AWS Lambda for start/stop environment actions.
- Slack for notifications of sensitive actions.

## Product Language Policy

All project screens and user-facing messages must be written in Portuguese.

Mandatory requirements:
- Always use correct Portuguese spelling and grammar.
- Always include proper accents and special characters (for example: "autenticação", "aprovação", "usuário", "configuração").
- Do not replace accented Portuguese words with ASCII-only variants in the UI.
- Keep this rule across Streamlit pages, alerts, buttons, labels, helper text, and error/success/warning messages.

## Coding Conventions

### Python
- Prefer small functions with a single responsibility.
- Wrap external calls in `try/except` with user-friendly messages.
- Do not hardcode credentials, keys, tokens, or sensitive URLs.
- Keep names descriptive and consistent with the operational domain.

### Streamlit
- Avoid extensive business logic inside rendering blocks.
- Centralize repeated actions in helper functions.
- Always use session state to persist information between reruns.

## Database and Migrations

- For SQL iteration, prefer `mcp_supabase_opsm_execute_sql`.
- For permanent, traceable changes, use `mcp_supabase_opsm_apply_migration`.
- Always validate impact after structural changes (security and performance).

## Development Workflow

1. Create a feature branch for relevant changes.
2. Implement with small, incremental scope.
3. Test locally with `streamlit run app.py`.
4. Update affected documentation when behavior changes.
5. Commit with clear messages (`feat: ...`, `fix: ...`, `chore: ...`).

## Quick Checklist

- [ ] No secrets in code
- [ ] Error handling for external integrations
- [ ] Consistent session state
- [ ] Validated database changes
- [ ] Documentation updated when needed

## References

- Streamlit Multi-page Apps: https://docs.streamlit.io/library/get-started/multipage-apps
- Supabase Docs: https://supabase.com/docs

---

Last Updated: April 22, 2026  
Version: 1.1.0