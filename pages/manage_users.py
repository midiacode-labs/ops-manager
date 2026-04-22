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
        response = client.table("authorized_users").select("*").eq("approved", False).order("created_at", desc=False).execute()
        
        pending_users = response.data if response.data else []
        
        if not pending_users:
            st.info("✅ Nenhum usuário aguardando aprovação")
        else:
            st.write(f"**{len(pending_users)} usuário(s) aguardando aprovação**")
            
            # Criar DataFrame para melhor visualização
            df_pending = pd.DataFrame(pending_users)
            df_pending = df_pending[["email", "name", "created_at", "notes"]]
            df_pending.columns = ["Email", "Nome", "Criado em", "Notas"]
            df_pending["Criado em"] = pd.to_datetime(df_pending["Criado em"]).dt.strftime("%d/%m/%Y %H:%M")
            
            st.dataframe(df_pending, use_container_width=True, hide_index=True)
            
            # Seção de ações
            st.markdown("---")
            st.subheader("Ações")
            
            selected_email = st.selectbox(
                "Selecione um usuário para aprovação",
                options=[u["email"] for u in pending_users],
                format_func=lambda x: f"{x} ({next(((u['name'] or 'Sem nome') for u in pending_users if u['email'] == x), 'N/A')})",
                key="pending_select"
            )
            
            if selected_email:
                col1, col2 = st.columns(2)
                
                with col1:
                    notes_input = st.text_area(
                        "Adicionar notas sobre este usuário",
                        value="",
                        height=100,
                        key=f"notes_{selected_email}"
                    )
                
                with col2:
                    st.markdown("**Ações Disponíveis**")
                    
                    if st.button("✅ Aprovar Usuário", key=f"approve_{selected_email}", type="primary", use_container_width=True):
                        try:
                            # Atualizar usuário para aprovado
                            update_data = {
                                "approved": True,
                                "approved_by": current_user.email,
                                "approved_at": datetime.utcnow().isoformat(),
                            }
                            
                            if notes_input:
                                update_data["notes"] = notes_input
                            
                            client.table("authorized_users").update(update_data).eq(
                                "email", selected_email
                            ).execute()
                            
                            st.success(f"✅ Usuário {selected_email} aprovado com sucesso!")
                            st.balloons()
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Erro ao aprovar usuário: {str(e)}")
                    
                    if st.button("❌ Rejeitar Usuário", key=f"reject_{selected_email}", use_container_width=True):
                        try:
                            # Deletar o usuário
                            client.table("authorized_users").delete().eq(
                                "email", selected_email
                            ).execute()
                            
                            st.warning(f"❌ Usuário {selected_email} rejeitado e removido da lista")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Erro ao rejeitar usuário: {str(e)}")
    
    except Exception as e:
        st.error(f"Erro ao carregar usuários pendentes: {str(e)}")

# ============================================================================
# TAB 2: Usuários Aprovados
# ============================================================================

with tab2:
    st.subheader("Usuários Aprovados")
    
    try:
        # Buscar usuários aprovados
        response = client.table("authorized_users").select("*").eq("approved", True).order("created_at", desc=False).execute()
        
        approved_users = response.data if response.data else []
        
        if not approved_users:
            st.info("Nenhum usuário aprovado ainda")
        else:
            st.write(f"**{len(approved_users)} usuário(s) aprovado(s)**")
            
            # Criar DataFrame
            df_approved = pd.DataFrame(approved_users)
            df_approved = df_approved[["email", "name", "created_at", "last_login", "approved_by", "notes"]]
            df_approved.columns = ["Email", "Nome", "Criado em", "Último Acesso", "Aprovado por", "Notas"]
            df_approved["Criado em"] = pd.to_datetime(df_approved["Criado em"]).dt.strftime("%d/%m/%Y %H:%M")
            df_approved["Último Acesso"] = df_approved["Último Acesso"].apply(
                lambda x: pd.to_datetime(x).strftime("%d/%m/%Y %H:%M") if x else "Nunca"
            )
            
            st.dataframe(df_approved, use_container_width=True, hide_index=True)
            
            # Seção de ações
            st.markdown("---")
            st.subheader("Ações")
            
            selected_approved_email = st.selectbox(
                "Selecione um usuário aprovado",
                options=[u["email"] for u in approved_users],
                format_func=lambda x: f"{x} ({next(((u['name'] or 'Sem nome') for u in approved_users if u['email'] == x), 'N/A')})",
                key="approved_select"
            )
            
            if selected_approved_email:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.info("👤 Detalhes do usuário")
                    user_detail = next((u for u in approved_users if u["email"] == selected_approved_email), None)
                    if user_detail:
                        st.write(f"**Email:** {user_detail['email']}")
                        st.write(f"**Nome:** {user_detail['name'] or 'Não informado'}")
                        st.write(f"**Criado em:** {pd.to_datetime(user_detail['created_at']).strftime('%d/%m/%Y %H:%M')}")
                        st.write(f"**Aprovado por:** {user_detail['approved_by']}")
                        st.write(f"**Notas:** {user_detail['notes'] or 'Nenhuma'}")
                
                with col2:
                    st.markdown("**Ações Disponíveis**")
                    
                    if st.button("🔒 Revogar Acesso", key=f"revoke_{selected_approved_email}", type="secondary", use_container_width=True):
                        try:
                            # Desaprovar usuário
                            client.table("authorized_users").update({
                                "approved": False,
                                "approved_by": None,
                                "approved_at": None,
                            }).eq("email", selected_approved_email).execute()
                            
                            st.warning(f"🔒 Acesso revogado para {selected_approved_email}")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Erro ao revogar acesso: {str(e)}")
                    
                    if st.button("🗑️ Deletar Usuário", key=f"delete_{selected_approved_email}", type="secondary", use_container_width=True):
                        try:
                            # Confirmar antes de deletar
                            if st.checkbox(f"Confirmar exclusão de {selected_approved_email}", key=f"confirm_delete_{selected_approved_email}"):
                                client.table("authorized_users").delete().eq(
                                    "email", selected_approved_email
                                ).execute()
                                
                                st.error(f"🗑️ Usuário {selected_approved_email} foi deletado")
                                st.rerun()
                        
                        except Exception as e:
                            st.error(f"Erro ao deletar usuário: {str(e)}")
    
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

