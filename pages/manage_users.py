"""
Página de Gestão de Usuários
Apenas usuários aprovados podem acessar esta página
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from auth import get_supabase_client, display_auth_ui, get_current_user

# Configurar página
st.set_page_config(
    page_title="Gestão de Usuários",
    page_icon="👥",
    layout="wide",
)

# Verificar autenticação
display_auth_ui()

st.title("👥 Gestão de Usuários")

# ============================================================================
# Verificar se o usuário atual está aprovado (admin implícito)
# ============================================================================

current_user = get_current_user()
if not current_user:
    st.error("Usuário não autenticado")
    st.stop()

try:
    client = get_supabase_client()

    # Verificar se usuário atual está aprovado
    current_user_record = client.table("authorized_users").select("approved").eq(
        "email", current_user.email
    ).execute()

    if not current_user_record.data or not current_user_record.data[0].get("approved"):
        st.error("❌ Você não tem permissão para acessar esta página")
        st.stop()

except Exception as e:
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
                        client.table("authorized_users").update({
                            "approved": True,
                            "approved_by": current_user.email,
                            "approved_at": datetime.utcnow().isoformat(),
                        }).eq("email", user.get("email")).execute()

                        st.success(f"✅ Usuário {user.get('email')} aprovado com sucesso!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro ao aprovar usuário: {str(e)}")

    except Exception as e:
        st.error(f"Erro ao carregar usuários pendentes: {str(e)}")

# ============================================================================
# TAB 2: Usuários Aprovados
# ============================================================================

with tab2:
    st.subheader("Usuários Aprovados")

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
                        client.table("authorized_users").update({
                            "approved": False,
                            "approved_by": None,
                            "approved_at": None,
                        }).eq("email", user.get("email")).execute()

                        st.warning(f"🔒 Acesso revogado para {user.get('email')}")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro ao revogar acesso: {str(e)}")

    except Exception as e:
        st.error(f"Erro ao carregar usuários aprovados: {str(e)}")

# ============================================================================
# TAB 3: Estatísticas
# ============================================================================

with tab3:
    st.subheader("📊 Estatísticas de Usuários")

    try:
        # Buscar todos os usuários
        response = client.table("authorized_users").select("*").execute()
        all_users = response.data if response.data else []

        # Calcular estatísticas
        total_users = len(all_users)
        approved_count = sum(1 for u in all_users if u["approved"])
        pending_count = total_users - approved_count

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
