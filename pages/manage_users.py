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


def _render_manage_users_styles():
    font_css_url = (
        "https://fonts.googleapis.com/css2?"
        "family=Manrope:wght@500;700;800&display=swap"
    )
    css = """
        <style>
        @import url('__FONT_URL__');

        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'Manrope', sans-serif;
        }

        .ops-table-toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin: 8px 0 16px 0;
            padding: 14px 16px;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-radius: 12px;
            color: #f8fafc;
        }

        .ops-table-count {
            font-size: 14px;
            opacity: 0.9;
        }

        .ops-table-header {
            margin-top: 10px;
            margin-bottom: 4px;
            font-weight: 800;
            font-size: 12px;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            color: #475569;
        }

        .ops-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 3px 10px;
            font-size: 12px;
            font-weight: 700;
            line-height: 1.4;
            white-space: nowrap;
        }

        .ops-pill--success {
            color: #166534;
            background: #dcfce7;
            border: 1px solid #86efac;
        }

        .ops-pill--muted {
            color: #334155;
            background: #e2e8f0;
            border: 1px solid #cbd5e1;
        }

        .ops-pill--warning {
            color: #92400e;
            background: #fef3c7;
            border: 1px solid #fcd34d;
        }

        .ops-cell-main {
            color: #0f172a;
            font-weight: 700;
            font-size: 14px;
        }

        .ops-cell-sub {
            color: #64748b;
            font-size: 12px;
            margin-top: 2px;
        }

        .ops-divider {
            margin: 6px 0 10px 0;
            border: none;
            border-top: 1px solid #e2e8f0;
        }

        .ops-stat-card {
            padding: 16px;
            border-radius: 14px;
            border: 1px solid #e2e8f0;
            background: #ffffff;
            min-height: 96px;
        }

        .ops-stat-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #64748b;
            font-weight: 800;
            margin-bottom: 6px;
        }

        .ops-stat-value {
            font-size: 30px;
            color: #0f172a;
            font-weight: 800;
            line-height: 1.1;
        }

        .ops-stat-hint {
            margin-top: 4px;
            color: #475569;
            font-size: 12px;
        }

        .ops-section-title {
            margin-top: 14px;
            margin-bottom: 10px;
            font-weight: 800;
            color: #0f172a;
            font-size: 18px;
        }

        .ops-page-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 14px;
            margin: 6px 0 20px 0;
            padding: 16px;
            border: 1px solid #e2e8f0;
            border-radius: 16px;
            background:
                radial-gradient(circle at top right, #e2e8f0 0%, transparent 50%),
                linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        }

        .ops-page-title {
            margin: 0;
            color: #0f172a;
            font-size: 30px;
            font-weight: 800;
            line-height: 1.15;
        }

        .ops-page-subtitle {
            margin-top: 8px;
            color: #475569;
            font-size: 14px;
            max-width: 760px;
        }

        .ops-page-badge {
            background: #0f172a;
            color: #f8fafc;
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            white-space: nowrap;
        }

        @media (max-width: 900px) {
            .ops-page-header {
                flex-direction: column;
                align-items: flex-start;
            }

            .ops-page-title {
                font-size: 25px;
            }
        }
        </style>
        """
    st.markdown(
        css.replace("__FONT_URL__", font_css_url),
        unsafe_allow_html=True,
    )


def _format_datetime(value) -> str:
    if not value:
        return "-"
    return pd.to_datetime(value).strftime("%d/%m/%Y %H:%M")


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

_render_manage_users_styles()
st.markdown(
    """
    <div class="ops-page-header">
        <div>
            <h1 class="ops-page-title">Gestão de Usuários</h1>
            <div class="ops-page-subtitle">
                Gerencie aprovações e permissões de acesso ao Ops Manager
                com rastreabilidade e segurança.
            </div>
        </div>
        <div class="ops-page-badge">Área administrativa</div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
            st.markdown(
                f"""
                <div
                    class="ops-table-toolbar"
                    style="background: linear-gradient(135deg, #7c2d12 0%, #9a3412 100%);"
                >
                    <div>
                        <div style="font-weight:800; font-size:16px;">
                            Solicitações aguardando revisão
                        </div>
                        <div class="ops-table-count">
                            Aprove ou mantenha em análise conforme a necessidade.
                        </div>
                    </div>
                    <div class="ops-pill ops-pill--warning">{len(pending_users)} pendente(s)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            header_cols = st.columns([3.0, 1.8, 1.8, 2.6, 1.5])
            header_cols[0].markdown(
                '<div class="ops-table-header">Email</div>',
                unsafe_allow_html=True,
            )
            header_cols[1].markdown(
                '<div class="ops-table-header">Nome</div>',
                unsafe_allow_html=True,
            )
            header_cols[2].markdown(
                '<div class="ops-table-header">Criado em</div>',
                unsafe_allow_html=True,
            )
            header_cols[3].markdown(
                '<div class="ops-table-header">Notas</div>',
                unsafe_allow_html=True,
            )
            header_cols[4].markdown(
                '<div class="ops-table-header">Ação</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<hr class="ops-divider" />', unsafe_allow_html=True)

            for user in pending_users:
                row_cols = st.columns(
                    [3.0, 1.8, 1.8, 2.6, 1.5],
                    vertical_alignment="center",
                )
                row_cols[0].markdown(
                    f'<div class="ops-cell-main">{user.get("email", "-")}</div>',
                    unsafe_allow_html=True,
                )
                row_cols[1].markdown(
                    f'<div class="ops-cell-main">{user.get("name") or "Sem nome"}</div>',
                    unsafe_allow_html=True,
                )
                row_cols[2].markdown(
                    f'<div class="ops-cell-sub">{_format_datetime(user.get("created_at"))}</div>',
                    unsafe_allow_html=True,
                )
                row_cols[3].markdown(
                    f'<div class="ops-cell-sub">{user.get("notes") or "Sem observações"}</div>',
                    unsafe_allow_html=True,
                )

                if row_cols[4].button(
                    "Aprovar",
                    key=f"approve_{user.get('email')}",
                    type="primary",
                    use_container_width=True,
                ):
                    _approved_ok = False
                    try:
                        _log_page(
                            logging.INFO,
                            "manage_users.user_approve.requested",
                            target_email=_mask_email(user.get("email", "")),
                        )
                        result = client.table("authorized_users").update({
                            "approved": True,
                            "approved_by": current_user.email,
                            "approved_at": datetime.utcnow().isoformat(),
                        }).eq("email", user.get("email")).execute()

                        if not result.data:
                            _log_page(
                                logging.WARNING,
                                "manage_users.user_approve.no_rows_updated",
                                target_email=_mask_email(user.get("email", "")),
                            )
                            st.error(
                                "❌ Nenhuma linha atualizada. Verifique se o seu usuário "
                                "tem permissão de aprovação no banco de dados."
                            )
                        else:
                            _log_page(
                                logging.INFO,
                                "manage_users.user_approve.success",
                                target_email=_mask_email(user.get("email", "")),
                            )
                            st.success(f"✅ Usuário {user.get('email')} aprovado com sucesso!")
                            _approved_ok = True

                    except Exception as e:
                        LOGGER.exception("Erro ao aprovar usuário")
                        _log_page(
                            logging.ERROR,
                            "manage_users.user_approve.error",
                            target_email=_mask_email(user.get("email", "")),
                            error=str(e),
                        )
                        st.error(f"Erro ao aprovar usuário: {str(e)}")

                    if _approved_ok:
                        st.rerun()

                st.markdown('<hr class="ops-divider" />', unsafe_allow_html=True)

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
            st.markdown(
                f"""
                <div class="ops-table-toolbar">
                    <div>
                        <div style="font-weight:800; font-size:16px;">Lista de acessos ativos</div>
                        <div class="ops-table-count">
                            Gerencie permissões de forma rápida e segura.
                        </div>
                    </div>
                    <div class="ops-pill ops-pill--success">{len(approved_users)} aprovado(s)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            header_cols = st.columns([2.8, 1.6, 1.5, 1.5, 2.0, 2.2, 1.5])
            header_cols[0].markdown(
                '<div class="ops-table-header">Email</div>',
                unsafe_allow_html=True,
            )
            header_cols[1].markdown(
                '<div class="ops-table-header">Nome</div>',
                unsafe_allow_html=True,
            )
            header_cols[2].markdown(
                '<div class="ops-table-header">Criado em</div>',
                unsafe_allow_html=True,
            )
            header_cols[3].markdown(
                '<div class="ops-table-header">Último acesso</div>',
                unsafe_allow_html=True,
            )
            header_cols[4].markdown(
                '<div class="ops-table-header">Aprovado por</div>',
                unsafe_allow_html=True,
            )
            header_cols[5].markdown(
                '<div class="ops-table-header">Notas</div>',
                unsafe_allow_html=True,
            )
            header_cols[6].markdown(
                '<div class="ops-table-header">Ação</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<hr class="ops-divider" />', unsafe_allow_html=True)

            for user in approved_users:
                row_cols = st.columns(
                    [2.8, 1.6, 1.5, 1.5, 2.0, 2.2, 1.5],
                    vertical_alignment="center",
                )
                row_cols[0].markdown(
                    f'<div class="ops-cell-main">{user.get("email", "-")}</div>',
                    unsafe_allow_html=True,
                )
                row_cols[1].markdown(
                    f'<div class="ops-cell-main">{user.get("name") or "Sem nome"}</div>',
                    unsafe_allow_html=True,
                )
                row_cols[2].markdown(
                    f'<div class="ops-cell-sub">{_format_datetime(user.get("created_at"))}</div>',
                    unsafe_allow_html=True,
                )
                row_cols[3].markdown(
                    (
                        f"<span class=\"ops-pill ops-pill--success\">"
                        f"{_format_datetime(user.get('last_login'))}</span>"
                        if user.get("last_login")
                        else '<span class="ops-pill ops-pill--muted">Nunca acessou</span>'
                    ),
                    unsafe_allow_html=True,
                )
                row_cols[4].markdown(
                    f'<div class="ops-cell-sub">{user.get("approved_by") or "-"}</div>',
                    unsafe_allow_html=True,
                )
                row_cols[5].markdown(
                    f'<div class="ops-cell-sub">{user.get("notes") or "Sem observações"}</div>',
                    unsafe_allow_html=True,
                )

                if row_cols[6].button(
                    "Revogar",
                    key=f"revoke_{user.get('email')}",
                    use_container_width=True,
                ):
                    _revoked_ok = False
                    try:
                        _log_page(
                            logging.INFO,
                            "manage_users.user_revoke.requested",
                            target_email=_mask_email(user.get("email", "")),
                        )
                        result = client.table("authorized_users").update({
                            "approved": False,
                            "approved_by": None,
                            "approved_at": None,
                        }).eq("email", user.get("email")).execute()

                        if not result.data:
                            _log_page(
                                logging.WARNING,
                                "manage_users.user_revoke.no_rows_updated",
                                target_email=_mask_email(user.get("email", "")),
                            )
                            st.error(
                                "❌ Nenhuma linha atualizada. Verifique se o seu usuário "
                                "tem permissão de revogação no banco de dados."
                            )
                        else:
                            _log_page(
                                logging.INFO,
                                "manage_users.user_revoke.success",
                                target_email=_mask_email(user.get("email", "")),
                            )
                            st.warning(f"🔒 Acesso revogado para {user.get('email')}")
                            _revoked_ok = True

                    except Exception as e:
                        LOGGER.exception("Erro ao revogar usuário")
                        _log_page(
                            logging.ERROR,
                            "manage_users.user_revoke.error",
                            target_email=_mask_email(user.get("email", "")),
                            error=str(e),
                        )
                        st.error(f"Erro ao revogar acesso: {str(e)}")

                    if _revoked_ok:
                        st.rerun()

                st.markdown('<hr class="ops-divider" />', unsafe_allow_html=True)

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
        approved_pct = (approved_count / total_users * 100) if total_users else 0.0
        pending_pct = (pending_count / total_users * 100) if total_users else 0.0

        st.markdown(
            """
            <div
                class="ops-table-toolbar"
                style="background: linear-gradient(135deg, #1d4ed8 0%, #0369a1 100%);"
            >
                <div>
                    <div style="font-weight:800; font-size:16px;">
                        Resumo operacional de usuários
                    </div>
                    <div class="ops-table-count">
                        Acompanhe volume total, aprovações e pendências em tempo real.
                    </div>
                </div>
                <div class="ops-pill ops-pill--muted">Atualizado agora</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Exibir métricas em cards
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                f"""
                <div class="ops-stat-card">
                    <div class="ops-stat-label">Total de usuários</div>
                    <div class="ops-stat-value">{total_users}</div>
                    <div class="ops-stat-hint">Base completa cadastrada</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                f"""
                <div class="ops-stat-card">
                    <div class="ops-stat-label">Aprovados</div>
                    <div class="ops-stat-value">{approved_count}</div>
                    <div class="ops-stat-hint">{approved_pct:.1f}% da base total</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                f"""
                <div class="ops-stat-card">
                    <div class="ops-stat-label">Pendentes</div>
                    <div class="ops-stat-value">{pending_count}</div>
                    <div class="ops-stat-hint">{pending_pct:.1f}% da base total</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # Distribuição de aprovação
        if total_users > 0:
            st.markdown(
                '<div class="ops-section-title">Status de Aprovação</div>',
                unsafe_allow_html=True,
            )

            progress_cols = st.columns(2)
            with progress_cols[0]:
                st.markdown("**Aprovados**")
                st.progress(
                    approved_count / total_users,
                    text=f"{approved_count} usuário(s) • {approved_pct:.1f}%",
                )
            with progress_cols[1]:
                st.markdown("**Pendentes**")
                st.progress(
                    pending_count / total_users,
                    text=f"{pending_count} usuário(s) • {pending_pct:.1f}%",
                )

        st.markdown("---")

        # Usuários mais recentes
        st.markdown(
            '<div class="ops-section-title">Usuários Mais Recentes</div>',
            unsafe_allow_html=True,
        )

        if all_users:
            recent_users = sorted(
                all_users,
                key=lambda x: x["created_at"],
                reverse=True,
            )[:5]

            recent_header = st.columns([3.0, 1.8, 1.6, 1.6])
            recent_header[0].markdown(
                '<div class="ops-table-header">Email</div>',
                unsafe_allow_html=True,
            )
            recent_header[1].markdown(
                '<div class="ops-table-header">Nome</div>',
                unsafe_allow_html=True,
            )
            recent_header[2].markdown(
                '<div class="ops-table-header">Status</div>',
                unsafe_allow_html=True,
            )
            recent_header[3].markdown(
                '<div class="ops-table-header">Criado em</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<hr class="ops-divider" />', unsafe_allow_html=True)

            for user in recent_users:
                recent_cols = st.columns([3.0, 1.8, 1.6, 1.6])
                recent_cols[0].markdown(
                    f'<div class="ops-cell-main">{user.get("email", "-")}</div>',
                    unsafe_allow_html=True,
                )
                recent_cols[1].markdown(
                    f'<div class="ops-cell-main">{user.get("name") or "Sem nome"}</div>',
                    unsafe_allow_html=True,
                )
                recent_cols[2].markdown(
                    (
                        '<span class="ops-pill ops-pill--success">Aprovado</span>'
                        if user.get("approved")
                        else '<span class="ops-pill ops-pill--warning">Pendente</span>'
                    ),
                    unsafe_allow_html=True,
                )
                recent_cols[3].markdown(
                    f'<div class="ops-cell-sub">{_format_datetime(user.get("created_at"))}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown('<hr class="ops-divider" />', unsafe_allow_html=True)
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
