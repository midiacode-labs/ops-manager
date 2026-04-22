"""
Página de Gestão de Usuários
Apenas usuários aprovados podem acessar esta página
"""

import streamlit as st
import pandas as pd
import logging
import os
from datetime import datetime
from uuid import uuid4
from auth import get_supabase_client, display_auth_ui, get_current_user


LOGGER = logging.getLogger("ops_manager.manage_users")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    LOGGER.addHandler(_handler)
LOGGER.setLevel(os.getenv("APP_LOG_LEVEL", os.getenv("AUTH_LOG_LEVEL", "INFO")).upper())
LOGGER.propagate = False


def _get_trace_id() -> str:
    if "auth_trace_id" not in st.session_state:
        st.session_state.auth_trace_id = uuid4().hex[:12]
    return st.session_state.auth_trace_id


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        local_masked = "*" * len(local)
    else:
        local_masked = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{local_masked}@{domain}"


def _log_page(level: int, event: str, **fields):
    payload = {
        "event": event,
        "trace_id": _get_trace_id(),
    }
    payload.update(fields)
    LOGGER.log(level, " ".join(f"{k}={v}" for k, v in payload.items()))


# Configurar página
st.set_page_config(
    page_title="Gestão de Usuários",
    page_icon="👥",
    layout="wide",
)
_log_page(logging.INFO, "manage_users.page_configured")

# Verificar autenticação
display_auth_ui()
_log_page(logging.INFO, "manage_users.auth_ok")

st.title("👥 Gestão de Usuários")

# ============================================================================
# Verificar se o usuário atual está aprovado (admin implícito)
# ============================================================================

current_user = get_current_user()
if not current_user:
    _log_page(logging.ERROR, "manage_users.user_missing")
    st.error("Usuário não autenticado")
    st.stop()

_log_page(logging.INFO, "manage_users.user_loaded", user_email=_mask_email(current_user.email))

try:
    client = get_supabase_client()
    _log_page(logging.DEBUG, "manage_users.client_ready")

    # Verificar se usuário atual está aprovado
    current_user_record = client.table("authorized_users").select("approved").eq(
        "email", current_user.email
    ).execute()
    _log_page(
        logging.INFO,
        "manage_users.permission_checked",
        found=bool(current_user_record.data),
        approved=bool(
            current_user_record.data
            and current_user_record.data[0].get("approved")
        ),
    )

    if not current_user_record.data or not current_user_record.data[0].get("approved"):
        _log_page(logging.WARNING, "manage_users.permission_denied")
        st.error("❌ Você não tem permissão para acessar esta página")
        st.stop()

except Exception as e:
    LOGGER.exception("Erro ao verificar permissões da página")
    _log_page(logging.ERROR, "manage_users.permission_error", error=str(e))
    st.error(f"Erro ao verificar permissões: {str(e)}")
    st.stop()

# ============================================================================
# Interface de Gestão
# ============================================================================

tab1, tab2, tab3 = st.tabs(["⏳ Pendentes de Aprovação", "✅ Usuários Aprovados", "📊 Estatísticas"])

# ============================================================================
# TAB 1: Usuários Pendentes
# ============================================================================

with tab1:
    st.subheader("Usuários Aguardando Aprovação")
    _log_page(logging.DEBUG, "manage_users.tab_pending.opened")

    try:
        # Buscar usuários não aprovados
        response = (
            client.table("authorized_users")
            .select("*")
            .eq("approved", False)
            .order("created_at", desc=False)
            .execute()
        )

        pending_users = response.data if response.data else []
        _log_page(logging.INFO, "manage_users.tab_pending.loaded", count=len(pending_users))

        if not pending_users:
            st.info("✅ Nenhum usuário aguardando aprovação")
        else:
            st.write(f"**{len(pending_users)} usuário(s) aguardando aprovação**")

            header_cols = st.columns([3, 2, 2, 3, 2])
            header_cols[0].markdown("**Email**")
            header_cols[1].markdown("**Nome**")
            header_cols[2].markdown("**Criado em**")
            header_cols[3].markdown("**Notas**")
            header_cols[4].markdown("**Ação**")

            for user in pending_users:
                row_cols = st.columns([3, 2, 2, 3, 2])
                row_cols[0].write(user.get("email", "-"))
                row_cols[1].write(user.get("name") or "Sem nome")
                row_cols[2].write(pd.to_datetime(user.get("created_at")).strftime("%d/%m/%Y %H:%M"))
                row_cols[3].write(user.get("notes") or "-")

                if row_cols[4].button(
                    "✅ Aprovar",
                    key=f"approve_{user.get('email')}",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        _log_page(
                            logging.INFO,
                            "manage_users.user_approve.requested",
                            target_email=_mask_email(user.get("email", "")),
                        )
                        client.table("authorized_users").update({
                            "approved": True,
                            "approved_by": current_user.email,
                            "approved_at": datetime.utcnow().isoformat(),
                        }).eq("email", user.get("email")).execute()

                        _log_page(
                            logging.INFO,
                            "manage_users.user_approve.success",
                            target_email=_mask_email(user.get("email", "")),
                        )

                        st.success(f"✅ Usuário {user.get('email')} aprovado com sucesso!")
                        st.rerun()

                    except Exception as e:
                        LOGGER.exception("Erro ao aprovar usuário")
                        _log_page(
                            logging.ERROR,
                            "manage_users.user_approve.error",
                            target_email=_mask_email(user.get("email", "")),
                            error=str(e),
                        )
                        st.error(f"Erro ao aprovar usuário: {str(e)}")

    except Exception as e:
        LOGGER.exception("Erro ao carregar pendentes")
        _log_page(logging.ERROR, "manage_users.tab_pending.error", error=str(e))
        st.error(f"Erro ao carregar usuários pendentes: {str(e)}")

# ============================================================================
# TAB 2: Usuários Aprovados
# ============================================================================

with tab2:
    st.subheader("Usuários Aprovados")
    _log_page(logging.DEBUG, "manage_users.tab_approved.opened")

    try:
        # Buscar usuários aprovados
        response = (
            client.table("authorized_users")
            .select("*")
            .eq("approved", True)
            .order("created_at", desc=False)
            .execute()
        )

        approved_users = response.data if response.data else []
        _log_page(logging.INFO, "manage_users.tab_approved.loaded", count=len(approved_users))

        if not approved_users:
            st.info("Nenhum usuário aprovado ainda")
        else:
            st.write(f"**{len(approved_users)} usuário(s) aprovado(s)**")

            header_cols = st.columns([3, 2, 2, 2, 2, 3, 2])
            header_cols[0].markdown("**Email**")
            header_cols[1].markdown("**Nome**")
            header_cols[2].markdown("**Criado em**")
            header_cols[3].markdown("**Último Acesso**")
            header_cols[4].markdown("**Aprovado por**")
            header_cols[5].markdown("**Notas**")
            header_cols[6].markdown("**Ação**")

            for user in approved_users:
                row_cols = st.columns([3, 2, 2, 2, 2, 3, 2])
                row_cols[0].write(user.get("email", "-"))
                row_cols[1].write(user.get("name") or "Sem nome")
                row_cols[2].write(pd.to_datetime(user.get("created_at")).strftime("%d/%m/%Y %H:%M"))
                row_cols[3].write(
                    pd.to_datetime(user.get("last_login")).strftime("%d/%m/%Y %H:%M")
                    if user.get("last_login")
                    else "Nunca"
                )
                row_cols[4].write(user.get("approved_by") or "-")
                row_cols[5].write(user.get("notes") or "-")

                if row_cols[6].button(
                    "🔒 Revogar",
                    key=f"revoke_{user.get('email')}",
                    use_container_width=True,
                ):
                    try:
                        _log_page(
                            logging.INFO,
                            "manage_users.user_revoke.requested",
                            target_email=_mask_email(user.get("email", "")),
                        )
                        client.table("authorized_users").update({
                            "approved": False,
                            "approved_by": None,
                            "approved_at": None,
                        }).eq("email", user.get("email")).execute()

                        _log_page(
                            logging.INFO,
                            "manage_users.user_revoke.success",
                            target_email=_mask_email(user.get("email", "")),
                        )

                        st.warning(f"🔒 Acesso revogado para {user.get('email')}")
                        st.rerun()

                    except Exception as e:
                        LOGGER.exception("Erro ao revogar usuário")
                        _log_page(
                            logging.ERROR,
                            "manage_users.user_revoke.error",
                            target_email=_mask_email(user.get("email", "")),
                            error=str(e),
                        )
                        st.error(f"Erro ao revogar acesso: {str(e)}")

    except Exception as e:
        LOGGER.exception("Erro ao carregar aprovados")
        _log_page(logging.ERROR, "manage_users.tab_approved.error", error=str(e))
        st.error(f"Erro ao carregar usuários aprovados: {str(e)}")

# ============================================================================
# TAB 3: Estatísticas
# ============================================================================

with tab3:
    st.subheader("📊 Estatísticas de Usuários")
    _log_page(logging.DEBUG, "manage_users.tab_stats.opened")

    try:
        # Buscar todos os usuários
        response = client.table("authorized_users").select("*").execute()
        all_users = response.data if response.data else []

        # Calcular estatísticas
        total_users = len(all_users)
        approved_count = sum(1 for u in all_users if u["approved"])
        pending_count = total_users - approved_count
        _log_page(
            logging.INFO,
            "manage_users.tab_stats.computed",
            total=total_users,
            approved=approved_count,
            pending=pending_count,
        )

        # Exibir métricas
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total de Usuários", total_users)

        with col2:
            st.metric("✅ Aprovados", approved_count)

        with col3:
            st.metric("⏳ Pendentes", pending_count)

        st.markdown("---")

        # Gráfico de aprovação
        if total_users > 0:
            st.subheader("Status de Aprovação")

            approval_data = pd.DataFrame({
                "Status": ["Aprovados", "Pendentes"],
                "Quantidade": [approved_count, pending_count]
            })

            st.bar_chart(approval_data.set_index("Status"))

        st.markdown("---")

        # Usuários mais recentes
        st.subheader("📝 Usuários Mais Recentes")

        if all_users:
            recent_users = sorted(all_users, key=lambda x: x["created_at"], reverse=True)[:5]

            df_recent = pd.DataFrame(recent_users)
            df_recent = df_recent[["email", "name", "approved", "created_at"]]
            df_recent.columns = ["Email", "Nome", "Aprovado", "Data"]
            df_recent["Aprovado"] = df_recent["Aprovado"].apply(lambda x: "✅ Sim" if x else "⏳ Não")
            df_recent["Data"] = pd.to_datetime(df_recent["Data"]).dt.strftime("%d/%m/%Y %H:%M")

            st.dataframe(df_recent, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum usuário registrado ainda")

    except Exception as e:
        LOGGER.exception("Erro ao carregar estatísticas")
        _log_page(logging.ERROR, "manage_users.tab_stats.error", error=str(e))
        st.error(f"Erro ao carregar estatísticas: {str(e)}")

# ============================================================================
# Rodapé
# ============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #888; font-size: 12px;'>
    <p>Você está autenticado como <strong>{email}</strong></p>
    <p>Apenas usuários aprovados podem acessar esta página.</p>
</div>
""".format(email=current_user.email), unsafe_allow_html=True)
