---
description: |
  Ops Manager - Streamlit app with Supabase authentication, user management, and operational dashboards.
  Follow these guidelines for development, code generation, and architectural decisions.
applyTo: "frontend/ops-manager" # Apply to all files in this project
---

# Ops Manager - Project Instructions

## 🎯 Project Overview

**Ops Manager** is a Streamlit-based operational dashboard with:
- ✅ Supabase authentication (Google OAuth)
- ✅ User management with manual approval workflow
- ✅ Multi-page architecture (Dashboard + Gestão de Usuários)
- ✅ Row-Level Security (RLS) for database access control
- ✅ Integration with AWS Lambda for environment management

## 🏗️ Architecture Principles

### Frontend (Streamlit)
- **Multi-page structure**: Main app in `app.py`, pages in `pages/` directory
- **Authentication on entry**: `display_auth_ui()` called at the start of `app.py`
- **Session management**: Use `st.session_state` for user data and authentication
- **Access control**: Check `approved` status before rendering sensitive pages
- **UI patterns**: Use `.success()`, `.error()`, `.warning()` for user feedback

### Backend (Supabase)
- **Authentication**: Google OAuth via Supabase Auth (not managed locally)
- **Database**: PostgreSQL with RLS policies for row-level security
- **Tables**: `authorized_users` is the main user management table
- **Default state**: New users are created with `approved=false` (must be manually approved)
- **Automation**: Use MCP Supabase tools whenever possible for schema changes

### Security Model
1. **OAuth 2.0**: Authentication via Google Cloud Console
2. **RLS Policies**: Database enforces access control
3. **Approval Workflow**: Admin must approve users in `Gestão de Usuários` page
4. **Session Validation**: Check `approved` status on each page load
5. **Never in RLS**: Do NOT use `user_metadata` for authorization (use `app_metadata`)

## 📋 Development Guidelines

### When Adding Features

#### Database Changes
- ✅ **Prefer**: Use `mcp_supabase_opsm_execute_sql` for schema changes
- ✅ **Then**: Use `mcp_supabase_opsm_apply_migration` if making permanent changes
- ❌ **Avoid**: Direct SQL files without version control in migrations

#### Authentication Changes
- If modifying `auth.py`: Always check that new logic works with `display_auth_ui()`
- If adding new pages: Always call `display_auth_ui()` at the top
- If restricting access: Use `st.stop()` to block unauthorized access
- RLS policies must exist for all `authorized_users` queries

#### New Pages
- Create in `pages/` directory with consistent naming
- Start with `display_auth_ui()` for authentication
- Check user `approved` status before rendering content
- Add to documentation (IMPLEMENTACAO.md or similar)

### Code Style

#### Python/Streamlit
```python
# Good: Check auth at top
from auth import display_auth_ui
display_auth_ui()  # Must be first

# Good: Use st.session_state for session data
user = st.session_state.user
user_id = st.session_state.user_id

# Good: Explicit error handling
try:
    response = client.table("authorized_users").select("*").execute()
except Exception as e:
    st.error(f"Database error: {str(e)}")

# Bad: Hardcoded credentials
SUPABASE_KEY = "secret_key"  # ❌ Use .env instead

# Bad: Unsafe authorization
if user.metadata.get("admin"):  # ❌ Use approved flag + RLS
```

#### SQL/Migrations
```sql
-- Good: RLS enabled by default
ALTER TABLE new_table ENABLE ROW LEVEL SECURITY;

-- Good: Clear policy names
CREATE POLICY "Enable read for authenticated users"
ON new_table FOR SELECT
USING (auth.role() = 'authenticated');

-- Bad: Disabling RLS
ALTER TABLE sensitive_table DISABLE ROW LEVEL SECURITY;  -- ❌

-- Bad: Authorization in app instead of database
-- Put this in RLS policies instead
```

### Documentation Requirements

#### When you create/modify features:
1. **Code comments**: Inline comments for complex logic (Python)
2. **README sections**: Update relevant .md files if behavior changes
3. **User-facing**: Add to SETUP_AUTENTICACAO.md if affects setup
4. **FAQ updates**: Add Q&A if it's something users might ask
5. **Checklists**: Update CHECKLIST.md if new manual steps needed

#### Existing documentation files (maintain):
- `IMPLEMENTACAO.md` - Main implementation guide
- `SETUP_AUTENTICACAO.md` - Quick start guide
- `FAQ.md` - Q&A and troubleshooting
- `CHECKLIST.md` - Step-by-step checklist
- `ARQUITETURA.md` - Architecture diagrams

### Using MCP Supabase Tools

#### Priority Order (what to try first):
1. **`mcp_supabase_opsm_execute_sql`** - For one-off SQL queries and schema changes
2. **`mcp_supabase_opsm_apply_migration`** - For permanent migrations to track history
3. **`mcp_supabase_opsm_list_tables`** - Verify table structure
4. **`mcp_supabase_opsm_get_advisors`** - Check for security/performance issues
5. **`mcp_supabase_opsm_list_extensions`** - Check available extensions

#### What you CANNOT do via MCP (manual steps):
- Configure Google OAuth (Google Cloud Console)
- Enable Google Provider (Supabase Dashboard UI)
- Create .env files locally
- Deploy to Streamlit Cloud

### Git Workflow

- Work on feature branches: `git flow feature start feature-name`
- Commit message format: `feat: description` or `fix: description`
- Never commit `.env` files (use .gitignore)
- Update documentation before merging
- Squash commits before merging to main

## 🔐 Security Checklist

Before deploying ANY change, verify:

- [ ] No credentials in code (use .env)
- [ ] RLS enabled on all new tables
- [ ] RLS policies configured correctly
- [ ] No `user_metadata` in authorization logic
- [ ] `approved=false` is the default for new users
- [ ] `st.stop()` blocks unauthorized access
- [ ] Secrets are in Streamlit Cloud (not .env in production)
- [ ] Database advisors run with no security issues

## 📦 Dependencies

### Core
- `streamlit>=1.45.1` - UI framework
- `supabase>=2.4.1` - Backend client
- `python-dotenv>=1.1.0` - Environment variables

### Optional (existing)
- `boto3` - AWS Lambda integration
- `requests` - HTTP calls
- `pandas` - Data manipulation

Always test locally before updating requirements.txt

## 🚀 Common Tasks

### Add a new user management feature
1. Plan in a new branch: `git flow feature start manage-users-X`
2. Update `pages/manage_users.py` with new UI
3. Add SQL/RLS changes via MCP if needed
4. Update documentation
5. Test locally
6. Commit and push

### Fix an authentication issue
1. Check `auth.py` - is `display_auth_ui()` working?
2. Check `authorized_users` table - is user `approved=true`?
3. Check RLS policies - do they allow the action?
4. Use `mcp_supabase_opsm_get_advisors` to check for security issues

### Deploy a change
1. Test locally: `streamlit run app.py`
2. Git push to feature branch
3. Update IMPLEMENTACAO.md if behavior changed
4. Create PR (or merge if solo)
5. Deploy: Push to main → Streamlit Cloud auto-deploys
6. Test in production

## ⚠️ Common Mistakes (Don't Do These!)

- ❌ Use `user_metadata` for authorization (use `app_metadata` + RLS)
- ❌ Disable RLS on sensitive tables
- ❌ Commit `.env` files
- ❌ Hardcode credentials in code
- ❌ Add pages without calling `display_auth_ui()`
- ❌ Use `st.stop()` without clear error message
- ❌ Create migrations manually (use `mcp_supabase_opsm_apply_migration`)
- ❌ Forget to update documentation

## 📞 References

- [Supabase Auth Docs](https://supabase.com/docs/guides/auth)
- [Streamlit Multi-page Apps](https://docs.streamlit.io/library/get-started/multipage-apps)
- [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [OAuth 2.0 Flow](https://developers.google.com/identity/protocols/oauth2)

---

**Last Updated**: April 22, 2026  
**Version**: 1.0.0