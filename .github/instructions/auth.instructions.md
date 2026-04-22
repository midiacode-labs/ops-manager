---
description: |
  Ops Manager - authentication and authorization specific instructions.
  Reflects the current flow implemented in auth.py and used by Streamlit pages.
applyTo: "frontend/ops-manager" # Auth-specialized file for this project
---

# Ops Manager - Authentication Instructions

## Scope

This file covers only authentication and authorization.
For general architecture and development workflow, use:
- `.github/instructions/general.instructions.md`

## Current Implemented State

The current authentication uses Supabase Auth with Google OAuth (PKCE) and access control through the `authorized_users` table.

## Relevant Files

- `auth.py`: main login, callback, session, authorization, and logout flow
- `app.py`: calls `display_auth_ui()` before any sensitive content
- `pages/manage_users.py`: calls `display_auth_ui()` and revalidates permission locally

## Product Language Policy

All project screens and user-facing messages must remain in Portuguese.

Mandatory requirements:
- Use correct Portuguese spelling and grammar in all UI text.
- Always keep accents and special characters (for example: "autenticação", "aprovação", "usuário", "não", "permissão").
- Never convert Portuguese UI text to ASCII-only variants.
- Apply this rule to login screens, authentication errors, pending/review notices, buttons, labels, and helper text.

## Mandatory Rules

1. Every protected page must call `display_auth_ui()` at the start.
2. On denied, pending, or permission error states, show a clear message and use `st.stop()`.
3. Do not use `user_metadata` for authorization decisions (only for display, such as name/photo).
4. Access decisions must depend on database data + RLS.
5. Never expose `SUPABASE_KEY` or other secrets in code.

## Authentication Flow (auth.py)

1. `initialize_auth_session()` creates the minimum `st.session_state` keys:
   - `session`
   - `user`
   - `authenticated`
   - `_supabase_auth_storage`
2. `handle_auth_callback()` processes the `code` query param and exchanges it for a session with `exchange_code_for_session`.
3. `check_session()` validates the current in-memory session.
4. If not authenticated:
   - renders the custom login screen
   - generates the OAuth URL via `get_google_oauth_url()`
   - stops execution with `st.stop()`
5. If authenticated:
   - looks up the user by email in `authorized_users`
   - if not found: pending status + optional logout + `st.stop()`
   - if `approved=false`: review status + optional logout + `st.stop()`
   - if approved:
     - stores `st.session_state.user_id` with the table `id`
     - updates `last_login`
     - shows welcome banner + logout button

## OAuth and Callback

- `get_google_oauth_url()` uses `sign_in_with_oauth` with:
  - provider: `google`
  - scopes: `profile email`
  - redirect: `STREAMLIT_REDIRECT_URL` (localhost fallback)
- The current flow uses PKCE and includes `pkce_code_verifier` in the redirect.
- `handle_auth_callback()` reads `code` and `pkce_code_verifier` from `st.query_params`.

## Environment Variables

Required:
- `SUPABASE_URL`
- `SUPABASE_KEY`

Optional:
- `STREAMLIT_REDIRECT_URL` (default: `http://localhost:8501`)

## Authorization Table

Main table: `authorized_users`

Fields used in current code:
- `id`
- `email`
- `approved`
- `last_login`
- (management) `approved_by`, `approved_at`, `notes`, `created_at`, `name`

Expected behavior:
- new users start with `approved=false`
- approval and revocation are managed in the user management page

## Usage in New Pages

When creating a new protected page:
1. Call `display_auth_ui()` at the top.
2. Use `get_current_user()` for user data in the UI.
3. If the page is administrative, revalidate `approved` in `authorized_users`.
4. For access blocking, show the reason and end with `st.stop()`.

## Security

- Do not base authorization on user-editable claims.
- Keep RLS enabled on exposed tables.
- Ensure policies required for auth read/update operations are in place.
- Remember that updates under RLS usually require a select policy.

## Auth Checklist

- [ ] `display_auth_ui()` at the start of protected pages
- [ ] OAuth callback flow working
- [ ] Unregistered user handled as pending
- [ ] User with `approved=false` blocked
- [ ] `last_login` updated for approved users
- [ ] Logout clears session and auth storage
- [ ] No hardcoded secrets

## References

- Supabase Auth: https://supabase.com/docs/guides/auth
- Streamlit Session State: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- OAuth 2.0: https://developers.google.com/identity/protocols/oauth2

---

Last Updated: April 22, 2026
Version: 1.0.0
